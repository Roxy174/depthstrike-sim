# 开发与测试

当前实现是单人、固定相机、正面上半身的三维目标击打原型。采集、交互规则、显示及离线实验均使用 Python；完整虚拟对手、格挡、闪避和独立 exe 发行尚未实现。

## 模块

处理流程：RGB-D 采集与对齐 → 姿态关键点 → 实测深度反投影 → 滤波与拳部代理 → 出拳状态与连续碰撞 → 显示／录制。

| 模块 | 职责 |
| --- | --- |
| `capture.py` / `astra_capture.py` / `openni_capture.py` / `opencv_capture.py` | 各采集后端与标定 |
| `pose.py` / `fusion.py` / `tracking.py` | MediaPipe、人体掩膜、深度融合及轨迹处理 |
| `calibration.py` / `interaction.py` | 个体化校准与手部交互代理 |
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
- 正式目标由舒适触达校准生成并固定。命中需满足活动手、有效出拳和连续三维接触，同次攻击仅结算一次，收拳后才能再次触发。
- 缺失、暂停、倒退时间或超过允许间隔的轨迹不桥接计分。恢复后必须重新满足出拳准备条件。

骨架 JSONL v2 保存原始关节、配置、无效原因、操作和事件；回放重新计算结果。v1 缺少新配置时采用 legacy 语义。RGB-D 记录另保存图像、深度、完整标定与上游来源；回放重新执行模型。读取检查路径、数组类型、尺寸及实际字节数，不使用 pickle。

## 配置

JSON 可只覆盖需要的字段；完整字段、默认值和校验见 [config.py](../src/depthstrike/config.py)。

| 配置 | 用途 |
| --- | --- |
| [default.json](../configs/default.json) | 完整双侧观测的 guided 流程 |
| [adaptive.json](../configs/adaptive.json) | 掩膜融合、One Euro、逐侧校准、目标预览和跳变抑制，推荐用于本机 Astra |
| [legacy.json](../configs/legacy.json) | 原手腕代理、固定目标及旧记录兼容 |

adaptive 的主要规则：

| 项目 | 行为 |
| --- | --- |
| 掩膜与深度 | 检查 5×5 局部人体支持、有效比例和表面一致性；孤立掩膜像素不压低姿态置信度。中心空洞需近期同名直接观测，恢复点不作为下一次空洞恢复的锚点 |
| 跳变抑制 | 滤波前比较近期接受的原始观测；允许位移为 `tracking_outlier_slack_m + speed × dt`。默认余量 0.08 m，躯干参数 2 m/s、手臂 10 m/s；异常点不更新锚点，锚点过期后允许重新获取 |
| 短暂恢复 | `calibration_grace_s=0.20` 保留当前采样进度，仅累计连续有效观测时间；默认配置宽限为零。暂停、持续缺失或明显移位仍重置当前采样段 |
| 显示预测 | 最多 0.20 s，随时间衰减；可维持校准预览位置。灰色预测点和预览目标不参与命中 |
| 手部代理 | 优先腕、食指、小指的有效表面观测，缺失时回退肘腕代理；来源变化取消攻击并要求重新收拳 |
| 路径与遮挡 | 校准检查目标路径的粗略深度支持；显示按深度遮挡虚拟球，无效深度保守隐藏 |

这些阈值是工程参数，仍需真人数据校准。系统未实现多人身份重识别或完整人体可达空间建模。

## 自动化测试

先按 [运行说明](RUNNING.md#环境) 设置 `$py`。使用新的仓库内临时目录，避免覆盖资料或受系统 Temp 权限影响：

```powershell
$testTemp = Join-Path (Get-Location) ("tmp/pytest-" + [guid]::NewGuid().ToString("N"))
& $py -m pytest -q -p no:cacheprovider --basetemp $testTemp
```

真实窗口测试需要桌面会话，运行前设置 `$env:DEPTHSTRIKE_GUI_TESTS = '1'`，结束后用 `Remove-Item Env:DEPTHSTRIKE_GUI_TESTS` 清除。未安装可选依赖或未下载模型时，相关测试可能跳过，跳过不计为通过。

固定合成入口可用于冒烟检查：默认 guided 为 600 帧、9 命中、90 分；legacy 为 240 帧、6 命中、60 分；动作工坊示例为九靶、六命中。合成结果验证软件规则。

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

作者录制需包含完整 guided 流程，仅从正式回合中有效出拳并完成收回的动作提取关卡；中断动作被舍弃。靶位按作者肩宽和舒适前伸量归一化，挑战者完成校准后映射一次并固定。当前限 32 靶、120 秒，不支持同时出拳。

复盘区分命中、空间未命中、无有效攻击、观测不足和未完成。局部修正只对满足观测与攻击条件的空间未命中生成，检查深度、触达范围及修正后的连续接触；紫色线段表示局部几何平移。

## 当前验证状态

最近一次完整回归为 **2026-10-31，362 项通过，含真实窗口测试**。抖动专项覆盖异常跳变拒绝、目标预览稳定、正常快速出拳、短暂缺失恢复及禁止跨缺口计分。

Astra 驱动与 RGB-D 读帧已有实机记录；最近一次追踪复测未发现在线的 Astra 深度设备，因此真人抖动改善和连续校准效果仍待重连后验证。出厂配准精度、独立接口曝光同步、真实三维定位精度和端到端延迟也未独立验收。

旧方案、审查结论及历次设备状态统一保存在 [历史档案](archive/HISTORY.md)，不再逐阶段维护独立说明文件。模型、原始人像、SDK 安装包和本地输出继续由 `.gitignore` 排除，第三方来源见 [依赖说明](THIRD_PARTY.md)。
