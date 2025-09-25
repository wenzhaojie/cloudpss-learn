import sys, os
import cloudpss
import json
import time

if __name__ == '__main__':
    # 填写 token
    api_token = os.getenv("CLOUDPSS_TOKEN")
    cloudpss.setToken(api_token)

    # 设置访问的地址
    os.environ['CLOUDPSS_API_URL'] = 'https://cloudpss.net/'

    # 选择算例，获取指定算例 rid 的项目
    # model = cloudpss.Model.fetch('model/CloudPSS/IEEE3')
    model = cloudpss.Model.fetch('model/wengod/T_3_Gen_9_Bus')

    print(model.rid)
    print([(j.get('name'), j.get('@type', j.get('type'))) for j in model.jobs])  # 看所有job
    # 选择参数方案，若未设置，则默认用 model 的第一个 config（参数方案）
    config = model.configs[0]

    # 选择计算方案，若未设置，则默认用 model 的第一个 job（潮流计算方案），此处选择 jobs[1]，为电磁暂态仿真任务
    job = model.jobs[1]

    # 启动计算任务
    runner = model.run(job, config)
    while not runner.status():
        logs = runner.result.getLogs()  # 获得运行日志
        for log in logs:
            print(log)  # 输出日志
        time.sleep(1)
    print('end')  # 运行结束

    # 获取全部输出通道
    plots = runner.result.getPlots()

    # 使用 plotly 绘制曲线
    import plotly.graph_objects as go

    for i in range(len(plots)):
        fig = go.Figure()
        channels = runner.result.getPlotChannelNames(i)
        for val in channels:
            channel = runner.result.getPlotChannelData(i, val)
            fig.add_trace(go.Scatter(channel))
        fig.show()