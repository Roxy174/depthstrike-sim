# 运行与复现

Windows PowerShell，Python 3.12。命令从仓库根目录运行，不需要激活虚拟环境。

本地 `0.3.0.dev0` 的动作生成关卡与三维复盘入口见 [Motion Studio](MOTION_STUDIO.md)。下文保留基础击球场景的安装与运行方式。

## 1. 安装

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,display,camera]"
.venv\Scripts\python.exe -m pip check
```

仅无窗口演示和合成评估可安装 `.[dev]`，核心只依赖 NumPy。overlay 需要 OpenCV，dual 另需 Open3D，均包含在 `.[display]`；相机与 RGB-D 回放需要 `.[camera]`。不要混用 Anaconda 全局依赖或 OpenCV headless 变体。

直接依赖固定于 `pyproject.toml`：NumPy 2.2.6、MediaPipe 0.10.32、pyorbbecsdk2 2.1.2、Open3D 0.19.0、OpenCV 4.11.0.86、pytest 8.3.5。SDK 导入名为 `pyorbbecsdk`。两个上游分别要求 OpenCV 标准与扩展分发包，因此固定为同版本，不单独升级。

## 2. 无相机演示

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo
.venv\Scripts\python.exe -m depthstrike --source demo --view dual
```

默认 overlay 为主交互窗口，dual 额外开启三维辅助视图。画面中的人物为明确标注的合成骨架，不读取电脑摄像头，不验证人体检测精度。不是蒙皮三维角色。

默认流程：稳定收拳 → 左手舒适前伸 → 收拳 → 右手舒适前伸 → 收拳 → 左右各试击一次 → 2 s 倒计时 → 60 s 回合。演示动作自动执行这些步骤，不绕过校准。

- 蓝色左手，橙色右手；活动球使用对应颜色，未激活球为灰色，命中短时绿色。
- 拳套圆表示交互代理，腕点与拳心不同；轨迹、出拳和碰撞使用同一拳心。
- `Gap` 为两代理球表面间距，正值尚未接触；`Depth` 为拳心 z 减目标 z，正值表示拳心仍在球后方；`Off-axis` 为横向偏差。缺失时不沿用旧距离。
- 二维圆圈重叠不等于三维命中；提示描述当前可观测条件，不保证是未命中的唯一原因。

按键：`Space` 暂停/继续；`R` 清分并重新校准；`Q` / `Esc` 退出。关闭任一已开启窗口也退出并释放资源。引导演示暂停时冻结合成动作，恢复时重启被打断的动作段；`R` 重启演示流程，但录制帧时间仍严格递增。真实相机输入在暂停期间继续读取。

`--sound` 可选开启 Windows 异步系统提示音；默认静音，不可用于 headless。不支持的平台或音频失败仅停止声音，不影响计分。

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 600
```

默认参数的固定结果：600 帧、9 次正式命中、90 分。试击不计入。headless 的 demo/camera 默认限制 600 帧；回放默认至 EOF 或回合结束。窗口模式按输入时间播放。

guided 演示的固定动作支持速度阈值不大于 2 m/s、平滑常数不大于 0.1 s；不满足几何触达、有效深度或连续采样要求时明确报错。其他参数组合优先使用与之匹配的录制，不将演示参数限制解释为相机算法的限制。

## 3. Gemini 2

显式下载官方模型，模型及同名 `.task.json` 来源说明任一已存在均拒绝覆盖，也不在启动时自动下载：

```powershell
.venv\Scripts\python.exe scripts/download_pose_model.py
.venv\Scripts\python.exe -m depthstrike --source camera
```

连接 USB 3，关闭占用设备的 Viewer。当前未完成真实设备采集、对齐和人体击球验收；camera 出错会明确失败，不会退回 demo。

保持单人正面、固定相机、双肩双肘双腕在画面内。收拳约 0.6 s，依次轻缓前伸并保持约 0.35 s；每次收回约 0.20 s。不需最大伸展，不击打屏幕、设备或实物。目标按每手舒适触达量的 0.85 生成，之后固定于相机空间。移动相机或改变站位后按 `R`。

新模式要求双肩、双肘、双腕及两拳心全部有效；非活动手丢失也会暂停回合计时、取消攻击，恢复后需要收拳。稳定采样中断不累计；倒计时中断后重新准备。若提示恢复站位，保持双肩接近校准参考；若提示距离或触达不足，调整并按 `R` 重来。

目标还必须与中立拳心至舒适前伸拳心的实测线段相交（计入两代理半径）。侧向伸手或过高的 `target_height_m` 导致不相交时，不进入试击；核对直拳方向、目标高度和站位后按 `R`。这是已测路径的保守检查，不等同于完整人体可达空间建模。

拳心为腕点沿前臂方向延长 0.06 m 的代理，不是解剖测量；深度来自可见表面。所有阈值仍需实机调整，不能据计分推断打击力量或专业动作质量。

采集优先 RGB 640×480/30 fps，深度用设备默认流，经软件 D2C 对齐；拒绝尺寸、时间不匹配帧。支持无畸变和标准 Brown–Conrady；未知或非标准模型不按针孔近似。旧 SDK 缺标定模型字段时必须独立确认后再配置 `legacy_sdk_distortion_model`，不可改名绕过检查。

## 4. 录制与回放

每次使用新的文件名或目录，以下路径已存在时会拒绝覆盖。

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 600 --record recordings/guided-demo.jsonl
.venv\Scripts\python.exe -m depthstrike --source replay --input recordings/guided-demo.jsonl --headless
```

