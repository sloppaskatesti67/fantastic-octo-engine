"""Read-only access to the Windows desktop: icon rectangles + names, and the wallpaper image.

Nothing here moves, renames or deletes icons; the pet only *draws* over them.
"""
import ctypes, os, struct, winreg
from ctypes import wintypes as W
from PIL import Image, ImageGrab

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
gdi = ctypes.windll.gdi32

u32.FindWindowW.restype = W.HWND
u32.FindWindowExW.restype = W.HWND
u32.FindWindowExW.argtypes = [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR]
u32.SendMessageW.restype = ctypes.c_ssize_t
u32.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
k32.OpenProcess.restype = W.HANDLE
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD, W.DWORD]
k32.VirtualFreeEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD]
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

LVM_GETITEMCOUNT = 0x1004
LVM_GETITEMRECT = 0x100E
LVM_GETITEMTEXTW = 0x1073
LVIR_BOUNDS, LVIR_ICON = 0, 1


def set_dpi_aware():
    try:
        u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            u32.SetProcessDPIAware()


def find_desktop_listview():
    progman = u32.FindWindowW("Progman", None)
    dv = u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    if not dv:
        w = None
        while True:
            w = u32.FindWindowExW(None, w, "WorkerW", None)
            if not w:
                break
            dv = u32.FindWindowExW(w, None, "SHELLDLL_DefView", None)
            if dv:
                break
    if not dv:
        return None
    return u32.FindWindowExW(dv, None, "SysListView32", None)


class DesktopIcons:
    def __init__(self):
        self.lv = find_desktop_listview()
        self.proc = None
        self.mem = None
        if self.lv:
            pid = W.DWORD()
            u32.GetWindowThreadProcessId(self.lv, ctypes.byref(pid))
            self.proc = k32.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid.value)
            if self.proc:
                self.mem = k32.VirtualAllocEx(self.proc, None, 4096, 0x3000, 0x04)

    def close(self):
        if self.mem:
            k32.VirtualFreeEx(self.proc, self.mem, 0, 0x8000)
            self.mem = None
        if self.proc:
            k32.CloseHandle(self.proc)
            self.proc = None

    def _w(self, off, data):
        k32.WriteProcessMemory(self.proc, self.mem + off, data, len(data), None)

    def _r(self, off, n):
        buf = ctypes.create_string_buffer(n)
        k32.ReadProcessMemory(self.proc, self.mem + off, buf, n, None)
        return buf.raw

    def visible(self):
        return bool(self.lv) and bool(u32.IsWindowVisible(self.lv))

    def icons(self):
        """List of dicts {i, name, rect:(l,t,r,b) screen px, icon:(l,t,r,b)}."""
        if not (self.lv and self.mem) or not self.visible():
            return []
        n = u32.SendMessageW(self.lv, LVM_GETITEMCOUNT, 0, 0)
        out = []
        for i in range(n):
            rects = []
            for code in (LVIR_BOUNDS, LVIR_ICON):
                self._w(0, struct.pack("<iiii", code, 0, 0, 0))
                if not u32.SendMessageW(self.lv, LVM_GETITEMRECT, i, self.mem):
                    break
                r = W.RECT(*struct.unpack("<iiii", self._r(0, 16)))
                u32.MapWindowPoints(self.lv, None, ctypes.byref(r), 2)
                rects.append((r.left, r.top, r.right, r.bottom))
            if len(rects) < 2:
                continue
            # item text: LVITEMW (64-bit layout) at +64, text buffer at +256
            lvitem = struct.pack("<IiiII4xQii", 0x1, i, 0, 0, 0, self.mem + 256, 260, 0) + bytes(88 - 40)
            self._w(64, lvitem)
            ln = u32.SendMessageW(self.lv, LVM_GETITEMTEXTW, i, self.mem + 64)
            name = self._r(256, max(0, ln) * 2).decode("utf-16-le", "replace") if ln > 0 else "?"
            out.append({"i": i, "name": name, "rect": rects[0], "icon": rects[1]})
        return out


def primary_monitor_rects():
    """(monitor rect, work area rect) of the primary monitor in physical px."""
    class MI(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]
    u32.MonitorFromPoint.restype = W.HANDLE
    hm = u32.MonitorFromPoint(W.POINT(0, 0), 1)
    mi = MI(); mi.cbSize = ctypes.sizeof(MI)
    u32.GetMonitorInfoW(hm, ctypes.byref(mi))
    m, w = mi.rcMonitor, mi.rcWork
    return (m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom)


def monitor_dpi():
    try:
        hm = u32.MonitorFromPoint(W.POINT(0, 0), 1)
        x, y = ctypes.c_uint(), ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(ctypes.c_void_p(hm), 0, ctypes.byref(x), ctypes.byref(y))
        return x.value
    except Exception:
        return 96


# ---------------- wallpaper ----------------
def _reg(name, default=""):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
        return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def _bg_color():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Colors")
        return tuple(int(v) for v in winreg.QueryValueEx(k, "Background")[0].split())
    except Exception:
        return (0, 0, 0)


def render_wallpaper(size):
    """Recreate the primary monitor's wallpaper as a PIL image of `size` (w, h)."""
    W_, H_ = size
    canvas = Image.new("RGB", size, _bg_color())
    path = _reg("WallPaper")
    cand = [path, os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper")]
    src = None
    for c in cand:
        if c and os.path.isfile(c):
            try:
                src = Image.open(c).convert("RGB"); break
            except Exception:
                pass
    if src is None:
        return canvas
    style = str(_reg("WallpaperStyle", "10")); tile = str(_reg("TileWallpaper", "0"))
    sw, sh = src.size
    if tile == "1":
        for y in range(0, H_, sh):
            for x in range(0, W_, sw):
                canvas.paste(src, (x, y))
    elif style == "2":  # stretch
        canvas = src.resize(size, Image.LANCZOS)
    elif style == "6":  # fit
        s = min(W_ / sw, H_ / sh); im = src.resize((round(sw * s), round(sh * s)), Image.LANCZOS)
        canvas.paste(im, ((W_ - im.width) // 2, (H_ - im.height) // 2))
    elif style == "0":  # center
        canvas.paste(src, ((W_ - sw) // 2, (H_ - sh) // 2))
    else:  # 10 fill / 22 span / default
        s = max(W_ / sw, H_ / sh); im = src.resize((round(sw * s), round(sh * s)), Image.LANCZOS)
        canvas.paste(im, ((W_ - im.width) // 2, (H_ - im.height) // 2))
    return canvas


if __name__ == "__main__":
    set_dpi_aware()
    mon, work = primary_monitor_rects()
    print("monitor", mon, "work", work, "dpi", monitor_dpi())
    d = DesktopIcons()
    print("listview", d.lv, "visible", d.visible())
    ic = d.icons()
    for it in ic:
        print(it)
    d.close()
    print("wallpaper", _reg("WallPaper"), "style", _reg("WallpaperStyle"), "tile", _reg("TileWallpaper"))
