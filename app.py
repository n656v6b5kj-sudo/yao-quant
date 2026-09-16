import os
from datetime import datetime
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# === 延迟导入：缓存（缺失也不崩）===
try:
    from flask_caching import Cache
    cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 30})
    def do_cache(key):
        def deco(fn): return fn
        return deco
except Exception:
    def do_cache(key):
        def deco(fn): return fn
        return deco

# === 延迟导入：akshare（用到时才导入，缺失也不崩）===
_ak = None
def get_ak():
    global _ak
    if _ak is None:
        try:
            import akshare as aks
            _ak = aks
        except Exception:
            _ak = False
    return _ak


def get_market_phase():
    now = datetime.now()
    if now.weekday() >= 5:
        return "closed"
    h, m = now.hour, now.minute
    t = h * 100 + m
    if 915 <= t < 920: return "auction_fake"
    if 920 <= t < 925: return "auction_real"
    if 925 <= t < 930: return "auction_final"
    if 930 <= t < 1500: return "continuous"
    return "closed"


def calc_level(pct, amount_wan):
    if pct >= 5 and amount_wan >= 2000: return "S"
    if pct >= 3 and amount_wan >= 1000: return "A"
    if pct >= 2: return "B"
    return "C"


def get_val(row, keys, default=0):
    for k in keys:
        if k in row:
            try: return float(row[k])
            except: pass
    return default


def get_str(row, keys, default=""):
    for k in keys:
        if k in row: return str(row[k])
    return default


@do_cache("jingjia_data")
def fetch_data():
    phase = get_market_phase()
    results = []
    aks = get_ak()

    if not aks:
        return [{"code": "INFO", "name": "akshare 未就绪（依赖安装中或接口不可用）",
                 "price": "-", "pct": "-", "vol": "-", "amount": "-",
                 "level": "C", "score": 0}]

    try:
        if phase == "auction_final":
            df = aks.stock_zh_a_spot_em()
            for _, r in df.head(80).iterrows():
                pct = float(r.get("涨跌幅", 0))
                open_price = float(r.get("今开", 0))
                pre_close = float(r.get("昨收", 1))
                amount = float(r.get("成交额", 0))
                amount_wan = amount / 10000
                if pre_close > 0 and open_price > 0:
                    auction_pct = (open_price - pre_close) / pre_close * 100
                else:
                    auction_pct = pct
                if auction_pct < 2 or amount_wan < 500:
                    continue
                score = auction_pct * 3 + amount_wan / 100
                results.append({
                    "code": str(r.get("代码", "")), "name": str(r.get("名称", "")),
                    "price": f"{open_price:.2f}", "pct": f"{auction_pct:.2f}",
                    "vol": f"{float(r.get('成交量',0))/10000:.1f}万",
                    "amount": f"{amount_wan:.0f}万",
                    "level": calc_level(auction_pct, amount_wan), "score": round(score, 1)
                })
        else:
            df = None
            for func in ("stock_auction_sse", "stock_auction_szse"):
                try:
                    df = getattr(aks, func)()
                    if df is not None and len(df) > 0: break
                except: pass
            if df is not None:
                for r in df.to_dict("records"):
                    price = get_val(r, ["竞价价格", "价格", "最新价"])
                    pct = get_val(r, ["竞价涨幅", "涨幅", "涨跌幅"])
                    amount = get_val(r, ["成交额", "竞价成交额"])
                    amount_wan = amount / 10000
                    if pct < 2 or amount_wan < 500: continue
                    results.append({
                        "code": get_str(r, ["代码", "股票代码"]),
                        "name": get_str(r, ["名称", "股票名称"]),
                        "price": f"{price:.2f}", "pct": f"{pct:.2f}",
                        "vol": f"{get_val(r, ['成交量','竞价成交量'])/10000:.1f}万",
                        "amount": f"{amount_wan:.0f}万",
                        "level": calc_level(pct, amount_wan),
                        "score": round(pct * 3 + amount_wan / 100, 1)
                    })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:25]
    except Exception as e:
        return [{"code": "ERR", "name": str(e)[:40], "price": "-", "pct": "-",
                 "vol": "-", "amount": "-", "level": "C", "score": 0}]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    data = fetch_data()
    phase = get_market_phase()
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
        "count": len([d for d in data if d["code"] not in ("ERR", "INFO")]),
        "time": datetime.now().strftime("%H:%M:%S")
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
