# 电力系统潮流计算与 CloudPSS SDK 可视化项目

## 一、潮流计算简介

潮流计算（Power Flow Calculation，又称负荷潮流分析）是电力系统分析中最基础、最常用的一类计算。它的主要任务是在给定电网结构、元件参数以及运行条件的情况下，求解电力系统中：

* **各节点电压**（幅值与相角）；
* **发电机的出力**（有功和无功功率）；
* **负荷的吸收功率**；
* **输电线路或变压器的功率流向与损耗**。

其本质是解一组非线性的功率平衡方程。
电力系统中常见的母线类型包括：

* **平衡母线（Slack Bus）**：平衡系统的功率不平衡，电压幅值和相角固定；
* **PV 母线**：有功功率和电压幅值已知，需要解出无功和相角；
* **PQ 母线**：有功和无功负荷已知，需要解出电压和相角。

通过潮流计算，运维人员可以了解系统在某一运行方式下的稳态分布情况，判断是否存在电压越限、线路过载或网损过大的问题。这些结果也是电力调度、规划和优化的基础。

---

## 二、项目思路与实现

本项目的目标是：
**利用 CloudPSS 提供的 Python SDK，运行标准算例的潮流计算任务，并通过一个 Web 服务将结果可视化展示，同时支持 CSV 导出。**

### 技术路线

1. **后端框架**：使用 Flask 搭建简单的 Web 服务；
2. **电力计算**：调用 CloudPSS SDK，运行潮流计算任务；
3. **结果处理**：将 CloudPSS 的表格结果（按列存储）转换为前端友好的“按行表格”形式；
4. **数据清洗**：去除列名中的 HTML 标签（例如 `<i>V</i><sub>m</sub>`），并提供更直观的别名（如 `Vm(pu)`）；
5. **数据接口**：

   * `/api/powerflow`：运行潮流计算并返回 JSON 格式的节点表与支路表；
   * `/api/export/csv`：根据参数选择导出 Buses 或 Branches 表为 CSV 文件；
6. **前端展示**：前端 HTML 页面通过 AJAX 调用接口，渲染出潮流计算结果的表格，并提供“运行计算”“下载 CSV”“清空结果”的按钮。

### 核心代码逻辑

* **运行潮流计算**

  ```python
  model = cloudpss.Model.fetch(rid)
  config = model.configs[0]
  job = model.jobs[0]
  runner = model.run(job, config)
  ```

  SDK 会提交计算任务并返回 `runner`，通过 `runner.status()` 轮询任务是否完成。

* **获取结果表**

  ```python
  buses_raw = runner.result.getBuses()
  branches_raw = runner.result.getBranches()
  ```

  这两个函数分别返回节点电压表和支路功率表。

* **结果转化与别名**

  ```python
  def convert_and_alias(table_list):
      headers, rows = table_to_rows(table_list[0])
      alias_headers = [ALIASES.get(h, clean_label(h)) for h in headers]
      ...
  ```

  将原始的列名替换为更友好的别名，并输出 JSON 供前端使用。

* **CSV 导出**

  ```python
  writer = csv.DictWriter(output, fieldnames=result["headers"])
  writer.writeheader()
  for r in result["rows"]:
      writer.writerow({h: r.get(h, "") for h in result["headers"]})
  ```

  生成标准 CSV 文件，方便 Excel 打开。

### 部署运行

1. 设置环境变量：

   ```bash
   export CLOUDPSS_TOKEN="你的token"
   ```
2. 启动 Flask 应用：

   ```bash
   python app.py
   ```
3. 浏览器打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)，即可看到页面。
