import os
import time
import pandas as pd
import akshare as ak
from flask import Flask, jsonify, render_template

app = Flask(__name__)

CACHE = {"ts": 0, "data": []}
CACHE_SECONDS = 300  # 5分钟缓存，防被封+防Railway超时

def yao_score(row):
    try:
        pct = float(row.get("涨跌幅", 0))
    except:
        pct = 0
    lianban = int(row.get("连板数", 0)) if "连板数" in row else 0
    try:
        amount = float(row.get("成交额", 0))
    except:
        amount = 0

    score = 0
    score += min(pct, 11) * 4          # 涨幅权重
    score += lianban * 8               # 连板权重
    if amount >= 300000000:
        score += 15
    if amount >= 1000000000:
        score += 10

    if pct >= 9.5 and lianban >= 3:
        grade = "S"
    elif pct >= 7 and lianban >= 2:
        grade = "A"
    elif pct >= 5:
        grade = "B"
    else:
        grade = "C"
    return round(score, 1), grade

def get_yao_list():
    now = time.time()
    if now - CACHE["ts"] < CACHE_SECONDS and CACHE["data"]:
        return CACHE["data"]

    try:
        # 涨停池：含连板数/封板资金/炸板次数
        df = ak.stock_zt_pool_em(date=time.strftime("%Y%m%d"))
        df["成交额"] = df.get("封板资金", 0)
        rows = []
        for _, r in df.head(30).iterrows():
            sc, gr = yao_score(r)
            rows.append({
                "code": str(r.get("代码", "")),
                "name": str(r.get("名称", "")),
                "pct": float(r.get("涨跌幅", 0)),
                "lianban": int(r.get("连板数", 0)),
                "seal_money": int(r.get("封板资金", 0)),
                "grade": gr,
                "score": sc,
                "reason": str(r.get("所属行业", ""))
            })
        rows.sort(key=lambda x: x["score"], reverse=True)
        CACHE["ts"] = now
        CACHE["data"] = rows
        return rows
    except Exception as e:
        # 数据源挂了：降级返回缓存/空
        if CACHE["data"]:
            return CACHE["data"]
        return [{"name": "数据源暂不可用", "pct": 0, "lianban": 0,
                 "seal_money": 0, "grade": "C", "score": 0, "reason": str(e)}]

@app.route("/")
def index():
    return render_template("index.html", stocks=get_yao_list())

@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(get_yao_list())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