v2 保存原始三维关节、失效原因、配置、控制操作和事件；回放重新计算校准与计分，事件序列一致。骨架回放不能验证原始深度或姿态模型。

```powershell
.venv\Scripts\python.exe -m depthstrike --source camera --record recordings/pose-session.jsonl --record-rgbd recordings/rgbd-session
.venv\Scripts\python.exe -m depthstrike --source rgbd-replay --input recordings/rgbd-session
```

RGB-D 回放保存配对图像、米制深度、内参与标定，并重新执行实际模型及融合。仅在参与者同意后录制，原始人像默认不提交。路径、数组类型、声明内存和实际字节数均检查；禁止 pickle 和越界引用。

RGB-D 转存骨架时，来源记为 `rgbd-replay`，原 metadata 完整保留在 `recording_metadata`，`evidence` 标记继续传递；`pose_model` 描述本次推理模型。合成输入不会因转存而成为真实录制证据。

v1 记录缺少新配置时显式采用 legacy：原手腕代理、固定距离和旧计时规则。随仓库的 4 帧夹具仍为 2 命中、20 分。显式 `--config` 会替代记录配置，结果可能改变。

```powershell
.venv\Scripts\python.exe -m depthstrike --source replay --input tests/fixtures/straight_punches.jsonl --headless
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/legacy.json --headless --frames 240
```

第二条是兼容模式：240 帧、6 命中、60 分；不是新引导模式的预期值。

## 5. 软件耗时与对比实验

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 600 --metrics outputs/demo-metrics.json
.venv\Scripts\python.exe -m depthstrike.evaluation --suite synthetic --output outputs/synthetic-comparison.json
```

metrics 记录 read、simulation、record、render、frame_total；相机或 RGB-D 回放另记录 capture、pose、fusion。read 已包含其子阶段，不可重复相加；frame_total 排除回放等待。每阶段最多保留最后 4096 条样本，p50/p95/max 基于保留样本，另给全程计数、失败次数、超时数和结束原因。read 包含超时/EOF 读取，frame_total 不包含 EOF；样本数不一定等于成功帧数。

初始化或运行失败时也尽可能导出 partial 统计。`processing_s` 是整个软件会话耗时，所有这些数值都不是曝光到显示的端到端延迟，也不能用无窗口 demo 的速度声称摄像头 FPS。

实验标签、四种方法的定义及真人数据要求见 [EVALUATION.md](EVALUATION.md)。默认只有合成证据。

## 6. 配置与测试

配置为 JSON，可只覆盖所需字段；完整校验见 `src/depthstrike/config.py`。guided 目标使用 `target_reach_ratio`，`target_forward_m` 仅对 legacy 生效。默认半径：拳套 0.06 m、目标 0.08 m；最大轨迹间隔 0.2 s；它们不是人体实测的最优参数。

```powershell
.venv\Scripts\python.exe -m depthstrike --config configs/default.json
$testTemp = Join-Path (Get-Location) ("tmp/pytest-" + [guid]::NewGuid().ToString("N"))
.venv\Scripts\python.exe -m pytest -q --basetemp $testTemp
```

独立的仓库内临时目录避免部分受管 Windows 环境中系统 Temp 权限问题。它只用于测试，不要指定已有资料目录。真实窗口测试需要桌面会话：

```powershell
$env:DEPTHSTRIKE_GUI_TESTS = '1'
$testTemp = Join-Path (Get-Location) ("tmp/pytest-gui-" + [guid]::NewGuid().ToString("N"))
.venv\Scripts\python.exe -m pytest -q --basetemp $testTemp
Remove-Item Env:DEPTHSTRIKE_GUI_TESTS
```

## 7. 故障定位

| 现象 | 处理 |
| --- | --- |
| 无设备／连续 5 s 无有效帧 | USB 3、供电、Viewer 占用、SDK/固件配套；先用官方 Viewer 验证，不自动升级固件 |
| 模型缺失／DLL 导入失败 | 显式下载，核对 x64 Python、固定依赖和 VC++ 运行库 |
| 无显示或 Open3D 失败 | 使用 `--view overlay` 或 `--headless`；检查图形驱动 |
| 校准停住 | 查看阶段与阻塞原因，双臂完整入镜，保持站位和连续稳定时间 |
| 看似碰到却没计分 | 核对 Depth/Gap、活动手、速度及收拳复位；二维重叠不是命中条件 |
| 输出已存在 | 改用新文件名，不删除或覆盖已有录制来重试 |

证据和限制见 [VERIFICATION.md](VERIFICATION.md)。
