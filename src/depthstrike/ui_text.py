"""Chinese UI labels and cached, baseline-aligned text for BGR canvases.

Pillow is loaded only when a display is rendered; headless use stays NumPy-only.
"""
from functools import lru_cache
import os
from pathlib import Path

import numpy as np

from .types import DepthStrikeError

MAIN_TITLE = "深度拳击｜体感交互"
ARENA_TITLE = "深度拳击｜三维辅助视图"
REVIEW_TITLE = "深度拳击｜动作复盘"

HANDS = {"left": "左手", "right": "右手"}
STATUSES = {"CALIBRATING": "引导校准", "RUNNING": "正式回合", "PAUSED": "已暂停",
            "FINISHED": "回合结束", "TRACKING LOST": "追踪中断", "WAITING FOR CAMERA": "等待相机"}
STAGES = {"HOLD_GUARD": "收拳准备", "REACH_LEFT": "左手前伸", "RETURN_LEFT": "左手收回",
          "REACH_RIGHT": "右手前伸", "RETURN_RIGHT": "右手收回", "PRACTICE_LEFT": "左手试击",
          "PRACTICE_RIGHT": "右手试击", "COUNTDOWN": "开始倒计时", **STATUSES}
PHASES = {"READY": "准备就绪", "ATTACKING": "出拳中", "RECOVERING": "收拳复位",
          "unavailable": "暂不可用"}
SOURCES = {"demo": "合成演示", "camera": "深度相机", "opencv-camera": "奥比中光相机体验",
           "opencv-experience": "奥比中光相机体验", "astra-camera": "奥比中光相机",
           "astra-experience": "奥比中光相机体验", "replay": "骨架回放", "rgbd-replay": "彩色与深度回放"}
EVIDENCE = {"synthetic": "合成内容", "recorded": "录制内容", "unverified": "未验证内容"}
OUTCOMES = {"hit": "命中", "miss": "未命中", "unobserved": "观测不足", "incomplete": "未完成"}
SESSIONS = {"complete": "已完成", "partial": "未完成"}


@lru_cache(maxsize=8)
def _font_path(override, bold):
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise DepthStrikeError("指定的中文字体不存在，请检查 DEPTHSTRIKE_FONT")
        return str(path)
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = ([windows / "msyhbd.ttc"] if bold else []) + [
        windows / "msyh.ttc", windows / "simhei.ttf", windows / "simsun.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/System/Library/Fonts/PingFang.ttc"), Path("/System/Library/Fonts/STHeiti Light.ttc"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise DepthStrikeError("未找到中文字体，请安装思源黑体或通过 DEPTHSTRIKE_FONT 指定中文字体文件")


@lru_cache(maxsize=64)
def _font(pixels, bold, override):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise DepthStrikeError('中文界面需要 Pillow，请安装显示依赖：python -m pip install -e ".[display]"') from exc
    return ImageFont.truetype(_font_path(override, bold), pixels, layout_engine=ImageFont.Layout.BASIC)


@lru_cache(maxsize=512)
def _glyph(value, pixels, bold, override):
    from PIL import Image, ImageDraw
    font = _font(pixels, bold, override)
    left, top, right, bottom = font.getbbox(value, anchor="ls")
    mask = Image.new("L", (max(1, right-left), max(1, bottom-top)), 0)
    ImageDraw.Draw(mask).text((-left, -top), value, font=font, fill=255, anchor="ls")
    return np.asarray(mask, dtype=np.uint16), left, top


def draw_text(canvas, value, at, size=.55, color=(72, 54, 38), weight=1, *, max_width=None):
    """Draw cached CJK glyph masks without repeatedly converting the whole image."""
    value = str(value)
    if not value:
        return canvas
    x, y = map(int, at)
    available = canvas.shape[1]-max(0, x)-4
    if max_width is not None:
        available = min(available, int(max_width))
    if available <= 0:
        return canvas
    pixels, bold, override = max(10, round(size*30)), weight > 1, os.environ.get("DEPTHSTRIKE_FONT")
    # Resolve first so missing font/dependency errors remain actionable.
    font = _font(pixels, bold, override)
    width = font.getlength(value)
    if width > available:
        pixels = max(10, int(pixels*available/width))
        font = _font(pixels, bold, override)
        if font.getlength(value) > available:
            lo, hi = 0, len(value)
            while lo < hi:
                middle = (lo+hi+1)//2
                if font.getlength(value[:middle]+"…") <= available:
                    lo = middle
                else:
                    hi = middle-1
            value = value[:lo]+"…"
            if font.getlength(value) > available:
                return canvas
    mask, left, top = _glyph(value, pixels, bold, override)
    x, y = x+left, y+top
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.shape[1], x+mask.shape[1]), min(canvas.shape[0], y+mask.shape[0])
    if x1 <= x0 or y1 <= y0:
        return canvas
    alpha = mask[y0-y:y1-y, x0-x:x1-x, None]
    region = canvas[y0:y1, x0:x1]
    ink = np.asarray(color, dtype=np.uint16)
    region[:] = ((region.astype(np.uint16)*(255-alpha)+ink*alpha+127)//255).astype(np.uint8)
    return canvas


def set_window_title(cv2_module, window_id, title):
    """Set this application's title in Unicode; OpenCV 4.11 Win32 uses ANSI."""
    if os.name != "nt":
        cv2_module.setWindowTitle(window_id, title)
        return
    import ctypes as ct
    from ctypes import wintypes
    user32 = ct.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ct.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.SetWindowTextW.restype = wintypes.BOOL
    handle = user32.FindWindowW(None, window_id)
    if not handle:
        # The window may have been closed already (or creation mocked by tests).
        return
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ct.byref(owner))
    if owner.value != os.getpid():
        raise DepthStrikeError("窗口不属于当前程序，无法设置中文标题")
    if not user32.SetWindowTextW(handle, title):
        raise DepthStrikeError("无法设置中文窗口标题")
    return handle
