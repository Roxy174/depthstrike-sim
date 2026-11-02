"""Sensor-first OpenCV overlay, optionally paired with an Open3D debug arena."""
from collections import deque
import os

import numpy as np

from .arena import ArenaRenderer, BONES, COLORS, display_position
from .audio import AudioFeedback
from .types import DepthStrikeError, Intrinsics
from .ui_text import (EVIDENCE, HANDS, MAIN_TITLE, PHASES, SOURCES, STAGES, STATUSES,
                      draw_text, set_window_title)

GUIDANCE = {
    "hold_guard": "将双手收至肩前，保持准备姿势",
    "reach_left": "请朝摄像头方向伸出蓝色左手并保持",
    "reach_right": "请朝摄像头方向伸出橙色右手并保持",
    "return_left": "请收拳回到准备位置",
    "return_right": "请收拳回到准备位置",
    "extend_comfortably": "请朝摄像头方向舒适前伸并保持，观察前伸读数",
    "wrong_hand": "请使用当前提示的手朝摄像头方向前伸",
    "hold_reach": "正在记录舒适前伸范围，请保持当前姿势",
    "return_guard": "请将双手收回准备位置",
    "restore_position": "请让双肩回到校准时的位置",
    "adjust_distance": "请调整与相机的距离，然后按 R 重新校准",
    "reach_too_small": "前伸距离不足，请舒适地重试或按 R 重新校准",
    "target_unreachable": "请检查目标高度和前伸方向，按 R 重新校准",
    "missing_body": "请让双肩、双肘和双腕保持入镜",
    "reacquiring": "追踪短暂中断，校准进度已保留，请保持当前姿势",
    "timestamp_invalid": "正在等待连续、稳定的采集数据",
    "practice_left": "左手试击：用左拳击打蓝色目标球",
    "practice_right": "右手试击：用右拳击打橙色目标球",
    "countdown": "保持收拳姿势，回合即将开始",
    "running": "请朝相机方向左右交替出直拳",
    "workspace_blocked": "目标路径存在遮挡，请调整站位并按 R 重新校准",
    "workspace_unknown": "目标路径的深度不完整，请调整取景并按 R 重新校准",
}
REASONS = {"depth_gap": "前后距离尚未到达目标", "off_axis": "请朝目标球的方向出拳",
           "adjust_distance": "请调整与相机的距离",
           "low_speed": "向前出拳的速度不足", "insufficient_travel": "请增加前伸距离",
           "return_guard": "请收拳复位", "ready": "可以出拳", "inactive_hand": "请使用提示的另一只手",
           "invalid_tracking": "人体追踪暂不可用", "invalid_depth": "暂未获得有效手部深度",
           "low_confidence": "关键点置信度不足", "missing_joint": "关节未进入有效视野",
           "degenerate_forearm": "暂时无法确定前臂方向", "depth_discontinuity": "已排除深度边缘干扰",
           "insufficient_depth": "有效深度数据不足", "out_of_frame": "请回到相机视野内",
           "missing_mask": "暂未获得人体分割结果", "outside_person": "关键点不在有效人体区域内",
           "timestamp_invalid": "采集数据不连续，请保持稳定", "attacking": "正在有效出拳",
           "motion_outlier": "已排除瞬时位置跳变，请保持稳定",
           "calibrating": "请按照校准引导完成动作", "paused": "已暂停", "finished": "回合结束"}


def _pixel(position, intrinsics):
    p = np.asarray(position, dtype=float)
    if p.shape != (3,) or not np.isfinite(p).all() or p[2] <= 0:
        return None
    x, y, z = p
    i = intrinsics
    if i.distortion_model == "brown_conrady":
        import cv2
        matrix = np.array([[i.fx, 0, i.cx], [0, i.fy, i.cy], [0, 0, 1.]])
        projected, _ = cv2.projectPoints(p.reshape(1, 3), np.zeros(3), np.zeros(3), matrix, np.asarray(i.distortion))
        u, v = projected.reshape(2)
    elif i.distortion_model in ("none", "pinhole_approximation"):
        u, v = i.fx*x/z+i.cx, i.fy*y/z+i.cy
    else:
        return None
    if not np.isfinite((u, v)).all() or abs(u) > 100000 or abs(v) > 100000:
        return None
    return int(u), int(v)


def _bgr(hand):
    return tuple(round(c * 255) for c in COLORS[hand][::-1])


