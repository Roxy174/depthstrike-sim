# DepthStrike · 深度拳击

基于 RGB-D 人体追踪的三维击球交互项目，使用 Python、MediaPipe、OpenCV 和 Open3D。识别到人物后直接开始左右交替击球，支持轨迹录制回放及动作关卡复盘。

## 快速运行

在项目根目录打开 PowerShell，使用本机已有的 `depthstrike` 环境启动已连接的 Gemini 2 或 Astra：

```powershell
$py = "$env:USERPROFILE\.conda\envs\depthstrike\python.exe"
& $py -m depthstrike --source auto-camera --config configs/adaptive.json
```

自动入口每轮使用一台相机。两种设备同时连接时，用 `--source gemini-camera` 或 `--source astra-camera` 指定；`--list-cameras` 只列出设备，不开始采集。更换设备后重新启动即可，仍无需校准。

人物识别默认使用 **Pose Landmarker Full**。本机已备好 Full 和 Heavy；增加 `--pose-model heavy` 可切换较大模型，`--pose-model lite` 可对比轻量版本。手部深度过滤和短暂空洞恢复也已优化；实机效果需在相同场景比较。

不连接相机时，可运行自动击球的合成演示：

```powershell
& $py -m depthstrike --source demo --config configs/adaptive.json
```

增加 `--view dual` 可显示三维辅助窗口。新电脑安装、其他相机与故障处理见 [运行说明](docs/RUNNING.md)。

## 操作

默认已取消校准：双肩被识别后自动放置 6 个目标，手腕追踪有效即可进入回合，无需前伸保持、左右试击或倒计时。使用上述 `adaptive.json` 时，所有小球中心固定在 `camera_target_depth_m` 指定的相机深度处；左右和高度仍按人物初始肩部排列，分为中间、上方和下方三组。触碰高亮球后切换下一个，蓝色代表左手，橙色代表右手。

在 `configs/adaptive.json` 中修改 `camera_target_depth_m` 可设置相机深度，单位米；数值越小越靠近摄像头。保存后重启生效，按 `R` 只重新定位左右和高度，深度保持设定值。若将 `direct_target_reference` 改为 `shoulder`，则使用 `direct_target_forward_m` 设置肩部前伸距离。`direct_targets_per_hand` 可设为 1～4，对应总共 2、4、6、8 个球。

| 按键 | 功能 |
| --- | --- |
| 空格 | 暂停／继续 |
| R | 清分、重新开始并按当前肩部位置放置目标 |
| Q / Esc | 退出并释放相机 |

保持单人正面，初始化时让双肩入镜，然后按高亮球提示用左手或右手触碰。默认手部球与目标球在三维空间重叠约 2 厘米即可命中，无需收拳或快速出拳；同一个球命中后，需要将手完全移开再触碰才能再次计分。命中增加 10 分，小球短暂变绿并切换下一个目标。改变站位或移动相机后按 `R`。

左下角的大号数字显示累计击中小球的次数，旁边显示积分和剩余时间。每次有效命中会出现约 0.9 秒的“+1 次、+10 分”提示。回合结束后保留总成绩，按 `R` 清零重开，按 `Q` 或 `Esc` 退出。

## 文档

- [运行说明](docs/RUNNING.md)：环境、Gemini 2／Astra、录制回放、动作复盘和常见问题。
- [开发与测试](docs/DEVELOPMENT.md)：模块、配置、测试、对比实验及当前验证状态。
- [第三方依赖](docs/THIRD_PARTY.md)：SDK、模型、字体和依赖来源。

旧设计、开发计划和分阶段验证已合并到 [历史档案](docs/archive/HISTORY.md)，按需展开查阅。当前原型以目标球交互为主，完整虚拟对手、格挡和闪避仍属后续设计。
