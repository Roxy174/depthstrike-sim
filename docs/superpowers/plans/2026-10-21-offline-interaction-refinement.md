# Offline Interaction Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Preserve the user's choice of inline implementation in the current session, followed by independent final review.

**Goal:** 在不接入 Gemini 2 的条件下实现可离线验收的个体化击球流程、清晰反馈、渲染更新、性能记录及受控对比实验。

**Architecture:** 在既有输入和几何边界上增加拳心代理、独立引导状态机及结构化反馈；BoxingSimulation 负责统一结算。显示、计时统计和实验比较不反向决定游戏结果；版本化录制保留旧行为。

**Tech Stack:** Python 3.12、NumPy 2.2.6、pytest 8.3.5；复用现有 OpenCV 4.11.0.86、Open3D 0.19.0、MediaPipe 0.10.32 和 pyorbbecsdk2 2.1.2。

**Spec:** `docs/superpowers/specs/2026-10-21-offline-interaction-refinement-design.md`

## Global Constraints

- Python >=3.12,<3.13；沿用 pyproject.toml 中已固定的依赖，不新增强制依赖。
- 相机 X 向右、Y 向下、Z 向前，长度单位米，时间单位秒。
- 人体数据无效即取消攻击；不使用旧点、预测点或显示插值参与命中。
- 目标在校准完成后固定于相机空间，不随身体逐帧移动。
- 相机、合成演示、骨架回放、RGB-D 回放四种来源保持显式区分；相机失败不得切换成合成演示。
- 本阶段不接入相机、不升级固件、不修改全局 Python 环境，不 push、合并或创建 PR。
- 课程材料、原始人像、模型权重、环境和输出不进入普通 Git 历史。

## Review Focus

1. 旧版记录缺少新配置或质量原因：仍选择 legacy 并重现原事件，不静默切换 guided。
2. 校准中暂停、缺肩/肘、重复时间戳或长间隔：不累计断开的稳定时间，不留下可得分的旧拳心。
3. 可达范围过小、身体移动或目标越出深度范围：保持引导并解释，不生成不可达/假有效目标。
4. 显示关闭、音频异常、输出文件已存在：正确释放资源，不覆盖用户文件，不改变计分。
5. 实验方法改变活动目标日程或从预测反推真值：明确禁止；同输入、目标和独立标签的一对一匹配才可比较。

---

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

## Task 1: 拳心代理、质量原因与格式兼容

**Files:** Create `src/depthstrike/interaction.py`, `tests/test_interaction.py`; modify `types.py`, `config.py`, `fusion.py`, `tracking.py`, `recording.py`, `configs/default.json`, `tests/test_config.py`, `tests/test_fusion.py`, `tests/test_recording.py`.

**Interfaces:**
- `Joint3D(position, confidence=0.0, invalid_reason: str | None=None)`；保持已有位置参数兼容。
- `estimate_fist(elbow: Joint3D | None, wrist: Joint3D | None, config: AppConfig) -> Joint3D`；无效原因与最小置信度按设计传播。
- `AppConfig.interaction_mode: str = "guided"`，只允许 guided/legacy；增加 `fist_offset_m=.06`、`forearm_min_length_m=.02`、`reach_hold_s=.35`、`return_guard_s=.20`、`reach_min_increment_m=.10`、`target_reach_ratio=.85`、`countdown_s=2.0`。零偏移合法，其余时长/长度为正，比例 (0,1)，枚举不能由 bool/数字替代。
- v2 headers 明示新配置；v1 reader 仅在未提供模式时注入 legacy 和零拳心偏移。v2 缺失 mode 报错。未知版本继续拒绝。

