# -*- coding: utf-8 -*-
import os
import time
import re
from flask import Flask, jsonify, request, render_template_string
import cloudpss

# ---------------- 工具函数：表结构转行 ----------------
def table_to_rows(table_obj):
    """
    CloudPSS 的表是按列存储：table_obj["data"]["columns"] = [{name,type,data}, ...]
    这里把它转成：rows = [{col_name: cell_value, ...}, ...]
    """
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

# 列名别名（更友好显示用；匹配原始列名，显示用别名）
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

# ---------------- Flask ----------------
app = Flask(__name__)

# 简单首页模板（直接内嵌，下面有完整 HTML）
INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>CloudPSS 潮流计算可视化</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css" />
<style>
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
  table thead th { white-space: nowrap; }
  .scroll-x { overflow-x: auto; }
</style>
</head>
<body class="container">
  <h2>CloudPSS 潮流计算可视化</h2>
  <form id="pfForm">
    <label>模型 RID
      <input name="rid" type="text" value="{{ rid }}" placeholder="model/CloudPSS/IEEE3" />
    </label>
    <button type="submit">运行潮流计算</button>
  </form>

  <article id="status" class="mono"></article>

  <h3>节点电压表（Buses）</h3>
  <div class="scroll-x"><table id="buses" role="grid"></table></div>

  <h3>支路功率表（Branches）</h3>
  <div class="scroll-x"><table id="branches" role="grid"></table></div>

<script>
async function runPowerFlow(rid) {
  const status = document.getElementById('status');
  status.textContent = '⏳ 提交任务中...';
  const resp = await fetch('/api/powerflow?rid=' + encodeURIComponent(rid));
  if (!resp.ok) {
    status.textContent = '❌ 请求失败：' + resp.status + ' ' + resp.statusText;
    return;
  }
  const data = await resp.json();
  status.textContent = data.logs && data.logs.length
    ? data.logs.map(l => '[' + l.level + '] ' + l.content).join('\\n')
    : '✅ 任务完成。';

  // 渲染表格
  renderTable('buses', data.buses.headers, data.buses.rows);
  renderTable('branches', data.branches.headers, data.branches.rows);
}

function renderTable(id, headers, rows) {
  const table = document.getElementById(id);
  if (!headers || !rows) { table.innerHTML = '<tbody><tr><td>无数据</td></tr></tbody>'; return; }
  let thead = '<thead><tr>' + headers.map(h => '<th>' + h + '</th>').join('') + '</tr></thead>';
  let tbody = '<tbody>' + rows.map(r => {
    return '<tr>' + headers.map(h => '<td>' + (r[h] ?? '') + '</td>').join('') + '</tr>';
  }).join('') + '</tbody>';
  table.innerHTML = thead + tbody;
}

document.getElementById('pfForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const rid = e.target.rid.value || 'model/CloudPSS/IEEE3';
  runPowerFlow(rid);
});

// 首次自动加载
runPowerFlow('{{ rid }}');
</script>
</body>
</html>"""

@app.route("/")
def index():
    # 默认演示 RID，可在页面更改
    rid = request.args.get("rid", "model/CloudPSS/IEEE3")
    return render_template_string(INDEX_HTML, rid=rid)

@app.route("/api/powerflow")
def api_powerflow():
    # --- 1) 鉴权 + 平台地址 ---
    api_token = os.getenv("CLOUDPSS_TOKEN")
    if not api_token:
        return jsonify({"error": "CLOUDPSS_TOKEN 未设置"}), 500
    cloudpss.setToken(api_token)

    api_url = os.getenv("CLOUDPSS_API_URL", "https://cloudpss.net/")
    os.environ["CLOUDPSS_API_URL"] = api_url

    # --- 2) 读取 RID 并获取模型 ---
    rid = request.args.get("rid", "model/CloudPSS/IEEE3")
    model = cloudpss.Model.fetch(rid)

    # --- 3) 选择方案 & 运行潮流 ---
    config = model.configs[0]
    job = model.jobs[0]  # 默认第一个为潮流计算方案
    runner = model.run(job, config)

    logs = []
    while not runner.status():
        for log in runner.result.getLogs():
            # log 结构：{"type":"log","verb":"create","version":1,"data":{"level":"info","content":"..." }}
            d = log.get("data", {})
            level = d.get("level", "info")
            content = d.get("content", "")
            logs.append({"level": level, "content": content})
        time.sleep(0.3)

    # --- 4) 读取结果（原始表） ---
    buses_raw = runner.result.getBuses()      # list[table]
    branches_raw = runner.result.getBranches()

    # --- 5) 转换为“按行可读”；并做列名别名/清洗 ---
    def convert_and_alias(table_list):
        if not table_list:
            return {"headers": [], "rows": []}
        headers, rows = table_to_rows(table_list[0])

        # 别名映射后的新表头（保序）
        alias_headers = []
        for h in headers:
            alias_headers.append(ALIASES.get(h, clean_label(h)))

        # 行字段用别名键
        aliased_rows = []
        for r in rows:
            new_r = {}
            for h, ah in zip(headers, alias_headers):
                new_r[ah] = r.get(h, "")
            aliased_rows.append(new_r)

        return {"headers": alias_headers, "rows": aliased_rows}

    buses = convert_and_alias(buses_raw)
    branches = convert_and_alias(branches_raw)

    # （可选）做个简单一致性校验：Ploss≈Pij+Pji、Qloss≈Qij+Qji
    # 不阻断，只返回到前端可视化时用
    def safe_float(x):
        try:
            return float(x)
        except Exception:
            return None

    checks = []
    if "Pij(MW)" in branches["headers"] and "Pji(MW)" in branches["headers"] and "Ploss(MW)" in branches["headers"]:
        for r in branches["rows"]:
            pij = safe_float(r.get("Pij(MW)"))
            pji = safe_float(r.get("Pji(MW)"))
            pl  = safe_float(r.get("Ploss(MW)"))
            ok_p = (pij is not None and pji is not None and pl is not None and abs((pij + pji) - pl) < 1e-3)
            checks.append({"branch": f"{r.get('From bus','?')}→{r.get('To bus','?')}", "P_check": ok_p})

    return jsonify({
        "rid": rid,
        "logs": logs,
        "buses": buses,
        "branches": branches,
        "checks": checks
    })

if __name__ == "__main__":
    # 运行：python app.py
    # 打开浏览器 http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)
