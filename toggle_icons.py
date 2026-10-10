"""Toggle Explorer's 'Show desktop icons' (same as right-click desktop > View > Show desktop icons)."""
import ctypes, sys
from desktop import u32, find_desktop_listview
lv = find_desktop_listview()
dv = u32.GetParent(lv)
want = sys.argv[1] if len(sys.argv) > 1 else "toggle"
vis = bool(u32.IsWindowVisible(lv))
if want == "toggle" or (want == "on" and not vis) or (want == "off" and vis):
    u32.SendMessageW(dv, 0x0111, 0x7402, 0)
import time; time.sleep(0.5)
print("icons visible:", bool(u32.IsWindowVisible(lv)))