- [ ] **Step 1: Write failing tests.** `test_fist_extends_forearm_by_six_cm`：`assert estimate_fist(Joint3D((0,0,2), .9), Joint3D((0,0,1.8), .8), AppConfig()).position == pytest.approx((0,0,1.74))`；`test_missing_elbow_and_degenerate_forearm_are_invalid` 覆盖缺失、低置信度、0.019 m；`test_quality_reason_survives_tracking_and_v2_roundtrip` 核对无效原因；参数化非法配置；`test_v1_fixture_retains_legacy_mode_and_twenty_points`：`assert (summary.frames, summary.hits, summary.score) == (4, 2, 20)`；`test_v2_requires_explicit_interaction_mode` 拒绝含混新格式。
- [ ] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_interaction.py tests/test_config.py tests/test_fusion.py tests/test_recording.py -q`；确认新增测试因缺接口/行为失败，而非环境失败。
- [ ] **Step 3: Implement contracts and proxy.** 按规范公式计算拳心；区分融合失败原因并保留现有保守有效性检查；读取器显式兼容 v1/v2，写入器使用 v2。保留 NPY 大小/路径/格式防护和独占文件创建。
- [ ] **Step 4: Run GREEN.** 上述测试全通过；另运行 `tests/test_cli.py::test_supplied_fixture_has_hand_checked_result`，结果仍为 4 帧、20 分。
- [ ] **Step 5: Commit only task files.** `feat: add quality-aware fist proxies and versioned replay compatibility`。

## Task 2: 个体化引导、练习及正式回合

**Files:** Create `src/depthstrike/calibration.py`, `tests/test_calibration.py`; modify `boxing.py`, `types.py`, `sources.py`, `cli.py`, `tests/conftest.py`, `tests/test_boxing.py`, `tests/test_app.py`, `tests/test_cli.py`.

**Interfaces:**
- `CalibrationProfile(reference_shoulders: dict[str, np.ndarray], neutral_extensions: dict[str, float], comfortable_extensions: dict[str, float], guard_thresholds: dict[str, float], attack_thresholds: dict[str, float], travel_thresholds: dict[str, float], target_centers: dict[str, np.ndarray])`。
- `GuidanceState(stage: str, progress: float, message_code: str, profile: CalibrationProfile | None)`。
- `GuidedCalibration(config).update(frame: SkeletonFrame, fists: dict[str, Joint3D]) -> GuidanceState`，另有 `reset()`、`invalidate()`；暂停时调用方不得推进。
- `PunchTracker` 保留旧 `update(timestamp_s, wrist, shoulder)` 调用兼容；新增可选 profile 阈值，输入代理点在 guided 模式为拳心。
- `SceneState` 新增默认字段 `guidance`、`fists`、`feedback`，不得破坏旧位置构造。
- `DemoPoseSource(config=None, fps=30., total_frames=None)` 依据 mode 选择旧轨迹或含引导的确定性动作；描述中持续标明 synthetic。

- [ ] **Step 1: Write failing tests.** 覆盖 0.6 s 中立、0.35 s 左右舒适前伸、0.20 s 收拳、练习和 2 s 倒计时的顺序；两个不同舒适范围生成不同目标，断言 `assert center[2] == pytest.approx(reference_shoulder[2] - .85 * comfortable_extension)` 且身体移动后不变；`test_pause_and_tracking_gap_do_not_complete_hold`；`test_missing_shoulder_cannot_score_or_consume_guided_round_time`；`test_practice_hits_never_increment_official_score`：`assert (state.score, state.hits, state.remaining_s) == (0, 0, 60)`；`test_resume_requires_guard_not_extended_fist`；`test_shoulder_drift_resets_current_reach_sample`；`test_guard_overlap_and_out_of_depth_targets_are_rejected`；`test_interrupted_countdown_restarts_after_guard`；`test_missing_inactive_elbow_suppresses_scoring_and_time`。原有测试显式使用 legacy，保留原预期。
- [ ] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_calibration.py tests/test_boxing.py tests/test_app.py tests/test_cli.py -q`。
- [ ] **Step 3: Implement staged calibration.** 用输入时间和有效连续样本推进；引导档案的公式、深度检查、暂停/失效/重置语义采用 spec。将 legacy 路径清晰隔离；guided 同一拳心用于出拳和扫掠碰撞。左右练习命中只推进练习；倒计时结束清空攻击；正式计时只累计有效连续区间。
- [ ] **Step 4: Implement deterministic demo and roundtrip.** 更新 CLI 构造使 source 接收所用配置；脚本包含所有阶段，不向 simulation 注入“已校准”标志。测试新 demo 能进入 RUNNING 并左右命中；相同配置两次事件完全一致；录制回放事件完全一致。
- [ ] **Step 5: Run GREEN and commit.** 上述测试通过，v1 夹具仍 20 分；提交 `feat: add reach-calibrated guided boxing sessions`。

