import os
import time
import datetime
import akshare as ak
from flask import Flask, jsonify, render_template
from flask_caching import Cache

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 60})


def is_jingjia_time():
    now = datetime.datetime.now().time()
    return datetime.time(9, 15) <= now <= datetime.time(9, 26)


def get_preclose(symbol):
    try:
        prefix = "sz" if symbol.startswith("0") else "sh"
        df = ak.stock_zh_a_daily(symbol=prefix + symbol, adjust="qfq")
        if df is not None and len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass
    return None


def get_call_auction_price(symbol):
    try:
        df = ak.stock_zh_a_hist_min_em(symbol=symbol, period="1", adjust="")
        if df is not None and len(df) > 0:
            row = df[df["时间"].astype(str).str.contains("09:25")]
            if len(row) > 0:
                return float(row.iloc[-1]["收盘"])
            return float(df.iloc[0]["收盘"])
    except Exception:
        pass
    return None


def jingjia_score(info):
    pct = info.get("pct", 0)
    amount = info.get("amount", 0)
    liangbi = info.get("liangbi", 0)
    buy_unmatched = info.get("buy_unmatched", 0)

    score = 0
    score += max(pct, 0) * 6
    if amount >= 20000000:
        score += 20
    if amount >= 50000000:
        score += 15
    score += min(liangbi, 10) * 3
    if buy_unmatched > 10000:
        score += 10

    if pct >= 5 and liangbi >= 2:
        grade = "S"
    elif pct >= 3:
        grade = "A"
    elif pct >= 1:
        grade = "B"
    else:
        grade = "C"
    return round(score, 1), grade


@cache.cached(key_prefix='jingjia_list')
def get_jingjia():
    try:
        df = ak.stock_zh_a_spot_em()
        df = df[(df["涨跌幅"].notna())].sort_values("成交额", ascending=False)
        rows = []
        for _, r in df.head(60).iterrows():
            code = str(r.get("代码", ""))
            name = str(r.get("名称", ""))
            pct = round(float(r.get("涨跌幅", 0)), 2)
            amount = float(r.get("成交额", 0))
            volume = float(r.get("成交量", 0))
            preclose = get_preclose(code)

            call_price = None
            if is_jingjia_time():
                call_price = get_call_auction_price(code)
            if call_price is None:
                call_price = float(r.get("今开", 0))

            liangbi = round(volume / max(preclose or 1, 1), 2) if volume > 0 else 0
            buy_unmatched = int(amount / 100)

            sc, grade = jingjia_score({
                "pct": pct, "amount": amount,
                "liangbi": liangbi, "buy_unmatched": buy_unmatched
            })
            rows.append({
                "code": code, "name": name, "pct": pct,
                "call_price": call_price,
                "amount_wan": round(amount / 10000, 0),
                "liangbi": liangbi,
                "buy_unmatched_wan": round(buy_unmatched / 10000, 1),
                "grade": grade, "score": sc,
                "time": time.strftime("%H:%M"),
            })
        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows[:25]
    except Exception as e:
        return [{"code": "ERR", "name": str(e)[:40], "pct": 0,
                 "call_price": 0, "amount_wan": 0, "liangbi": 0,
                 "buy_unmatched_wan": 0, "grade": "C", "score": 0, "time": ""}]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api():
    return jsonify({
        "jingjia": is_jingjia_time(),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": get_jingjia(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
