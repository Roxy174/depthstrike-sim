# Motion Studio Local Prototype Implementation Plan

> **For agentic workers:** User authorized immediate local prototyping. Implement inline in this session. Use meaningful RED→GREEN tests for geometry, state and file boundaries; retain the existing root checkout preference.

**Goal:** 将 guided 骨架示范转为跨体型三维击球关卡，提供可运行的挑战和局部反事实复盘。

**Architecture:** 纯数值关卡／复盘与可选显示分离。复用既有校准、过滤、拳心和攻击状态；新回合仅在显式加载关卡时生效。

**Tech Stack:** 当前 Python 3.12、NumPy、pytest；可选 OpenCV/Open3D；无新依赖。

**Spec:** `docs/superpowers/specs/2026-10-22-motion-studio-prototype-design.md`

## Global Constraints

- 仅本地分支，不推送。
- 单相机米制坐标和有效连续时间；最多 32 靶、120 s；位置固定、不使用无效点或预测点计分。
- 输出独占创建，来源证据与 SHA-256 保留。
- 原有功能无关卡时保持兼容；核心无图形和设备依赖。

## Review Focus

1. 无攻击、断轨和暂停不应被解释成可修正的空间未命中。
2. 时间窗边界、快速穿越和单攻击跨靶不能额外得分。
3. 体型重映射不能以尺度变换隐藏不可达／深度越界目标。
4. EOF、重置和失败导出不能伪装完整回合或覆盖旧文件。
5. 生成关卡不是独立实验标签；合成与 partial 必须保留。

## Task 1: 数据与几何

- [x] 先写手算尺度映射、格式拒绝、局部线段修正和越界拒绝测试，运行 RED。
- [x] 实现 `ChallengeRecipe.from_dict/load/to_dict/map_targets`、独占 JSON、最近线段与局部修正，运行 GREEN。

## Task 2: 示范转关卡

- [x] 完成 guided 合成示范与中断用例；断言有效出拳顺序、归一化、来源标记，不依赖 events。
- [x] 实现 `author_recording(input_path)`，仅收录正式回合中完整收回的有效直拳，保留源文件哈希与参数。

## Task 3: 挑战回合与复盘

- [x] 测试顺序命中、空间偏差、无攻击／观测不足、时间窗、partial 和去重。
- [x] 实现 `ChallengeRound` 与条件委托，新增 CLI `--challenge` / `--review-output`；原功能不带参数时回归通过。

## Task 4: 本地入口与可视化

- [x] 实现 `python -m depthstrike.studio author|demo|review`，合成示例完成整条链路。
- [x] 复盘视图显示正面／侧面轨迹、目标、最近点和局部修正；逐靶选择与动画播放；测试投影与非覆盖图像导出。
- [x] 实际运行显示窗口、核对截图，完善启动说明。

## Task 5: 交付验证

- [x] 运行全套测试、依赖检查、全链路 CLI、实际显示和局部修正接触核验。
- [x] 记录本地试做结果与限制，保存本地提交；不推送。

最终证据及独立审查处理见 `docs/MOTION_STUDIO_VERIFICATION.md`。交付保留于本地开发分支，按用户要求不合并、不推送。
