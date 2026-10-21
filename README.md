# DepthStrike

**RGB-D Skeleton-Guided Combat Simulation**

DepthStrike 是面向三维体感格斗的视觉交互项目。以人体关键点检测与实测深度融合为基础，设计人体动作的空间映射、三维碰撞检测与攻防判定方法。

项目关注深度差异、快速运动与局部遮挡对交互判定的影响，以简化场景验证人体动作与虚拟目标之间的空间关系。

## 技术路线

RGB-D 采集与对齐 → 人体关键点检测 → 深度反投影 → 三维轨迹估计 → 碰撞检测与攻防判定。

通过 Orbbec Gemini 2 获取彩色图像与深度数据，结合人体关键点的图像位置及相机参数，估计统一坐标下的三维交互点。在此基础上，引入轨迹平滑、有效性筛选与跨帧碰撞检测，建立接触事件与攻防规则之间的对应关系。

## 交互场景

- 人体三维交互点估计与可视化。
- 基于空间距离和运动轨迹的目标击打判定。
- 左右交替的目标球击打、攻击复位、计分与回合管理。
- 交互记录、离线回放与回合结果分析。

## 评估设计

重点比较二维与三维接触判定、逐帧与跨帧碰撞检测的差异，并评估轨迹平滑对静止抖动与处理延迟的影响。评价指标包括误触发率、漏检率、重复结算次数及追踪无效率。

## 运行

Python 3.12，纯 Python 场景，不依赖 Unity。安装依赖后运行：

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo
```

相机入口为 `--source camera`。安装、模型下载、录制回放和按键说明见 [运行文档](docs/RUNNING.md)，测试边界见 [验证记录](docs/VERIFICATION.md)。

## 实现方案

采用 Python，结合 Orbbec SDK、MediaPipe Pose、NumPy、OpenCV 与 Open3D，测试使用 pytest。首期采用几何代理构建交互场景，不依赖 Unity。

简化对手与格挡、闪避列为后续扩展。详细技术设计和验收标准见 [PROJECT.md](PROJECT.md)，第三方来源见 [THIRD_PARTY.md](docs/THIRD_PARTY.md)。
