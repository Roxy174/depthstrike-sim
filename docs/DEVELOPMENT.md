# 开发与测试

当前实现是单人、固定相机、正面上半身的三维目标击打原型。采集、交互规则、显示及离线实验均使用 Python；完整虚拟对手、格挡、闪避和独立 exe 发行尚未实现。

## 模块

处理流程：RGB-D 采集与对齐 → 姿态关键点 → 实测深度反投影 → 滤波与拳部代理 → 出拳状态与连续碰撞 → 显示／录制。

| 模块 | 职责 |
| --- | --- |
| `camera_selection.py` / `capture.py` / `astra_capture.py` / `openni_capture.py` / `opencv_capture.py` | 设备选择、各采集后端与标定 |
| `pose.py` / `fusion.py` / `tracking.py` | MediaPipe、人体掩膜、深度融合及轨迹处理 |
| `automatic_layout.py` / `interaction.py` / `calibration.py` | 自动放置目标、手部代理与旧 guided 录制兼容 |
| `geometry.py` / `boxing.py` / `feedback.py` | 三维碰撞、出拳状态、回合和空间反馈 |
| `visualization.py` / `arena.py` / `ui_text.py` | 中文主界面、三维辅助视图和字体 |
| `recording.py` / `sources.py` / `app.py` / `cli.py` | 输入抽象、录制回放和程序入口 |
| `studio.py` / `motion_authoring.py` / `challenge_round.py` / `review_view.py` | 动作关卡与复盘 |
| `evaluation.py` / `robustness.py` / `metrics.py` | 对比实验、故障注入和软件耗时 |

源码位于 [src/depthstrike](../src/depthstrike)，依赖版本由 [pyproject.toml](../pyproject.toml) 固定。

## 数据与判定约定

- 相机坐标为 X 向右、Y 向下、Z 向前，位置单位米，时间单位秒；彩色图为 RGB，深度已经对齐到彩色网格。
- 三维点使用图像位置、实测表面深度及设备内参计算。支持的畸变模型必须明确，MediaPipe 的身体局部 `world landmarks` 不作为相机空间坐标。
- 拳部代理与显示、轨迹、碰撞采用相同位置。`observed`、`depth_patch`、`hand_surface` 与 `predicted` 保留来源；预测只用于显示。
- 默认 direct 模式从有效双肩自动生成固定目标，不进行前伸测量或试击。普通回合使用 `hit_mode=overlap`，只需活动手的有效当前观测与高亮球重叠到门槛，不要求收拳、攻击速度或位移。旧录制默认 `punch`，动作关卡保留出拳判定。
- 重叠模式不沿历史线段推测接触，也不使用预测点计分。同一球命中后，需观测到该手与球完全分离并额外离开 0.01 米才解除锁定；暂停、丢失及重新获取不清除锁定，重开回合清除。

骨架 JSONL v2 保存原始关节、配置、无效原因、操作和事件；回放重新计算结果。v1 缺少新配置时采用 legacy 语义。RGB-D 记录另保存图像、深度、完整标定与上游来源；回放重新执行模型。读取检查路径、数组类型、尺寸及实际字节数，不使用 pickle。

## 相机适配

`auto-camera` 通过 SDK 名称识别 Gemini 2，通过 USB `2bc5:050f` 识别旧款 Astra 彩色接口；两者都在线或同型号多台时拒绝隐式选择。Gemini 使用枚举到的设备创建 Pipeline，避免默认设备变化；Astra 继续由 OpenNI 验证 `2bc5:060f` 深度设备。

Gemini 2 协商 RGB／BGR／MJPG 彩色格式及可用深度分辨率，保留单位换算、设备时间戳、原始帧同步检查与软件对齐。各后端元数据经骨架、RGB-D 录制和回放保留，界面据实际来源显示采集方式。Astra 的主机读取时差仍不代表曝光同步。

## 配置

JSON 可只覆盖需要的字段；运行时缺省使用 direct、腕点代理和局部追踪。`AppConfig()` 保留历史 guided 默认值，供旧录制及解析演示兼容；旧录制不经运行时缺省配置重写。完整字段与校验见 [config.py](../src/depthstrike/config.py)。

| 配置 | 用途 |
| --- | --- |
| [default.json](../configs/default.json) | 无需校准的直接回合 |
| [adaptive.json](../configs/adaptive.json) | 直接回合、掩膜融合、One Euro 和跳变抑制，共用于 Gemini 2 和本机 Astra |
| [legacy.json](../configs/legacy.json) | 原手腕代理、固定目标及旧记录兼容 |

