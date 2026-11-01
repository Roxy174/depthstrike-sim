# DepthStrike · 深度拳击

基于 RGB-D 人体追踪的三维击球交互项目，使用 Python、MediaPipe、OpenCV 和 Open3D。识别到人物后直接开始左右交替击球，支持轨迹录制回放及动作关卡复盘。

## 快速运行

在项目根目录打开 PowerShell，使用本机已有的 `depthstrike` 环境启动已连接的 Gemini 2 或 Astra：

```powershell
$py = "$env:USERPROFILE\.conda\envs\depthstrike\python.exe"
& $py -m depthstrike --source auto-camera --config configs/adaptive.json
```

自动入口每轮使用一台相机。两种设备同时连接时，用 `--source gemini-camera` 或 `--source astra-camera` 指定；`--list-cameras` 只列出设备，不开始采集。更换设备后重新启动即可，仍无需校准。

不连接相机时，可运行自动击球的合成演示：

```powershell
& $py -m depthstrike --source demo --config configs/adaptive.json
```

增加 `--view dual` 可显示三维辅助窗口。新电脑安装、其他相机与故障处理见 [运行说明](docs/RUNNING.md)。

## 操作

默认已取消校准：双肩被识别后自动放置目标，手腕追踪有效即可进入回合，无需前伸保持、左右试击或倒计时。目标固定在初始肩部前方约 38 厘米，蓝色代表左手，橙色代表右手。

| 按键 | 功能 |
| --- | --- |
| 空格 | 暂停／继续 |
| R | 清分、重新开始并按当前肩部位置放置目标 |
| Q / Esc | 退出并释放相机 |

保持单人正面、双肩和双手入镜；先收拳，再朝目标交替出拳。改变站位或移动相机后按 `R`。命中依据三维空间接触和有效出拳条件。

## 文档

- [运行说明](docs/RUNNING.md)：环境、Gemini 2／Astra、录制回放、动作复盘和常见问题。
- [开发与测试](docs/DEVELOPMENT.md)：模块、配置、测试、对比实验及当前验证状态。
- [第三方依赖](docs/THIRD_PARTY.md)：SDK、模型、字体和依赖来源。

旧设计、开发计划和分阶段验证已合并到 [历史档案](docs/archive/HISTORY.md)，按需展开查阅。当前原型以目标球交互为主，完整虚拟对手、格挡和闪避仍属后续设计。
