# -*- coding: utf-8 -*-
import os
import time
import re
import csv
import io
from flask import Flask, jsonify, request, render_template, Response
import cloudpss

app = Flask(__name__)

# ---------- 工具函数：表结构转行 ----------
def table_to_rows(table_obj):
    columns = table_obj["data"]["columns"]
    headers = [c["name"] for c in columns]
    n = len(columns[0]["data"]) if columns else 0
    rows = []
    for i in range(n):
        row = {}
        for h, c in zip(headers, columns):
            vals = c.get("data", [])
            row[h] = vals[i] if i < len(vals) else None
        rows.append(row)
    return headers, rows

# HTML 标签清洗（列名里常见 <i>V</i><sub>m</sub>/pu 这类）
_tag_re = re.compile(r"<[^>]+>")
def clean_label(label: str) -> str:
    if not isinstance(label, str):
        return label
    return _tag_re.sub("", label).replace("_", "")

# 列名别名（更友好显示）
ALIASES = {
    "<i>V</i><sub>m</sub> / pu": "Vm(pu)",
    "<i>V</i><sub>a</sub> / deg": "Va(deg)",
    "<i>P</i><sub>gen</sub> / MW": "Pgen(MW)",
    "<i>Q</i><sub>gen</sub> / MVar": "Qgen(MVar)",
    "<i>P</i><sub>load</sub> / MW": "Pload(MW)",
    "<i>Q</i><sub>load</sub> / MVar": "Qload(MVar)",
    "<i>P</i><sub>shunt</sub> / MW": "Pshunt(MW)",
    "<i>Q</i><sub>shunt</sub> / MVar": "Qshunt(MVar)",
    "<i>P</i><sub>res</sub> / MW": "Pres(MW)",
    "<i>Q</i><sub>res</sub> / MVar": "Qres(MVar)",
    "<i>P</i><sub>ij</sub> / MW": "Pij(MW)",
    "<i>Q</i><sub>ij</sub> / MVar": "Qij(MVar)",
    "<i>P</i><sub>ji</sub> / MW": "Pji(MW)",
    "<i>Q</i><sub>ji</sub> / MVar": "Qji(MVar)",
    "<i>P</i><sub>loss</sub> / MW": "Ploss(MW)",
    "<i>Q</i><sub>loss</sub> / MVar": "Qloss(MVar)",
}

def convert_and_alias(table_list):
    if not table_list:
        return {"headers": [], "rows": []}
    headers, rows = table_to_rows(table_list[0])
    alias_headers = [ALIASES.get(h, clean_label(h)) for h in headers]
    aliased_rows = []
    for r in rows:
        new_r = {}
        for h, ah in zip(headers, alias_headers):
            new_r[ah] = r.get(h, "")
        aliased_rows.append(new_r)
    return {"headers": alias_headers, "rows": aliased_rows}

def run_pf_and_get_tables(rid: str):
    # 1) 鉴权 + 平台地址
    api_token = os.getenv("CLOUDPSS_TOKEN")
    if not api_token:
        raise RuntimeError("CLOUDPSS_TOKEN 未设置")
    cloudpss.setToken(api_token)
    api_url = os.getenv("CLOUDPSS_API_URL", "https://cloudpss.net/")
    os.environ["CLOUDPSS_API_URL"] = api_url

    # 2) 获取模型
    model = cloudpss.Model.fetch(rid)

    # 3) 运行潮流
    config = model.configs[0]
    job = model.jobs[0]
    runner = model.run(job, config)

    logs = []
    while not runner.status():
        for log in runner.result.getLogs():
            d = log.get("data", {})
            logs.append({"level": d.get("level", "info"), "content": d.get("content", "")})
        time.sleep(0.3)

    # 4) 结果
    buses_raw = runner.result.getBuses()
    branches_raw = runner.result.getBranches()
    buses = convert_and_alias(buses_raw)
    branches = convert_and_alias(branches_raw)
    return logs, buses, branches

@app.route("/")
def index():
    rid = request.args.get("rid", "model/CloudPSS/IEEE3")
    return render_template("index.html", rid=rid)

@app.route("/api/powerflow")
def api_powerflow():
    rid = request.args.get("rid", "model/CloudPSS/IEEE3")
    try:
        logs, buses, branches = run_pf_and_get_tables(rid)
        return jsonify({"rid": rid, "logs": logs, "buses": buses, "branches": branches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/csv")
def export_csv():
    """
    下载 CSV：/api/export/csv?rid=...&table=buses|branches
    每次下载会按指定 rid 重新计算一次（简单、无状态；如需避免重复计算，可做缓存）。
    """
    rid = request.args.get("rid", "model/CloudPSS/IEEE3")
    table = request.args.get("table", "buses").lower()
    if table not in ("buses", "branches"):
        return jsonify({"error": "table 参数必须是 buses 或 branches"}), 400

    try:
        _, buses, branches = run_pf_and_get_tables(rid)
        result = buses if table == "buses" else branches

        # 写入 CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=result["headers"])
        writer.writeheader()
        for r in result["rows"]:
            writer.writerow({h: r.get(h, "") for h in result["headers"]})

        csv_bytes = output.getvalue().encode("utf-8-sig")  # 带 BOM 便于 Excel 识别 UTF-8
        filename = f"{rid.split('/')[-1]}_{table}.csv"
        return Response(
            csv_bytes,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # 打开 http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)
