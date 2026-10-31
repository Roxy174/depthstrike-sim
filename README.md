# DepthStrike · 深度拳击

基于 RGB-D 人体追踪的三维击球交互项目，使用 Python、MediaPipe、OpenCV 和 Open3D。当前支持引导校准、左右交替击球、轨迹录制回放及动作关卡复盘。

## 快速运行

在项目根目录打开 PowerShell，使用本机已有的 `depthstrike` 环境启动 Astra：

```powershell
$py = "$env:USERPROFILE\.conda\envs\depthstrike\python.exe"
& $py -m depthstrike --source astra-camera --config configs/adaptive.json
```

不连接相机时，可运行自动完成校准和击球的合成演示：

```powershell
& $py -m depthstrike --source demo --config configs/adaptive.json
```

增加 `--view dual` 可显示三维辅助窗口。新电脑安装、其他相机与故障处理见 [运行说明](docs/RUNNING.md)。

## 操作

校准顺序：收拳准备 → 左手前伸并收回 → 右手前伸并收回 → 左右试击 → 倒计时 → 正式回合。

| 按键 | 功能 |
| --- | --- |
| 空格 | 暂停／继续 |
| R | 清分并重新校准 |
| Q / Esc | 退出并释放相机 |

保持单人正面、双肩双肘双手入镜；改变站位或移动相机后重新校准。蓝色代表左手，橙色代表右手，命中依据三维空间接触和有效出拳条件。

## 文档

- [运行说明](docs/RUNNING.md)：环境、Astra、录制回放、动作复盘和常见问题。
- [开发与测试](docs/DEVELOPMENT.md)：模块、配置、测试、对比实验及当前验证状态。
- [第三方依赖](docs/THIRD_PARTY.md)：SDK、模型、字体和依赖来源。

旧设计、开发计划和分阶段验证已合并到 [历史档案](docs/archive/HISTORY.md)，按需展开查阅。当前原型以目标球交互为主，完整虚拟对手、格挡和闪避仍属后续设计。
