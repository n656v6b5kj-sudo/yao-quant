import os, json
from flask import Flask, jsonify, render_template

app = Flask(__name__)
DATA = [
    {"name":"测试妖股A","pct":9.8,"lianban":3,"main_in":5200,"grade":"S"},
    {"name":"测试妖股B","pct":7.2,"lianban":2,"main_in":3100,"grade":"A"},
]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard")
def dash():
    return jsonify(DATA)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
