# Terraria Desktop Pet — MODLOG

Idea: user's Terraria character lives on the real Windows desktop, runs/jumps, mines desktop icons.
Route: NOT a game mod — standalone Python overlay (tkinter colour-key window, click-through, z-ordered
just above Progman). Reads user's own .plr + own Terraria textures at runtime; ships no game files.
Icon "breaking" is visual only (wallpaper patch drawn over icon). Never moves/deletes icons.

## Facts
- Terraria: E:\SteamLibrary\steamapps\common\Terraria ; player: Documents\My Games\Terraria\Players\aleksi_vataa.plr
- .plr = AES-128-CBC, key=IV=UTF-16LE "h3y_gUyZ". v319 layout: name@24 (7bit str), diff(1), playtime(8),
  hair(i32), hairDye(1), hideVisual(2), hideMisc(1), skinVariant(1), +1 unknown byte, life/lifeMax/mana/manaMax (4×i32),
  15 bytes bools/taxMoney, deathsPVE i32, deathsPVP i32, then 7 RGB: hair,skin,eye,shirt,undershirt,pants,shoe.
- Content XNBs are LZX-compressed (flag 0x80) for Images; Sounds uncompressed. Own LZX decoder in xnb.py.
- Player_0_N: 0 head,1 eye white,2 iris,10 legs,11 pants,12 shoes = 40x56 vertical strips (20 frames: 0 idle,5 jump,6-19 walk).
  3 torso,4/8 undershirt sleeve,5/9 hand,6 shirt (row2=shoulder),7 arm = composite 9x4 grid of 40x56.
  Hair: Player_Hair_{hair+1}. Pickaxe Item_3509. TileCracks 6 variants x 4 stages, 16px+2 pad.
- User had desktop icons HIDDEN (HideIcons=1). User OK'd: on for testing only, then hide again (`python toggle_icons.py off`).
- Desktop: 1920x1080 @96dpi, work area = full screen (taskbar autohide?). Wallpaper style 10 (fill).
