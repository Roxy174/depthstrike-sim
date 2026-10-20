# DepthStrike Boxing Target Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现纯 Python 三维击球模拟器，贯通 Gemini 2 RGB-D 输入、人体关键点与深度融合、有效出拳、跨帧碰撞、计分及离线演示回放。

**Architecture:** 将采集与姿态检测、三维追踪、交互规则、显示及记录分离。真实相机和合成演示输出相同的三维骨架数据，几何和游戏逻辑可脱离相机与窗口测试。首版以目标球场景验收，不展开完整 NPC 对战。

**Tech Stack:** Python、NumPy、pytest；相机路径使用 Orbbec Python SDK、MediaPipe Pose Landmarker，显示使用 OpenCV 与 Open3D。

**Spec:** `D:\3D视觉\PROJECT.md`；本计划收敛其阶段 A、B，以及记录回放和基础评估，不将阶段 C 的完整攻防对战纳入首版。

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

## Review Focus

1. 无 SDK、无模型、无相机或断连时，给出可操作错误并释放资源，不静默切换成伪实时演示。由任务 5、7 测试。
2. 深度单位、内参、图像尺寸及时间戳不一致时，拒绝该帧，不能用二维重叠产生错误命中。由任务 1、2、5 测试。
3. 图像边缘、低置信度、深度空洞和背景误读时，交互点无效，不沿用上次位置继续攻击。由任务 2、3 测试。
4. 快速跨越、初始重叠、停留、收拳与恢复追踪时，既避免漏检，也避免重复计分和跨断轨命中。由任务 1、3、4 测试。
5. 回放数据损坏、非有限数、时间倒退，以及暂停、重置、退出时，保证错误明确、结果可复现和资源正常关闭。由任务 6、7、8 测试。

---

## 已有环境与执行准备

2026-10-20 的只读检查结果：仓库在 `main`，与 `origin/main` 同步，无待提交修改；仅包含文档与忽略规则。当前 `python` 为 Anaconda Python 3.12.7；另有 Python 3.9。可见依赖为 NumPy 1.26.4、OpenCV 4.11.0.86、Open3D 0.19.0、pytest 7.4.4，未发现 MediaPipe 和 Orbbec Python SDK 的已安装分发包。

Windows PnP 查询未返回名称匹配 Gemini/Orbbec 的设备。这不能代替 SDK 枚举，不据此断言摄像头不存在；真实采集验收需要实际连接设备。

执行前使用 `superpowers:using-git-worktrees` 核对隔离方案，保留 `D:\3D视觉` 为用户指定的主仓库，不移动课程资料。实施者需按所选执行技能进行任务级测试与审查。Git 如需联网，复用已核实的系统代理并仅作用于当前命令，不修改全局网络设置。

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

## Task 8: 使用文档与完整验收

**Files:** 更新 `README.md`、`PROJECT.md`；创建 `docs/RUNNING.md`、`docs/VERIFICATION.md`；补充 `tests/test_cli.py` 的端到端测试。

**Interfaces:** 消费前七项的公开 CLI 和回放格式，不再建立另一套运行入口。

- [ ] **Step 1:** 先写端到端测试：子进程在规定帧数内完成 headless 演示；轨迹录制后 replay 得分与事件一致；无设备 camera 模式失败时保留可操作错误，不能输出伪造成功摘要。
- [ ] **Step 2:** 执行新测试确认预期失败，补足 CLI 集成与诊断，再运行完整 `pytest`。
- [ ] **Step 3:** 根据实际验证结果固定依赖版本，记录模型来源、系统、SDK 和固件信息。提供独立环境安装、模型下载、演示、相机模式、轨迹/RGB-D 回放及常见错误说明，命令须实测后才写为可运行。
- [ ] **Step 4:** 分别记录自动测试、headless 演示、窗口演示、真实设备采集和真实人体击球的通过/未测/失败结果。无硬件时仍交付可运行演示和适配代码，但明确设备联调尚未验收，不用模拟测试替代。
- [ ] **Step 5:** 更新 PROJECT 中与首版已实现代码明显冲突的历史描述；README 保持此前确定的学术简洁风格，安装细节链接到 RUNNING，不加入冗长状态免责声明。
- [ ] **Step 6:** 核对只包含项目文件、无权重或人像数据，提交 `docs: document simulator usage and verification`；按所选执行方式完成独立审查。未经再次授权不 push。

## 自查结果

- 范围覆盖 PROJECT 的阶段 A、B，以及首版所需采集、融合、计分、回放和测试；阶段 C 完整虚拟对手、格挡/闪避对战及打包发行另行实施。
- 五项 Review Focus 均已分配至具体测试任务；共享类型与命令命名贯穿一致。
- 两种回放分别验证规则与视觉输入链路，不混淆证据。
- 依赖安装、模型下载和设备验收位于执行阶段，未在计划阶段实施。
- 本计划未批准实施，最终执行方式待用户选择。首版优先推荐 Native，因为模块依赖顺序紧密，接口在同一会话中较易保持一致；实现后仍需独立审查。

## 核对过的官方参考

- [Orbbec Python SDK 示例目录](https://github.com/orbbec/pyorbbecsdk/tree/v2-main/examples)
- [深度到彩色对齐示例](https://github.com/orbbec/pyorbbecsdk/blob/v2-main/examples/beginner/03_color_and_depth_aligned.py)
- [SDK 坐标变换示例](https://github.com/orbbec/pyorbbecsdk/blob/v2-main/examples/advanced/16_coordinate_transform.py)
- [MediaPipe Pose Landmarker Python 接口](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Open3D 非阻塞可视化](https://www.open3d.org/docs/release/tutorial/visualization/non_blocking_visualization.html)
