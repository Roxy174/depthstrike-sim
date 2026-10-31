# 历史文档归档

这里合并保存旧版设计、开发计划、相机检查及分阶段验证记录。原文按文件收录，点击条目展开；其中的旧路径、版本和待办仅代表记录当时的状态。

当前操作请阅读 [项目首页](../../README.md)、[运行说明](../RUNNING.md) 和 [开发与测试](../DEVELOPMENT.md)。

## 原始文档索引

- [PROJECT.md](#project-md)
- [docs/ADAPTIVE.md](#docs-adaptive-md)
- [docs/ADAPTIVE_VERIFICATION.md](#docs-adaptive-verification-md)
- [docs/ASTRA.md](#docs-astra-md)
- [docs/ASTRA_VERIFICATION_2026-10-31.md](#docs-astra-verification-2026-10-31-md)
- [docs/CAMERA_DIAGNOSIS_2026-10-30.md](#docs-camera-diagnosis-2026-10-30-md)
- [docs/CAMERA_SMOKE_2026-10-23.md](#docs-camera-smoke-2026-10-23-md)
- [docs/EVALUATION.md](#docs-evaluation-md)
- [docs/IMPLEMENTATION_NOTES.md](#docs-implementation-notes-md)
- [docs/MOTION_STUDIO.md](#docs-motion-studio-md)
- [docs/MOTION_STUDIO_VERIFICATION.md](#docs-motion-studio-verification-md)
- [docs/superpowers/plans/2026-10-20-boxing-target-prototype.md](#docs-superpowers-plans-2026-10-20-boxing-target-prototype-md)
- [docs/superpowers/plans/2026-10-21-offline-interaction-refinement.md](#docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md)
- [docs/superpowers/plans/2026-10-22-motion-studio-prototype.md](#docs-superpowers-plans-2026-10-22-motion-studio-prototype-md)
- [docs/superpowers/plans/2026-10-23-observation-aware-interaction.md](#docs-superpowers-plans-2026-10-23-observation-aware-interaction-md)
- [docs/superpowers/specs/2026-10-21-offline-interaction-refinement-design.md](#docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md)
- [docs/superpowers/specs/2026-10-22-motion-studio-prototype-design.md](#docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md)
- [docs/superpowers/specs/2026-10-23-observation-aware-interaction.md](#docs-superpowers-specs-2026-10-23-observation-aware-interaction-md)
- [docs/TRACKING_VERIFICATION_2026-10-31.md](#docs-tracking-verification-2026-10-31-md)
- [docs/VERIFICATION.md](#docs-verification-md)

<a id="project-md"></a>
## PROJECT.md

<details>
<summary>展开原始记录</summary>

<a id="project-md--depthstrike"></a>
# DepthStrike

<a id="project-md--an-rgb-d-skeleton-guided-combat-simulator"></a>
## An RGB-D Skeleton-Guided Combat Simulator

**中文名：基于 RGB-D 人体骨架追踪的三维体感格斗交互模拟器**

- 工作名称：**DepthStrike**，由 Depth（深度视觉）和 Strike（打击）组合而成。
- GitHub 仓库：[Roxy174/depthstrike-sim](https://github.com/Roxy174/depthstrike-sim)，可见性为 **Private**。
- 文档日期：2026-10-21。
- 本文保留整体设计；首版实现范围为阶段 A/B 的目标球场景。实际验证边界见 [验证记录](#docs-verification-md)，阶段 C 对练仍为后续设计。
- 当前交互迭代采用个体化引导、拳心代理、可解释空间反馈与离线对比；具体行为以 [流程优化设计](#docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md)、[运行说明](../RUNNING.md) 和 [实验协议](#docs-evaluation-md) 为准。原有固定目标模式作为 legacy 回放兼容保留。
- 命名说明：这是项目工作名，尚未核验商标或全网名称唯一性；不作为新算法名称使用。

<a id="project-md--1-项目概述"></a>
## 1. 项目概述

DepthStrike 使用 Orbbec Gemini 2 深度摄像头获取玩家的 RGB-D 数据，通过预训练人体姿态模型检测人体关键点，融合实测深度构建三维交互代理点，并在虚拟空间中完成击球、出拳、格挡和闪避判定。

项目首先开发一个纯 Python 三维交互模拟器，不依赖 Unity，不以高精度角色建模或复杂动画制作为前提。初期用球体、线段和胶囊体表示玩家、目标与对手，重点验证真实人体动作与虚拟三维空间的对应关系。

核心问题是：**如何在存在深度噪声、人体遮挡和快速运动的情况下，让三维动作稳定、可解释地影响模拟世界？**

<a id="project-md--11-已确定的方向"></a>
### 1.1 已确定的方向

| 项目 | 当前决定 |
| --- | --- |
| 硬件 | Orbbec Gemini 2 |
| 视觉路线 | 人体关键点检测＋RGB-D 深度融合，即此前讨论的方案二 |
| 首期形态 | Python 模拟器，不引入 Unity |
| 基础交互 | 判断人体交互部位是否接触空间中的虚拟小球 |
| 后续方向 | 三维体感格斗：出拳、格挡、闪避、简化虚拟对手 |
| 代码管理 | 私有 GitHub 仓库；本地根目录为 `D:\3D视觉` |

<a id="project-md--12-本文采用的建议默认值"></a>
### 1.2 本文采用的建议默认值

以下是便于控制工作量的设计建议，而非用户已确认的全部细节：单人、固定相机、室内场景、上半身为主、对战脚本控制的虚拟对手；先支持左右直拳、一种格挡和一种闪避。开发平台优先考虑 Windows x64，实际依赖版本在设备验证阶段确定。

<a id="project-md--2-目标边界与项目定位"></a>
## 2. 目标、边界与项目定位

<a id="project-md--21-项目目标"></a>
### 2.1 项目目标

1. 稳定获取时间对应的彩色和深度帧，并完成深度到彩色图像的对齐。
2. 检测头部、肩、肘、腕等关键点，构建可用于交互的三维位置。
3. 实现与真实前后距离有关的碰撞判定，而非仅依据二维画面重叠。
4. 逐步形成出拳、命中、格挡、闪避、计分和回合结束的交互闭环。
5. 支持记录回放、参数配置和可复现的算法对比实验。

<a id="project-md--22-首期不包含"></a>
### 2.2 首期不包含

- Unity、VR 头显、联网对战及多人身份追踪。
- 任意转身、复杂踢腿、摔投和完整自由移动格斗。
- 从零训练人体姿态大模型或使用强化学习训练对手。
- 精确人体解剖骨架、真实打击力测量或医学、专业运动评估。
- 高精度人体网格、布料、肌肉或复杂刚体物理仿真。

<a id="project-md--23-课程项目贡献"></a>
### 2.3 课程项目贡献

本项目对应课程的“3D 数据＋3D 方法”：输入包括实测深度，方法包括深度融合、三维坐标变换、时序轨迹处理和三维几何碰撞。

定位为**应用与系统实现，并包含可验证的技术改进**，不声称发明了人体追踪或体感格斗。计划重点展示深度信息对误触发的影响、快速运动下的漏检处理，以及追踪稳定性与交互延迟之间的权衡。

<a id="project-md--3-功能范围与开发顺序"></a>
## 3. 功能范围与开发顺序

<a id="project-md--阶段-a三维击球验证"></a>
### 阶段 A：三维击球验证

- 实时显示 RGB 画面、二维人体骨架和关键点有效状态。
- 显示三维骨架代理、虚拟拳套及不同位置的目标球。
- 支持手与球接触后的变色、消失或计分反馈。
- 明确验证“二维重叠但深度不一致时不命中”。
- 支持重置、重新校准和退出。

<a id="project-md--阶段-b有效出拳判定"></a>
### 阶段 B：有效出拳判定

- 根据手相对肩部的运动和时序状态区分出拳、停留与收回。
- 每次出拳对同一目标最多结算一次；收回或完成复位后才允许新攻击。
- 加入跨帧轨迹检测，降低快速出拳穿过目标造成的漏判。
- 关键点低置信度、深度无效或追踪过期时，停止对应攻击判定。

<a id="project-md--阶段-c简化格斗对练"></a>
### 阶段 C：简化格斗对练

- 用球体、胶囊体构建虚拟对手的头部、躯干和手臂碰撞区域。
- 对手按预设状态和轨迹攻击，具有预备提示及攻击间隔。
- 支持左右直拳、一种格挡及一种闪避；区分命中、格挡和未命中。
- 支持血量、得分、回合计时、开始、暂停、结束和重新开始。
- 回合结束展示命中率、反应时间及轨迹回放等结果。

<a id="project-md--可选扩展"></a>
### 可选扩展

按价值与风险选择，不要求全部实现：不同深度的发光弱点、按体型调整目标位置、方向性格挡、简单连击、自适应难度及三维攻防复盘。真实手指姿态、踢腿和多人模式暂不列为核心验收项。

<a id="project-md--4-技术栈"></a>
## 4. 技术栈

| 组件 | 职责 | 说明 |
| --- | --- | --- |
| Python | 核心程序 | 当前验证环境为 Python 3.12.7；依赖固定于 pyproject.toml |
| Orbbec SDK / Python Wrapper | RGB-D 采集、对齐、内参读取与录制 | SDK 与 Gemini 2 固件需配套，不盲目升级固件 |
| MediaPipe Pose Landmarker | 预训练人体关键点检测 | 不直接把其身体局部三维坐标当相机绝对坐标 |
| NumPy | 坐标、轨迹和几何运算 | 核心碰撞逻辑不依赖显示窗口或相机 |
| OpenCV | 二维调试画面、状态文字 | 处理图像格式和显示 |
| Open3D | 三维骨架、目标和碰撞区域可视化 | 不自动提供格斗规则或物理系统 |
| pytest | 自动化测试 | 使用合成轨迹和离线记录测试 |

本表为组件职责；具体版本与测试证据见运行和验证文档。首期不要求 CUDA，也不承诺未知电脑上的实时性能。实际设备、固件与人体动作仍需独立联调。

<a id="project-md--5-总体流程与模块边界"></a>
## 5. 总体流程与模块边界

```text
Gemini 2：RGB＋Depth＋时间戳＋相机参数
                    ↓
             帧匹配与深度对齐
                    ↓
           RGB 人体关键点检测
                    ↓
      有效深度选择与相机坐标反投影
                    ↓
        置信度处理、轨迹平滑与速度估计
                    ↓
        碰撞检测＋出拳／攻防状态管理
                    ↓
       可视化、计分、日志、记录与回放
```

| 模块 | 输入 | 输出 |
| --- | --- | --- |
| `capture` | 相机或录制文件 | 匹配的 RGB-D 帧、时间戳、内参与深度单位 |
| `pose` | RGB 图像 | 二维关键点、可见性与存在置信度 |
| `fusion` | 关键点、对齐深度、内参 | 三维交互点、有效性和质量标记 |
| `tracking` | 带时间戳的交互点 | 平滑位置、速度及追踪状态 |
| `geometry` | 轨迹、球体与胶囊体 | 接触候选及几何信息 |
| `combat` | 接触候选和动作状态 | 命中、格挡、闪避、伤害与回合事件 |
| `visualization` | 当前场景和事件 | 二维、三维显示反馈 |
| `recording` / `evaluation` | 数据、事件和配置 | 回放记录、指标与实验结果 |

显示层不反向决定命中结果。算法和格斗规则应能在不连接摄像头、不打开窗口的情况下接受离线输入并运行测试。

<a id="project-md--6-三维追踪设计"></a>
## 6. 三维追踪设计

<a id="project-md--61-采集与时间一致性"></a>
### 6.1 采集与时间一致性

- 从 SDK 获取时间对应的 RGB-D 数据；不能随意拼接不同时刻的彩色与深度帧。
- 完成深度到彩色坐标的对齐后，用相应内参进行反投影。
- 将深度单位统一为米，并记录无效值定义。
- 若姿态推理异步执行，应按输入时间戳匹配原始帧；不得对旧关键点读取新深度。
- 推理跟不上采集时，采用有界队列或丢弃旧帧，避免延迟持续累积。

<a id="project-md--62-关键点与深度融合"></a>
### 6.2 关键点与深度融合

首期主要使用头部代表点、双肩、双肘、双腕及躯干参考点。姿态模型负责定位，实测深度用于估计这些部位在相机前方的位置。

对于与彩色图像对齐的有效深度，在正确处理畸变及相机模型后，可用针孔形式表示反投影：

```text
X = (u - cx) × Z / fx
Y = (v - cy) × Z / fy
```

其中 `(u, v)` 为图像像素位置，`Z` 为轴向深度，`fx, fy, cx, cy` 来自相应图像的相机参数。优先使用 SDK 提供的校准和坐标变换能力，不能用示意公式替代所有相机模型处理。

深度读取策略：结合关键点置信度、邻域有效深度、深度连续性和人体区域约束过滤异常。邻域中值只能缓解部分噪声，不能保证消除背景误读。关节点被遮住时，不强行把背景深度补成有效位置。

**限制：深度读到的是可见表面，不是人体内部关节中心。**首期将其定义为用于交互的代理点，配合虚拟拳套半径与校准容差；不宣称得到高精度解剖骨架。

<a id="project-md--63-坐标约定与校准"></a>
### 6.3 坐标约定与校准

- 核心计算统一采用相机坐标：X 向右、Y 向下、Z 向前，单位为米。
- 可视化坐标转换独立处理；碰撞双方必须使用同一坐标约定。
- 镜像仅用于显示，避免把镜像后的像素直接用于原始深度查询。
- 开局采集稳定站姿，确认有效活动范围、肩部参考位置和玩家大致可达空间。
- guided 模式依次测量双手舒适前伸范围，按 0.85 比例生成目标；以腕点沿前臂延长 0.06 m 形成拳部代理。试击不计正式得分，倒计时后开始回合；双肩、双肘、双腕和拳部代理须有效，断轨暂停计时并要求收拳。
- 目标生成后保留在场景坐标中，不能每帧跟随当前身体原点移动。
- MediaPipe 的人体 `WorldLandmarks` 以髋部中点为原点，不能直接用来表示相机空间中的绝对位置。

<a id="project-md--64-时序稳定性"></a>
### 6.4 时序稳定性

先实现可开关的简单平滑基线，再决定是否加入更复杂滤波。使用真实时间间隔计算速度；禁止对丢帧后的时间间隔作固定帧率假设。恢复追踪时重置速度和攻击状态，不把长时间断开的两个位置连接成一次攻击。

<a id="project-md--7-碰撞与格斗规则"></a>
## 7. 碰撞与格斗规则

<a id="project-md--71-基础接触"></a>
### 7.1 基础接触

手部用虚拟球体表示；目标也可用球体表示。当球心距离不大于两者半径之和时，产生接触候选。身体与手臂可逐步扩展为球体和胶囊体，不要求精确人体网格。

<a id="project-md--72-快速运动与连续检测"></a>
### 7.2 快速运动与连续检测

使用上一有效帧到当前帧的手部轨迹检查经过的区域，而非只检查帧末位置。移动目标应考虑双方的相对运动；首版可采用分段线性轨迹，球体使用相对线段距离检测，复杂形状再引入合理子步进。

初始重叠、轨迹相切、静止、零长度线段和追踪间断需要分别处理并编写测试。

<a id="project-md--73-攻击状态"></a>
### 7.3 攻击状态

建议采用 `READY → ATTACKING → RECOVERING → READY` 的显式状态。阈值由配置管理，结合运动方向、相对肩部位置、速度和时序判断；先限制为左右直拳，不声称识别任意格斗动作。

- 接触只是攻击结算条件之一，手停在目标内不能持续扣血。
- 同一攻击编号对同一目标最多结算一次。
- 追踪无效时取消当前攻击，并要求有效复位后重新激活。
- 游戏伤害是人为设计的数值，不等同于真实力量。

<a id="project-md--74-防守与对手"></a>
### 7.4 防守与对手

格挡依赖有效的前臂防御区域、来袭方向和时间窗口；闪避由攻击轨迹未接触头部或躯干代理区域判定，不能仅因检测到下蹲就自动判定成功。

同一次来袭先检查是否被有效格挡；否则检查是否击中身体，两者均否才记录未命中。对手先使用有预备提示的脚本状态机，不要求学习型 AI。具体碰撞区域、动作阈值及攻击节奏属于实现者在配置中调整并通过测试记录的参数。

<a id="project-md--8-记录回放与测试数据"></a>
## 8. 记录、回放与测试数据

必须区分两种回放能力：

1. **三维轨迹回放**：保存带时间戳的位置、有效标记、配置和事件，用于重现碰撞及游戏逻辑；不能用它验证原始深度融合质量。
2. **RGB-D 回放**：保存短时匹配图像、深度、相机参数和时间信息，用于重新运行姿态检测、深度融合与滤波。

计划提交小型合成轨迹作为无硬件测试数据；另保留至少一段经参与者同意的短时 RGB-D 测试录制或明确的获取方式，供完整链路复现。原始人像和大体积录制默认不提交普通 Git 历史。

建议元信息采用 JSON，事件与轨迹使用 JSONL，数组采用不包含 Python 对象的 NumPy 数据或 SDK 官方录制格式。元信息包含格式版本、帧编号、时间戳及其单位、坐标约定、内参、深度单位、模型和程序版本。具体编码在 M0 根据可用 SDK 决定并固化；避免依赖不安全的任意对象反序列化。

<a id="project-md--9-建议仓库结构"></a>
## 9. 建议仓库结构

首版采用平面模块以保持接口清晰；完整对战与评估模块随后扩展：

```text
depthstrike-sim/
├── README.md                 # 项目简介、安装、运行、演示与状态
├── PROJECT.md                # 本设计文档
├── pyproject.toml            # 包信息与依赖定义，版本验证后填写
├── .gitignore
├── configs/                  # 可提交的默认配置，不包含密钥
├── src/depthstrike/
│   ├── capture.py / pose.py / fusion.py
│   ├── tracking.py / geometry.py / boxing.py
│   ├── sources.py / recording.py
│   └── visualization.py / app.py / cli.py
├── tests/
│   └── fixtures/             # 小型合成轨迹和预期结果
├── data/
│   ├── samples/              # 小型、授权且可分发的测试数据
│   └── raw/                  # 原始采集，默认忽略
├── models/                   # 权重下载说明；模型文件默认忽略
├── recordings/               # 本地录制，默认忽略
├── outputs/                  # 日志、视频、统计结果，默认忽略
└── docs/                     # 安装说明、实验、报告与分工记录
```

统一入口为 `python -m depthstrike`；相机、合成输入和两类回放通过 `--source` 区分。具体命令见 [RUNNING.md](../RUNNING.md)。独立可执行程序的打包发行不在首版范围。

<a id="project-md--10-里程碑与验收"></a>
## 10. 里程碑与验收

| 里程碑 | 工作内容 | 完成证据 |
| --- | --- | --- |
| M0 环境与设备 | 核实固件、SDK、Python、电脑配置、帧格式与对齐能力 | 可重复的 RGB-D 采集和短时录制回放；环境记录 |
| M1 人体追踪 | 二维关键点、置信度显示和输入时间匹配 | 单人追踪演示、丢失处理、实际延迟与帧率记录 |
| M2 三维击球 | 深度融合、校准、静态球及计分 | 不同深度的命中与不命中案例；合成几何测试 |
| M3 稳定攻击 | 轨迹处理、跨帧碰撞、攻击复位 | 快速运动、停留不连扣、追踪恢复等测试 |
| M4 格斗对练 | 简化对手、格挡、闪避和回合 | 可完整进行并重新开始一场对练；规则测试 |
| M5 交付与实验 | 对比实验、打包、说明与报告 | 无硬件回放入口、源码、可执行版本、测试数据及演示 |

不预设尚未确认的日历截止日期。M0 完成后，根据实测性能与课程截止日期估算各阶段时间；资源不足时优先缩减美术、对手复杂度和可选扩展。

<a id="project-md--101-最低交付验收清单"></a>
### 10.1 最低交付验收清单

- [ ] 可读取 Gemini 2 的 RGB-D 输入并验证对齐。
- [ ] 可显示三维交互代理及其有效状态。
- [ ] 二维重叠但深度明显不一致时不会命中。
- [ ] 有效出拳可命中，停留和收回不会造成错误连续扣血。
- [ ] 快速运动和追踪丢失有明确处理。
- [ ] 至少实现一种格挡和一种闪避，并能完成一轮对练。
- [ ] 存在无需摄像头的轨迹回放及几何测试入口。
- [ ] 完整视觉链路有短时 RGB-D 回放数据或清晰可执行的获取说明。
- [ ] 有环境、运行说明、参数与版本记录，文档区分已实现和计划功能。

<a id="project-md--11-实验与评价"></a>
## 11. 实验与评价

<a id="project-md--111-建议对比"></a>
### 11.1 建议对比

| 实验 | 基线与改进 | 主要观察 |
| --- | --- | --- |
| 深度价值 | 二维重叠判定 vs 三维距离判定 | 前后错位时的误触发率 |
| 轨迹连续性 | 逐帧位置检测 vs 跨帧轨迹检测 | 快速运动漏检率 |
| 稳定性与响应 | 不平滑 vs 可配置平滑 | 静止抖动与新增延迟 |
| 攻击规则 | 接触即结算 vs 出拳状态管理 | 重复计分与非攻击误触发 |

<a id="project-md--112-测试原则与指标"></a>
### 11.2 测试原则与指标

- 合成轨迹提供解析可知的命中真值，覆盖相切、初始重叠、快速跨越及无效数据，作为几何正确性依据。
- 真实交互覆盖左右手、不同深度、不同速度、停留和遮挡；记录参与者、重复次数、配置与失败案例。
- 真实命中标签不能来自被测算法自己的输出。可用已测量位置的实物参照及独立观察辅助标注；边界模糊的事件单独列出，不伪装成精确真值。
- 统计误触发、漏检、每次攻击重复结算次数和追踪无效率；准确率需同时给出样本数与标签定义。
- 记录处理帧率及延迟分布；以同一时钟测量软件链路各阶段，不能把未同步的设备时间戳直接与系统时间相减。
- 静止抖动只是稳定性指标，不等于绝对定位精度；没有独立三维真值时不报告毫米级骨架精度。
- 性能目标在 M0 根据电脑配置确定并冻结；当前不把目标帧率或延迟写成已达到的性能。
- 比较方法使用相同录制与划分，调参样例与最终评价样例分开，并保留负面结果。

<a id="project-md--12-私有-github-仓库管理"></a>
## 12. 私有 GitHub 仓库管理

<a id="project-md--121-当前仓库与后续管理"></a>
### 12.1 当前仓库与后续管理

1. 远端仓库为 `Roxy174/depthstrike-sim`，可见性为 **Private**，描述为：`RGB-D skeleton-guided 3D combat interaction simulator using Orbbec Gemini 2.`
2. 按用户决定，直接以 `D:\3D视觉` 为本地仓库根目录，不另建项目子目录。课程材料继续保留在原位置，由根目录 `.gitignore` 明确排除 `Shares/`、`$dst/` 等目录。
3. `main` 为主分支；首版在 `feature/boxing-target-prototype` 本地分支开发。普通历史纳入代码、配置、说明和合成测试，不上传课程资料、模型权重或原始采集数据。
4. 本文作为仓库的 `PROJECT.md`，README 保持简明；安装、运行和测试数据入口集中于 `docs/RUNNING.md`，验证边界单独维护。
5. 按需邀请组员；私有权限不替代数据授权，也不应提交密码、令牌或个人敏感信息。

创建方式参考 [GitHub 官方文档](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。仓库初始化不代表模拟器已完成；后续功能以实际代码、测试与演示记录为准。

<a id="project-md--122-文件管理"></a>
### 12.2 文件管理

普通 Git 历史保存源码、小型配置、文档、测试夹具和下载说明。模型权重、SDK 安装包、长视频及原始 RGB-D 默认不加入普通历史；需要分发的大文件另行规划，Git LFS 和 Releases 均需结合授权与存储限制选择。GitHub 普通 Git 仓库会阻止大于 100 MiB 的单个文件，参见 [官方大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。

根目录已提供 `.gitignore`，其中包含课程资料忽略规则；以下列出后续项目数据管理的主要规则：

```gitignore
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
*.egg-info/
build/
dist/
.env
.env.*
!.env.example
models/*
!models/README.md
data/raw/
recordings/
outputs/
.cache/
```

不要用 `*.jsonl`、`*.npz` 等全局规则误排除必要测试数据。提交前检查待提交列表，尤其避免把课程 PDF、原始人像、权重和临时文件一起加入。第三方代码、模型和素材需记录来源、版本及使用条件，私有仓库并不免除这些要求。

<a id="project-md--123-协作方式"></a>
### 12.3 协作方式

- `main` 保持可运行；每个功能使用短期分支，如 `feature/rgbd-capture`、`feature/target-collision`。
- 用 Issue 对应里程碑和验收条件；通过小规模 Pull Request 合并，记录测试和演示证据。
- 提交信息说明实际改动，例如 `feat: add depth-aware target collision`，不要把计划写成完成记录。
- 模块接口、坐标约定、配置变更和数据格式变更应同步更新文档。
- 在里程碑可复现后打标签；最终报告的团队分工应与实际提交和工作记录一致。

<a id="project-md--13-风险与处理"></a>
## 13. 风险与处理

| 风险 | 处理策略 |
| --- | --- |
| 固件或 SDK 不兼容 | M0 记录并验证版本；已有可用环境不盲目升级 |
| 深度空洞与背景误读 | 置信度、邻域与连续性过滤；无法确认时标为无效 |
| 双臂交叉或出拳遮挡 | 首期限制单人正面上半身；追踪丢失时取消攻击 |
| 平滑过强造成迟钝 | 同时记录抖动与延迟，可切换基线参数 |
| 快速出拳漏判 | 跨帧轨迹检测；处理时间间隔和断轨 |
| 窗口或推理阻塞 | 有界数据传递；显示更新遵守图形库线程要求 |
| 项目变成只有美术的游戏 | 优先完成可测试的视觉、几何和攻防模块 |
| 实际空间或动作范围不足 | 校准舒适可达范围，目标不要求击打实物或靠近设备 |
| 数据或大文件进入历史 | 根目录明确忽略课程材料与原始数据，提交前检查 |

<a id="project-md--14-最终交付与分工"></a>
## 14. 最终交付与分工

按此前读取的课程项目要求，计划交付：源代码、可执行程序与测试数据、最终报告，以及可选演示视频或实验补充材料。课程文件中的截止日期未明确，本文件不另行假定日期。

报告应包含功能演示、实现方法与代码分析、实验、局限及实际团队分工。可执行程序的打包与 SDK 本地依赖需要在目标电脑上验证，不能只以开发环境运行成功作为完成标准。

可按四个工作包分工，人数较少时合并：设备采集与回放；人体追踪与深度融合；几何碰撞与格斗规则；可视化、测试与文档。实验与接口联调由团队共同负责，不预填成员姓名或虚构贡献。

<a id="project-md--15-开发前需要核实的信息"></a>
## 15. 开发前需要核实的信息

- Gemini 2 当前固件、已有 Viewer／SDK 是否正常、可用流配置。
- 电脑操作系统、CPU、内存和显卡；以 M0 实测决定模型与显示配置。
- 组员人数、课程实际截止日期和可用于联调的时间。
- 测试录制参与者的授权及数据分发范围。

以上是阶段性核实项，不影响先建立设计文档和私有代码仓库。实现者可在本文范围内决定窗口布局、配置格式、几何参数和内部实现细节；如引入 Unity、商业骨架 SDK、多用户或大幅扩展玩法，应先更新范围并与团队确认。

<a id="project-md--16-技术参考"></a>
## 16. 技术参考

- [Orbbec SDK v2：设备支持、固件与环境说明](https://github.com/orbbec/OrbbecSDK_v2)
- [Orbbec Python Wrapper：采集、对齐与相机参数](https://github.com/orbbec/pyorbbecsdk/blob/v2-main/README.md)
- [MediaPipe Pose Landmarker：Python 使用与坐标定义](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Open3D：三维可视化](https://www.open3d.org/docs/release/tutorial/visualization/visualization.html)
- [GitHub：创建仓库](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [GitHub：大文件限制与管理](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

后续实现应继续记录所用模型、依赖和素材的准确版本、来源及适用许可。本文中的技术路线与验收标准是项目计划，不是已取得的实验结论。

</details>

<a id="docs-adaptive-md"></a>
## docs/ADAPTIVE.md

<details>
<summary>展开原始记录</summary>

<a id="docs-adaptive-md--可观测性驱动的交互扩展"></a>
# 可观测性驱动的交互扩展

Python 本地扩展，仍使用既有依赖。真人、空间精度与真实遮挡效果尚未验收；以下报告只验证合成输入下的软件行为。

<a id="docs-adaptive-md--启动"></a>
## 启动

在 `D:\3D视觉` 的 PowerShell 中运行：

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/adaptive.json --view dual
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/adaptive.json --headless --frames 600
```

演示自动完成校准和击球，不使用相机。合成输入没有 RGB-D 场景，因此不进行真实障碍检查，也不显示真实深度遮挡。

恢复真人测试后，体验入口可显式使用同一配置：

```powershell
.venv\Scripts\python.exe -m depthstrike --source opencv-camera --config configs/adaptive.json
```

OpenCV 后端仍是主机时间、型号默认内参和未验证 RGB-D 同步；不能用体验入口证明空间精度。默认配置继续使用完整双侧观测协议，`adaptive.json` 才启用局部交互。

<a id="docs-adaptive-md--技术行为"></a>
## 技术行为

| 组件 | 实现与边界 |
| --- | --- |
| 掩膜深度融合 | 5×5 局部窗口，检查足量的人体掩膜支持、深度有效比例与表面离散度；孤立的低掩膜像素不再直接压低姿态置信度。中心深度必须与局部人体表面一致；中心空洞额外要求同名的近期直接观测。恢复点不能继续充当下一次空洞恢复的历史锚点。人体掩膜不区分不同身体部位，因此仍可能存在同深度表面歧义。 |
| 手部交互点 | 优先使用腕、食指、小指的有效观测，指点距腕不得超过 0.20 m；缺失时回退肘腕代理。来源改变取消当前攻击，需重新收拳。该点是表面交互代理。 |
| 滤波 | `exponential`、`one_euro`、`kalman` 可选。One Euro 根据速度改变截止频率；Kalman 使用位置—速度状态，按置信度和深度质量调节观测噪声。质量分数是工程权重，不是已标定概率。 |
| 跳变抑制 | 本配置启用 `reject_tracking_outliers`，在滤波前比较同名关节近期接受的原始观测。允许位移为 `tracking_outlier_slack_m + speed × dt`；默认余量 0.08 m，躯干速度参数 2 m/s，手臂速度参数 10 m/s。超出时返回无效点，不更新锚点；锚点超过 `max_track_gap_s` 后失效。参数是工程筛选条件，不是实测人体速度结论或人物身份识别。 |
| 显示预测 | 只在 adaptive 的局部追踪启用；本配置最多预测 0.20 s（默认配置仍为 0.12 s）。手臂速度上限 5 m/s，躯干不超过 `tracking_body_speed_m_s`，可信度随缺失时间下降。HUD 空心灰点、三维灰线与观测分开。校准预览可沿用此短期显示位置；没有新的有效点时不延长预测，不进入碰撞。 |
| 逐侧校准 | 初始收拳仍需双侧肩部和交互点；前伸、收回、试击分别检查当前侧。对侧肩部若仍可见，继续检查站位偏移。启用 `calibration_grace_s=0.20`：短暂丢点冻结采样进度，恢复相同姿势后继续；缺失与恢复首帧之间的时间不计入保持时长。超过宽限、明显移位、暂停或采集时间中断会重置当前采样段。已经完成的校准阶段保留，倒计时在丢点后重新开始。默认配置宽限为零。 |
| 局部击球 | 普通回合按活动手有效性计时和判定，另一侧缺失不清除当前侧攻击。活动手缺失后重现不能跨缺口计分。Motion Studio 挑战继续要求完整观测。 |
| 目标预览 | 校准期间根据肩部显示“预览”目标；不参与碰撞，正式目标仍需通过舒适触达校准。 |
| 深度遮挡 | 按相机射线与虚拟球体前表面求交，前方实测表面遮住虚拟球；无效深度保守不绘制该像素。只影响绘制，不改变计分几何。 |
| 路径检查 | 校准生成目标时，沿中立拳心到目标的路径按约 2 cm 步长采样中心与六个轴向偏移。初始手部占据体积被排除；遇到遮挡表面拒绝、超视野或缺深度返回未知。目标生成后固定，不在出拳途中移动。 |

路径检查仅使用当前视野的粗略采样，不是完整占据地图、连续体积碰撞证明或人身安全认证。桌面/墙面的语义识别、场景建图和自动重排目标不包含在此实现中。SDK 和 OpenCV 的几何证据限制随输入保留。

`Joint3D` 记录 `provenance`、`depth_quality`、`age_s`。旧 JSONL 缺少这些字段时按旧观测语义读取；新文件保留来源，标为 `predicted` 的输入在追踪边界被拒绝为物理观测。显示预测不写入原始骨架录制。

<a id="docs-adaptive-md--离线故障报告"></a>
## 离线故障报告

```powershell
.venv\Scripts\python.exe -m depthstrike.robustness --output outputs/adaptive-report.json --image outputs/adaptive-preview.png
```

文件已存在时拒绝覆盖，请换新名称。核心报告仅依赖 NumPy；PNG 需要 OpenCV，不打开窗口。

报告比较默认与扩展配置的 600 帧合成序列：正常、左腕遮挡、右肘遮挡、左右腕交换、时间倒退；另比较中心深度空洞恢复和不匹配历史深度的拒绝。命中数只是该输入下的实际结果，没有独立真值标签，不作为准确率；腕交换用来暴露失败边界，尚无身份重识别模型。

对三种滤波方案进行进一步实验时，创建新的 JSON 配置并设置 `filter_mode`。不要同时串联多个滤波器；比较相同输入下的抖动、响应滞后、有效覆盖和错误接触。真实肢体定位须使用图像级数据与独立参考。

<a id="docs-adaptive-md--姿态模型对比入口"></a>
## 姿态模型对比入口

仅在准备比较时显式下载，不在程序启动时联网：

```powershell
.venv\Scripts\python.exe scripts/download_pose_model.py --variant full
.venv\Scripts\python.exe scripts/download_pose_model.py --variant heavy
```

默认仍为 lite。脚本使用 Google 官方版本 1 端点，保留 SHA256、变体与 URL，已有模型或 sidecar 不覆盖。在新的 JSON 配置中设置：

```json
{
  "model_path": "models/pose_landmarker_full.task",
  "fusion_mode": "masked",
  "fist_mode": "hand",
  "filter_mode": "one_euro",
  "partial_tracking": true,
  "preview_targets": true
}
```

模型选择接口已测试，本轮没有下载 Full/Heavy 或比较真实推理性能。RTMPose、CoTracker3、学习式三维补全与骨架逆运动学仍属后续备选，未作为依赖接入。

</details>

<a id="docs-adaptive-verification-md"></a>
## docs/ADAPTIVE_VERIFICATION.md

<details>
<summary>展开原始记录</summary>

<a id="docs-adaptive-verification-md--扩展验证记录--2026-10-23"></a>
# 扩展验证记录 · 2026-10-23

环境：项目 `.venv`，Windows / Python 3.12。根目录本地工作树改动；本轮未运行摄像头、下载模型或推送远程。

<a id="docs-adaptive-verification-md--软件验证"></a>
## 软件验证

- 新增 `tests/test_adaptive.py`：深度空洞恢复、背景拒绝、来源往返、有限显示预测、One Euro、Kalman 质量加权、缺键失踪、单侧校准、局部击球、恢复禁止跨帧命中、工作空间拒绝、深度遮挡、预览、模型选择、正式回合故障注入，以及动作作者/评估一致性。
- 各批新增用例在实现前运行失败，再实现运行通过。
- 首次完整显示验证：`DEPTHSTRIKE_GUI_TESTS=1`，298 passed，21.86 s。
- 独立审查发现3项 Important，已用回归用例复现并修复；修复阶段完整验证302 passed，24.52 s。补充作者代理来源切换回归后，最终结果附后。
- 最终完整验证：`DEPTHSTRIKE_GUI_TESTS=1`，`pytest -q --basetemp=tmp/pytest-adaptive-verified --tb=short` → **303 passed in 23.03 s**，0 skipped。
- `compileall` 和 `pip check` 通过；`git diff --check` 无空白错误，仅提示已有文件的 LF/CRLF 转换。

<a id="docs-adaptive-verification-md--独立审查"></a>
## 独立审查

只读审查 `/root/adaptive_review` 针对修复前快照，没有启动相机。三项发现：

1. partial_tracking 下作者会跨失踪片段完成 pending 动作。修复为完整观测检查，并在交互点来源变化时取消待完成动作。
2. evaluation 固定使用肘腕代理，忽略 hand 配置。修复为与实时模拟共享 `estimate_hand`，来源切换中断接触历史，输入指纹包括来源与质量字段。
3. Kalman 未清除空关节字典中的历史，会制造虚假恢复运动。修复为缺键与显式无效相同处理，显示预测仍与观测独立。

未发现 Critical/Minor。最终修复由回归及全仓测试核验，没有第二轮审查。实机准确率、不同身体部位身份、模型性能、同步和连续空间覆盖不在这份合成证据中作结论。

<a id="docs-adaptive-verification-md--可重复演示"></a>
## 可重复演示

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/adaptive.json --headless --frames 600
.venv\Scripts\python.exe -m depthstrike.robustness --output outputs/my-adaptive-report.json --image outputs/my-adaptive-preview.png
```

第一条实测600帧、9次正式命中、90分、0采集超时。第二条需要新输出路径；本轮输出见 `outputs/adaptive-20261023-final/`（本地忽略文件，不进 Git）。

正式回合11–12秒注入故障，默认/扩展均使用600帧。正常均9次命中；非活动右肘丢失时默认7次、扩展9次；活动左腕丢失时均7次。扩展显示3帧短时预测，没有把预测作为观测补记得分。左右腕交换仍是已知失败边界，未接身份恢复模型。

局部深度合成探针30次：默认中心空洞恢复0次，掩膜+匹配历史恢复30次；与历史深度不一致时两种策略均拒绝30次。输入为手工构造的一致表面，不是人体定位准确率。

<a id="docs-adaptive-verification-md--本轮边界"></a>
## 本轮边界

路径检查只拒绝不可用布局，不自动重新排靶、不建完整房间地图；粗采样不能证明整个体积无障碍。Full/Heavy 仅提供显式下载选择，RTMPose/CoTracker3/IK 尚未集成。真人追踪效果继续等待后续实测。

</details>

<a id="docs-astra-md"></a>
## docs/ASTRA.md

<details>
<summary>展开原始记录</summary>

<a id="docs-astra-md--旧款-astra-接入"></a>
# 旧款 Astra 接入

本入口支持本机实测的 Astra：OpenNI 深度接口 USB `2bc5:060f`，独立 UVC 彩色接口 `2bc5:050f`。其他 Astra 型号的协议和固件可能不同，不根据产品系列名称自动选用此适配器。

本次设备与运行证据见 [2026-10-31 验证记录](#docs-astra-verification-2026-10-31-md)。

<a id="docs-astra-md--运行"></a>
## 运行

本机已建立 Python 3.12 的 `depthstrike` 环境，安装官方深度驱动、OpenNI 运行库和姿态模型。在项目根目录的 PowerShell 中执行：

```powershell
& "$env:USERPROFILE\.conda\envs\depthstrike\python.exe" -m depthstrike --source astra-camera --config configs/adaptive.json
```

增加 `--view dual` 显示三维辅助窗口。`空格` 暂停/继续，`R` 重新校准，`Q` / `Esc` 退出；关闭窗口会释放两个采集接口。窗口标题为“深度拳击｜体感交互”，来源提示为“奥比中光相机体验｜主机计时｜出厂深度对齐”。

调整取景，使双肩、双肘、双腕在画面内，按引导完成收拳、左右舒适前伸、收回、试击和倒计时。追踪条件不足时保留校准提示。所有关节置信度、深度质量和攻击阈值沿用现有配置。

当前 `adaptive.json` 已启用瞬时位置跳变抑制和 0.20 秒的校准恢复宽限。出现“追踪恢复中”时保持当前姿势，短暂丢点期间的进度会保留，重新观测到稳定姿势后继续。校准预览可短暂沿用显示预测，减少目标闪失；预测点不参与计分。

修改程序后先退出旧窗口，再按上述命令启动并按 `R` 重新校准。若启动提示找到 0 个深度设备，先检查 USB 和供电是否接好，并在设备管理器确认 `ORBBEC Depth Sensor` 在线；需要先恢复采集才能验证真人追踪效果。

<a id="docs-astra-md--在其他电脑准备环境"></a>
## 在其他电脑准备环境

Python 3.12，Windows x64：

```powershell
python -m pip install -e ".[display,astra]"
python scripts/download_pose_model.py
```

安装适合设备的 [Orbbec 官方 Astra 驱动](https://www.orbbec.com/developers/openni-sdk/)。本机使用 4.3.0.22；安装后检查设备管理器中的 `ORBBEC Depth Sensor` 是否正常。安装器与内核驱动的签名不同：本次安装器无 Authenticode 签名，安装后的深度驱动由 Windows 报告为已签名。驱动安装由用户明确授权并通过交互安装器完成；应用启动不自动安装驱动或更改固件。

从同一官方页面下载 OpenNI SDK 2.3.0.86 beta6，解开外层及内层 ZIP，将 `Win64-Release/sdk/libs/` 的内容放入 `.cache/openni2/`，保留目录结构：

```text
.cache/openni2/
  OpenNI2.dll
  OpenNI2/Drivers/orbbec.dll
  OpenNI2/Drivers/orbbec.ini
  ...
```

也可通过 `--openni-dir PATH` 指定这些文件所在的目录。适配器的 C 结构布局按该版官方头文件绑定，启动时拒绝其他 SDK 版本。运行库与模型不纳入 Git 历史，分发前应核对原有许可。

<a id="docs-astra-md--数据与验证口径"></a>
## 数据与验证口径

- 深度使用 OpenNI `DEPTH_1_MM`，640×480、30 fps；读取前关闭深度镜像，开启深度到彩色配准并读回确认。每帧检查格式、裁剪、步长及缓冲区大小，拷贝后立即释放原生帧。
- 彩色使用 DirectShow，按 VID/PID 精确选择 Astra UVC 接口；多台匹配设备会报错。彩色为 640×480 BGR，转换为 RGB；深度毫米转换为米。错误尺寸会失败，不通过缩放深度图凑尺寸。
- 反投影及显示使用设备返回的彩色内参和五个 Brown–Conrady 畸变系数；出厂配准的实际空间精度尚未独立测量。
- 两个接口没有经过独立曝光同步验证。采样时间为两次主机读取完成时间的中点，只检查完成时间差不超过 `frame_sync_tolerance_s`；该限制不能证明曝光同步，也不是传感器到显示延迟。原生深度时间戳和帧号另行检查严格递增。
- 来源固定保留 `capture_backend=openni2_astra_uvc`、`evidence=unverified`。限制随 RGB-D/骨架转录和回放传递，画面继续显示体验模式提示。
- 默认不保存图像或人体轨迹。显式使用 `--record` / `--record-rgbd` 才录制；软件阶段统计可单独使用 `--metrics`。

这属于真实传感器输入下的体验入口。连续人体校准、真人命中计分、同步性能和定位准确率分别验收，不能用程序成功读帧替代这些结论。

</details>

<a id="docs-astra-verification-2026-10-31-md"></a>
## docs/ASTRA_VERIFICATION_2026-10-31.md

<details>
<summary>展开原始记录</summary>

<a id="docs-astra-verification-2026-10-31-md--astra-接入验证--2026-10-31"></a>
# Astra 接入验证 · 2026-10-31

环境：Windows x64，Python 3.12 的 `depthstrike` 独立环境。范围为旧款 Astra 的驱动、真实 RGB-D 输入及项目体验入口。

<a id="docs-astra-verification-2026-10-31-md--设备与驱动"></a>
## 设备与驱动

- 彩色接口 USB `2bc5:050f`，深度接口 `2bc5:060f`。安装前深度接口为驱动安装失败，项目原有 SDK v2 枚举为 0。
- 用户明确授权后，通过可见的交互安装器安装官网 Astra 4.3.0.22 驱动。安装后 Windows 显示 `ORBBEC Depth Sensor`、状态 OK、错误码 0、`oem56.inf`、Orbbec 4.3.0.22，`IsSigned=True`。
- OpenNI 2.3.0.86 beta6 枚举到一台 `Orbbec / Astra`。此型号没有 OpenNI 彩色传感器，因此组合其独立 UVC 彩色接口。

<a id="docs-astra-verification-2026-10-31-md--实际输入"></a>
## 实际输入

- 单独彩色检查：640×480、uint8 BGR，30/30 帧读取成功；二维模型检查 30 帧中 29 帧检测到人体，完整六个上肢关键点有效帧为 0。这是当时取景下的结果。
- 原生深度检查：640×480、30 fps、1 mm 单位，12 帧读入成功。深度有效像素比例约 31–34%；首帧原生时间戳为 0，随后递增，表示流内相对时钟，不能与主机时钟直接相减。
- 出厂彩色内参读取成功：fx/fy≈545.0596，cx≈324.5886，cy≈235.1736，保留五个畸变系数。OpenNI 报告支持深度到彩色配准，启用后读回值为 1。该结果不等于独立空间对齐精度验收。
- 正式 `--source astra-camera --config configs/adaptive.json` 无窗口链路：60 帧、0 次采集超时，0 分，软件会话 3.313 s。
- 真实主窗口检查：300 帧、0 次采集超时，软件会话 15.266 s。该段未检测到人体，阶段保持 `HOLD_GUARD`，0 分；不能据此声明真人校准、出拳或命中计分通过。

测试不保存相机图像、深度图或人体轨迹。临时软件指标仅记录采集/推理/模拟/绘制耗时、来源及出厂标定。

<a id="docs-astra-verification-2026-10-31-md--软件检查"></a>
## 软件检查

定向测试覆盖精确选取彩色接口、毫米与 BGR 转换、拒绝错误网格、主机读取时间差拒绝与恢复、原生内存步长及边界、缓冲区拷贝、关闭释放、出厂畸变保留、回放来源提示和命令行约束。新增断连异常用例验证驱动异常被转成可读错误，并释放两个接口。

完整回归：`python -m pytest -q --basetemp=tmp/pytest-astra-final-20261031 --tb=short` → **324 passed，3 skipped**。三项为未启用的真实窗口专项；本轮另进行了上述 300 帧真实 Astra 主窗口检查。`pip check`、相关文件 `compileall` 与 `git diff --check` 通过。

两流使用独立接口，主机读取完成时间差只作为交付数据的限制，不证明曝光同步。当前入口持续标注 `ASTRA EXPERIENCE` 和 `evidence=unverified`；真实定位精度、同步及真人击球另行验收。操作与安装见 [Astra 接入说明](#docs-astra-md)。

</details>

<a id="docs-camera-diagnosis-2026-10-30-md"></a>
## docs/CAMERA_DIAGNOSIS_2026-10-30.md

<details>
<summary>展开原始记录</summary>

<a id="docs-camera-diagnosis-2026-10-30-md--摄像头上半身不可见诊断--2026-10-30"></a>
# 摄像头上半身不可见诊断 · 2026-10-30

输入：Gemini 2，OpenCV 体验入口，`configs/adaptive.json`。用户报告正常真人画面，但没有骨架或手部点；用户退出原程序后进行了两段数值诊断。没有保存或上传 RGB、深度图或人体轨迹。

<a id="docs-camera-diagnosis-2026-10-30-md--原因与证据"></a>
## 原因与证据

扩展融合要求二维人体掩膜 `(H,W)`，实际 MediaPipe 输出的单通道 NumPy 视图为 `(480,640,1)`。原代码将它当作尺寸错误，返回 `missing_mask`，使本来有效的肩部三维点全部消失。HUD 仅显示融合成功的三维点，因此呈现为“没有检测到人体”。

修复前15.03秒：426帧、426帧有姿态、426帧掩膜网格检查失败。左肩378次、右肩405次被 `missing_mask` 拒绝；同帧使用保守深度融合时这些点有效。全幅深度有效比例中位数约81.45%，因此不是整张深度图失效。

另有取景问题：左/右肘归一化纵坐标中位数约1.348/1.267，左/右腕约1.701/1.587（有效图像范围 `[0,1)`）；肘腕的姿态置信度均低于阈值。肩部接近画面底部。修复掩膜后仍需相机向下取景或调整站位，不能将本次修复视为手臂追踪完成验收。

<a id="docs-camera-diagnosis-2026-10-30-md--最小修复"></a>
## 最小修复

`person_mask_2d` 只接受 `(H,W)` 与 `(H,W,1)`，仅移除末尾的单通道维度。不缩放掩膜，不放宽置信度或深度阈值，不接受多通道及错误空间尺寸。

姿态结果的掩膜采样、缓存和融合边界共用此归一化，消除 `float(array)` 的 NumPy 弃用警告。新增 `tests/test_mask_layout.py`，修复前2失败、4通过，修复后相关78项通过。

<a id="docs-camera-diagnosis-2026-10-30-md--实机复核"></a>
## 实机复核

修复后使用实际 `PoseEstimator.detect` 与 `CameraPoseSource.read` 路径复核10.02秒：

- 原始掩膜 `(480,640,1)`，缓存掩膜 `(480,640)`。
- 300帧，300帧姿态，双肩各300帧三维有效。
- 双肘、双腕仍各300帧 `low_confidence`；没有完整六点帧，未进入真人击球或计分验收。
- 两段相机均已关闭释放，没有调整设备注册表、模型或保护阈值。

完整软件回归：`DEPTHSTRIKE_GUI_TESTS=1`，`.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/pytest-mask-layout-full-20261030 --tb=short` → **309 passed in 42.10 s**，无跳过。`compileall` 与 `git diff --check` 通过。合入 main 前再次完整验证：**309 passed in 22.34 s**；提交与发布状态以 Git 历史为准。

</details>

<a id="docs-camera-smoke-2026-10-23-md"></a>
## docs/CAMERA_SMOKE_2026-10-23.md

<details>
<summary>展开原始记录</summary>

<a id="docs-camera-smoke-2026-10-23-md--gemini-2-实机接入检查"></a>
# Gemini 2 实机接入检查

日期：2026-10-23。当前分支 `codex/motion-challenge-prototype`。本次以实际连接设备检查采集适配，不保存或上传彩色／深度影像，也不录制骨架。设备注册与人体交互验收分开记录。

<a id="docs-camera-smoke-2026-10-23-md--已确认"></a>
## 已确认

- SDK 枚举到一台 Orbbec Gemini 2，固件 `1.4.87`，连接类型 `USB3.0`。未升级固件。
- 当前环境：Python 3.12、pyorbbecsdk2 2.1.2、MediaPipe 0.10.32、OpenCV 4.11.0.86；官方 pose lite 模型可加载。
- 普通受限执行环境打开设备曾返回拒绝访问；经允许在沙箱外运行后设备可打开。这不等同于 Windows 隐私开关被关闭，未修改隐私设置。
- 彩色原始流 640×480@30、深度原始流 1280×800@30；软件 D2C 后 RGB 和深度均为 640×480。一次样本非零深度比例约 99.27%，不是人体关节有效率或定位精度。

<a id="docs-camera-smoke-2026-10-23-md--k6-标定兼容修复"></a>
## K6 标定兼容修复

实际彩色标定模型为 `OBCameraDistortionModel.BROWN_CONRADY_K6`，原采集适配只接受 `BROWN_CONRADY`，导致首帧转换失败。用户已同意修复。

该型号按八系数有理模型归一为内部 `brown_conrady`，不丢弃 k4、k5、k6，也不按无畸变近似。依据为 [Orbbec 原生坐标变换实现](https://raw.githubusercontent.com/orbbec/OrbbecSDK_v2/main/src/shared/utils/CoordinateUtil.cpp)、[SDK 枚举定义](https://orbbec.github.io/pyorbbecsdk/source/6_API_Reference/data_structures.html) 和 [OpenCV 标定模型](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)。

在本机已安装 SDK 中，以同一彩色相机的恒等外参做原生 2D→2D 去畸变，再做 2D→3D；与现有 OpenCV 八系数反投影比较五个像素位置：中心、两个中间位置和两个近边缘位置。在假定深度 1 m 下，最大三维计算差约 `1.34e-6 m`。这仅是计算路径的一致性检查，不是实测绝对精度。

回归测试覆盖两种 K6 枚举拼写、系数顺序和独立手算有理投影的反投影；逆 Brown／鱼眼模型仍拒绝。修复前 2 failed／20 passed，修复后适配与融合专项通过。

<a id="docs-camera-smoke-2026-10-23-md--当前实机阻塞零设备时间戳"></a>
## 当前实机阻塞：零设备时间戳

兼容修复后运行原生 `CameraPoseSource` 约 12 s，仅接受首帧，后续 370 次被拒绝，未完成连续人体检测。单帧无人体结果不能用于评价检测模型。

进一步直接检查 24 组实际帧：帧序号递增，但 RGB、深度在对齐前后的设备毫秒／微秒时间戳均为 0。主机到达时间递增且两流存在约 85 ms 到达差，但它不是曝光时间，不能用来声称采集同步。

只读注册表检查发现当前连接相机各 UVC 接口缺少 `MetadataBufferSizeInKB0`。这与 [Orbbec 官方 Windows 元数据／时间戳说明](https://orbbec.github.io/pyorbbecsdk/source/7_FAQ/FAQ.html) 一致。程序现已对零设备时间戳给出注册 UVC 元数据的明确错误，不将 0／0 当作同步成功；该行为先由三个失败回归场景复现后修复。

用户已同意仅为当前连接设备运行官方元数据注册脚本。脚本需 Windows 管理员确认；启动或正常退出不能替代读回验证。注册项生效后还需重新插拔和重测，不改变固件、执行策略或隐私设置。

本次首次启动脚本后，读回仍见当前六个接口的元数据值缺失；带日志的管理员启动随后由 Windows 返回“操作已被用户取消”。因此停止重试，注册未通过验收，需用户在管理员终端完成后再测。

<a id="docs-camera-smoke-2026-10-23-md--软件验证"></a>
## 软件验证

`DEPTHSTRIKE_GUI_TESTS=1` 下完整测试为 **264 passed，13.09 s，无跳过**；`pip check` 无依赖冲突。新增七个场景保护 K6 适配、系数处理、其他模型拒绝及零设备时间戳拒绝。这不是硬件或真人验收结果。

<a id="docs-camera-smoke-2026-10-23-md--lab3-路线对照与-opencv-体验接入"></a>
## LAB3 路线对照与 OpenCV 体验接入

复查 LAB2／LAB3 后确认：LAB2 的 Gemini 验收为红外预览；LAB3 第 42 页明确要求用 OpenCV 替换 pyorbbecsdk，现有 `scanner.py` 使用 `CAP_OBSENSOR` 和同一次 `grab()` 后的两次 `retrieve()`，未验证设备时间戳。

本机按相同读法成功获得 30 组 640×480 RGB／深度，3 次初始缺帧，约 1.13 s，不保存影像。这证明该路径可读帧，不证明同曝光同步。

用户同意增加独立的 `--source opencv-camera` 体验入口，原 `--source camera` 保持严格检查、没有自动降级。前者明确标注主机时间、同步未经验证和近似几何；像素／米转换、数据有效性、资源释放及来源记录均保留。依据 [OpenCV 4.11 采集实现](https://raw.githubusercontent.com/opencv/opencv/4.11.0/modules/videoio/src/cap_obsensor_capture.cpp) 和 [Gemini 2 默认参数实现](https://raw.githubusercontent.com/opencv/opencv/4.11.0/modules/videoio/src/cap_obsensor/obsensor_uvc_stream_channel.cpp)，其默认内参不能声称是本机独立校准结果。

实际双窗口运行约 90 s，2664 帧，666 帧有姿态输出；没有一帧满足完整双肩／双肘／双腕三维有效条件，因此引导保持 HOLD_GUARD，正式命中 0、分数 0。随后约 20 s 的逐关节诊断读入 600 帧，其中 39 帧有姿态结果：双肩置信度中位数约 0.99，双肘约 0.22，双腕约 0.09–0.12，并出现肘／腕出画。用户确认当前空间暂时无法同时拍到全部六个上肢关节，停止真人校准和击球测试；不是已通过的游戏验收。

双窗口和后续诊断均已结束，摄像头、模型、显示资源已释放。未保存原始 RGB／深度、骨架轨迹或人像截图；仅保留汇总记录。

审查前完整软件测试为 274 passed；独立只读审查发现一项 Important：RGB-D 转骨架并再次录制后，限制仍保存在嵌套来源信息里，但体验模式画面提醒可能消失。已用三段转录／回放链路的失败测试复现，再修复为沿来源链识别 OpenCV 体验模式。

最终完整软件测试 **275 passed，10.34 s，无跳过**，包含体验入口的十一个新增场景；`pip check`、`compileall`、wheel 构建及隔离安装的核心演示检查通过。wheel SHA-256 为 `3312969edd19ff6c45eba0df92a3ab88f734190b4766d2313c5ad3f60046c483`。软件测试不替代真人验收。

独立审查未发现 Critical，另有 12 项定向测试通过；未复跑全套或访问设备。其未判断硬件同步、实际标定精度、曝光时间、端到端延迟和真人计分，主开发同意这些仍须独立证据。修复后未再请求第二次审查，以上最终全套由主开发执行。

另已定位前述官方脚本未执行的一项原因：Windows PowerShell 5.1 的本机策略为 AllSigned，会拒绝未签名脚本；未更改或绕过该策略，也未继续尝试注册表写入。

<a id="docs-camera-smoke-2026-10-23-md--验收边界"></a>
## 验收边界

OpenCV 体验路径的连续读帧与实际窗口已检查，但 RGB-D 设备同步、每台设备的完整标定、连续完整上肢三维骨架、引导校准、真人有效出拳和命中计分尚未验收。上述项目不得因软件测试或画面可显示而标为通过。未运行付费服务，未上传人体数据，未推送代码。

</details>

<a id="docs-evaluation-md"></a>
## docs/EVALUATION.md

<details>
<summary>展开原始记录</summary>

<a id="docs-evaluation-md--三维交互对比协议"></a>
# 三维交互对比协议

评估对象是三维轨迹到接触／攻击事件的规则，不是姿态模型或 RGB-D 定位精度。无真实输入时报告必须标注 synthetic，不从合成分数推断人体准确率。

<a id="docs-evaluation-md--1-入口"></a>
## 1. 入口

```powershell
.venv\Scripts\python.exe -m depthstrike.evaluation --suite synthetic --output outputs/comparison.json
.venv\Scripts\python.exe -m depthstrike.evaluation --input tests/fixtures/straight_punches.jsonl --labels tests/fixtures/evaluation/straight-punch-labels.json --output outputs/fixture-comparison.json
```

输出采用独占创建，不能覆盖旧报告。第二条使用手工核对的 4 帧合成夹具：左右直拳各一次，连续碰撞＋状态机应匹配 2 个窗口。不是读取记录中的 events 作为标签。

<a id="docs-evaluation-md--2-受控方法"></a>
## 2. 受控方法

| 代号 | 规则 | 保持一致的条件 |
| --- | --- | --- |
| 2d_entry | 内参投影后的二维代理接触上升沿 | 同一骨架、平滑、拳心、半径、有效性和目标日程 |
| 3d_discrete_entry | 当前帧三维球体接触上升沿 | 同上 |
| 3d_swept_entry | 连续有效帧间球体扫掠进入 | 同上 |
| 3d_swept_punch | 连续进入且满足出拳／收拳状态，同一攻击一次结算 | 同上，增加攻击状态条件 |

接触基线均不是“每帧重叠就计分”；静止停留不应被故意构造成弱基线。二维基线以给定内参投影代理中心，按两轴焦距归一化，以半径/深度近似投影范围；不代表精确渲染球体轮廓。

四方法始终使用标签清单中的固定目标及活动手时间表，不随某个方法得分切换任务。激活目标、初始重叠、暂停或恢复追踪不凭空产生进入事件；断轨和忽略区间不桥接。扫掠时间使用线段交点在两帧间插值，单帧时间使用当前输入帧时间；这不是测得的真实接触时刻。

按各方法的候选接触时间检查活动区间，不要求两端采样帧都处于同一活动区间。所有目标在非活动期间仍更新几何接触历史，避免激活已经重叠的目标制造命中。离散检测与扫掠插值在日程边界可能给出不同结果，这是采样方法的区别。

评估不重演引导阶段。基础阈值来自录制配置；若要评价个体校准后的阈值，在标签清单的 `punch_thresholds` 中显式提供双手参数。全部参数进入报告，不能只保留最优结果。

<a id="docs-evaluation-md--3-标签清单"></a>
## 3. 标签清单

可运行示例：[straight-punch-labels.json](../../tests/fixtures/evaluation/straight-punch-labels.json)。顶层字段：

| 字段 | 内容 |
| --- | --- |
| schema_version | 整数 1 |
| evidence | synthetic 或 recorded；带 synthetic 来源的记录不能改标为 recorded |
| label_basis | 独立标注依据，不可写“模型认为命中” |
| unit / timestamp_unit / coordinates | m / s / camera_x_right_y_down_z_forward |
| intrinsics | width、height、fx、fy、cx、cy；可含 distortion_model 与 distortion |
| targets | 固定 target_id、hand、center[x,y,z]、radius |
| active_schedule | 非空、不重叠的 start_s、end_s、hand、target_id；左闭右开 |
| expected_windows | 独立定义的有效攻击命中窗口；同手同目标不重叠、不共用端点；闭区间 |
| ignore_windows | 不确定或无法独立判断的闭区间 start_s、end_s |
| punch_thresholds（可选） | left/right 各含 guard_extension_m、attack_extension_m、min_travel_m |

忽略区间内的预测和完全包含的标签排除；标签与忽略区间仅部分相交则拒绝，须人工拆分或重新界定。时间必须有限且 `0 <= start < end`，目标引用及深度范围必须有效，畸变模型不允许静默替换。manifest 限 4 MiB。

真人数据应在授权后录制，通过实测空间参照及独立观察标注有效直拳、未命中、重复接触和不确定区间。保留标注依据、参与者匿名标识、重复次数和调参／评价划分。recorded 仅说明使用录制数据，不等于标签已被外部核验。

<a id="docs-evaluation-md--4-匹配与输出"></a>
## 4. 匹配与输出

按时间顺序，将同手同目标且位于窗口中的一条预测匹配一个未使用标签。额外预测记 FP，未匹配标签记 FN；落入已匹配窗口的额外预测也记 duplicates。输出 TP/FP/FN、precision/recall、重复数、样本数、追踪无效比例、逐场景预测、输入与标签 SHA-256、方法参数和证据类型。零分母为 null，不写成 100%。

sample_count 包含全部输入帧；evaluated_frame_count 排除暂停和忽略区间；tracking_invalid_ratio 以其为分母。比较窗口应覆盖目标任务，不能拿缺少相应输入的时间段包装算法性能。

内置 7 个解析场景用于区分深度错位、快速跨越、慢伸手、未收拳重入、静止停留、断轨恢复和正常左右拳，推导见 [夹具说明](../../tests/fixtures/evaluation/README.md)。当前组合在这些刻意构造的场景上通过，不代表对真实运动的统计泛化。

软件计时使用 `--metrics`，口径见 [运行说明](../RUNNING.md#耗时统计)。没有同步的曝光／显示测量，不报告端到端延迟。

</details>

<a id="docs-implementation-notes-md"></a>
## docs/IMPLEMENTATION_NOTES.md

<details>
<summary>展开原始记录</summary>

<a id="docs-implementation-notes-md--首版实施决策与审查"></a>
# 首版实施决策与审查

<a id="docs-implementation-notes-md--实施决策"></a>
## 实施决策

按作出顺序记录：

1. 保留用户指定的仓库根目录，在本地功能分支开发，不另建工作树。这样保留现有目录布局，但不具备工作树级的文件隔离。
2. 固定 Python 3.12、NumPy 2.2.6、MediaPipe 0.10.32 与 SDK 2.1.2。旧版本存在 NumPy 约束冲突及标定绑定缺字段问题；其他 Python/系统组合不在本次验证范围。
3. 标准 Brown–Conrady 反投影使用校准参数与 OpenCV；SDK 简化的 2D→3D 接口不接受畸变参数。未知模型拒绝处理。旧绑定缺字段时需独立核对再显式配置，可能增加首次设备联调步骤。
4. 完整 NPC 对练、格挡、闪避及独立可执行程序发行不纳入已批准的 A/B 首版范围；因此交付的是目标击打原型，而非完整格斗游戏。
5. 无真实 Gemini 2 输入时，不将设备流兼容性、对齐精度、人体识别和实时性能判定为通过；真实设备接入仍可能需要调整。
6. 不声称彻底消除所有遮挡或一致性背景误读。当前采用保守失效策略和攻击取消机制；实机仍可能出现无效追踪或误触发，需通过真实数据继续评估。

<a id="docs-implementation-notes-md--独立审查"></a>
## 独立审查

对首版全部变更进行独立代码审查，发现四项重要问题，无严重或次要遗留项。逐项先建立失败测试，再修复：

- 背景占据深度邻域时的静止手腕误计分：中心深度缺失或与邻域表面矛盾时判无效，恢复帧不得构成攻击。
- NPY 伪造形状导致的大内存申请及空文件异常：加载前检查格式头、dtype、维度、声明字节数和实际长度，损坏文件统一报告。
- SDK `OBError` 运行期异常：转换为带有连接/同步指引的错误，同时保留暂时缺帧的独立语义。
- 低帧率回放加速：等待至记录时间，并在短等待中持续处理窗口操作。

回归测试不实际申请巨大内存。完整测试与运行边界见 [验证记录](#docs-verification-md)。

<a id="docs-implementation-notes-md--v020-离线流程迭代"></a>
## v0.2.0 离线流程迭代

依据已批准的 [设计](#docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md) 与 [计划](#docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md)，采用当前会话逐模块实现、先失败再通过的测试流程，最后进行一次独立全分支审查。

- 新增 guided 模式，legacy 保留原腕点、固定目标及旧计时语义。v2 记录显式保存配置和质量原因，v1 缺字段时不能静默采用新模式。
- 全关节有效策略覆盖双肩、双肘、双腕和两拳心；非活动手缺失也冻结新模式计时。该保守策略可能增加真实场景的暂停频率，需设备阶段评估。
- 拳心是可配置前臂外推代理；不新增手指模型，不宣称提高了解剖定位精度。
- 主界面突出实际空间关系，三维场景降为可选辅助视图。Open3D 对象常驻更新，避免每帧删建；参考 [官方更新示例](https://www.open3d.org/docs/release/tutorial/visualization/non_blocking_visualization.html)。可选声音使用 [Windows 异步接口](https://docs.python.org/3.12/library/winsound.html)，失败不影响计分。
- 保留同步配对输入，暂不引入后台线程；先提供可验证的软件阶段统计，之后依据实机测量决定是否解耦。
- 引导演示在暂停时冻结动作、恢复时重启当前脚本段，重置时重新执行校准；输入时间戳仍递增，录制回放可复现控制结果。
- 演示采用固定动作，明确拒绝无法满足几何、采样或速度／平滑约束的配置；相机／回放的参数范围不因此受限。
- 实验使用独立标签和固定日程，不以 recorded events 为真值，不让各方法的得分改变活动目标。基线使用接触进入事件，不人为按停留帧数重复计分。
- 阶段统计区分输入时间与软件时钟、嵌套阶段与整体耗时；只有最后 4096 个样本参与分位数，不伪装成全程精确分布或端到端延迟。

本轮沿用根目录功能分支，仍无工作树级隔离；未连接相机，也未 push、合并或创建 PR。原始人像、模型和输出继续忽略。仅交付 Python wheel，不扩大为 Unity 或完整格斗游戏。

<a id="docs-implementation-notes-md--本轮独立审查与修复"></a>
### 本轮独立审查与修复

对 `96bca67..6b86f29` 整分支进行一次独立审查。审查者独立运行 198 项通过、3 项显示测试跳过；无严重或次要问题，四项重要问题均确认并在同一轮修复中先失败、后通过：

1. RGB-D 回放转存骨架丢失来源：新增来源描述，保留完整上游 metadata、synthetic 标记和当前模型信息，测试转存后不能改标 recorded。
2. 目标日程切换漏判：按候选接触时间检查活动日程，持续维护所有目标的接触历史；覆盖激活后进入、停用前进入、激活前进入及既有重叠。
3. 校准接受不可达目标：保存舒适拳心的完整肩部相对向量；生成目标必须与已测中立至前伸线段相交，否则保持引导并解释高度／方向问题。
4. 模型下载覆盖已有说明：下载前检查模型和 sidecar，写入均独占创建；网络期间出现的 sidecar 也不能覆盖。

修复后真实显示专项全开：210 项通过、无跳过；重新构建及隔离安装 wheel，演示／回放仍为 600 帧、9 命中、90 分。没有再次委托审查，也没有将解析场景结果解释为真人性能。

审查未判断的边界按下列顺序保留：

- 真实 Gemini 2 采集、标定／对齐和 SDK／固件兼容性仍未验收，因为本轮未接设备；代价是首次联调可能还需调整驱动、流配置或标定。
- 真人校准易用性、骨架／拳心准确率和曝光至显示延迟仍未验收，空帧与解析轨迹不足以证明；代价是实测后可能需要修改阈值、引导或采集／显示调度。

无次要遗留项。本地分支保留，不执行推送、合并或外部发行；临时审查差异包与执行日志可清理，设计、实施决策、代码及测试证据由 Git 保留。

</details>

<a id="docs-motion-studio-md"></a>
## docs/MOTION_STUDIO.md

<details>
<summary>展开原始记录</summary>

<a id="docs-motion-studio-md--motion-studio-本地试做"></a>
# Motion Studio 本地试做

版本 `0.3.0.dev0`。在既有 guided 流程上试验“动作生成关卡”和“三维局部反事实复盘”。以下命令在仓库根目录的 PowerShell 中运行，使用已有 `.venv`；依赖安装见 [运行说明](../RUNNING.md)。

本地试验结果见 [验证记录](#docs-motion-studio-verification-md)。

<a id="docs-motion-studio-md--一键体验"></a>
## 一键体验

```powershell
.venv\Scripts\python.exe -m depthstrike.studio demo --output outputs/studio-try
```

该命令生成一段合成作者动作、九靶关卡和带三处空间偏差的合成挑战者，随后显示挑战画面。回合结束后打开逐靶复盘窗口，默认选中第一个有局部修正的未命中。数据都是合成示例，不读取相机。

额外显示三维辅助场景：

```powershell
.venv\Scripts\python.exe -m depthstrike.studio demo --output outputs/studio-dual --view dual
```

挑战窗口：`Space` 暂停判定，`Q` / `Esc` 退出。回放来源在暂停判定期间仍继续读取；中断窗口不生成空间修正，需重新运行命令从头开始。回放中的 `R` 仅重新校准判定，并不倒带原始输入；固定录制演示建议重新启动。

复盘窗口：`A` / 左箭头、`D` / 右箭头切换靶位，`Space` 播放／暂停轨迹，`R` 从头播放当前轨迹，`Q` / `Esc` 关闭。

每次 demo 使用一个新目录，已有目录拒绝覆盖。默认参数下示例得到九靶、六次命中、三次空间未命中；三处偏差是预设的，不能作为算法准确率。

<a id="docs-motion-studio-md--无窗口生成及再次查看"></a>
## 无窗口生成及再次查看

```powershell
.venv\Scripts\python.exe -m depthstrike.studio demo --output outputs/studio-batch --headless
.venv\Scripts\python.exe -m depthstrike.studio review --input outputs/studio-batch/review.json --trial 2
.venv\Scripts\python.exe -m depthstrike.studio review --input outputs/studio-batch/review.json --trial 2 --image outputs/studio-batch/review.png
```

无窗口链路只使用核心 NumPy；查看及 PNG 导出需要 OpenCV，dual 另需 Open3D。图片也采用独占创建。`--trial` 从 1 开始。

输出目录包括：

| 文件 | 内容 |
| --- | --- |
| author.jsonl | 原始合成骨架示范，含正常 guided 校准及完整收拳 |
| challenge.json | 身体相对靶位、峰值节奏、活动时间窗及作者来源 |
| player.jsonl | 同源合成挑战者，第 2、5、8 靶的腕／肘加入 (0.22, 0, 0.04) m 位移 |
| review.json | 逐靶结果、原始轨迹、最近点、可选局部修正及实际挑战者校准尺度 |

<a id="docs-motion-studio-md--自己的录制转关卡"></a>
## 自己的录制转关卡

输入须包含完整 guided 校准、试击、倒计时，以及正式回合中至少一拳有效出拳并收回。只截取出拳片段的旧文件不满足要求。

```powershell
.venv\Scripts\python.exe -m depthstrike.studio author --input recordings/guided-session.jsonl --output outputs/my-challenge.json
.venv\Scripts\python.exe -m depthstrike --source replay --input recordings/guided-session.jsonl --challenge outputs/my-challenge.json --review-output outputs/my-review.json
```

后续相机接入可使用同一关卡入口：

```powershell
.venv\Scripts\python.exe -m depthstrike --source camera --challenge outputs/my-challenge.json --review-output outputs/camera-review.json
```

相机入口复用了既有采集流程，本轮未作真实 Gemini 2／人体测试。

提取过程重新计算拳心和攻击状态，不读取录制 events 作为标签。只收录正式阶段中完成收回的攻击；失效、暂停或长间隔打断的攻击舍弃。正式阶段出现 reset 须先拆分文件；暂不支持同时出拳或超过 32 靶／120 s 的长关卡。

单靶时间窗为峰值前 0.40 s 至后 0.45 s；相邻窗口在峰值中点分界，末端不超过录制配置的回合时长。因此生成关卡可沿用该配置，不因最后一靶的延后窗口而被拒绝。

关卡以作者参考肩部为原点，x/y 按肩宽归一化，z 按该手舒适前伸量归一化。挑战者完成自己的校准后反变换一次，靶位固定于相机空间。映射时检查有效深度、中立拳心分离和舒适触达距离；检查失败直接报告，不自动扩大目标或移动靶位。

<a id="docs-motion-studio-md--复盘含义"></a>
## 复盘含义

- `hit`：有效出拳在活动时间窗内发生观测到的接触进入。
- `miss / spatial_miss`：窗口完整可观测且有有效攻击，但有效轨迹未接触目标。
- `miss / no_valid_attack`：没有可结算的有效出拳；慢伸手、未收拳或同次攻击已得分均不会得到空间修正。
- `unobserved`：窗口内观测不完整，不能将失败归因于玩家。
- `incomplete`：退出／EOF 时该窗口尚未结束；不按未命中统计。

攻击起始以相邻观测的前伸量线性插值确定，碰撞与修正均限于有效攻击区间和靶位活动窗口的交集。后一帧达到出拳条件，不会让前面已结束的窗口追溯得分。该插值仍是离散观测间的运动近似。

正面图使用相机 X/Y，侧面图使用 Z/Y。蓝色为观测轨迹；绿色实圈为目标球，浅圈为目标半径加拳心半径的接触范围；紫色为局部修正段。图上的轨迹是拳心代理中心，不是人体表面网格。

局部修正将最近的有效线段向球心平移，加入 1 mm 接触余量。两端需满足深度和保守触达球约束：拳心至参考肩部的距离不得超过校准的舒适前伸量，不额外加拳心半径；修正后重新进行连续碰撞核验。该触达球不是完整人体可达空间模型。修正仅表示固定时机与攻击状态下的局部几何接触；不生成完整人体动作，不证明关节可执行性，也不评价专业拳击动作。没有满足约束的局部修正时保留空值。

生成关卡属于派生内容，不是独立标注真值；作者自回放命中不能证明真实定位精度。跨体型体验效果、反馈是否改善学习以及真实遮挡表现仍需另行采样和用户实验。

</details>

<a id="docs-motion-studio-verification-md"></a>
## docs/MOTION_STUDIO_VERIFICATION.md

<details>
<summary>展开原始记录</summary>

<a id="docs-motion-studio-verification-md--motion-studio-本地验证"></a>
# Motion Studio 本地验证

日期：2026-10-22，Windows／Python 3.12，分支 `codex/motion-challenge-prototype`，版本 `0.3.0.dev0`。这是本地试做记录。

<a id="docs-motion-studio-verification-md--最终验证"></a>
## 最终验证

- 完整测试：`DEPTHSTRIKE_GUI_TESTS=1`，257 passed，17.06 s，无跳过；包括原有 210 项及本轮 47 项。命令为 `.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/pytest-studio-final-reviewed --tb=short`。
- `pip check` 无依赖冲突；`compileall -q src tests` 通过。未新增依赖。
- 修正后的真实 CLI 合成演示：588 帧，九靶中六次命中、三次空间未命中，60 分，报告完整。三次预设偏差的局部修正均通过接触复核及严格拳心触达限制；这不是准确率。
- wheel 构建成功，61,416 bytes，SHA-256：`1ff0d8cb0fe0f4e4a17bb088502628e6c4f56fac2ffbcbb04009c3e70d31fcde`。在不继承系统包、仅 pip／NumPy／本包的隔离环境重新安装后，`python -I -m depthstrike.studio demo --headless` 完成同一 588 帧／60 分链路。
- 实际 overlay＋Open3D dual 按输入时间播放；保存修正后截图，并核对窗口关闭和源文件释放。复盘窗口实际绘制并通过 R、A/D、Space、Q 的输入边界检查。自动注入按键仅用于检查交互分支，不是人工可用性测试。

<a id="docs-motion-studio-verification-md--独立审查与处理"></a>
## 独立审查与处理

独立审查覆盖基线 `3dbdda1` 至原型 `6bd3b1e` 的源码和内存复现；测试、打包及真实窗口证据由主开发执行。审查未发现 Critical，报告三项 Important 和一项 Minor，均在本地处理：

1. 攻击资格不可追溯应用于整个前一帧区间：增加插值资格起止时间，碰撞和局部修正只使用有效交集。
2. 回合时长分支可能跳过最后窗口：先处理最后观测区间再结束，不提前失效，也不压缩端点时间。
3. 局部修正触达球错误计入拳心半径：改用严格拳心距离上限，仅保留数值容差。
4. 短回合的末靶窗口可能超出源配置：将窗口末端限制在源回合时长。原审查为 Minor，本地按阻断同配置生成／播放的流程问题一并修复。

先执行七个新回归场景，得到 7 failed／30 passed；逐项实现后通过。补充攻击超时区间及修正触达约束检查，最后运行完整 257 项。原有击中夹具中的一处目标进入发生在资格形成之前，已调整靶深并手算新的接触时间；没有放宽判定。

示例中第 2、5、8 靶的腕／肘位移明确记录为 `(0.22, 0, 0.04) m`，使其局部修正在严格约束内可行。原始全伸横向偏移示例可能被拒绝修正，这一拒绝行为保留于测试，而非扩大触达限制。

未扩展为本轮结论的事项：回放暂停仍读帧和 R 不倒带是已说明的原型交互约定；派生关卡、自回放和合成偏差不能证明真实精度；实际人体生物力学、跨真人效果和教学价值未验证。没有进行第二轮独立审查，修复依靠上述回归及全套测试核验。

<a id="docs-motion-studio-verification-md--审查前补充检查"></a>
## 审查前补充检查

- 全套启用真实显示专项：249 passed，19.44 s，无跳过。包含原有 210 项，以及关卡、提取、复盘与 CLI 的新增用例。
- `pip check` 无依赖冲突，`compileall` 通过。
- 一键无窗口示例：588 帧，九靶中六次命中、三次空间未命中，60 分；三个预设偏差均有通过接触核验的局部修正。
- 原始合成作者重新生成关卡并自回放：588 帧、九次命中、90 分。仅检查派生链路一致性，不作独立精度实验。
- 人为将合成人体 x/y 及肩部相对 z 缩为 0.8：挑战者肩部 x 为 ±0.16 m，实际 guided 校准后重映射九靶并全部命中。不是跨真人泛化结论。
- 在第二靶内注入三个缺失右肘帧：该靶为 `unobserved`，不生成局部修正；其余输入保留，回合正常结束。
- 原有 guided 600 帧仍九次命中、90 分；旧 v1 四帧夹具仍两次命中、20 分。
- 实际 overlay＋Open3D dual 输入时间播放 588 帧，六次命中；两窗口关闭释放资源。复盘窗口实际绘制，输入边界触发 R、A/D、Space 与 Q 后正常关闭。
- 构建 wheel 后在不继承系统包、仅 pip／NumPy／本包的既有隔离环境中替换安装，`python -I -m depthstrike.studio demo --headless` 完成同一 588 帧／60 分链路。

<a id="docs-motion-studio-verification-md--本地产物"></a>
## 本地产物

最终产物位于 `outputs/motion-studio-reviewed-20261022/`：作者、关卡、挑战者、报告，以及 `review.png`、`challenge-hud.png`、`challenge-arena.png`。隔离安装结果位于 `outputs/motion-studio-wheel-reviewed-20261022/`。

审查前产物仍保留在 `outputs/motion-studio-local-20261022/` 和 `outputs/motion-studio-wheel-20261022/`，其中含 0.8 体型和中断检查。它们不替代最终输出；原始输出均由 Git 忽略。

启动和再次查看见 [Motion Studio](#docs-motion-studio-md)。

<a id="docs-motion-studio-verification-md--解释范围"></a>
## 解释范围

关卡是由运动数据提取的内容，不能作为独立标注；六次／九次命中由示例设计决定。局部修正只重新核验平移后的线段接触及深度／触达球约束，未核验完整人体关节可行性。没有真实 Gemini 2、真人跨体型、真实遮挡或学习效果证据。

本轮仅本地试做，主分支和远程没有更新。

</details>

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md"></a>
## docs/superpowers/plans/2026-10-20-boxing-target-prototype.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--depthstrike-boxing-target-prototype-implementation-plan"></a>
# DepthStrike Boxing Target Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现纯 Python 三维击球模拟器，贯通 Gemini 2 RGB-D 输入、人体关键点与深度融合、有效出拳、跨帧碰撞、计分及离线演示回放。

**Architecture:** 将采集与姿态检测、三维追踪、交互规则、显示及记录分离。真实相机和合成演示输出相同的三维骨架数据，几何和游戏逻辑可脱离相机与窗口测试。首版以目标球场景验收，不展开完整 NPC 对战。

**Tech Stack:** Python、NumPy、pytest；相机路径使用 Orbbec Python SDK、MediaPipe Pose Landmarker，显示使用 OpenCV 与 Open3D。

**Spec:** `D:\3D视觉\PROJECT.md`；本计划收敛其阶段 A、B，以及记录回放和基础评估，不将阶段 C 的完整攻防对战纳入首版。

**执行审批：** 用户已确认在当前会话逐步实现，完成后进行一次独立审查。以下“计划阶段”限制保留为审批前的历史约束。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--global-constraints"></a>
## Global Constraints

- 硬件：Orbbec Gemini 2。
- 首期形态：Python 模拟器，不引入 Unity。
- 输入为 RGB-D，不用单目模型的身体局部坐标冒充相机空间中的绝对位置。
- 核心计算采用相机坐标：X 向右、Y 向下、Z 向前，单位为米。
- 目标生成后保留在场景坐标中，不能每帧跟随当前身体原点移动。
- 追踪无效时取消当前攻击，并要求有效复位后重新激活。
- 游戏伤害不等同于真实力量；三维交互点是可见表面的代理位置，不是精确解剖关节。
- 不更改或上传课程材料；权重、录制和输出遵守既有 `.gitignore`。
- 使用独立 `.venv`，不修改 Anaconda 全局依赖；优先验证已安装的 Python 3.12，兼容失败时说明原因后再决定其他版本。
- 当前只编写计划。须经用户审核并选择执行方式，才创建生产代码、测试、环境或安装依赖。用户本次没有要求推送后续实现，完成代码后不自动 push。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--review-focus"></a>
## Review Focus

1. 无 SDK、无模型、无相机或断连时，给出可操作错误并释放资源，不静默切换成伪实时演示。由任务 5、7 测试。
2. 深度单位、内参、图像尺寸及时间戳不一致时，拒绝该帧，不能用二维重叠产生错误命中。由任务 1、2、5 测试。
3. 图像边缘、低置信度、深度空洞和背景误读时，交互点无效，不沿用上次位置继续攻击。由任务 2、3 测试。
4. 快速跨越、初始重叠、停留、收拳与恢复追踪时，既避免漏检，也避免重复计分和跨断轨命中。由任务 1、3、4 测试。
5. 回放数据损坏、非有限数、时间倒退，以及暂停、重置、退出时，保证错误明确、结果可复现和资源正常关闭。由任务 6、7、8 测试。

---

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--已有环境与执行准备"></a>
## 已有环境与执行准备

2026-10-20 的只读检查结果：仓库在 `main`，与 `origin/main` 同步，无待提交修改；仅包含文档与忽略规则。当前 `python` 为 Anaconda Python 3.12.7；另有 Python 3.9。可见依赖为 NumPy 1.26.4、OpenCV 4.11.0.86、Open3D 0.19.0、pytest 7.4.4，未发现 MediaPipe 和 Orbbec Python SDK 的已安装分发包。

Windows PnP 查询未返回名称匹配 Gemini/Orbbec 的设备。这不能代替 SDK 枚举，不据此断言摄像头不存在；真实采集验收需要实际连接设备。

执行前使用 `superpowers:using-git-worktrees` 核对隔离方案，保留 `D:\3D视觉` 为用户指定的主仓库，不移动课程资料。实施者需按所选执行技能进行任务级测试与审查。Git 如需联网，复用已核实的系统代理并仅作用于当前命令，不修改全局网络设置。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--文件与数据约定"></a>
## 文件与数据约定

计划新增以下文件；此清单不表示它们已经存在：

```text
pyproject.toml
configs/default.json
src/depthstrike/
  __init__.py             # 包入口
  __main__.py             # CLI 入口
  types.py                # 坐标、帧、关键点和事件类型
  config.py               # 参数加载与验证
  geometry.py             # 球体及轨迹相交
  fusion.py               # 有效深度选择、反投影
  tracking.py             # 时序过滤与失效处理
  boxing.py               # 校准、出拳状态、目标和计分
  capture.py              # Gemini 2 采集与对齐
  pose.py                 # MediaPipe 同步推理
  sources.py              # 相机、演示、回放输入
  recording.py            # 轨迹与 RGB-D 记录回放
  visualization.py        # OpenCV 与 Open3D 显示
  app.py                  # 主循环与资源管理
  cli.py                  # 参数、诊断和运行模式
scripts/download_pose_model.py
models/README.md
tests/conftest.py
tests/test_geometry.py
tests/test_config.py
tests/test_fusion.py
tests/test_tracking.py
tests/test_boxing.py
tests/test_adapters.py
tests/test_recording.py
tests/test_app.py
tests/test_cli.py
tests/fixtures/           # 小型合成轨迹与预期结果
docs/RUNNING.md
docs/VERIFICATION.md
```

共享接口固定如下，后续任务不得自行更名或改变单位：

- `Intrinsics(width, height, fx, fy, cx, cy, distortion_model, distortion)`：反投影所需的相机参数。
- `RGBDFrame(frame_id, timestamp_s, color_rgb, depth_m, intrinsics)`：已对齐 RGB 图像与米制深度；时间戳单位为秒。
- `Landmark(u, v, confidence)`：未镜像图像中的归一化二维坐标。
- `Joint3D(position, confidence)`：位置为三个有限浮点数或 `None`；`None` 明确表示无效。
- `SkeletonFrame(frame_id, timestamp_s, joints)`：名称到 `Joint3D` 的映射，至少约定 `left_shoulder`、`right_shoulder`、`left_elbow`、`right_elbow`、`left_wrist`、`right_wrist`。
- `HitEvent(timestamp_s, hand, target_id, attack_id, points)`：可序列化命中事件。
- `SceneState`：当前骨架、目标、得分、命中数、剩余时间、最近事件与状态提示。
- 输入协议统一约定 `read()` 的 `None` 只表示正常结束；实时采集暂时缺帧抛出 `FrameTimeout`，不能误当文件结束。应用收到超时后取消现有攻击、继续处理窗口事件；连续 5 s 无帧时以明确错误退出并释放设备，不复用旧位置判定。

工程初值均可配置，不视为实测结论：手代理半径 0.06 m，目标半径 0.08 m，关键点置信度阈值 0.6，最大轨迹间隔 0.2 s，回合长度 60 s。相机可用流配置、深度范围与出拳阈值在设备测试中记录、调整。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-1-可独立验证的几何与配置核心"></a>
## Task 1: 可独立验证的几何与配置核心

**Files:** 创建 `pyproject.toml`、`src/depthstrike/__init__.py`、`types.py`、`config.py`、`geometry.py`、`configs/default.json`；测试 `tests/test_geometry.py`、`tests/test_config.py`。

**Interfaces:**
- Produces: `segment_sphere_intersection(start, end, center, radius) -> float | None`，返回最早相交参数 `t∈[0,1]`。
- Produces: `load_config(path: Path | None) -> AppConfig`，校验有限数、正半径和合法阈值；提供上述共享类型。

- [ ] **Step 1:** 先写测试。核心断言示例：

  ```python
  def test_sweep_detects_crossing_between_frames():
      from depthstrike.geometry import segment_sphere_intersection
      assert segment_sphere_intersection((-1, 0, 1), (1, 0, 1), (0, 0, 1), 0.1) == pytest.approx(0.45)
  ```

  同时断言深度错位返回 `None`、相切命中、初始重叠返回 0、静止内外各自正确，NaN 与负半径被拒绝；配置覆盖负数、缺失文件与未知字段。
- [ ] **Step 2:** 设置最小测试加载配置，运行 `.venv\Scripts\python -m pytest tests/test_geometry.py tests/test_config.py -q`；确认因缺少目标功能而失败，不以拼写或依赖缺失代替行为红灯。
- [ ] **Step 3:** 实现类型、配置和几何函数。移动球相交使用相对轨迹，不引入物理引擎。
- [ ] **Step 4:** 重跑上述测试，再运行全部 `pytest`，确认通过。
- [ ] **Step 5:** 显式暂存本任务文件，提交 `feat: add validated geometry and configuration core`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-2-深度融合与空间坐标"></a>
## Task 2: 深度融合与空间坐标

**Files:** 创建 `fusion.py`；测试 `tests/test_fusion.py`。

**Interfaces:**
- Consumes: `RGBDFrame`、`Landmark`、`Intrinsics`、`AppConfig`。
- Produces: `estimate_joint(landmark, frame, config) -> Joint3D`；`fuse_skeleton(frame, landmarks, config) -> SkeletonFrame`。

- [ ] **Step 1:** 写测试，构造 640×480、`fx=fy=600`、`cx=320`、`cy=240`、深度 2 m 的合成帧，断言主点反投影为 `(0,0,2)`，右移 60 像素为 `(0.2,0,2)`；覆盖低置信度、边界、全零邻域、图像尺寸不匹配、无穷深度和畸变参数。
- [ ] **Step 2:** 运行融合测试，确认预期失败。
- [ ] **Step 3:** 实现深度有效性筛选与反投影。畸变模型必须有明确处理；未支持的模型拒绝运行，不能静默当作无畸变。相机适配层优先使用 SDK 校准变换，离线合成数据使用已知针孔模型。
- [ ] **Step 4:** 运行融合与全套测试；验证同一像素不同 Z 得到不同三维位置。
- [ ] **Step 5:** 提交 `feat: fuse pose landmarks with calibrated depth`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-3-时序追踪与攻击状态"></a>
## Task 3: 时序追踪与攻击状态

**Files:** 创建 `tracking.py`；在 `boxing.py` 实现攻击状态部分；测试 `tests/test_tracking.py`、`tests/test_boxing.py`。

**Interfaces:**
- Produces: `SkeletonTracker.update(frame: SkeletonFrame) -> SkeletonFrame`、`reset()`。
- Produces: `PunchTracker.update(timestamp_s, wrist, shoulder) -> PunchState`、`reset()`；`PunchState` 包含 `phase`、`attack_id`、`previous_position`、`position`、`can_hit`。

- [ ] **Step 1:** 写行为测试：低速停留不启动攻击；向前快速伸手进入 `ATTACKING`；收回后复位；无效关节、非递增时间、超过 0.2 s 的间断均清除扫掠起点；恢复追踪不能连接断轨两端产生攻击。另测试不同帧间隔下的速度计算与可关闭平滑。
- [ ] **Step 2:** 运行追踪和攻击测试，确认预期失败。
- [ ] **Step 3:** 实现基于时间间隔的平滑与 `READY → ATTACKING → RECOVERING` 状态机，使用手相对肩部的前向运动，首版不扩展任意拳型分类。
- [ ] **Step 4:** 运行本任务及全套测试，确认恢复帧不产生有效扫掠。
- [ ] **Step 5:** 提交 `feat: track valid punches and reject broken trajectories`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-4-目标球校准与计分"></a>
## Task 4: 目标球、校准与计分

**Files:** 完成 `boxing.py` 的场景管理；扩展 `tests/test_boxing.py`。

**Interfaces:**
- Consumes: `SkeletonFrame`、`PunchTracker`、几何函数与配置。
- Produces: `BoxingSimulation.step(frame: SkeletonFrame) -> SceneState`、`reset()`、`set_paused(paused: bool)`、`invalidate_tracking()`；最后一个接口清除当前攻击与扫掠起点，供采集超时使用，不混用相机与系统时间戳。

- [ ] **Step 1:** 写测试：稳定中立姿势形成固定校准参考；左右目标位于舒适的前伸区域；身体之后移动不拖动目标；一次攻击只计一次命中；停留、收回、生成新目标不额外计分；暂停不推进回合，重置清除得分与旧攻击；回合结束停止结算。
- [ ] **Step 2:** 运行场景测试，确认新规则尚未实现而失败。
- [ ] **Step 3:** 实现两个左右交替的静态目标球、短时命中反馈、固定分数及 60 s 回合。目标前方取相机 Z 减小方向；校准与目标状态保留在场景坐标，不使用每帧身体局部原点。
- [ ] **Step 4:** 运行本任务及全套测试；用完全相同轨迹重复运行得到相同事件与得分。
- [ ] **Step 5:** 提交 `feat: add calibrated target boxing scene and scoring`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-5-gemini-2-与-mediapipe-适配"></a>
## Task 5: Gemini 2 与 MediaPipe 适配

**Files:** 创建 `capture.py`、`pose.py`、`sources.py`、`scripts/download_pose_model.py`、`models/README.md`；测试 `tests/test_adapters.py`。

**Interfaces:**
- Produces: 上下文管理器 `GeminiSource.read() -> RGBDFrame | None`、`close()`、`describe() -> dict`。
- Produces: `PoseEstimator.detect(frame: RGBDFrame) -> dict[str, Landmark]`、`close()`。
- Produces: `CameraPoseSource.read() -> SkeletonFrame | None`，组合采集、推理和融合，不让界面重新读取不同时刻的深度。

- [ ] **Step 1:** 先测试帧数据转换与资源行为：RGB/BGR/MJPG 等实际选择的格式、深度缩放到米、对齐后尺寸与内参、时间差超限、无设备、流启动失败、采集超时及推理异常。断言暂时缺帧抛出 `FrameTimeout` 而非返回 EOF。仅在 SDK/模型边界使用最小替身，不模拟核心碰撞逻辑。
- [ ] **Step 2:** 运行适配测试，确认缺少功能时失败；测试不要求 CI 连接设备。
- [ ] **Step 3:** 参考官方示例实现 SDK 软件深度到彩色对齐、帧聚合与同步；选择设备支持的合理流组合并记录参数。MediaPipe 采用同步 VIDEO 推理，使用对应输入帧的严格递增时间戳。SDK/MediaPipe 延迟导入，演示和纯几何测试不强制加载它们。
- [ ] **Step 4:** 实现显式模型下载命令，只从官方模型源下载并记录 SHA-256，写入被忽略的模型目录；不在程序启动或模块导入时自动下载。
- [ ] **Step 5:** 在独立环境中安装并验证真实依赖；设备存在时运行采集与对齐检查，不存在时记录“未进行真实设备验收”，不虚报通过。不要自动升级相机固件或变更 Windows 执行策略。
- [ ] **Step 6:** 运行全套测试，提交 `feat: add Gemini RGB-D and MediaPipe adapters`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-6-合成输入与双层回放"></a>
## Task 6: 合成输入与双层回放

**Files:** 完成 `sources.py` 的演示与回放输入；创建 `recording.py`、测试夹具；测试 `tests/test_recording.py`。

**Interfaces:**
- Produces: `DemoPoseSource.read() -> SkeletonFrame | None`，以固定时间步生成可复现的左右出拳、收回与停留样例。
- Produces: `PoseRecorder.write(frame, events)`、`PoseReplaySource.read()`；`RGBDRecorder.write(frame)`、`RGBDReplaySource.read()`，均有 `close()` 与上下文管理。

- [ ] **Step 1:** 写往返测试，断言时间戳、单位、有效关节及 RGB/深度数组恢复一致；覆盖损坏行、非有限数、非递增时间、未知格式版本、缺失数组与指向记录目录之外的路径。
- [ ] **Step 2:** 运行回放测试并确认预期失败。
- [ ] **Step 3:** 实现版本化 JSONL 轨迹与 JSON 元信息＋无对象 NumPy 数组的 RGB-D 格式；数组读取禁用 pickle；限制路径在记录目录内。不把姿态回放标为视觉模型验证。
- [ ] **Step 4:** 演示轨迹输入场景后至少产生一次有效命中；回放同一记录的事件与分数保持一致；执行全套测试。
- [ ] **Step 5:** 提交 `feat: add deterministic demo and safe recording replay`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-7-三维场景cli-与主循环"></a>
## Task 7: 三维场景、CLI 与主循环

**Files:** 创建 `visualization.py`、`app.py`、`cli.py`、`__main__.py`；测试 `tests/test_app.py`、`tests/test_cli.py`。

**Interfaces:**
- Produces: `SceneView.render(state: SceneState, rgbd_frame: RGBDFrame | None)`、`poll_actions() -> list[str]`、`close()`。
- Produces: `run_session(source, simulation, view, recorder, max_frames: int | None) -> SessionSummary`。
- Produces: `main(argv: list[str] | None = None) -> int`，供 `python -m depthstrike` 和安装后的命令入口调用。

- [ ] **Step 1:** 写测试：错误参数返回非零退出码和用法；`--source demo --headless` 不导入相机 SDK；无显示环境给出 headless 指引；暂停、重置、退出和来源异常都会正确关闭资源；暂时缺帧清除攻击但保留窗口响应，连续 5 s 无帧正常关闭后报错；有限帧演示退出并输出有限数值摘要。
- [ ] **Step 2:** 运行应用测试并确认预期失败。
- [ ] **Step 3:** 实现 Open3D 非阻塞显示，包含地面/坐标参考、骨架、左右拳套、目标球、轨迹与命中变色；OpenCV 提供 RGB 骨架叠加和得分提示。所有碰撞仍由场景核心决定；显示线程不采集相机或修改判定。
- [ ] **Step 4:** 连接 CLI：计划支持 `--source demo|camera|replay|rgbd-replay`、`--input`、`--headless`、`--frames`、`--config`、`--record`、`--record-rgbd`。输入不匹配时直接报错；不静默切换模式。键位 `Space` 暂停、`R` 重置/重新校准、`Esc` 或 `Q` 退出。
- [ ] **Step 5:** 验证演示可见窗口的骨架/目标/命中反馈与 headless 事件一致；验证关闭任一主窗口后退出、无后台相机残留。
- [ ] **Step 6:** 运行全套测试，提交 `feat: add interactive target simulator and CLI`。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--task-8-使用文档与完整验收"></a>
## Task 8: 使用文档与完整验收

**Files:** 更新 `README.md`、`PROJECT.md`；创建 `docs/RUNNING.md`、`docs/VERIFICATION.md`；补充 `tests/test_cli.py` 的端到端测试。

**Interfaces:** 消费前七项的公开 CLI 和回放格式，不再建立另一套运行入口。

- [ ] **Step 1:** 先写端到端测试：子进程在规定帧数内完成 headless 演示；轨迹录制后 replay 得分与事件一致；无设备 camera 模式失败时保留可操作错误，不能输出伪造成功摘要。
- [ ] **Step 2:** 执行新测试确认预期失败，补足 CLI 集成与诊断，再运行完整 `pytest`。
- [ ] **Step 3:** 根据实际验证结果固定依赖版本，记录模型来源、系统、SDK 和固件信息。提供独立环境安装、模型下载、演示、相机模式、轨迹/RGB-D 回放及常见错误说明，命令须实测后才写为可运行。
- [ ] **Step 4:** 分别记录自动测试、headless 演示、窗口演示、真实设备采集和真实人体击球的通过/未测/失败结果。无硬件时仍交付可运行演示和适配代码，但明确设备联调尚未验收，不用模拟测试替代。
- [ ] **Step 5:** 更新 PROJECT 中与首版已实现代码明显冲突的历史描述；README 保持此前确定的学术简洁风格，安装细节链接到 RUNNING，不加入冗长状态免责声明。
- [ ] **Step 6:** 核对只包含项目文件、无权重或人像数据，提交 `docs: document simulator usage and verification`；按所选执行方式完成独立审查。未经再次授权不 push。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--自查结果"></a>
## 自查结果

- 范围覆盖 PROJECT 的阶段 A、B，以及首版所需采集、融合、计分、回放和测试；阶段 C 完整虚拟对手、格挡/闪避对战及打包发行另行实施。
- 五项 Review Focus 均已分配至具体测试任务；共享类型与命令命名贯穿一致。
- 两种回放分别验证规则与视觉输入链路，不混淆证据。
- 依赖安装、模型下载和设备验收位于执行阶段，未在计划阶段实施。
- 用户已选择 Native：模块依赖顺序紧密，接口在同一会话中保持一致；实现后仍需独立审查。

<a id="docs-superpowers-plans-2026-10-20-boxing-target-prototype-md--核对过的官方参考"></a>
## 核对过的官方参考

- [Orbbec Python SDK 示例目录](https://github.com/orbbec/pyorbbecsdk/tree/v2-main/examples)
- [深度到彩色对齐示例](https://github.com/orbbec/pyorbbecsdk/blob/v2-main/examples/beginner/03_color_and_depth_aligned.py)
- [SDK 坐标变换示例](https://github.com/orbbec/pyorbbecsdk/blob/v2-main/examples/advanced/16_coordinate_transform.py)
- [MediaPipe Pose Landmarker Python 接口](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Open3D 非阻塞可视化](https://www.open3d.org/docs/release/tutorial/visualization/non_blocking_visualization.html)

</details>

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md"></a>
## docs/superpowers/plans/2026-10-21-offline-interaction-refinement.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--offline-interaction-refinement-implementation-plan"></a>
# Offline Interaction Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Preserve the user's choice of inline implementation in the current session, followed by independent final review.

**Goal:** 在不接入 Gemini 2 的条件下实现可离线验收的个体化击球流程、清晰反馈、渲染更新、性能记录及受控对比实验。

**Architecture:** 在既有输入和几何边界上增加拳心代理、独立引导状态机及结构化反馈；BoxingSimulation 负责统一结算。显示、计时统计和实验比较不反向决定游戏结果；版本化录制保留旧行为。

**Tech Stack:** Python 3.12、NumPy 2.2.6、pytest 8.3.5；复用现有 OpenCV 4.11.0.86、Open3D 0.19.0、MediaPipe 0.10.32 和 pyorbbecsdk2 2.1.2。

**Spec:** `docs/superpowers/specs/2026-10-21-offline-interaction-refinement-design.md`

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--global-constraints"></a>
## Global Constraints

- Python >=3.12,<3.13；沿用 pyproject.toml 中已固定的依赖，不新增强制依赖。
- 相机 X 向右、Y 向下、Z 向前，长度单位米，时间单位秒。
- 人体数据无效即取消攻击；不使用旧点、预测点或显示插值参与命中。
- 目标在校准完成后固定于相机空间，不随身体逐帧移动。
- 相机、合成演示、骨架回放、RGB-D 回放四种来源保持显式区分；相机失败不得切换成合成演示。
- 本阶段不接入相机、不升级固件、不修改全局 Python 环境，不 push、合并或创建 PR。
- 课程材料、原始人像、模型权重、环境和输出不进入普通 Git 历史。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--review-focus"></a>
## Review Focus

1. 旧版记录缺少新配置或质量原因：仍选择 legacy 并重现原事件，不静默切换 guided。
2. 校准中暂停、缺肩/肘、重复时间戳或长间隔：不累计断开的稳定时间，不留下可得分的旧拳心。
3. 可达范围过小、身体移动或目标越出深度范围：保持引导并解释，不生成不可达/假有效目标。
4. 显示关闭、音频异常、输出文件已存在：正确释放资源，不覆盖用户文件，不改变计分。
5. 实验方法改变活动目标日程或从预测反推真值：明确禁止；同输入、目标和独立标签的一对一匹配才可比较。

---

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--文件职责"></a>
## 文件职责

保留 `capture.py`、`pose.py` 的同步配对模型；不为本轮引入后台采集。

| 文件 | 职责 |
| --- | --- |
| `interaction.py`（新） | 无图形依赖的拳心代理与有效性 |
| `calibration.py`（新） | 引导阶段、舒适触达范围与校准档案 |
| `feedback.py`（新） | 当前可观测条件到结构化提示的映射 |
| `arena.py`（新） | 常驻 Open3D 几何更新与生命周期 |
| `audio.py`（新） | 可选异步提示音与失败降级 |
| `metrics.py`（新） | 有界阶段统计与独占输出 |
| `evaluation.py`（新） | 标签验证、受控方法及事件匹配/命令行 |
| `evaluation_scenarios.py`（新） | 解析合成场景与独立预期窗口 |
| `types.py` / `config.py` | 共享数据契约与参数校验 |
| `boxing.py` | legacy/guided 调度、连续碰撞和正式计分 |
| `visualization.py` | 叠加主视图与 dual 组合视图 |
| `sources.py` / `app.py` / `cli.py` | 新演示流程、阶段观测与入口 |
| `recording.py` | v2 写入与 v1/v2 兼容读取 |

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--task-1-拳心代理质量原因与格式兼容"></a>
## Task 1: 拳心代理、质量原因与格式兼容

**Files:** Create `src/depthstrike/interaction.py`, `tests/test_interaction.py`; modify `types.py`, `config.py`, `fusion.py`, `tracking.py`, `recording.py`, `configs/default.json`, `tests/test_config.py`, `tests/test_fusion.py`, `tests/test_recording.py`.

**Interfaces:**
- `Joint3D(position, confidence=0.0, invalid_reason: str | None=None)`；保持已有位置参数兼容。
- `estimate_fist(elbow: Joint3D | None, wrist: Joint3D | None, config: AppConfig) -> Joint3D`；无效原因与最小置信度按设计传播。
- `AppConfig.interaction_mode: str = "guided"`，只允许 guided/legacy；增加 `fist_offset_m=.06`、`forearm_min_length_m=.02`、`reach_hold_s=.35`、`return_guard_s=.20`、`reach_min_increment_m=.10`、`target_reach_ratio=.85`、`countdown_s=2.0`。零偏移合法，其余时长/长度为正，比例 (0,1)，枚举不能由 bool/数字替代。
- v2 headers 明示新配置；v1 reader 仅在未提供模式时注入 legacy 和零拳心偏移。v2 缺失 mode 报错。未知版本继续拒绝。

- [x] **Step 1: Write failing tests.** `test_fist_extends_forearm_by_six_cm`：`assert estimate_fist(Joint3D((0,0,2), .9), Joint3D((0,0,1.8), .8), AppConfig()).position == pytest.approx((0,0,1.74))`；`test_missing_elbow_and_degenerate_forearm_are_invalid` 覆盖缺失、低置信度、0.019 m；`test_quality_reason_survives_tracking_and_v2_roundtrip` 核对无效原因；参数化非法配置；`test_v1_fixture_retains_legacy_mode_and_twenty_points`：`assert (summary.frames, summary.hits, summary.score) == (4, 2, 20)`；`test_v2_requires_explicit_interaction_mode` 拒绝含混新格式。
- [x] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_interaction.py tests/test_config.py tests/test_fusion.py tests/test_recording.py -q`；确认新增测试因缺接口/行为失败，而非环境失败。
- [x] **Step 3: Implement contracts and proxy.** 按规范公式计算拳心；区分融合失败原因并保留现有保守有效性检查；读取器显式兼容 v1/v2，写入器使用 v2。保留 NPY 大小/路径/格式防护和独占文件创建。
- [x] **Step 4: Run GREEN.** 上述测试全通过；另运行 `tests/test_cli.py::test_supplied_fixture_has_hand_checked_result`，结果仍为 4 帧、20 分。
- [x] **Step 5: Commit only task files.** `feat: add quality-aware fist proxies and versioned replay compatibility`。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--task-2-个体化引导练习及正式回合"></a>
## Task 2: 个体化引导、练习及正式回合

**Files:** Create `src/depthstrike/calibration.py`, `tests/test_calibration.py`; modify `boxing.py`, `types.py`, `sources.py`, `cli.py`, `tests/conftest.py`, `tests/test_boxing.py`, `tests/test_app.py`, `tests/test_cli.py`.

**Interfaces:**
- `CalibrationProfile(reference_shoulders: dict[str, np.ndarray], neutral_extensions: dict[str, float], comfortable_extensions: dict[str, float], guard_thresholds: dict[str, float], attack_thresholds: dict[str, float], travel_thresholds: dict[str, float], target_centers: dict[str, np.ndarray])`。
- `GuidanceState(stage: str, progress: float, message_code: str, profile: CalibrationProfile | None)`。
- `GuidedCalibration(config).update(frame: SkeletonFrame, fists: dict[str, Joint3D]) -> GuidanceState`，另有 `reset()`、`invalidate()`；暂停时调用方不得推进。
- `PunchTracker` 保留旧 `update(timestamp_s, wrist, shoulder)` 调用兼容；新增可选 profile 阈值，输入代理点在 guided 模式为拳心。
- `SceneState` 新增默认字段 `guidance`、`fists`、`feedback`，不得破坏旧位置构造。
- `DemoPoseSource(config=None, fps=30., total_frames=None)` 依据 mode 选择旧轨迹或含引导的确定性动作；描述中持续标明 synthetic。

- [x] **Step 1: Write failing tests.** 覆盖 0.6 s 中立、0.35 s 左右舒适前伸、0.20 s 收拳、练习和 2 s 倒计时的顺序；两个不同舒适范围生成不同目标，断言 `assert center[2] == pytest.approx(reference_shoulder[2] - .85 * comfortable_extension)` 且身体移动后不变；`test_pause_and_tracking_gap_do_not_complete_hold`；`test_missing_shoulder_cannot_score_or_consume_guided_round_time`；`test_practice_hits_never_increment_official_score`：`assert (state.score, state.hits, state.remaining_s) == (0, 0, 60)`；`test_resume_requires_guard_not_extended_fist`；`test_shoulder_drift_resets_current_reach_sample`；`test_guard_overlap_and_out_of_depth_targets_are_rejected`；`test_interrupted_countdown_restarts_after_guard`；`test_missing_inactive_elbow_suppresses_scoring_and_time`。原有测试显式使用 legacy，保留原预期。
- [x] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_calibration.py tests/test_boxing.py tests/test_app.py tests/test_cli.py -q`。
- [x] **Step 3: Implement staged calibration.** 用输入时间和有效连续样本推进；引导档案的公式、深度检查、暂停/失效/重置语义采用 spec。将 legacy 路径清晰隔离；guided 同一拳心用于出拳和扫掠碰撞。左右练习命中只推进练习；倒计时结束清空攻击；正式计时只累计有效连续区间。
- [x] **Step 4: Implement deterministic demo and roundtrip.** 更新 CLI 构造使 source 接收所用配置；脚本包含所有阶段，不向 simulation 注入“已校准”标志。测试新 demo 能进入 RUNNING 并左右命中；相同配置两次事件完全一致；录制回放事件完全一致。
- [x] **Step 5: Run GREEN and commit.** 上述测试通过，v1 夹具仍 20 分；提交 `feat: add reach-calibrated guided boxing sessions`。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--task-3-解释性反馈叠加主视图与几何复用"></a>
## Task 3: 解释性反馈、叠加主视图与几何复用

**Files:** Create `src/depthstrike/feedback.py`, `src/depthstrike/arena.py`, `src/depthstrike/audio.py`, `tests/test_feedback.py`, `tests/test_visualization.py`; modify `types.py`, `boxing.py`, `visualization.py`, `cli.py`, `tests/test_app.py`.

**Interfaces:**
- `HandFeedback(reason: str, surface_gap_m: float | None, depth_delta_m: float | None, lateral_m: float | None)`；`build_feedback(fists: dict[str, Joint3D], targets: tuple[Target, ...], phases: dict[str, str], status: str, config: AppConfig, diagnostics: dict[str, str]) -> dict[str, HandFeedback]`；diagnostics 是当前攻击条件的原因代号，不读取旧帧补值。
- `SceneView(config, mode="demo", layout="overlay", sound=False)`；保持 `render/poll_actions/close`；dual 才构造 `ArenaRenderer`。
- `ArenaRenderer(config)`：`render(state)`、`poll_actions()`、`close()`；建立固定命名对象池，稳定帧只 update_geometry。
- `AudioFeedback(enabled=False).notify(events)` / `close()`；仅 Windows 上懒导入 winsound，使用异步系统声音，错误最多提示一次，不传播为计分错误。
- CLI 添加 `--view overlay|dual` 和 `--sound`；headless 与 sound 冲突时报可操作参数错误。

- [x] **Step 1: Write failing tests.** `test_depth_mismatch_is_explained_without_hit`、`test_invalid_hand_clears_all_distance_fields`：`assert (feedback.surface_gap_m, feedback.depth_delta_m, feedback.lateral_m) == (None, None, None)`、`test_tracking_loss_precedes_speed_hint`；纯图像测试含阶段/进度和拳心，NaN/后方目标不绘制；mock Open3D 下连续 100 帧对象创建/增删数量不随帧数增长，断言 `assert final_add_count == initial_add_count`，无效后复用恢复；overlay 不导入 open3d；双窗口各自关闭释放资源；音频失败不会改变分数。
- [x] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_feedback.py tests/test_visualization.py tests/test_app.py -q`。
- [x] **Step 3: Implement feedback and views.** 数值距离与命中使用同一拳心/半径；按 spec 优先级映射提示。拆分常驻三维渲染，mesh 顶点从原始局部模板重算，避免逐帧 transform 累积漂移；空线集/空网格隐藏失效对象。目标深度线索只用于显示。图形调用均保留在主线程。
- [x] **Step 4: Run GREEN and visible smoke.** 单测通过；分别运行新 demo 的 overlay/dual，检查引导、拳心、空间反馈、闪烁、暂停和退出。可用桌面时执行 opt-in GUI 测试并保存本地截图；无显示时明确记为未验收，不伪造通过。
- [x] **Step 5: Commit task files.** `feat: add explanatory overlay feedback and persistent arena geometry`。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--task-4-软件阶段观测与可靠导出"></a>
## Task 4: 软件阶段观测与可靠导出

**Files:** Create `src/depthstrike/metrics.py`, `tests/test_metrics.py`; modify `sources.py`, `app.py`, `cli.py`, `tests/test_adapters.py`, `tests/test_app.py`, `tests/test_cli.py`.

**Interfaces:**
- `StageMetrics(clock=time.perf_counter, capacity=4096)`，`measure(name)` context manager，`snapshot() -> dict`，`write_exclusive(path, metadata)`。
- 使用固定容量环形样本，并报告 total_count / retained_count；p50/p95/max 明示基于保留样本，避免无限内存或误称全程精确分位数。
- `CameraPoseSource(..., metrics=None)` 观测 capture/pose/fusion；`run_session(..., metrics=None)` 观测 read/simulation/record/render/frame_total；现有会话 clock 仍仅控制超时/播放，不与 profiling 时钟混用。
- `--metrics PATH` 输出非覆盖 JSON；已有文件在启动设备/模型前拒绝。执行异常时由 CLI finally 关闭后导出 partial 状态，不能用导出异常覆盖原错误。

- [x] **Step 1: Write failing tests.** 假时钟断言各阶段耗时、分位数与样本计数，单次 0.012 s 时断言 `assert stage["p50_s"] == pytest.approx(.012)`；`test_nested_read_metrics_are_not_summed_twice`；超过 4096 样本内存有界，断言 `assert stage["retained_count"] == 4096`；异常、超时、提前退出产生部分统计；已有输出内容不变；设备时间戳远离软件时钟仍输出非负合法耗时。
- [x] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_metrics.py tests/test_adapters.py tests/test_app.py tests/test_cli.py -q`。
- [x] **Step 3: Implement metrics boundaries.** 区分软件耗时、播放等待和设备时间；metadata 保存输入类型/配置/版本和成功或 partial 状态。不加入线程或修改 RGB-D 配对。
- [x] **Step 4: Run GREEN and CLI smoke.** `.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 600 --metrics outputs/offline-stage-metrics-UNIQUE.json`；JSON 可解析、阶段存在且 evidence 为 synthetic；记录软件结果，不标注真实端到端延迟。
- [x] **Step 5: Commit task files.** `feat: add bounded software-stage timing diagnostics`。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--task-5-独立标签与受控对比评估"></a>
## Task 5: 独立标签与受控对比评估

**Files:** Create `src/depthstrike/evaluation.py`, `src/depthstrike/evaluation_scenarios.py`, `tests/test_evaluation.py`, `tests/fixtures/evaluation/README.md`; modify `geometry.py` only if shared pure numeric projection is needed; modify `recording.py` only to expose public read-only metadata.

**Interfaces:**
- `EvaluationManifest`：schema_version=1、evidence、intrinsics、固定 targets、active_schedule、expected_windows、ignore_windows 和标签依据。
- `evaluate_recording(input_path: Path, manifest_path: Path) -> dict`；`evaluate_synthetic_suite() -> dict`；模块 `main(argv=None) -> int` 独占创建 output。
- 四方法代号 `2d_entry`、`3d_discrete_entry`、`3d_swept_entry`、`3d_swept_punch`。接触上升沿在真正离开后重置；无效/断轨时取消连续线段，恢复的首帧不凭初始重叠产生 entry。状态机方法额外要求 guard/attack。
- 2D 基线用给定 intrinsics 投影拳心与目标及半径；仅支持 none 或已有受支持 Brown 标定。Brown 所需 cv2 缺失时报说明，不自动替换标定。
- 固定日程和目标来自 manifest；所有方法共享预处理、拳心及阈值。按时间、手、目标作确定性一对一窗口匹配，额外落入已匹配窗口的预测单列 duplicates 并计 FP；null 表示零分母。

- [x] **Step 1: Write failing tests.** 两个标签窗口，一窗内两条预测及窗外一条预测：`assert (result["tp"], result["fp"], result["fn"], result["duplicates"]) == (1, 2, 1, 1)`；空预测/空标签分母为 null；重叠/共端点窗口、无效目标/时间/内参被拒绝；忽略区间同时排除预测和完全包含标签，部分相交拒绝；`test_each_method_sees_same_target_schedule`；`test_active_hand_switch_cannot_create_contact_entry`；重复运行除耗时外报告一致；读取录制 events 不改变真值。每个解析场景检查 spec 中相应区分，而非强求改进方法在所有场景都最好。
- [x] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_evaluation.py -q`。
- [x] **Step 3: Implement labels, methods and analytic scenarios.** 标签由独立几何/动作定义指定，使用独立代码核对预期事件；禁止从被测输出生成窗口。JSON 输出含证据类型、输入 SHA256、完整方法配置和场景级计数。manifest/输入格式错误转换为可操作 CLI 错误，无 traceback 泄露。
- [x] **Step 4: Run GREEN and reproducibility smoke.** `.venv\Scripts\python.exe -m depthstrike.evaluation --suite synthetic --output outputs/synthetic-comparison-UNIQUE.json`；报告声明 synthetic，指标与测试手算一致，输出拒绝覆盖。补测 external pose + labels 路径。
- [x] **Step 5: Commit task files.** `feat: add reproducible labeled interaction comparisons`。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--task-6-集成交付文档与独立审查"></a>
## Task 6: 集成、交付文档与独立审查

**Files:** Modify `README.md`, `PROJECT.md`, `docs/RUNNING.md`, `docs/VERIFICATION.md`, `docs/IMPLEMENTATION_NOTES.md`; add `docs/EVALUATION.md`; update integration tests where needed.

**Interfaces:** 前五项已冻结的 CLI、配置、版本 1/2 与实验标签格式；不在最后一项扩展玩法。

- [x] **Step 1: Add regression tests first.** 新引导演示 → 录制 → 回放的事件一致；legacy 240 帧仍 6 命中/60 分，旧 4 帧夹具仍 20 分；headless 不导入 SDK/MediaPipe/Open3D；无相机明确失败；不同新参数的 demo 仍可完成引导或明确报告不可达配置；暂停/失效/重置录制往返一致。
- [x] **Step 2: Run RED, then fix integration only.** 如测试暴露接口漏接，按最小范围补齐；不松动断轨、深度有效性或安全测试来获得通过。
- [x] **Step 3: Verify fresh outputs.** `.venv\Scripts\python.exe -m pytest -q`；可用时 `$env:DEPTHSTRIKE_GUI_TESTS='1'` 后再运行完整测试；`.venv\Scripts\python.exe -m pip check`；demo/两类回放/评估/metrics CLI；重新构建 wheel 并在隔离环境执行 headless smoke，核心只需 NumPy。
- [x] **Step 4: Document measured evidence and camera checklist.** 安装命令保持可执行；更新默认 guided 流程和 legacy 命令，给出 v2/标签字段、图形/音频可选项及性能计时口径。列出实机仍待验收的采集、对齐、遮挡、参数与延迟，不将本轮结果标为实机通过。
- [x] **Step 5: Request one fresh independent whole-branch review.** 按 requesting-code-review 技能提交明确 base/head、设计和验证记录。处理实际缺陷并增加回归，重跑受影响项与全套；若需改变产品范围先征询用户。
- [x] **Step 6: Final verification and local commit.** `git diff --check`、检查提交文件和 clean status；提交文档与最终修复。遵循 finishing-a-development-branch 技能汇报本地分支结果；不 push、合并或创建 PR，除非用户另行授权。

<a id="docs-superpowers-plans-2026-10-21-offline-interaction-refinement-md--计划自检"></a>
## 计划自检

- 六项原建议均有任务落点；真实设备验证明确延期而非宣称被离线替代。
- 引导和拳心只影响 guided；旧录制、旧安全边界及坐标约定保留。
- Review Focus 1–5 分别由任务 1、2、2、3/4、5 的具名测试覆盖。
- 执行方式沿用用户选择的当前会话逐模块开发、测试，最后独立审查；实现开始前需用户确认本设计与计划。

</details>

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md"></a>
## docs/superpowers/plans/2026-10-22-motion-studio-prototype.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--motion-studio-local-prototype-implementation-plan"></a>
# Motion Studio Local Prototype Implementation Plan

> **For agentic workers:** User authorized immediate local prototyping. Implement inline in this session. Use meaningful RED→GREEN tests for geometry, state and file boundaries; retain the existing root checkout preference.

**Goal:** 将 guided 骨架示范转为跨体型三维击球关卡，提供可运行的挑战和局部反事实复盘。

**Architecture:** 纯数值关卡／复盘与可选显示分离。复用既有校准、过滤、拳心和攻击状态；新回合仅在显式加载关卡时生效。

**Tech Stack:** 当前 Python 3.12、NumPy、pytest；可选 OpenCV/Open3D；无新依赖。

**Spec:** `docs/superpowers/specs/2026-10-22-motion-studio-prototype-design.md`

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--global-constraints"></a>
## Global Constraints

- 仅本地分支，不推送。
- 单相机米制坐标和有效连续时间；最多 32 靶、120 s；位置固定、不使用无效点或预测点计分。
- 输出独占创建，来源证据与 SHA-256 保留。
- 原有功能无关卡时保持兼容；核心无图形和设备依赖。

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--review-focus"></a>
## Review Focus

1. 无攻击、断轨和暂停不应被解释成可修正的空间未命中。
2. 时间窗边界、快速穿越和单攻击跨靶不能额外得分。
3. 体型重映射不能以尺度变换隐藏不可达／深度越界目标。
4. EOF、重置和失败导出不能伪装完整回合或覆盖旧文件。
5. 生成关卡不是独立实验标签；合成与 partial 必须保留。

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--task-1-数据与几何"></a>
## Task 1: 数据与几何

- [x] 先写手算尺度映射、格式拒绝、局部线段修正和越界拒绝测试，运行 RED。
- [x] 实现 `ChallengeRecipe.from_dict/load/to_dict/map_targets`、独占 JSON、最近线段与局部修正，运行 GREEN。

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--task-2-示范转关卡"></a>
## Task 2: 示范转关卡

- [x] 完成 guided 合成示范与中断用例；断言有效出拳顺序、归一化、来源标记，不依赖 events。
- [x] 实现 `author_recording(input_path)`，仅收录正式回合中完整收回的有效直拳，保留源文件哈希与参数。

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--task-3-挑战回合与复盘"></a>
## Task 3: 挑战回合与复盘

- [x] 测试顺序命中、空间偏差、无攻击／观测不足、时间窗、partial 和去重。
- [x] 实现 `ChallengeRound` 与条件委托，新增 CLI `--challenge` / `--review-output`；原功能不带参数时回归通过。

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--task-4-本地入口与可视化"></a>
## Task 4: 本地入口与可视化

- [x] 实现 `python -m depthstrike.studio author|demo|review`，合成示例完成整条链路。
- [x] 复盘视图显示正面／侧面轨迹、目标、最近点和局部修正；逐靶选择与动画播放；测试投影与非覆盖图像导出。
- [x] 实际运行显示窗口、核对截图，完善启动说明。

<a id="docs-superpowers-plans-2026-10-22-motion-studio-prototype-md--task-5-交付验证"></a>
## Task 5: 交付验证

- [x] 运行全套测试、依赖检查、全链路 CLI、实际显示和局部修正接触核验。
- [x] 记录本地试做结果与限制，保存本地提交；不推送。

最终证据及独立审查处理见 `docs/MOTION_STUDIO_VERIFICATION.md`。交付保留于本地开发分支，按用户要求不合并、不推送。

</details>

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md"></a>
## docs/superpowers/plans/2026-10-23-observation-aware-interaction.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--observation-aware-interaction-implementation-plan"></a>
# Observation-aware Interaction Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. User has authorized implementation of the list.

**Goal:** 可离线验证的深度融合、局部交互和空间展示扩展。
**Architecture:** 采集保持 RGB-D 边界，融合新增可选掩膜及短时历史；物理判定只消费观测点，显示预测独立传递。新配置显式启用，旧录制保持可重放。
**Tech Stack:** Python 3.12、NumPy、现有 OpenCV/MediaPipe/Open3D、pytest。
**Spec:** `docs/superpowers/specs/2026-10-23-observation-aware-interaction.md`

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--global-constraints"></a>
## Global Constraints

- 不运行真人测试，不下载模型、不推送；当前根目录工作。
- 不将预测作为观测，不跨时间缺口计分；保留旧配置行为。
- 合成输入只能支持软件逻辑验证。

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--review-focus"></a>
## Review Focus

- 对齐深度里另一部位/背景取代真实关节点。
- 时间倒退、长间隔、暂停与 reset 后预测残留。
- 部分追踪放开后跨失踪区间错误计分。
- 录制 provenance 丢失导致预测被重放为实测。
- 未知空间被误判为可通过、预览被误计分。

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--tasks"></a>
## Tasks

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--task-1-fusion-and-hand-observations"></a>
### Task 1: Fusion and hand observations

Files: types.py, config.py, fusion.py, pose.py, sources.py, interaction.py, recording.py; tests/test_adaptive.py.
Interfaces: Joint3D provenance/depth_quality/age_s; estimate_joint(..., mask=None, previous=None); fuse_skeleton(..., mask=None, previous=None); estimate_hand(joints, hand, config).
- [x] 写背景拒绝、掩膜空洞恢复、来源序列化与手部代理测试并运行 RED。
- [x] 实现并运行融合/适配器/录制测试 GREEN。

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--task-2-tracking-and-local-calibration"></a>
### Task 2: Tracking and local calibration

Files: tracking.py, calibration.py, boxing.py, config.py, types.py; tests/test_adaptive.py.
Interfaces: SkeletonTracker.display_joints; valid_hand(...); config partial_tracking/filter_mode/fist_mode; SceneState.display_joints.
- [x] 写预测失效、单侧校准与缺口恢复攻击测试，运行 RED。
- [x] 实现滤波、显示预测、按动作有效性与校准，运行 GREEN。

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--task-3-space-and-presentation"></a>
### Task 3: Space and presentation

Files: spatial.py, visualization.py, arena.py, app.py, configs/adaptive.json; tests/test_adaptive.py.
Interfaces: DepthWorkspace.path_status(start, end, radius); target_visibility_mask(...); calibration preview flag; simulation.set_workspace(...).
- [x] 写遮挡、未知路径和预览不计分测试，运行 RED。
- [x] 实现深度合成和布局检查、HUD 预测，运行 GREEN。

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--task-4-offline-report-and-model-selection"></a>
### Task 4: Offline report and model selection

Files: robustness.py, scripts/download_pose_model.py, docs/ADAPTIVE.md, docs/RUNNING.md; tests/test_adaptive.py, tests/test_adapters.py.
- [x] 写故障注入报告及模型 URL 选择测试，运行 RED。
- [x] 实现并运行报告和 600 帧无硬件演示。
- [x] 全仓 pytest、compileall、独立代码审查、修复重要发现，记录结果。

<a id="docs-superpowers-plans-2026-10-23-observation-aware-interaction-md--execution-ledger"></a>
## Execution ledger

Pre-flight: 现有根目录工作树干净，采用可选 adaptive 配置保持兼容；本轮以工作树改动交付，不包含 Git 操作。

Task 1: RED 4 个缺失接口；GREEN 75 passed（adaptive/fusion/recording/adapters/interaction）。
Task 2: RED 显示预测、单侧校准、对侧丢失与预测被提升；GREEN 67 passed（含 calibration/tracking/boxing/authoring/challenge）。
Task 3: RED 5 项；GREEN 48 passed, 1 GUI skipped（含空间检查/预览/校准/显示/app）。
Task 4: RED 变体与故障报告；GREEN 45 passed（adaptive/adapters）；600 帧 adaptive demo 9 hits/90 points，无摄像头。
Additional guards: RED 空洞恢复链、代理来源切换、Kalman 质量加权；加入对应实现后全仓 295 passed, 3 skipped（14.15 s）；GUI 验证和独立审查待收尾。

Final review: 独立只读审查 /root/adaptive_review，3 Important、0 Critical、0 Minor。原始快照发现：动作作者跨遮挡保留 pending；evaluation 未使用 hand 配置；Kalman 对缺失键保留旧状态并可能制造恢复后的虚假命中。
Final fix pass: 三项均增加失败用例并 RED→GREEN；另验证来源切换取消作者 pending、PunchTracker 直接拒绝 predicted 输入。修复后相关62项、作者与adaptive33项通过。最终完整验证见 docs/ADAPTIVE_VERIFICATION.md。
Final: Ruling: 真人定位、身体部位身份、Full/Heavy 性能与相机同步不由合成测试推断，遵循暂停真人测试的要求；成本：实机收益尚未验证。
Final: Ruling: 路径只采用当前视野离散采样，不宣称完整连续扫掠体积无障碍；成本：稀疏采样间的小障碍可能遗漏，因此不作安全保证。
Final: Ruling: 最终修复版依据本轮回归测试与全仓验证接收，未再派第二轮审查；成本：保留单次独立审查后的残余盲点。

Final verification: `DEPTHSTRIKE_GUI_TESTS=1 .venv/Scripts/python.exe -m pytest -q --basetemp=tmp/pytest-adaptive-verified --tb=short` → **303 passed in 23.03 s**, 0 skipped；compileall / pip check / diff --check 通过。本地工作树交付，未提交/合并/推送，未运行真人测试。

</details>

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md"></a>
## docs/superpowers/specs/2026-10-21-offline-interaction-refinement-design.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--无设备阶段的三维击球流程优化"></a>
# 无设备阶段的三维击球流程优化

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--1-目标与依据"></a>
## 1. 目标与依据

依据用户认可的六项优化建议，在现有 DepthStrike 原型上完善引导校准、拳部代理、空间反馈、性能观测、追踪质量管理和对比实验。用户暂时不能接入 Gemini 2，因此本阶段交付可离线验证的软件流程，不将模拟轨迹、空白 RGB-D 推理或软件计时解释为真实相机验收。

保留 Python、MediaPipe 关键点与实测深度融合、OpenCV/Open3D 的既有技术路线。范围不包括 Unity、蒙皮角色、虚拟对手、格挡闪避、多用户、替换骨架模型或独立安装程序。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--2-全局约束"></a>
## 2. 全局约束

- Python >=3.12,<3.13；沿用 pyproject.toml 中已固定的依赖，不新增强制依赖。
- 相机 X 向右、Y 向下、Z 向前，长度单位米，时间单位秒。
- 人体数据无效即取消攻击；不使用旧点、预测点或显示插值参与命中。
- 目标在校准完成后固定于相机空间，不随身体逐帧移动。
- 相机、合成演示、骨架回放、RGB-D 回放四种来源保持显式区分；相机失败不得切换成合成演示。
- 本阶段不接入相机、不升级固件、不修改全局 Python 环境，不 push、合并或创建 PR。
- 课程材料、原始人像、模型权重、环境和输出不进入普通 Git 历史。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--3-已确认需求与实现者选择"></a>
## 3. 已确认需求与实现者选择

已确认：按此前六项清单继续推进；先离线完善完整流程，后接入实测；不依赖 Unity。

以下为实现者选择，待用户审阅：默认启用新引导流程；保留 legacy 行为；摄像头叠加窗口作为主视图，三维窗口通过启动参数开启；先保留同步 RGB-D 推理，不在未测量时引入线程和丢帧策略；拳心采用可配置前臂延长代理，而非新增手指模型。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--4-引导流程与个体化校准"></a>
## 4. 引导流程与个体化校准

新流程：等待有效人体 → 稳定收拳 → 左手舒适前伸 → 收拳 → 右手舒适前伸 → 收拳 → 交替试击 → 倒计时 → 正式回合。

- 所有阶段均显示名称、进度和当前阻塞原因。前置设备/模型失败仍在现有边界报可操作错误。
- 只支持面向相机的轻缓直拳；不要求最大伸展或真实击打实物。提示保留活动空间、不靠近设备。
- 稳定收拳持续 0.6 s；中途关键点无效、时间不递增、间隔大于 0.2 s 或运动超限时重新累计，不将断轨前后样本拼接。
- 各手前伸时须肩、肘、腕有效，拳心相对肩部向相机前伸；超过收拳基线至少 0.10 m，并稳定 0.35 s。左右独立测量，收拳稳定 0.20 s 后才进入下一阶段。
- 前伸采样期间双肩相对中立参考位置偏移不得超过 0.06 m；超限只清除当前阶段的连续样本并提示恢复站位。各阶段的“有效人体”均要求双肩、双肘、双腕及两个拳心有效。
- 以参考肩部、舒适前伸量和目标系数生成目标：`center = reference_shoulder + (0, target_height_m, -0.85 * comfortable_extension_m)`。舒适前伸量使用拳心相对肩部的轴向距离，不用身体前移量代替。
- 每手的前伸量不得小于收拳基线 + 0.10 m；目标和代理球必须位于配置的有效深度范围内，否则保持引导并提示调整站位，不裁剪成假有效目标。
- 中立拳心到拟生成目标的距离必须大于两代理半径之和 + 0.02 m；否则拒绝该校准档案，提示舒适前伸量不足，不自动扩大半径或让收拳姿势与目标重叠。
- 每手收拳阈值为中立前伸量 + 0.04 m；攻击阈值为收拳阈值 + 0.5 ×（舒适前伸量 − 收拳阈值）。最小前伸行程为 `min(0.08 m, 0.25 ×（舒适前伸量 − 收拳阈值）)`；速度阈值沿用 0.65 m/s，可配置但不宣称个体最优。
- 练习阶段左右各完成一次有效命中，不增加正式得分、不消耗回合时间。完成后倒计时 2 s，并清空攻击状态；正式回合要求重新收拳激活。
- 暂停冻结引导进度、倒计时和回合时间；恢复后重新建立有效连续轨迹。重置清除校准、练习和得分。
- 暂停恢复时保留已完成的阶段和校准档案，但清除未完成的连续稳定样本；若在倒计时阶段失效或暂停，恢复有效收拳后重新倒计时 2 s，防止准备不足直接开局。
- 正式回合的追踪无效帧不计分、不跨缺口碰撞，并暂停回合计时；仅有效连续帧之间累计时间，恢复后要求收拳。该行为限于新模式，legacy 维持原语义。
- 合成演示增加对应引导动作，不自动绕过阶段；生成器在配置的合理参数范围内构造可达动作，无法满足的配置明确报错。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--5-拳心代理与追踪质量"></a>
## 5. 拳心代理与追踪质量

新增纯数值模块：`fist = wrist + offset_m * normalize(wrist - elbow)`，默认偏移 0.06 m，可设为零。它是表面交互代理，不是解剖拳心测量。拳心置信度取腕、肘最小值；任一无效、低置信度或前臂长度小于 0.02 m 时拳心无效。肩无效也不得激活该手攻击。

新模式的出拳、连续碰撞、轨迹和可视拳套统一使用同一拳心。骨架仍显示原始腕点；可视化可显示腕—拳心连线。legacy 使用原有腕点与阈值。

`Joint3D` 增加可选无效原因。融合区分关键点置信度不足、超出图像、中心深度无效、邻域不足、深度不连续；追踪层保留原因。没有关键点的情况使用明确缺失原因，不推测具体遮挡成因。

状态与反馈区分：缺少人体、校准中、可以出拳、需要收拳、速度不足、深度未接近、横向偏离、追踪无效、暂停、结束。原因是当前可观测条件，不声称唯一因果。反馈优先级：暂停/结束 → 追踪无效 → 引导 → 需收拳 → 速度/行程 → 空间差距 → 可击打。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--6-主交互视图与反馈"></a>
## 6. 主交互视图与反馈

- `--view overlay|dual`，默认 overlay；dual 增加 Open3D 辅助观察窗口。headless 不导入图形或 SDK。
- 主窗口保留真实 RGB 或明确标注的合成投影背景、骨架、拳心与目标；显示活动手、阶段、剩余时间、得分和阻塞原因。
- 对活动手给出两代理球表面间距 `norm(fist-target) - hand_radius - target_radius`、轴向差 `fist.z-target.z`（正值表示手仍在球后方）和横向偏差 `norm((fist-target)[:2])`；缺失时显示 unavailable，不显示上次测量。
- 目标用明暗、轮廓和接近指示增强深度感。二维外观不参与命中，也不承诺真实遮挡或照片级 AR。
- 命中提供绿色闪烁、单次提示与短轨迹。`--sound` 为可选 Windows 系统提示音，异步触发；不支持平台或音频失败时降级为可视反馈，不影响计分。
- 维持 Space 暂停、R 重置、Q/Esc 退出；关闭任一实际开启的窗口均释放资源并退出。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--7-渲染与性能观测"></a>
## 7. 渲染与性能观测

Open3D 常驻球体、骨架线与轨迹对象。更新顶点、位置和颜色，通过 update_geometry 刷新；正常连续帧不逐帧删除/创建网格。无效部位通过空几何隐藏，恢复时复用对象。目标重置或对象数量改变可重建相应对象，不影响判定。

新增 `--metrics PATH`，以独占创建方式输出 JSON：帧数、超时次数、软件阶段样本数、p50/p95/最大耗时、输入源与配置。CameraPoseSource 分别测量 capture/pose/fusion；会话测量 read/simulation/record/render/frame_total，read 与其子阶段不得叠加为总耗时。使用同一单调软件时钟；设备时间戳只用于顺序与动作时间，不与系统时钟直接相减。失败/提前退出也尽可能写出部分统计；已有输出不得覆盖。

本轮保留同步输入。是否拆分线程、采用容量 1–2 的最新帧队列，以后续真实测量决定；不能仅凭离线 FPS 承诺摄像头延迟。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--8-录制兼容性"></a>
## 8. 录制兼容性

新记录写 version 2，保存完整配置、新质量原因及引导相关控制。骨架回放重新执行确定性校准和规则；不使用记录中的命中事件作为真值。RGB-D 回放继续重新执行模型与融合。

version 1 可读且缺失新字段时明确选择 legacy，包括原腕点、固定目标与计时行为；保留现有 4 帧夹具的 2 命中/20 分。显式配置覆盖可以选择新模式，文档注明结果可能改变。所有现有路径、数组预分配限制、禁止 pickle、拒绝覆盖等安全边界保持。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--9-可复现对比实验"></a>
## 9. 可复现对比实验

新增独立命令 `python -m depthstrike.evaluation --suite synthetic --output PATH`；也可通过 `--input POSE_JSONL --labels MANIFEST --output PATH` 评价授权记录。无真实数据时仅输出 synthetic 证据，不生成真人精度结论。

标签清单声明来源 synthetic/recorded、固定目标及活动手时间表、相机内参、有效攻击的预期命中窗口（手、目标、起止时间）、忽略区间。它独立于被测输出；活动目标不随各方法得分改变，避免比较不同任务。真实标签需要人工提供并说明依据，不从原录制 events 自动生成。

比较 2D 接触进入事件、3D 单帧接触进入事件、3D 连续接触进入事件、3D 连续接触加攻击状态机。前三者使用接触上升沿，不能人为设置为停留每帧计分。共享输入、拳心、目标与过滤配置，差异仅来自指定组件；暂不加入平滑优劣的自动结论。

预测按时间排序，同手同目标且处于窗口内的一条预测匹配一个未匹配标签；其余为误触发/重复候选。命中与忽略窗口均为闭区间；同手同目标的标签窗口不得重叠或共用端点。忽略区间内的预测和完全包含其中的标签不参与计数；标签只与忽略区间部分相交时拒绝清单，避免含混裁剪。活动手时间表采用不重叠的左闭右开区间，切换不能虚构接触上升沿。

输出 TP/FP/FN、重复计数、precision/recall（分母零时 null）、样本与标签数、追踪无效比例、每个场景明细、方法参数、输入 SHA256 与证据类型；不把软件耗时当端到端延迟。空数据、相互重叠的同手同目标标签窗口、无效目标、内参/单位/时间错误应明确拒绝。

小型解析场景覆盖深度错位、快速穿越、正常左右拳、慢伸手、停留及再进入、追踪丢失后恢复。预期窗口由场景几何和动作定义编写，不调用被测算法生成。

<a id="docs-superpowers-specs-2026-10-21-offline-interaction-refinement-design-md--10-验收与后续实机边界"></a>
## 10. 验收与后续实机边界

离线验收：新阶段推进及冻结；不同可达范围目标个体化且不跟随身体；拳心一致性；缺肘/肩和深度跳变不误计分；版本 1/2 回放确定性；窗口生命周期；稳定帧无几何增删；阶段耗时使用假时钟核对；合成对比报告可复现；旧安全回归仍通过。

实机待验收：Gemini 2 采集与对齐、骨架/拳心误差、舒适校准的易用性、遮挡与背景误读、真实处理延迟、参数适用性。接入后应先短时录制和回放，再调参；不能保证本轮离线工作消除所有设备问题。

</details>

<a id="docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md"></a>
## docs/superpowers/specs/2026-10-22-motion-studio-prototype-design.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md--动作关卡与三维复盘本地试做"></a>
# 动作关卡与三维复盘：本地试做

用户已授权按选题建议开始本地试做。本轮沿用 Python、现有依赖和根目录，开发分支为 `codex/motion-challenge-prototype`。具体交互与数值为本轮实现选择。

<a id="docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md--可体验的流程"></a>
## 可体验的流程

1. 从完成 guided 校准的骨架录制中提取已收回的有效直拳；不以 recorded events 作标签。
2. 保存左右手顺序、峰值前伸位置与节奏，生成独立的版本化关卡 JSON。
3. 根据挑战者本轮校准的肩宽、各手舒适前伸范围，将归一化靶位固定映射到相机空间。
4. 按固定时间窗击球，继续采用真实拳心、有效出拳、跨帧碰撞与单攻击去重。
5. 输出逐靶复盘：命中、空间未命中、无有效攻击、观测不足；显示最近轨迹段及有条件的局部修正。
6. 提供不接相机的一键合成示例，以及可浏览各次尝试的正面／侧面轨迹视图。

<a id="docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md--范围与边界"></a>
## 范围与边界

- 首次仅支持单人、顺序直拳关卡；重叠时间窗、无完成校准或无完整出拳的来源明确拒绝。
- 原 guided／legacy 不带关卡时的行为保持现有测试契约。
- 无新增依赖。关卡、报告使用独占创建；原始录制、输出和截图继续由现有忽略规则管理。
- 合成输入及派生文件持续标明 synthetic；保留来源 SHA-256、配置、归一化尺度和提取规则。生成关卡不是独立真值，回放命中率不能充当真人精度。
- 归一化：每手拳心相对参考肩部的 x/y 位移除以参考肩宽，z 位移除以该手舒适前伸量。重映射使用挑战者的同类尺度，映射后每个目标固定。
- 关卡最多 32 靶，时间范围不超过 120 s，单靶窗口以演示峰值为中心：提前 0.40 s、延后 0.45 s；末端裁至源配置的回合时长，相邻窗口相交时在两个峰值的中点拆分。相同峰值时间拒绝。
- 目标球须处于深度范围，且不与中立拳心重叠、不超出舒适触达距离；失败拒绝该关卡，不裁剪成可用目标。
- 时间由新模式的有效回合时间驱动，暂停／失效不推进；被中断的当前尝试标记观测不足。恢复帧不桥接，需收拳。
- 出拳条件的首次满足时间由相邻前伸量线性插值；仅在有效攻击区间、连续观测和靶位活动窗口的交集中结算。最后一个有效帧先结算再结束，不将跨越截止时刻的帧压缩到截止时刻。
- 反事实仅用于完整可观测且有有效攻击的空间未命中：求最近有效轨迹段到球心的距离，以两代理半径计算局部平移，加入 1 mm 接触余量。平移后段的两端必须处于保守触达球与深度范围，重新运行纯几何碰撞核验。触达球半径直接使用舒适前伸量，不加拳心半径，也不代表完整人体可达空间。
- 该修正仅说明固定时机／攻击状态下的局部几何接触，不能证明整个人体动作可执行，也不是拳击技术指导。缺帧、慢伸手、未收拳和未完成窗口均不生成空间修正。
- EOF／提前退出导出 partial 报告，未完成窗口标为 incomplete；不将其当作失败。
- 关卡运行默认到最后一个时间窗结束；独立复盘窗口可逐靶选择并动画查看轨迹。
- 本地演示同时提供原始合成作者和带部分空间偏差的合成挑战者，偏差只出现在正式回合；可以看到命中与空间未命中的不同结果。

<a id="docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md--模块"></a>
## 模块

- `motion_challenge.py`：关卡格式、验证、归一化、重映射与非覆盖 JSON。
- `motion_authoring.py`：骨架来源到完整有效出拳的提取。
- `counterfactual.py`：最近线段和局部几何修正。
- `challenge_round.py`：固定靶序列、计分、轨迹采样和逐靶报告。
- `studio.py`：author／demo／review 本地入口。
- `review_view.py`：正面与侧面轨迹、修正段和播放控制。
- 既有 `BoxingSimulation` 仅在显式传入关卡时委托新回合；CLI 增加关卡与报告路径。

<a id="docs-superpowers-specs-2026-10-22-motion-studio-prototype-design-md--验收"></a>
## 验收

手算几何与尺度映射；动作不依赖录制得分；断轨／控制不拼接；关卡与报告往返及拒绝覆盖；已有 210 项测试；新 CLI 合成作者→关卡→挑战→复盘完整运行，实际窗口检查与截图。本轮交付标记为本地试做，不推送远程。

</details>

<a id="docs-superpowers-specs-2026-10-23-observation-aware-interaction-md"></a>
## docs/superpowers/specs/2026-10-23-observation-aware-interaction.md

<details>
<summary>展开原始记录</summary>

<a id="docs-superpowers-specs-2026-10-23-observation-aware-interaction-md--可观测性驱动的交互扩展"></a>
# 可观测性驱动的交互扩展

本轮按已批准的技术清单在根目录本地实现；暂停真人测试，不下载模型、不推送远程。

<a id="docs-superpowers-specs-2026-10-23-observation-aware-interaction-md--交付范围"></a>
## 交付范围

- 保留旧配置和录制行为；新增 `configs/adaptive.json` 显式启用扩展。
- 人体掩膜约束的局部深度融合。中心深度空洞只在新鲜的同名历史深度、足够局部支持和单一深度表面同时成立时恢复；不能把任意背景作为手的位置。
- 从已有 Pose 的手部点估计交互点，缺少手部观测时沿用肘腕代理。记录来源和深度质量。
- One Euro 可选滤波；有限时长、带来源的显示预测。预测不能进入校准、碰撞、录制真值或跨缺口攻击。
- 按手检查动作条件，逐侧完成前伸校准；丢失另一侧时可继续当前侧的普通击球。Motion Studio 对比仍采用完整观测协议。
- 校准期间预览目标、局部追踪状态、深度遮挡合成。预览目标不计分。
- 基于可见深度的目标路径检查：未知区域拒绝作为已知空闲；只在校准布局阶段拒绝被障碍阻挡的目标，不在攻击中移动目标。
- Full/Heavy 模型下载选择入口和对比说明，不声称本机性能；RTMPose/CoTracker3 作为备选，不在本轮强制增加大依赖。
- 离线故障注入与可重复报告，覆盖丢点、深度空洞、背景混合、时间异常、恢复后误计分；合成结果不代表真实识别准确率。

<a id="docs-superpowers-specs-2026-10-23-observation-aware-interaction-md--验收"></a>
## 验收

现有测试通过；新增测试验证融合不会取错背景、预测不能得分、恢复不能跨缺口击中、单侧校准保留进度、障碍和未知空间拒绝。通过 CLI 演示与合成报告，无摄像头。

</details>

<a id="docs-tracking-verification-2026-10-31-md"></a>
## docs/TRACKING_VERIFICATION_2026-10-31.md

<details>
<summary>展开原始记录</summary>

<a id="docs-tracking-verification-2026-10-31-md--追踪跳变与校准恢复验证2026-10-31"></a>
# 追踪跳变与校准恢复验证（2026-10-31）

用户反馈：骨架或目标位置抖动、跳走，影响校准与持续追踪。

<a id="docs-tracking-verification-2026-10-31-md--修改"></a>
## 修改

- 姿态关键点保留自身可见度与存在置信度，人体掩膜在深度融合阶段检查局部支持，避免单个掩膜像素导致关节反复失效。深度有效比例、表面一致性与中心空洞恢复约束保留。
- `adaptive.json` 开启滤波前的位置跳变检查。躯干与手臂使用不同的允许速度；参照来自近期接受的原始观测，拒绝的跳变不更新参照，避免滤波滞后造成连锁误拒绝。参照会过期，不会无限锁死旧位置。
- 一个关节缺失时，其他有效关节继续滤波。
- 校准短暂丢点时保留 0.20 秒宽限内的稳定采样进度，仅累计有效且连续的观测间隔；恢复首帧和缺失时间不补入保持时长。暂停、长时间缺失和位置明显变化仍重置当前采样段，倒计时仍在中断后重新开始。
- 校准目标预览可使用最多 0.20 秒的显示预测，躯干预测限制速度。预测点和预览目标不参与正式计分，已完成校准的正式目标仍保持固定。

<a id="docs-tracking-verification-2026-10-31-md--软件验证"></a>
## 软件验证

执行完整测试，开启 `DEPTHSTRIKE_GUI_TESTS=1`，结果为 **362 passed**。覆盖真实窗口、中文显示、校准阶段、快速出拳、丢失后恢复、拒绝跨缺口计分、回放与录制兼容。

新增的合成故障验证包括：

- 注入一次 0.8 米横向跳变，9 个异常关节被拒绝，校准进度保持 50%，目标预览最大位移为 0 米；下一帧正常输入恢复 9 个有效关节。
- 每五帧缺失一次手腕，零宽限的稳定保持阶段无法完成；开启宽限后可完成初始保持。
- 连续快速手部运动可通过检查，正常出拳仍可计分；异常手腕位置及其恢复不能直接跨缺口生成命中。
- 一直交替缺失、恢复时，不会把缺失时间累计成完整保持时间。

合成预览和统计保存在本机 `tmp/tracking-stability-20261031/`。这些结果验证软件行为，不代表真人定位精度或身份锁定能力。阈值为工程参数，尚未通过真人数据标定。

<a id="docs-tracking-verification-2026-10-31-md--相机状态"></a>
## 相机状态

本次 Astra 短测返回：预期的 `2bc5:060f` 深度设备数量为 0。随后只读检查 Windows 在线设备，也没有发现名称包含 ORBBEC 或 Astra 的设备。因此本次没有完成真人追踪效果对比，没有保存相机图像或人体轨迹，也没有修改驱动。

重新连接并确认设备在线后，按 [Astra 启动说明](#docs-astra-md) 运行，按 `R` 重新校准。需继续观察正常站立时的骨架抖动、快速出拳的跟随、遮挡恢复和实际校准完成率。

</details>

<a id="docs-verification-md"></a>
## docs/VERIFICATION.md

<details>
<summary>展开原始记录</summary>

<a id="docs-verification-md--验证记录"></a>
# 验证记录

日期：2026-10-21（Asia/Hong_Kong），v0.2.0 离线流程迭代。范围为三维目标击打，不含完整虚拟对手、格挡/闪避或独立 exe 发行。

<a id="docs-verification-md--环境"></a>
## 环境

- Windows 11 x64，系统版本 10.0.26200；Python 3.12.7，项目独立 `.venv`。
- NumPy 2.2.6、MediaPipe 0.10.32、Orbbec Python SDK 2.1.2、Open3D 0.19.0、OpenCV 4.11.0.86、pytest 8.3.5。
- `pip check`：无依赖冲突。旧版 MediaPipe 0.10.21 与新版 SDK 在 Python 3.12 的 NumPy 约束冲突，故未采用该组合。
- 上轮 Gemini SDK 枚举结果：0 台设备。本轮按用户要求未接入相机；固件、真实流配置和人体性能待设备测试。
- 模型：Pose Landmarker Lite，float16，版本 1，5,777,746 bytes。
- SHA-256：`59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`。

<a id="docs-verification-md--证据分层"></a>
## 证据分层

| 项目 | 结果 | 证据与边界 |
| --- | --- | --- |
| 几何与状态规则 | 通过 | 相切、初始重叠、快速扫掠、深度错位、停留、复位和断轨测试 |
| 深度融合 | 合成验证通过 | 已知内参反投影、邻域空洞/跳变与置信度拒绝；不代表真实定位精度 |
| 引导与个体化目标 | 离线通过 | 收拳、左右舒适前伸、收回、无分数试击、倒计时；不同可达范围对应不同目标，生成后不随身体移动 |
| 拳心与质量状态 | 离线通过 | 腕—肘外推代理统一用于判定与显示；缺失肩/肘、深度失效、断轨、恢复和暂停取消攻击；不延用旧距离 |
| 固定目标与回合 | 通过 | 左右交替、单次攻击去重；新模式无效帧暂停计时，恢复必须收拳；重置与引导演示恢复往返一致 |
| 无窗口演示 | 通过 | guided 600 帧、9 命中、90 分；legacy 240 帧仍为 6 命中、60 分；两类配置各自保持录制回放一致 |
| 图形场景 | 通过 | 实际 overlay CLI 300 帧取得 10 分；实际 dual 300 帧显示；截图核对拳心、空间提示、阶段和目标 |
| 几何复用 | 通过 | 真实 Open3D 几何＋替身显示边界，连续 100 帧无对象增删；失效隐藏后同对象恢复，顶点位置无累积漂移 |
| 默认视角 | 通过 | 真实窗口投影回归测试；修正坐标轴几何重置场景边界框的问题 |
| 实际姿态模型 | 冒烟验证通过 | 官方模型在中文目录加载并处理合成空白 RGB；无人体时输出空关键点，不代表人体检测效果 |
| 轨迹及 RGB-D 编码 | 通过 | 往返、时间倒退、非法版本、非有限数、路径越界、对象数组、空文件及伪造大形状拒绝 |
| RGB-D 正式回放入口 | 冒烟验证通过 | CLI 读取 3 帧合成空白 RGB-D，执行实际模型，0 分；不代表人体数据 |
| 本地打包 | 通过 | v0.2.0 wheel；在不继承系统 site-packages、仅有 pip/NumPy/本包的隔离环境安装，以 `-I` 运行 600 帧/90 分和全部合成评估；未发行 exe |
| 软件阶段计时 | 通过 | 假时钟核对嵌套阶段与回放等待排除；容量 4096、partial 帧/超时计数、独占输出；实际 demo 与 RGB-D 回放生成 JSON |
| 独立标签评估 | 合成通过 | 7 个解析场景、34 帧、6 个有效攻击窗口；四方法固定日程、相同预处理；外部标签例含 2 个手工核对窗口 |
| 无相机诊断 | 回归通过 | 替身设备边界和故障路径仍明确失败且不回退 demo；本轮不重复连接／枚举实机 |
| 真实 RGB-D 采集/对齐 | 未测 | 需要 Gemini 2 连接与官方 Viewer 基线 |
| 真实人体三维击球 | 未测 | 需要设备、参与者授权、空间测量和独立标签 |
| 窗口关闭/按键交互 | 软件通过 | 实际主窗口／三维窗口分别关闭，主循环均在 1 帧后退出且输入已关闭；暂停、重置、断轨和回放有集成测试；真人操作待复核 |

本轮独立审查后完整验收启用真实显示专项：**210 项通过，无跳过**（13.96 s）。默认运行跳过 3 项真实显示测试；无模型时实际模型冒烟也跳过，跳过不算通过。可复现命令见 [RUNNING.md](../RUNNING.md)。

审查新增 9 个回归用例：RGB-D 转录的合成来源保留，目标日程启停边界的候选时间判定，垂直／侧向不可达目标拒绝，以及下载说明文件的预检查和并发独占创建。均先复现失败再修复；原有激活重叠、断轨及兼容性测试保持通过。

审查后重新构建 wheel（45,659 bytes），SHA-256：`2af425889710999ed40e55ffdbd8d4b2a502dedf32786a386be26815e8b2f924`。在既有隔离冒烟环境中替换安装，`python -I` 下演示仍为 600 帧／90 分，7 个合成评估场景无需图形、模型或设备依赖。实际模型再次处理 3 帧合成空白 RGB-D，转存的骨架和阶段报告均保留 synthetic 标记。

独立审查与实施取舍见 [IMPLEMENTATION_NOTES.md](#docs-implementation-notes-md)。背景污染误计分、数组声明分配、SDK 断连异常及低帧率回放均有失败后修复的回归测试。

<a id="docs-verification-md--复现边界"></a>
## 复现边界

合成轨迹覆盖解析可知的交互条件，不能据此报告真实误触发率、运动识别准确率或毫米级精度。`processing_s` 仅表示软件会话时间，不是从曝光到显示的端到端延迟。MediaPipe 输出只取归一化图像位置；身体局部 world landmarks 不参与相机空间定位。

当前采用可见表面深度代理点。人体分割置信度、关键点置信度、邻域有效率和深度跳变筛选无法消除所有遮挡与背景误读。正面直拳也可能遮挡肩/腕，追踪无效时取消攻击，必须收回后再激活。

拳心外推尚未与真实拳头中心对照；舒适范围校准、0.06 m 外推偏移、速度与状态阈值均是工程设计而非人体实测最优值。主窗口的球体深度线索不包含真实遮挡或照片级 AR。

合成评估中的连续碰撞＋状态机在 6 个预设正例窗口上无误触发／漏检，只说明这些解析用例符合设计。不能写成真实识别准确率 100%，也不能从该构造性样本选择最优模型。

真实设备验收应记录：设备型号/序列匿名标识、固件、RGB/深度流、内参/畸变、同步误差、有效深度率、处理帧率、失败样例；之后再调整默认阈值。不得将合成或空帧验证写为设备联调通过。

</details>
