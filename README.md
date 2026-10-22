# DepthStrike

**RGB-D Skeleton-Guided Combat Simulation**

DepthStrike 是面向三维体感格斗的视觉交互项目。以人体关键点检测与实测深度融合为基础，设计人体动作的空间映射、三维碰撞检测与攻防判定方法。

项目以目标球击打为验证场景，关注深度差异、快速运动与追踪失效对交互判定的影响。使用纯 Python，不依赖 Unity。

## 技术路线

RGB-D 采集与对齐 → 人体关键点检测 → 深度反投影 → 拳部代理与轨迹处理 → 连续碰撞与出拳判定。

通过 Orbbec Gemini 2 获取彩色图像与深度数据，结合人体关键点的图像位置及相机参数，估计统一坐标下的三维交互点。在此基础上，引入轨迹平滑、有效性筛选与跨帧碰撞检测，建立接触事件与攻防规则之间的对应关系。

## 交互场景

- 基于舒适触达范围的引导校准、试击与回合管理。
- 统一坐标下的拳部代理、空间距离反馈与连续碰撞。
- 左右交替击球、攻击复位、追踪失效抑制与单次结算。
- RGB-D／骨架回放、软件阶段计时与独立标签对比。

## 评估设计

比较二维接触、三维单帧接触、三维连续接触及连续接触结合出拳状态机。各方法共享输入、预处理与固定目标日程，依据独立标签统计误触发、漏检、重复结算和追踪无效率。合成场景用于验证方法差异，不代表真实人体精度；实验入口见 [评估说明](docs/EVALUATION.md)。

## 运行

Python 3.12，纯 Python 场景，不依赖 Unity。安装依赖后运行：

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo
.venv\Scripts\python.exe -m depthstrike --source demo --view dual
```

默认显示主交互画面；`--view dual` 额外开启三维辅助视图。`--source demo` 为合成动作，`--source camera` 才读取 Gemini 2。真实采集、对齐和人体击球仍待设备验收。安装、模型下载、录制回放和按键见 [运行文档](docs/RUNNING.md)，证据边界见 [验证记录](docs/VERIFICATION.md)。

本地 `0.3.0.dev0` 分支增加动作关卡与三维复盘试验。运行 `python -m depthstrike.studio demo --output outputs/studio-try` 可生成并体验合成示例；操作、关卡生成及证据边界见 [Motion Studio](docs/MOTION_STUDIO.md)。

## 实现方案

采用 Python，结合 Orbbec SDK、MediaPipe Pose、NumPy、OpenCV 与 Open3D，测试使用 pytest。首期采用几何代理构建交互场景，不依赖 Unity。

简化对手与格挡、闪避列为后续扩展。详细技术设计和验收标准见 [PROJECT.md](PROJECT.md)，第三方来源见 [THIRD_PARTY.md](docs/THIRD_PARTY.md)。