adaptive 的主要规则：

| 项目 | 行为 |
| --- | --- |
| 自动目标 | 第一帧有效双肩即可初始化。adaptive 使用 `direct_target_reference=camera`、`camera_target_depth_m=1.5`，所有球心固定在同一相机 Z 平面，X/Y 仍基于初始肩部。`shoulder` 模式保留前伸距离及空间层次。每手 1～4 球，默认共 6 球，按中间、上方、下方、外侧顺序左右交替；生成后固定，R 重新取肩部位置，相机模式的深度不变 |
| 重叠判定 | 当前活动手的三维中心距离不超过 `hand_radius_m + target_radius_m - overlap_depth_m` 即命中；默认重叠深度 0.02 米，即中心距离最多 0.12 米。每帧最多切换一次，按球锁定重复接触；初始已重叠、缓慢触碰及未命中球的有效重新获取均可命中 |
| 掩膜与深度 | 关节置信度仍为 0.6，掩码像素门槛独立为 0.35。中心深度有效时，要求 5×5 区域至少 60% 的像素支持同一中心表面，允许少量背景；空洞恢复必须有未过期的同名直接观测和当前有效邻域。期限为 `min(depth_recovery_s, max_track_gap_s)`，默认 0.20 秒，恢复点不刷新期限 |
| 跳变抑制 | 滤波前比较近期接受的原始观测；允许位移为 `tracking_outlier_slack_m + speed × dt`。异常点不更新锚点，锚点过期后允许重新获取 |
| 局部追踪 | 重叠普通回合在初始化后只要求活动手腕点有效；中断和暂停不累计回合时间，也不将缺失点当作离开小球。保留 `punch` 模式与关卡的肩腕及出拳条件 |
| 显示与代理 | 使用有效腕点，不依赖手指或肘部推算；最多 0.20 秒的预测只维持显示，不参与命中。按实测深度遮挡虚拟球 |

自动布局使用工程预设，未测量个体舒适触达范围；默认不执行 guided 的路径采样检查。系统未实现多人身份重识别或完整人体可达空间建模。`guided`、`legacy` 及历史确认操作仍用于旧录制复现。

## 模型选择与耗时

运行时默认 Full，`--pose-model lite/full/heavy` 只替换实时输入或 RGB-D 回放的识别权重；骨架回放沿用录制结果。库级 `AppConfig()` 及旧录制仍默认 Lite、严格深度表面判定、掩码阈值继承关节阈值，保持历史语义。

2026-11-01 在本机 Core Ultra 9 290HX Plus 上，以 Google 官方公开 `pose.jpg` 等比填充至 640×480，预热 5 帧后重复处理静态图像 30 帧，测得：

| 模型 | CPU 平均推理耗时 | P95 |
| --- | --- | --- |
| Lite | 8.4 ms | 8.8 ms |
| Full | 12.2 ms | 12.9 ms |
| Heavy | 41.0 ms | 41.9 ms |

三者均在样例中产生姿态及掩码。结果仅衡量这张静态样例的模型推理耗时，未使用独显，不包含相机、融合或显示耗时，也不能证明真人手部准确率。完整记录在本机 `tmp/pose-model-benchmark-20261101.json`。