## Task 3: 解释性反馈、叠加主视图与几何复用

**Files:** Create `src/depthstrike/feedback.py`, `src/depthstrike/arena.py`, `src/depthstrike/audio.py`, `tests/test_feedback.py`, `tests/test_visualization.py`; modify `types.py`, `boxing.py`, `visualization.py`, `cli.py`, `tests/test_app.py`.

**Interfaces:**
- `HandFeedback(reason: str, surface_gap_m: float | None, depth_delta_m: float | None, lateral_m: float | None)`；`build_feedback(fists: dict[str, Joint3D], targets: tuple[Target, ...], phases: dict[str, str], status: str, config: AppConfig, diagnostics: dict[str, str]) -> dict[str, HandFeedback]`；diagnostics 是当前攻击条件的原因代号，不读取旧帧补值。
- `SceneView(config, mode="demo", layout="overlay", sound=False)`；保持 `render/poll_actions/close`；dual 才构造 `ArenaRenderer`。
- `ArenaRenderer(config)`：`render(state)`、`poll_actions()`、`close()`；建立固定命名对象池，稳定帧只 update_geometry。
- `AudioFeedback(enabled=False).notify(events)` / `close()`；仅 Windows 上懒导入 winsound，使用异步系统声音，错误最多提示一次，不传播为计分错误。
- CLI 添加 `--view overlay|dual` 和 `--sound`；headless 与 sound 冲突时报可操作参数错误。

