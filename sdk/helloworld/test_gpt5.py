# -*- coding: utf-8 -*-
"""
CloudPSS SDK 官方推荐实践（含保存到个人空间）：
1. 通过 Model.fetch 获取公共示例算例
2. 将示例算例复制保存到个人空间 (Model.create)
3. 使用 Model.fetchTopology 获取拓扑实例
4. 使用 ModelTopology.dump 保存完整拓扑 JSON（官方推荐）
5. 运行潮流计算并获取结果（并以可读方式打印关键字段）

准备：
  - 在系统环境变量中配置：
      CLOUDPSS_TOKEN   # 你的 CloudPSS 访问令牌
      CLOUDPSS_ACCOUNT # 你的账号名称（用来构造个人空间 rid）
  - pip install cloudpss
"""

import os
import time
import json
import cloudpss

def main():
    # ===== 0. 设置平台地址 + Token =====
    os.environ["CLOUDPSS_API_URL"] = "https://cloudpss.net/"  # 公网地址；如用专网，请改为专网地址
    api_token = os.getenv("CLOUDPSS_TOKEN")                   # 从环境变量读取 Token（推荐做法）
    if not api_token:
        raise RuntimeError("❌ 未获取到 CLOUDPSS_TOKEN，请先在环境变量中设置。")
    cloudpss.setToken(api_token)

    account = os.getenv("CLOUDPSS_ACCOUNT")                   # 你的 CloudPSS 账号名，用于个人空间 rid
    if not account:
        raise RuntimeError("❌ 未获取到 CLOUDPSS_ACCOUNT，请在环境变量中设置你的账号名称，例如 'Maxwell'。")

    # ===== 1. 获取公共示例算例（3机9节点系统）=====
    # 说明：这是公共库中的只读项目，无法直接修改；下面第 2 步会将其复制到你的个人空间
    public_rid = "model/CloudPSS/IEEE3"
    model = cloudpss.Model.fetch(public_rid)
    print(f"✅ 已获取公共示例项目：{public_rid}")

    # ===== 2. 保存一份到个人空间（可读可写）=====
    # 目标 rid 示例：model/<你的账号>/ieee3_pf_demo
    personal_rid = f"model/{account}/ieee3_pf_demo"

    # 如果你反复运行脚本，项目可能已存在，这里做一个安全处理：
    try:
        # 改写 rid 到你的个人空间，然后创建（相当于“另存为”）
        model.rid = personal_rid
        cloudpss.Model.create(model)
        print(f"✅ 已将项目复制到你的个人空间：{personal_rid}")
    except Exception as e:
        # 若已存在或其他原因创建失败，打印提示并尝试直接 fetch
        print(f"⚠️ 复制到个人空间时出现提示：{e}\n   将直接使用已存在的个人空间项目。")

    # 获取你个人空间里的副本（后续所有操作都基于它）
    model = cloudpss.Model.fetch(personal_rid)
    print(f"✅ 从个人空间获取成功，项目名：{model.name}")

    # ===== 3. 获取拓扑实例（官方推荐：从模型对象获取）=====
    # implementType='powerFlow' 表示以潮流计算内核解析拓扑；maximumDepth=1 仅展开一层
    model_topology = model.fetchTopology(
        implementType="powerFlow",
        config=model.configs[0],
        maximumDepth=1
    )

    # ===== 4. 导出拓扑到本地 JSON（官方推荐：ModelTopology.dump）=====
    file_path = f"{model.name}_topology.json"
    cloudpss.ModelTopology.dump(model_topology, file_path, indent=2)
    print(f"✅ 已保存拓扑文件：{file_path}")

    # ===== 5. 启动潮流计算 =====
    # 约定：jobs[0] 一般为潮流计算方案（若你的项目结构不同，请按需调整索引）
    config = model.configs[0]
    job    = model.jobs[0]
    runner = model.run(job, config)

    # 监听运行状态，打印运行日志（可选）
    while not runner.status():
        for log in runner.result.getLogs():
            print(log)
        time.sleep(0.5)
    print("✅ 潮流计算结束")

    # ===== 6. 获取并“可读化”打印结果 =====
    # 原始接口：返回一个表格结构（包含列名与数据），直接打印会很乱
    # 这里解析列名并给出易懂的摘要
    buses    = runner.result.getBuses()     # 节点电压表
    branches = runner.result.getBranches()  # 支路功率表

    # ---- 节点电压表解析 ----
    print("\n=== 节点电压表 (Buses) ===")
    # buses 是一个列表，通常取第一个元素；其结构为 {"data": {"columns": [...]}, ...}
    bus_columns = buses[0]["data"]["columns"]
    # 简单健壮性检查
    if len(bus_columns) >= 4:
        # 逐行输出：Bus、Node、Vm（pu）、Va（deg）
        num_rows = len(bus_columns[0]["data"])
        for i in range(num_rows):
            bus_id = str(bus_columns[0]["data"][i])  # Bus（内部 Key，如 canvas_0_xxxx）
            node   = str(bus_columns[1]["data"][i])  # Node（可能为空，取决于算例）
            vm     = bus_columns[2]["data"][i]       # 电压幅值 (pu)
            va     = bus_columns[3]["data"][i]       # 电压角度 (deg)
            print(f"节点 {bus_id} (Node={node}): Vm={vm} pu, Va={va} °")
    else:
        # 如果列不足，直接把原始表结构打印出来以便排查
        print(json.dumps(buses, ensure_ascii=False, indent=2))

    # ---- 支路功率表解析 ----
    print("\n=== 支路功率表 (Branches) ===")
    branch_columns = branches[0]["data"]["columns"]
    # 期望顺序（常见）：[Branch, From bus, Pij, Qij, To bus, Pji, Qji, Ploss, Qloss]
    if len(branch_columns) >= 5:
        num_rows = len(branch_columns[0]["data"])
        for i in range(num_rows):
            from_bus = branch_columns[1]["data"][i]  # 起始节点 Key
            to_bus   = branch_columns[4]["data"][i]  # 终止节点 Key
            pij      = branch_columns[2]["data"][i]  # 有功功率 MW（i->j）
            qij      = branch_columns[3]["data"][i]  # 无功功率 MVar（i->j）
            # 统一保留 3 位小数显示（有些数据可能是字符串，先转 float 失败就原样显示）
            try:
                pij_disp = f"{float(pij):.3f}"
                qij_disp = f"{float(qij):.3f}"
            except Exception:
                pij_disp = str(pij)
                qij_disp = str(qij)
            print(f"支路 {from_bus} → {to_bus}: Pij={pij_disp} MW, Qij={qij_disp} MVar")
    else:
        print(json.dumps(branches, ensure_ascii=False, indent=2))

    # （可选）如果你修改了计算方案或参数方案，想把这些变更持久化到个人空间：
    # cloudpss.Model.update(model)
    # print("✅ 已将最新方案/参数更新保存到个人空间。")

if __name__ == "__main__":
    main()
