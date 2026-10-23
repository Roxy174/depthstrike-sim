# Observation-aware Interaction Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. User has authorized implementation of the list.

**Goal:** 可离线验证的深度融合、局部交互和空间展示扩展。
**Architecture:** 采集保持 RGB-D 边界，融合新增可选掩膜及短时历史；物理判定只消费观测点，显示预测独立传递。新配置显式启用，旧录制保持可重放。
**Tech Stack:** Python 3.12、NumPy、现有 OpenCV/MediaPipe/Open3D、pytest。
**Spec:** `docs/superpowers/specs/2026-10-23-observation-aware-interaction.md`

## Global Constraints

- 不运行真人测试，不下载模型、不推送；当前根目录工作。
- 不将预测作为观测，不跨时间缺口计分；保留旧配置行为。
- 合成输入只能支持软件逻辑验证。

## Review Focus

- 对齐深度里另一部位/背景取代真实关节点。
- 时间倒退、长间隔、暂停与 reset 后预测残留。
- 部分追踪放开后跨失踪区间错误计分。
- 录制 provenance 丢失导致预测被重放为实测。
- 未知空间被误判为可通过、预览被误计分。

## Tasks

### Task 1: Fusion and hand observations

Files: types.py, config.py, fusion.py, pose.py, sources.py, interaction.py, recording.py; tests/test_adaptive.py.
Interfaces: Joint3D provenance/depth_quality/age_s; estimate_joint(..., mask=None, previous=None); fuse_skeleton(..., mask=None, previous=None); estimate_hand(joints, hand, config).
- [x] 写背景拒绝、掩膜空洞恢复、来源序列化与手部代理测试并运行 RED。
- [x] 实现并运行融合/适配器/录制测试 GREEN。

### Task 2: Tracking and local calibration

Files: tracking.py, calibration.py, boxing.py, config.py, types.py; tests/test_adaptive.py.
Interfaces: SkeletonTracker.display_joints; valid_hand(...); config partial_tracking/filter_mode/fist_mode; SceneState.display_joints.
- [x] 写预测失效、单侧校准与缺口恢复攻击测试，运行 RED。
- [x] 实现滤波、显示预测、按动作有效性与校准，运行 GREEN。

### Task 3: Space and presentation

Files: spatial.py, visualization.py, arena.py, app.py, configs/adaptive.json; tests/test_adaptive.py.
Interfaces: DepthWorkspace.path_status(start, end, radius); target_visibility_mask(...); calibration preview flag; simulation.set_workspace(...).
- [x] 写遮挡、未知路径和预览不计分测试，运行 RED。
- [x] 实现深度合成和布局检查、HUD 预测，运行 GREEN。

### Task 4: Offline report and model selection

Files: robustness.py, scripts/download_pose_model.py, docs/ADAPTIVE.md, docs/RUNNING.md; tests/test_adaptive.py, tests/test_adapters.py.
- [x] 写故障注入报告及模型 URL 选择测试，运行 RED。
- [x] 实现并运行报告和 600 帧无硬件演示。
- [x] 全仓 pytest、compileall、独立代码审查、修复重要发现，记录结果。

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