- [ ] **Step 1: Write failing tests.** `test_depth_mismatch_is_explained_without_hit`、`test_invalid_hand_clears_all_distance_fields`：`assert (feedback.surface_gap_m, feedback.depth_delta_m, feedback.lateral_m) == (None, None, None)`、`test_tracking_loss_precedes_speed_hint`；纯图像测试含阶段/进度和拳心，NaN/后方目标不绘制；mock Open3D 下连续 100 帧对象创建/增删数量不随帧数增长，断言 `assert final_add_count == initial_add_count`，无效后复用恢复；overlay 不导入 open3d；双窗口各自关闭释放资源；音频失败不会改变分数。
- [ ] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_feedback.py tests/test_visualization.py tests/test_app.py -q`。
- [ ] **Step 3: Implement feedback and views.** 数值距离与命中使用同一拳心/半径；按 spec 优先级映射提示。拆分常驻三维渲染，mesh 顶点从原始局部模板重算，避免逐帧 transform 累积漂移；空线集/空网格隐藏失效对象。目标深度线索只用于显示。图形调用均保留在主线程。
- [ ] **Step 4: Run GREEN and visible smoke.** 单测通过；分别运行新 demo 的 overlay/dual，检查引导、拳心、空间反馈、闪烁、暂停和退出。可用桌面时执行 opt-in GUI 测试并保存本地截图；无显示时明确记为未验收，不伪造通过。
- [ ] **Step 5: Commit task files.** `feat: add explanatory overlay feedback and persistent arena geometry`。

## Task 4: 软件阶段观测与可靠导出

**Files:** Create `src/depthstrike/metrics.py`, `tests/test_metrics.py`; modify `sources.py`, `app.py`, `cli.py`, `tests/test_adapters.py`, `tests/test_app.py`, `tests/test_cli.py`.

**Interfaces:**
- `StageMetrics(clock=time.perf_counter, capacity=4096)`，`measure(name)` context manager，`snapshot() -> dict`，`write_exclusive(path, metadata)`。
- 使用固定容量环形样本，并报告 total_count / retained_count；p50/p95/max 明示基于保留样本，避免无限内存或误称全程精确分位数。
- `CameraPoseSource(..., metrics=None)` 观测 capture/pose/fusion；`run_session(..., metrics=None)` 观测 read/simulation/record/render/frame_total；现有会话 clock 仍仅控制超时/播放，不与 profiling 时钟混用。
- `--metrics PATH` 输出非覆盖 JSON；已有文件在启动设备/模型前拒绝。执行异常时由 CLI finally 关闭后导出 partial 状态，不能用导出异常覆盖原错误。

- [ ] **Step 1: Write failing tests.** 假时钟断言各阶段耗时、分位数与样本计数，单次 0.012 s 时断言 `assert stage["p50_s"] == pytest.approx(.012)`；`test_nested_read_metrics_are_not_summed_twice`；超过 4096 样本内存有界，断言 `assert stage["retained_count"] == 4096`；异常、超时、提前退出产生部分统计；已有输出内容不变；设备时间戳远离软件时钟仍输出非负合法耗时。
- [ ] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_metrics.py tests/test_adapters.py tests/test_app.py tests/test_cli.py -q`。
- [ ] **Step 3: Implement metrics boundaries.** 区分软件耗时、播放等待和设备时间；metadata 保存输入类型/配置/版本和成功或 partial 状态。不加入线程或修改 RGB-D 配对。
- [ ] **Step 4: Run GREEN and CLI smoke.** `.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 600 --metrics outputs/offline-stage-metrics-UNIQUE.json`；JSON 可解析、阶段存在且 evidence 为 synthetic；记录软件结果，不标注真实端到端延迟。
- [ ] **Step 5: Commit task files.** `feat: add bounded software-stage timing diagnostics`。

## Task 5: 独立标签与受控对比评估

**Files:** Create `src/depthstrike/evaluation.py`, `src/depthstrike/evaluation_scenarios.py`, `tests/test_evaluation.py`, `tests/fixtures/evaluation/README.md`; modify `geometry.py` only if shared pure numeric projection is needed; modify `recording.py` only to expose public read-only metadata.

**Interfaces:**
- `EvaluationManifest`：schema_version=1、evidence、intrinsics、固定 targets、active_schedule、expected_windows、ignore_windows 和标签依据。
- `evaluate_recording(input_path: Path, manifest_path: Path) -> dict`；`evaluate_synthetic_suite() -> dict`；模块 `main(argv=None) -> int` 独占创建 output。
- 四方法代号 `2d_entry`、`3d_discrete_entry`、`3d_swept_entry`、`3d_swept_punch`。接触上升沿在真正离开后重置；无效/断轨时取消连续线段，恢复的首帧不凭初始重叠产生 entry。状态机方法额外要求 guard/attack。
- 2D 基线用给定 intrinsics 投影拳心与目标及半径；仅支持 none 或已有受支持 Brown 标定。Brown 所需 cv2 缺失时报说明，不自动替换标定。
- 固定日程和目标来自 manifest；所有方法共享预处理、拳心及阈值。按时间、手、目标作确定性一对一窗口匹配，额外落入已匹配窗口的预测单列 duplicates 并计 FP；null 表示零分母。

