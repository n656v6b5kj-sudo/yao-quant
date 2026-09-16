import os
import time
from flask import Flask, render_template, jsonify
from flask_caching import Cache
import akshare as ak

app = Flask(__name__)
# 缓存配置（减轻数据源压力）
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 300
cache = Cache(app)

# 竞价时段判断
def is_auction_time():
    tm = time.localtime()
    h, m = tm.tm_hour, tm.tm_min
    # 9:15 - 9:25 为有效竞价时段
    return (h == 9 and 15 <= m <= 25) or (h == 9 and m >= 15)

# 获取竞价数据（带缓存）
@cache.cached(timeout=60, key_prefix='auction_data')
def get_auction_data():
    try:
        # 获取当日早盘竞价数据（akshare接口）
        df = ak.stock_auction_trade_em()
        if df.empty:
            return []
        
        # 简化处理逻辑，提取核心字段
        res = []
        for _, row in df.iterrows():
            res.append({
                "code": row.get("代码", ""),
                "name": row.get("名称", ""),
                "price": row.get("竞价价格", 0),
                "pct": row.get("竞价涨幅", 0),
                "vol": row.get("竞价成交量", 0),
                "amount": row.get("竞价成交额", 0)
            })
        return res
    except Exception as e:
        print("数据获取异常:", e)
        return []

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    data = get_auction_data()
    return jsonify({
        "active": is_auction_time(),
        "data": data
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
