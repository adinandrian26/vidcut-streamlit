"""Driver background untuk tab Gemini di Chrome yang terbuka.

Tidak pernah membuka Chrome baru, tidak mengambil fokus layar (foreground
dikembalikan tiap burst), tidak meminimize (konten harus tetap render).

Teknik:
- klik/ketik via PostMessage ke Chrome_RenderWidgetHWND (tanpa fokus),
- screenshot via PrintWindow (bisa walau jendela tertutup jendela lain),
- koordinat dalam piksel client widget (stabil saat maximized).
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32

u32.GetWindowDC.argtypes = [wintypes.HWND]
u32.GetWindowDC.restype = wintypes.HDC
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
u32.PrintWindow.restype = wintypes.BOOL
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi.CreateCompatibleDC.restype = wintypes.HDC
gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi.DeleteDC.argtypes = [wintypes.HDC]
gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                          wintypes.UINT, ctypes.c_void_p,
                          ctypes.c_void_p, wintypes.UINT]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
MK_LBUTTON = 0x0001
VK_CONTROL = 0x11
VK_RETURN = 0x0D
PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


def _rect(hwnd) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def find_gemini_main() -> int:
    """HWND jendela Chrome yang tab aktifnya Gemini. 0 bila tidak ketemu."""
    import uiautomation as auto

    root = auto.GetRootControl()
    wins = [w for w in root.GetChildren()
            if getattr(w, "ClassName", "") == "Chrome_WidgetWin_1"]

    def find_omni(x, d=0):
        if d > 14:
            return None
        try:
            if (x.ControlTypeName == "EditControl"
                    and "Address and search" in (x.Name or "")):
                try:
                    return x.GetValuePattern().Value
                except Exception:
                    return None
            for ch in x.GetChildren():
                v = find_omni(ch, d + 1)
                if v:
                    return v
        except Exception:
            pass
        return None

    for w in wins:
        try:
            hwnd = w.NativeWindowHandle
        except Exception:
            continue
        if "gemini.google.com" in (find_omni(w) or ""):
            return int(hwnd)
    return 0


def render_widget(main_hwnd: int) -> int:
    """HWND Chrome_RenderWidgetHostHWND terbesar di jendela utama."""
    found = []

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(hwnd, buf, 64)
        if buf.value == "Chrome_RenderWidgetHostHWND":
            r = wintypes.RECT()
            if u32.GetWindowRect(hwnd, ctypes.byref(r)):
                area = (r.right - r.left) * (r.bottom - r.top)
                found.append((area, hwnd))
        return True

    CMP = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    u32.EnumChildWindows(main_hwnd, CMP(cb), 0)
    if not found:
        return 0
    return max(found)[1]


def _lparam(x: int, y: int) -> int:
    return (y << 16) | (x & 0xFFFF)


def post_click(widget_hwnd: int, cx: int, cy: int) -> None:
    u32.PostMessageW(widget_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, _lparam(cx, cy))
    time.sleep(0.08)
    u32.PostMessageW(widget_hwnd, WM_LBUTTONUP, 0, _lparam(cx, cy))
    time.sleep(0.3)


def post_key(widget_hwnd: int, vk: int, gap: float = 0.05) -> None:
    scan = u32.MapVirtualKeyW(vk, 0)
    u32.PostMessageW(widget_hwnd, WM_KEYDOWN, vk, (scan << 16) | 1)
    time.sleep(gap)
    u32.PostMessageW(widget_hwnd, WM_KEYUP, vk,
                      (scan << 16) | 0xC0000001)
    time.sleep(gap)


def post_text(widget_hwnd: int, text: str, gap: float = 0.004) -> None:
    for ch in text:
        u32.PostMessageW(widget_hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(gap)


def post_ctrl(widget_hwnd: int, key: str) -> None:
    """Ctrl+<key>, mis. 'a', 'v'. Mengembalikan fokus jika perlu."""
    vk = ord(key.upper())
    scan_ctrl = u32.MapVirtualKeyW(VK_CONTROL, 0)
    scan_k = u32.MapVirtualKeyW(vk, 0)
    u32.PostMessageW(widget_hwnd, WM_KEYDOWN, VK_CONTROL, (scan_ctrl << 16) | 1)
    time.sleep(0.05)
    u32.PostMessageW(widget_hwnd, WM_KEYDOWN, vk, (scan_k << 16) | 1)
    time.sleep(0.05)
    u32.PostMessageW(widget_hwnd, WM_KEYUP, vk, (scan_k << 16) | 0xC0000001)
    time.sleep(0.05)
    u32.PostMessageW(widget_hwnd, WM_KEYUP, VK_CONTROL,
                      (scan_ctrl << 16) | 0xC0000001)
    time.sleep(0.2)


def capture_window(main_hwnd: int, dest: Path) -> Path:
    """Screenshot jendela walau tertutup (PrintWindow)."""
    from PIL import Image

    l, t, r, b = _rect(main_hwnd)
    w, h = r - l, b - t
    hdc_win = u32.GetWindowDC(main_hwnd)
    hdc_mem = gdi.CreateCompatibleDC(hdc_win)
    hbmp = gdi.CreateCompatibleBitmap(hdc_win, w, h)
    gdi.SelectObject(hdc_mem, hbmp)
    u32.PrintWindow(main_hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    bmp_info = BITMAPINFO()
    bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmp_info.bmiHeader.biWidth = w
    bmp_info.bmiHeader.biHeight = -h
    bmp_info.bmiHeader.biPlanes = 1
    bmp_info.bmiHeader.biBitCount = 32
    buf_len = w * h * 4
    buf = ctypes.create_string_buffer(buf_len)
    gdi.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmp_info), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    img.convert("RGB").save(dest)
    gdi.DeleteObject(hbmp)
    gdi.DeleteDC(hdc_mem)
    u32.ReleaseDC(main_hwnd, hdc_win)
    return dest


def region_diff(a, b, box: tuple[int, int, int, int]) -> float:
    """Rata-rata beda piksel absolut region box (0 = identik)."""
    import numpy as np

    ra = np.asarray(a.convert("L"), dtype=float)
    rb = np.asarray(b.convert("L"), dtype=float)
    x0, y0, x1, y1 = box
    da = ra[y0:y1, x0:x1]
    db = rb[y0:y1, x0:x1]
    if da.size == 0:
        return 0.0
    return float(abs(da - db).mean())