- [ ] **Step 1: Write failing tests.** 两个标签窗口，一窗内两条预测及窗外一条预测：`assert (result["tp"], result["fp"], result["fn"], result["duplicates"]) == (1, 2, 1, 1)`；空预测/空标签分母为 null；重叠/共端点窗口、无效目标/时间/内参被拒绝；忽略区间同时排除预测和完全包含标签，部分相交拒绝；`test_each_method_sees_same_target_schedule`；`test_active_hand_switch_cannot_create_contact_entry`；重复运行除耗时外报告一致；读取录制 events 不改变真值。每个解析场景检查 spec 中相应区分，而非强求改进方法在所有场景都最好。
- [ ] **Step 2: Run RED.** `.venv\Scripts\python.exe -m pytest tests/test_evaluation.py -q`。
- [ ] **Step 3: Implement labels, methods and analytic scenarios.** 标签由独立几何/动作定义指定，使用独立代码核对预期事件；禁止从被测输出生成窗口。JSON 输出含证据类型、输入 SHA256、完整方法配置和场景级计数。manifest/输入格式错误转换为可操作 CLI 错误，无 traceback 泄露。
- [ ] **Step 4: Run GREEN and reproducibility smoke.** `.venv\Scripts\python.exe -m depthstrike.evaluation --suite synthetic --output outputs/synthetic-comparison-UNIQUE.json`；报告声明 synthetic，指标与测试手算一致，输出拒绝覆盖。补测 external pose + labels 路径。
- [ ] **Step 5: Commit task files.** `feat: add reproducible labeled interaction comparisons`。

## Task 6: 集成、交付文档与独立审查

**Files:** Modify `README.md`, `PROJECT.md`, `docs/RUNNING.md`, `docs/VERIFICATION.md`, `docs/IMPLEMENTATION_NOTES.md`; add `docs/EVALUATION.md`; update integration tests where needed.

**Interfaces:** 前五项已冻结的 CLI、配置、版本 1/2 与实验标签格式；不在最后一项扩展玩法。

- [ ] **Step 1: Add regression tests first.** 新引导演示 → 录制 → 回放的事件一致；legacy 240 帧仍 6 命中/60 分，旧 4 帧夹具仍 20 分；headless 不导入 SDK/MediaPipe/Open3D；无相机明确失败；不同新参数的 demo 仍可完成引导或明确报告不可达配置；暂停/失效/重置录制往返一致。
- [ ] **Step 2: Run RED, then fix integration only.** 如测试暴露接口漏接，按最小范围补齐；不松动断轨、深度有效性或安全测试来获得通过。
- [ ] **Step 3: Verify fresh outputs.** `.venv\Scripts\python.exe -m pytest -q`；可用时 `$env:DEPTHSTRIKE_GUI_TESTS='1'` 后再运行完整测试；`.venv\Scripts\python.exe -m pip check`；demo/两类回放/评估/metrics CLI；重新构建 wheel 并在隔离环境执行 headless smoke，核心只需 NumPy。
- [ ] **Step 4: Document measured evidence and camera checklist.** 安装命令保持可执行；更新默认 guided 流程和 legacy 命令，给出 v2/标签字段、图形/音频可选项及性能计时口径。列出实机仍待验收的采集、对齐、遮挡、参数与延迟，不将本轮结果标为实机通过。
- [ ] **Step 5: Request one fresh independent whole-branch review.** 按 requesting-code-review 技能提交明确 base/head、设计和验证记录。处理实际缺陷并增加回归，重跑受影响项与全套；若需改变产品范围先征询用户。
- [ ] **Step 6: Final verification and local commit.** `git diff --check`、检查提交文件和 clean status；提交文档与最终修复。遵循 finishing-a-development-branch 技能汇报本地分支结果；不 push、合并或创建 PR，除非用户另行授权。

## 计划自检

- 六项原建议均有任务落点；真实设备验证明确延期而非宣称被离线替代。
- 引导和拳心只影响 guided；旧录制、旧安全边界及坐标约定保留。
- Review Focus 1–5 分别由任务 1、2、2、3/4、5 的具名测试覆盖。
- 执行方式沿用用户选择的当前会话逐模块开发、测试，最后独立审查；实现开始前需用户确认本设计与计划。
