import sys, os
import cloudpss  # 引入 cloudpss 依赖
import json
import time

if __name__ == '__main__':

    # 申请 token
    api_token = os.getenv("CLOUDPSS_TOKEN")
    cloudpss.setToken(api_token)

    # 设置算例所在的平台地址
    os.environ['CLOUDPSS_API_URL'] = 'https://cloudpss.net/'

    # 获取指定 rid 的算例项目
    model = cloudpss.Model.fetch('model/CloudPSS/IEEE3')

    # 选择参数方案，若未设置，则默认用 model 的第一个 config（参数方案）
    config = model.configs[0]

    # 选择计算方案，若未设置，则默认用 model 的第一个 job（潮流计算方案）
    job = model.jobs[0]

    # 启动计算任务
    runner = model.run(job, config)  # 运行计算方案
    while not runner.status():
        logs = runner.result.getLogs()  # 获得运行日志
        for log in logs:
            print(log)  # 输出日志
        time.sleep(1)
    print('end')  # 运行结束

    # 打印潮流计算结果
    print(runner.result.getBuses())  # 节点电压表
    print(runner.result.getBranches())  # 支路功率表