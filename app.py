import os
import time
from datetime import datetime
from flask import Flask, render_template, jsonify
from flask_caching import Cache
import akshare as ak

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 30})


def get_market_phase():
    """返回当前时段标识"""
    now = datetime.now()
    if now.weekday() >= 5:
        return "closed"
    h, m = now.hour, now.minute
    t = h * 100 + m
    if 915 <= t < 920:
        return "auction_fake"
    elif 920 <= t < 925:
        return "auction_real"
    elif 925 <= t < 930:
        return "auction_final"
    elif 930 <= t < 1500:
        return "continuous"
    else:
        return "closed"


def calc_level(pct, amount_wan):
    """评级：涨幅 + 成交额(万)"""
    if pct >= 5 and amount_wan >= 2000:
        return "S"
    elif pct >= 3 and amount_wan >= 1000:
        return "A"
    elif pct >= 2:
        return "B"
    else:
        return "C"


def get_val(row, keys, default=0):
    for k in keys:
        if k in row:
            try:
                return float(row[k])
            except:
                pass
    return default


def get_str(row, keys, default=""):
    for k in keys:
        if k in row:
            return str(row[k])
    return default


@cache.cached(key_prefix='jingjia_data')
def fetch_data():
    """9:25-9:30 优先用实时快照的「今开」字段（最稳定）"""
    phase = get_market_phase()
    results = []

    try:
        if phase == "auction_final":
            # 9:25-9:30：用 stock_zh_a_spot_em 的「今开」字段
            df = ak.stock_zh_a_spot_em()
            for _, r in df.head(80).iterrows():
                code = str(r.get("代码", ""))
                name = str(r.get("名称", ""))
                pct = float(r.get("涨跌幅", 0))
                open_price = float(r.get("今开", 0))
                pre_close = float(r.get("昨收", 1))
                amount = float(r.get("成交额", 0))
                amount_wan = amount / 10000

                # 今开相对昨收的涨幅（竞价真实涨幅）
                if pre_close > 0 and open_price > 0:
                    auction_pct = (open_price - pre_close) / pre_close * 100
                else:
                    auction_pct = pct

                # 硬过滤
                if auction_pct < 2:
                    continue
                if amount_wan < 500:
                    continue

                score = auction_pct * 3 + amount_wan / 100
                level = calc_level(auction_pct, amount_wan)

                results.append({
                    "code": code,
                    "name": name,
                    "price": f"{open_price:.2f}",
                    "pct": f"{auction_pct:.2f}",
                    "vol": f"{float(r.get('成交量',0))/10000:.1f}万",
                    "amount": f"{amount_wan:.0f}万",
                    "level": level,
                    "score": round(score, 1)
                })
        else:
            # 其他时段：用竞价专用接口
            try:
                df = ak.stock_auction_sse()
            except:
                try:
                    df = ak.stock_auction_szse()
                except:
                    df = None

            if df is not None and len(df) > 0:
                rows = df.to_dict("records")
                for r in rows:
                    price = get_val(r, ["竞价价格", "价格", "最新价"])
                    pct = get_val(r, ["竞价涨幅", "涨幅", "涨跌幅"])
                    vol = get_val(r, ["成交量", "竞价成交量"])
                    amount = get_val(r, ["成交额", "竞价成交额"])
                    code = get_str(r, ["代码", "股票代码"])
                    name = get_str(r, ["名称", "股票名称"])
                    amount_wan = amount / 10000

                    if pct < 2 or amount_wan < 500:
                        continue

                    score = pct * 3 + amount_wan / 100
                    level = calc_level(pct, amount_wan)

                    results.append({
                        "code": code,
                        "name": name,
                        "price": f"{price:.2f}",
                        "pct": f"{pct:.2f}",
                        "vol": f"{vol/10000:.1f}万",
                        "amount": f"{amount_wan:.0f}万",
                        "level": level,
                        "score": round(score, 1)
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:25]

    except Exception as e:
        return [{"code": "ERR", "name": str(e)[:30], "price": "0", "pct": "0",
                 "vol": "0", "amount": "0", "level": "C", "score": 0}]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    phase = get_market_phase()
    data = fetch_data()
    phase_text = {
        "auction_fake": "🟡 9:15-9:20 可撤单（含虚假单）",
        "auction_real": "🟡 9:20-9:25 不可撤单博弈中",
        "auction_final": "🟢 9:25-9:30 竞价定盘·真实数据",
        "continuous": "🔵 9:30后 连续竞价中",
        "closed": "⚪ 非交易时段"
    }
    return jsonify({
        "phase": phase,
        "phase_text": phase_text.get(phase, "未知"),
        "data": data,
        "count": len([d for d in data if d["code"] != "ERR"]),
        "time": datetime.now().strftime("%H:%M:%S")
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