[Google 公开姿态评测](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose.md#pose-estimation-quality) 中 Full／Heavy 的整体指标高于 Lite，但不是本项目的出拳测试。完全替换路线可考虑 [RTMW 全身姿态模型](https://arxiv.org/abs/2407.08634) 与 [RTMLib 部署](https://github.com/Tau-J/rtmlib)；本轮未接入 RTMW，也未将其公开指标当作本项目收益。

`pose_confidence_threshold=0`、`segmentation_threshold=0` 表示继承旧的 `confidence_threshold`。`depth_surface_mode=strict` 和 `depth_recovery_s=0` 保留旧策略；运行时采用 `center_cluster` 与限时直接观测缓存。指标报告分别记录模型／深度融合阶段与运动滤波后的手部可用性，计数跨暂停、断轨和回合重置累积，仅在创建新会话时清零。

## 自动化测试

先按 [运行说明](RUNNING.md#环境) 设置 `$py`。使用新的仓库内临时目录，避免覆盖资料或受系统 Temp 权限影响：

```powershell
$testTemp = Join-Path (Get-Location) ("tmp/pytest-" + [guid]::NewGuid().ToString("N"))
& $py -m pytest -q -p no:cacheprovider --basetemp $testTemp
```

真实窗口测试需要桌面会话，运行前设置 `$env:DEPTHSTRIKE_GUI_TESTS = '1'`，结束后用 `Remove-Item Env:DEPTHSTRIKE_GUI_TESTS` 清除。未安装可选依赖或未下载模型时，相关测试可能跳过，跳过不计为通过。

固定合成入口可用于冒烟检查：`configs/adaptive.json` 直接回合为 600 帧、16 命中、160 分；历史 guided 为 600 帧、9 命中、90 分，legacy 为 240 帧、6 命中、60 分；动作工坊示例为九靶、六命中。合成结果验证软件规则。

## 对比实验

```powershell
& $py -m depthstrike.evaluation --suite synthetic --output outputs/comparison.json
& $py -m depthstrike.evaluation --input tests/fixtures/straight_punches.jsonl --labels tests/fixtures/evaluation/straight-punch-labels.json --output outputs/fixture-comparison.json
& $py -m depthstrike.robustness --output outputs/adaptive-report.json --image outputs/adaptive-preview.png
```

比较四种方法：

| 方法 | 判定 |
| --- | --- |
| `2d_entry` | 二维代理接触进入 |
| `3d_discrete_entry` | 单帧三维接触进入 |
| `3d_swept_entry` | 连续轨迹的三维扫掠进入 |
| `3d_swept_punch` | 连续进入加出拳／收拳状态及单次结算 |

方法共享骨架、预处理、固定目标和活动日程；标签独立于被测事件输出。使用 [标签清单示例](../tests/fixtures/evaluation/straight-punch-labels.json) 和 [解析场景说明](../tests/fixtures/evaluation/README.md)，不要用录制中的 events 充当真值。

报告包括 TP/FP/FN、precision/recall、重复结算、追踪无效比例、输入摘要、参数和证据类型。零分母为 null，忽略区间不参与匹配，断轨不桥接。真人数据另需独立空间参照、标注依据和调参／评价划分；完整标签协议保留于 [历史档案](archive/HISTORY.md#docs-evaluation-md)。

## 动作关卡原理

作者录制支持 direct 和 guided，仅从有效出拳并完成收回的动作提取关卡；中断动作被舍弃。靶位按肩宽和参考前伸量归一化，挑战者识别后映射一次并固定；direct 的前伸量来自工程预设，报告标记为 `automatic_preset`，guided 则来自实测。当前限 32 靶、120 秒，不支持同时出拳。

复盘区分命中、空间未命中、无有效攻击、观测不足和未完成。局部修正只对满足观测与攻击条件的空间未命中生成，检查深度、触达范围及修正后的连续接触；紫色线段表示局部几何平移。

## 当前验证状态

最近一次完整回归为 **2026-11-04，558 项通过，含真实窗口测试及三种实际模型初始化／推理测试**。覆盖相机固定深度、不同初始站位、左右肩深度不同、重置及录制回放，也保留重叠计分与局部遮挡绘制检查。已实际渲染相机深度 1.5 米的六球双窗口，并检查“目标深度”显示。合成演示仍为 600 帧、16 命中、160 分。

多球绘制已将整幅图的重复复制、混合和深度遮挡计算改为球附近的局部区域。640×480 合成 RGB-D、预热 3 帧后测量 20 帧，6 球主界面平均绘制耗时由约 140 ms 降至 6.6 ms；24 组优化前后画面逐像素一致，覆盖无畸变／Brown-Conrady、2／6／8 球、前景遮挡、无效深度及画面边缘。记录在本机 `tmp/target-render-benchmark-20261102.json`；这是绘制耗时，非相机实际帧率。相机采集设置保持 Astra 640×480／30 fps、Gemini 2 优先 640×480／30 fps。

Astra 已有实机读帧记录。本次相机固定深度布局使用合成骨架验证，真人触碰体验仍需连接摄像头复测。Gemini 2 实机读帧、设备切换、静止丢手改善程度、出厂配准精度、独立接口曝光同步、真实三维定位精度和端到端延迟未独立验收。

旧方案、审查结论及历次设备状态统一保存在 [历史档案](archive/HISTORY.md)，不再逐阶段维护独立说明文件。模型、原始人像、SDK 安装包和本地输出继续由 `.gitignore` 排除，第三方来源见 [依赖说明](THIRD_PARTY.md)。
