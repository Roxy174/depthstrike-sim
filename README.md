# DepthStrike

**An RGB-D Skeleton-Guided Combat Simulator**

基于 Orbbec Gemini 2、人体关键点检测与实测深度融合的三维体感格斗交互模拟器。

## 项目状态

当前处于设计与仓库初始化阶段，尚未实现可运行的模拟器。首期采用 Python，不依赖 Unity。完整设计、技术边界与验收标准见 [PROJECT.md](PROJECT.md)。

## 技术路线

RGB-D 采集与对齐 → 人体关键点检测 → 三维交互点融合 → 轨迹处理 → 碰撞与攻防判定 → 可视化与记录回放。

- 硬件：Orbbec Gemini 2。
- 计划使用：Orbbec SDK、MediaPipe Pose、NumPy、OpenCV、Open3D、pytest。
- SDK、固件、Python 与依赖版本在设备验证后固定；当前没有可执行的安装或启动命令。

## 开发阶段

- [ ] M0：环境、RGB-D 采集、对齐与短时录制回放。
- [ ] M1：人体关键点追踪与有效状态显示。
- [ ] M2：不同深度的虚拟小球与三维命中判定。
- [ ] M3：有效出拳、跨帧轨迹碰撞及重复计分抑制。
- [ ] M4：简化虚拟对手、格挡、闪避与回合管理。
- [ ] M5：对比实验、无硬件回放、打包与最终报告。

## 仓库与数据管理

- 远程仓库：[Roxy174/depthstrike-sim](https://github.com/Roxy174/depthstrike-sim)，可见性为 Private。
- 本地仓库按团队决定直接位于 `D:\3D视觉` 根目录。
- 课程材料目录 `Shares/`、`$dst/`、原始采集、模型权重、输出及环境文件由 `.gitignore` 排除，仅保留在本地。
- 小型合成测试夹具、默认配置和数据获取说明可以提交；不要把所有课程资料或人像录制加入 Git。
- 新功能通过短期分支与小规模 Pull Request 管理，`main` 保持与实际实现状态一致。

项目名称为工作名，不声称提出了新的骨架追踪算法。第三方代码、模型与素材的来源和许可将在使用时记录。
