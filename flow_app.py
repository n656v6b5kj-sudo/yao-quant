"""
主力资金跟踪模块（独立，不影响原有竞价选股）
用法：在 app.py 里 from flow_app import flow_bp; app.register_blueprint(flow_bp)
数据说明：免费接口无逐笔大单，主力净额 = 成交额 × 涨跌幅系数 估算，趋势参考
"""
from flask import Blueprint, render_template, jsonify
from datetime import datetime
from zoneinfo import ZoneInfo

flow_bp = Blueprint("flow", __name__, url_prefix="/flow")
CST = ZoneInfo("Asia/Shanghai")


def get_ak():
    try:
        import akshare as ak
        return ak
    except Exception:
        return None


def now_cst():
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def estimate_main_net(amount, pct):
    if amount <= 0:
        return 0
    sign = 1 if pct >= 0 else -1
    return sign * amount * min(abs(pct), 10) / 100 * 0.15


@flow_bp.route("/")
def flow_page():
    return render_template("flow.html")


@flow_bp.route("/api/flow_data")
def api_flow_data():
    ak = get_ak()
    if not ak:
        return jsonify({
            "time": now_cst(),
            "sectors": [], "stocks": [],
            "msg": "akshare 未就绪（依赖安装中或接口不可用），网页正常"
        })

    # 1. 板块主力净流入
    sectors = []
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日")
        for _, r in df.iterrows():
            name = str(r.get("名称", ""))
            net = float(r.get("今日主力净流入-净额", r.get("主力净流入", 0)))
            ratio = float(r.get("今日主力净流入-净占比", r.get("净占比", 0)))
            sectors.append({"name": name, "net": round(net / 1e8, 2), "ratio": round(ratio, 2)})
        sectors.sort(key=lambda x: x["net"], reverse=True)
    except Exception:
        sectors = []

    # 2. 个股主力净流入（全A快照，按净额降序）
    stocks = []
    try:
        df = ak.stock_zh_a_spot_em()
        for _, r in df.iterrows():
            amount = float(r.get("成交额", 0))
            pct = float(r.get("涨跌幅", 0))
            net = estimate_main_net(amount, pct)
            stocks.append({
                "code": str(r.get("代码", "")), "name": str(r.get("名称", "")),
                "pct": round(pct, 2), "amount": round(amount / 1e4, 0),
                "net": round(net / 1e4, 0),
            })
        stocks.sort(key=lambda x: x["net"], reverse=True)
        for s in stocks[:30]:
            s["hot"] = s["pct"] >= 5 or s["net"] >= 10000
    except Exception:
        stocks = []

    return jsonify({
        "time": now_cst(), "sectors": sectors[:15],
        "stocks": stocks, "msg": "ok"
    })
