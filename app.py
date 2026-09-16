from flask import Flask, render_template, jsonify
import akshare as ak
import time
from datetime import datetime

app = Flask(__name__)

# 竞价时段判断
def is_auction_time():
    now = datetime.now()
    h, m = now.hour, now.minute
    # 9:15 - 9:25 为真实竞价
    return (h == 9 and 15 <= m <= 25) or (h == 9 and m > 25 and m < 30)

# 字段别名兼容（防止 akshare 版本差异）
def get_val(row, keys, default=0):
    for k in keys:
        if k in row:
            try:
                return float(row[k])
            except:
                return default
    return default

def get_str(row, keys, default=""):
    for k in keys:
        if k in row:
            return str(row[k])
    return default

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    active = is_auction_time()
    try:
        # 获取竞价数据（不同版本 akshare 返回字段可能不同）
        df = ak.stock_auction_sse()
        if df is None or df.empty:
            # 兜底：尝试深市或全市场接口
            try:
                df = ak.stock_auction_szse()
            except:
                pass
        
        if df is None or df.empty:
            return jsonify({"active": active, "data": [], "msg": "接口暂无数据"})

        rows = df.to_dict("records")
        res = []
        for r in rows:
            price = get_val(r, ["竞价价格", "价格", "最新价"])
            pct = get_val(r, ["竞价涨幅", "涨幅", "涨跌幅"])
            vol = get_val(r, ["成交量", "竞价成交量"])
            amount = get_val(r, ["成交额", "竞价成交额"])
            code = get_str(r, ["代码", "股票代码"])
            name = get_str(r, ["名称", "股票名称"])

            # 硬过滤
            if pct < 2: continue
            if amount < 500: continue  # 500万

            # 评分 & 评级
            score = pct * 3 + amount / 100
            level = "C"
            if pct >= 5 and amount >= 2000: level = "S"
            elif pct >= 3 and amount >= 1000: level = "A"
            elif pct >= 2: level = "B"

            res.append({
                "code": code, "name": name,
                "price": f"{price:.2f}", "pct": f"{pct:.2f}",
                "vol": f"{vol/10000:.1f}万", "amount": f"{amount/10000:.1f}万",
                "level": level, "score": score
            })
        res.sort(key=lambda x: x["score"], reverse=True)
        return jsonify({
            "active": active,
            "data": res[:25],
            "count": len(res),
            "time": datetime.now().strftime("%H:%M:%S")
        })
    except Exception as e:
        return jsonify({"active": active, "data": [], "msg": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