def _draw_target(image, target, intrinsics, *, depth_frame=None, numbered=False):
    """Blend and depth-test only the pixels touched by this target."""
    import cv2
    p = _pixel(target.center, intrinsics)
    if p is None: return
    radius = max(3, min(200, round(intrinsics.fx * target.radius / target.center[2])))
    # Include anti-aliasing and the number, including partially offscreen balls.
    margin = radius + 8
    x0, y0 = max(0, p[0]-margin), max(0, p[1]-margin)
    x1, y1 = min(image.shape[1], p[0]+margin+1), min(image.shape[0], p[1]+margin+1)
    color = (93, 138, 43) if target.flash else (_bgr(target.hand) if target.active else (182, 169, 154))
    if x1 > x0 and y1 > y0:
        region = image[y0:y1, x0:x1]
        before = region.copy() if depth_frame is not None else None
        local = (p[0]-x0, p[1]-y0)
        layer = region.copy()
        cv2.circle(layer, local, radius, color, -1, cv2.LINE_AA)
        cv2.addWeighted(layer, .18 if target.active else .08, region, .82 if target.active else .92, 0, region)
        cv2.circle(region, local, radius, color, 3 if target.active else 1, cv2.LINE_AA)
        cv2.ellipse(region, local, (radius, max(2, radius//3)), 0, 0, 360, color, 1, cv2.LINE_AA)
        cv2.circle(region, (local[0]-radius//3, local[1]-radius//3), max(2, radius//7), (255, 255, 255), -1, cv2.LINE_AA)
        if numbered:
            draw_text(region, str(target.target_id + 1), (local[0]-5, local[1]+5), .42, color)
        if before is not None:
            from .spatial import target_visibility_mask
            visible = target_visibility_mask(depth_frame, target.center, target.radius,
                                             region=(x0, y0, x1, y1))
            region[~visible] = before[~visible]
    if target.preview:
        draw_text(image, "预览", (p[0]-12, p[1]-radius-8), .4, color)


def render_hud(state, rgbd_frame, config, mode="demo", trails=None):
    import cv2
    canvas = np.full((800, 960, 3), (247, 242, 237), np.uint8)
    ink, muted, teal = (72, 54, 38), (130, 112, 95), (122, 122, 31)
    def text(value, at, size=.55, color=ink, weight=1, **kwargs):
        draw_text(canvas, value, at, size, color, weight, **kwargs)
    cv2.rectangle(canvas, (0, 0), (959, 78), (72, 54, 38), -1)
    text("深度拳击", (25, 36), .95, (255, 255, 255), 2)
    source_label = "合成动作演示｜无需摄像头" if mode == "demo" else f"三维体感击球｜{SOURCES.get(mode, '交互输入')}"
    if state.challenge:
        source_label = f"动作关卡｜{SOURCES.get(mode, '交互输入')}｜{EVIDENCE.get(state.challenge['content_evidence'], '待核验内容')}"
    if mode == "opencv-experience" or (rgbd_frame is not None and rgbd_frame.intrinsics.distortion_model == "pinhole_approximation"):
        source_label = "相机体验模式｜主机计时｜近似空间计算"
    if mode == "astra-experience":
        source_label = "奥比中光相机体验｜主机计时｜出厂深度对齐"
    if mode == "gemini-camera":
        source_label = "奥比中光双目相机｜设备计时｜软件深度对齐"
    text(source_label, (26, 61), .48, (227, 218, 207))
    recovering = state.guidance is not None and state.guidance.message_code == "reacquiring"
    text("追踪恢复中" if recovering else STATUSES.get(state.status, "状态更新中"), (660, 43), .62, (244, 234, 219), 2)
    if rgbd_frame is None:
        image = np.full((360, 640, 3), (239, 233, 226), np.uint8)
        intrinsics = Intrinsics(640, 360, 750, 750, 320, 130)
        # Spatial references belong to the synthetic field, never the live feed.
        for u in range(0, 640, 40): cv2.line(image, (u, 0), (u, 359), (225, 217, 207), 1)
        for v in range(0, 360, 40): cv2.line(image, (0, v), (639, v), (225, 217, 207), 1)
    else:
        image = cv2.cvtColor(rgbd_frame.color_rgb, cv2.COLOR_RGB2BGR).copy()
        intrinsics = rgbd_frame.intrinsics
    points = {}
    if state.skeleton is not None:
        points = {name: _pixel(j.position, intrinsics) for name, j in state.skeleton.joints.items() if j.position is not None}
        for a, b in BONES:
            if points.get(a) is not None and points.get(b) is not None:
                cv2.line(image, points[a], points[b], (110, 100, 87), 2, cv2.LINE_AA)
        for name, point in points.items():
            if point is not None:
                cv2.circle(image, point, 4, _bgr("left" if name.startswith("left") else "right"), -1, cv2.LINE_AA)
        for name, joint in state.display_joints.items():
            p = _pixel(joint.position, intrinsics)
            if p is not None: cv2.circle(image, p, 8, (160, 160, 160), 1, cv2.LINE_AA)
        for hand, joint in state.fists.items():
            if joint.position is None: continue
            p = _pixel(joint.position, intrinsics)
            if p is None: continue
            if trails:
                prior = [_pixel(v, intrinsics) for v in trails.get(hand, ())]
                for a, b in zip(prior[:-1], prior[1:]):
                    if a is not None and b is not None: cv2.line(image, a, b, _bgr(hand), 2, cv2.LINE_AA)
            wrist = points.get(f"{hand}_wrist")
            if wrist is not None: cv2.line(image, wrist, p, _bgr(hand), 2, cv2.LINE_AA)
            r = max(4, min(100, round(intrinsics.fx * config.hand_radius_m / joint.position[2])))
            cv2.circle(image, p, r, _bgr(hand), 2, cv2.LINE_AA)
            cv2.circle(image, p, 4, _bgr(hand), -1, cv2.LINE_AA)
            if state.guidance and state.guidance.stage.startswith("REACH_"):
                draw_text(image, f"{HANDS[hand]}位置", (p[0]-22, p[1]-r-8), .4, _bgr(hand))
    for target in state.targets:
        _draw_target(image, target, intrinsics,
                     depth_frame=rgbd_frame if config.depth_occlusion else None,
                     numbered=len(state.targets) > 2)
    scale = min(700 / image.shape[1], 500 / image.shape[0])
    w, h = round(image.shape[1] * scale), round(image.shape[0] * scale)
    x, y = 20 + (700-w)//2, 98 + (500-h)//2
    canvas[y:y+h, x:x+w] = cv2.resize(image, (w, h))
    active = next((t.hand for t in state.targets if t.active), None)
    if state.challenge and active is None: active = state.challenge["hand"]
    if active is None and state.guidance:
        if state.guidance.stage.endswith("LEFT"): active = "left"
        elif state.guidance.stage.endswith("RIGHT"): active = "right"
    text("校准引导" if state.guidance and state.guidance.stage != "RUNNING" else "回合信息", (744, 116), .68, weight=2)
    stage = state.guidance.stage if state.guidance else state.status
    text(STAGES.get(stage, "状态更新中"), (744, 155), .64, teal, 2, max_width=188)
    measurements = getattr(state.guidance, "measurements", None) or {}
    if stage.startswith("REACH_") and measurements:
        forward = measurements.get("forward_m") if state.status not in ("WAITING FOR CAMERA", "PAUSED", "FINISHED") else None
        if forward is None:
            text("前伸：等待有效追踪", (744, 185), .4, muted, max_width=188)
        else:
            required = measurements.get("required_forward_m", config.reach_min_increment_m)
            text(f"前伸 {forward*100:+.1f} / {required*100:.1f} 厘米", (744, 185), .4, muted, max_width=188)
        elapsed = measurements.get("hold_s", 0.)
        required_hold = measurements.get("required_hold_s", config.reach_hold_s)
        text(f"保持 {elapsed:.2f} / {required_hold:.2f} 秒", (744, 208), .4, muted, max_width=188)
        text("C：确认当前前伸姿势", (744, 505), .43, muted, max_width=188)
        text("无需触碰目标", (744, 528), .43, muted, max_width=188)
    elif stage == "HOLD_GUARD" or stage.startswith(("REACH_", "RETURN_")):
        text("正在记录动作范围", (744, 185), .43, muted, max_width=188)
        text("无需触碰目标", (744, 208), .43, muted, max_width=188)
    if state.guidance:
        progress = state.guidance.progress
        cv2.rectangle(canvas, (744, 231), (932, 237), (216, 207, 195), -1)
        cv2.rectangle(canvas, (744, 231), (744+round(188*progress), 237), teal, -1)
    text("当前使用", (744, 280), .48, muted)
    text(HANDS.get(active, "等待人物" if config.interaction_mode == "direct" else "校准中"),
         (744, 311), .78, _bgr(active) if active else ink, 2)
    if len(state.targets) > 2 and not state.challenge:
        current_target = next((t for t in state.targets if t.active), None)
        if current_target is not None:
            text(f"目标 {current_target.target_id + 1} / {len(state.targets)}", (744, 337), .43, muted)
    for n, hand in enumerate(("left", "right")):
        text(HANDS[hand], (744, 365+n*75), .55, _bgr(hand), 2)
        text(PHASES.get(state.phases.get(hand), "暂不可用"), (744, 391+n*75), .43, muted)
    text("空格：暂停／继续", (744, 557), .44, muted)
    text("R：重新开始" if config.interaction_mode == "direct" else "R：重新校准", (744, 579), .44, muted)
    text("Q / Esc：退出", (744, 601), .44, muted)
    if config.partial_tracking:
        observed = sum(j.is_observed for j in state.skeleton.joints.values()) if state.skeleton else 0
        text(f"已观测 {observed} 个点｜预测 {len(state.display_joints)} 个点", (24, 611), .42, muted)
    guidance = state.guidance
    if state.status == "WAITING FOR CAMERA": hint = "正在等待彩色与深度画面，交互已暂停"
    elif state.status == "PAUSED": hint = "已暂停，按空格继续"
    elif state.status == "FINISHED":
        hint = "回合结束，按 R 重新开始" if config.interaction_mode == "direct" else "回合结束，按 R 重新校准并开始"
    elif state.status == "WAITING FOR PLAYER": hint = "请让双肩和手腕进入画面，识别后自动放置目标"
    elif state.status == "ADJUST DISTANCE": hint = "请远离相机一些，让目标处于有效深度范围"
    elif state.status == "TRACKING LOST" and config.interaction_mode == "direct": hint = "请让当前出拳手的肩部和手腕保持入镜"
    else:
        hint = GUIDANCE.get(guidance.message_code, "请按照画面引导完成动作") if guidance else "请朝相机方向左右交替出直拳"
        if guidance and guidance.stage.startswith("REACH_") and guidance.message_code in ("extend_comfortably", "hold_reach"):
            hand = "left" if guidance.stage.endswith("LEFT") else "right"
            hint = f"{HANDS[hand]}：{hint}"
    if guidance and guidance.message_code == "wrong_hand":
        hand = "left" if guidance.stage.endswith("LEFT") else "right"
        other = "right" if hand == "left" else "left"
        color = "蓝色" if hand == "left" else "橙色"
        hint = f"检测到{HANDS[other]}前伸，请伸出{color}{HANDS[hand]}朝向摄像头"
    elif guidance and guidance.message_code == "hold_reach" and measurements.get("hold_reset_reason") == "position_motion":
        hint = "前伸已达标，位置变化使保持重新计时；可保持当前姿势按 C 确认"
    elif guidance and guidance.message_code == "missing_body" and measurements.get("blocked_joint"):
        side, _, part = measurements["blocked_joint"].partition("_")
        label = HANDS.get(side, "当前手") + {"wrist": "腕点", "shoulder": "肩部", "hand": "交互点"}.get(part, "关节")
        reason = REASONS.get(measurements.get("blocked_reason"), "追踪暂不可用")
        hint = f"{label}：{reason}，请调整取景并保持可见"
    elif config.partial_tracking and guidance and guidance.message_code == "missing_body":
        side = "左手、左肩及手臂" if guidance.stage.endswith("LEFT") else ("右手、右肩及手臂" if guidance.stage.endswith("RIGHT") else "双手、双肩及手臂")
        hint = f"请让{side}保持入镜"
    if state.challenge and state.status not in ("PAUSED", "WAITING FOR CAMERA", "TRACKING LOST"):
        c = state.challenge
        hint = f"第 {c['cue_index']} / {c['total']} 靶：{HANDS.get(c['hand'], '指定手')}。"
        hint += f"请准备，{c['until_window_s']:.2f} 秒后开始" if c["until_window_s"] > 0 else "请在当前时间窗内出拳"
        if state.status == "FINISHED": hint = "关卡完成，可打开动作复盘查看各靶结果"
    text(hint, (24, 637), .52, ink, 1)
    cv2.line(canvas, (24, 652), (934, 652), (212, 202, 188), 1)
    text(state.score, (24, 707), 1.35, ink, 2)
    text("得分", (26, 737), .45, muted)
    text(f"命中 {state.hits} 次", (160, 707), .8, ink, 2, max_width=145)
    text(f"{state.remaining_s:04.1f} 秒", (315, 707), .8, ink, 2, max_width=160)
    feedback = state.feedback.get(active) if active else None
    fields = None if feedback is None else (feedback.surface_gap_m, feedback.depth_delta_m, feedback.lateral_m)
    if fields is None or any(v is None for v in fields):
        text("空间反馈暂不可用", (490, 688), .5, muted)
    else:
        text(f"表面间距 {fields[0]:+.2f} 米　深度差 {fields[1]:+.2f} 米", (490, 686), .49, teal)
        text(f"横向偏差 {fields[2]:.2f} 米", (490, 713), .49, muted)
        amount = float(np.clip(1-max(0., fields[0])/.5, 0, 1))
        cv2.rectangle(canvas, (492, 733), (931, 739), (216, 207, 195), -1)
        cv2.rectangle(canvas, (492, 733), (492+round(439*amount), 739), teal, -1)
    missing_hint = "请让肩部和手腕保持入镜" if config.fist_mode == "wrist" else "请让肩、肘和手腕保持入镜"
    reason = REASONS.get(feedback.reason, "请调整站位并保持稳定") if feedback else missing_hint
    text(reason, (24, 778), .5, muted)
    text("以三维交互点的空间接触判定命中", (540, 778), .43, muted)
    return canvas


class NullView:
    def render(self, state, rgbd_frame): pass
    def poll_actions(self): return []
    def close(self): pass


class SceneView:
    def __init__(self, config, mode="demo", layout="overlay", sound=False):
        self.config, self.mode = config, mode
        self._closed = False
        self.arena = None
        self.cv2 = None
        self.audio = AudioFeedback(sound)
        self._last_t = None
        self._trails = {h: deque(maxlen=16) for h in COLORS}
        self.hud_name = f"DepthStrikeHUD-{os.getpid()}"
        if layout not in ("overlay", "dual"):
            raise ValueError("view layout must be overlay or dual")
        if os.environ.get("DEPTHSTRIKE_NO_DISPLAY") or (os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")):
            raise DepthStrikeError("当前没有可用的显示环境，请使用 --headless --frames 600")
        try:
            import cv2
            self.cv2 = cv2
            cv2.namedWindow(self.hud_name, cv2.WINDOW_AUTOSIZE)
            set_window_title(cv2, self.hud_name, MAIN_TITLE)
            cv2.moveWindow(self.hud_name, 25, 40)
            if layout == "dual": self.arena = ArenaRenderer(config)
        except BaseException as exc:
            self.close()
            if isinstance(exc, DepthStrikeError): raise
            raise DepthStrikeError(f"显示界面初始化失败：{exc}。请安装 .[display] 依赖或使用 --headless") from exc

    @property
    def vis(self):
        return self.arena.vis if self.arena else None

    def render(self, state, rgbd_frame):
        if self._closed: return
        frame = state.skeleton
        broken = frame is None or self._last_t is not None and not 0 < frame.timestamp_s-self._last_t <= self.config.max_track_gap_s + 1e-9
        self._last_t = frame.timestamp_s if frame else None
        for hand, trail in self._trails.items():
            joint = state.fists.get(hand)
            if broken or joint is None or joint.position is None or state.status in ("PAUSED", "CALIBRATING", "TRACKING LOST"):
                trail.clear()
            if frame is not None and joint is not None and joint.position is not None:
                trail.append(joint.position.copy())
        if self.arena: self.arena.render(state)
        self.cv2.imshow(self.hud_name, render_hud(state, rgbd_frame, self.config, self.mode, self._trails))
        self.audio.notify(state.events)

    def poll_actions(self):
        if self._closed: return ["quit"]
        actions = self.arena.poll_actions() if self.arena else []
        if "quit" in actions: return ["quit"]
        try:
            if self.cv2.getWindowProperty(self.hud_name, self.cv2.WND_PROP_VISIBLE) < 1: return ["quit"]
            key = self.cv2.waitKey(1) & 0xff
        except self.cv2.error:
            return ["quit"]
        action = {32: "pause", ord("c"): "capture_reach", ord("C"): "capture_reach",
                  ord("r"): "reset", ord("q"): "quit", 27: "quit"}.get(key)
        if action and action not in actions: actions.append(action)
        return actions

    def close(self):
        if self._closed: return
        try:
            if self.arena: self.arena.close()
        finally:
            self.audio.close()
            if self.cv2 is not None:
                try: self.cv2.destroyWindow(self.hud_name)
                except self.cv2.error: pass
            self._closed = True

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
