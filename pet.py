"""Terraria Desktop Pet - your own Terraria character runs, jumps and mines your desktop icons.

Everything is visual: icons are never moved, renamed or deleted. "Broken" icons are covered with a
patch of your wallpaper drawn by this overlay; quitting the pet makes them all come back.

Hotkeys (global):  Ctrl+Shift+Q quit   Ctrl+Shift+R restore all icons   Ctrl+Shift+J jump
"""
import argparse, ctypes, math, os, random, sys, time, winsound
import tkinter as tk
from PIL import Image, ImageTk, ImageGrab, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desktop
import character as ch
from xnb import load_texture, load_sound_wav

KEY = (255, 0, 254)          # transparent colour key
KEY_HEX = "#ff00fe"
u32 = ctypes.windll.user32


def log(*a):
    try:
        with open(os.path.join(HERE, "pet.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except OSError:
        pass


def binarize(im):
    r, g, b, a = im.split()
    a = a.point(lambda v: 255 if v >= 128 else 0)
    im = Image.merge("RGBA", (r, g, b, a))
    # avoid accidentally hitting the colour key
    return im


def to_photo(im):
    """RGBA (binary alpha) -> PhotoImage on the key colour."""
    bg = Image.new("RGBA", im.size, KEY + (255,))
    bg.alpha_composite(im)
    return ImageTk.PhotoImage(bg.convert("RGB"))


class Sounds:
    def __init__(self, terraria, cache):
        self.files = {}
        for n in ["Dig_0", "Dig_1", "Dig_2", "Item_1", "Tink_0", "Grab"]:
            out = os.path.join(cache, n + ".wav")
            try:
                if not os.path.exists(out):
                    load_sound_wav(os.path.join(terraria, "Content", "Sounds", n + ".xnb"), out)
                self.files[n] = out
            except Exception as e:
                log("sound fail", n, e)
        self.enabled = True

    def play(self, n):
        if not self.enabled:
            return
        if n == "dig":
            n = random.choice(["Dig_0", "Dig_1", "Dig_2"])
        f = self.files.get(n)
        if f:
            winsound.PlaySound(f, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


class Icon:
    def __init__(self, d):
        self.update(d)
        self.broken = False
        self.dmg = 0
        self.crack_variant = random.randrange(6)
        self.unreachable_until = 0

    def update(self, d):
        self.name = d["name"]
        self.l, self.t, self.r, self.b = d["rect"]
        self.icon = d["icon"]

    @property
    def key(self):
        return (self.name, self.l, self.t)

    @property
    def cx(self):
        return (self.l + self.r) / 2

    @property
    def cy(self):
        return (self.t + self.b) / 2


class Pet:
    HP = 5  # pickaxe hits per icon

    def __init__(self, args):
        self.args = args
        desktop.set_dpi_aware()
        self.mon, self.work = desktop.primary_monitor_rects()
        dpi = desktop.monitor_dpi()
        self.S = args.scale or max(2, round(2 * dpi / 96))
        S = self.S
        self.ox, self.oy = self.mon[0], self.mon[1]
        self.W, self.H = self.mon[2] - self.mon[0], self.mon[3] - self.mon[1]

        terraria = args.terraria or ch.find_terraria()
        if not terraria:
            raise SystemExit("Couldn't find your Terraria install. Pass --terraria \"<path to Terraria folder>\".")
        cache = os.path.join(HERE, "cache")
        plr = args.player or ch.find_player()
        look = ch.read_player(plr) if plr else dict(ch.DEFAULT_LOOK)
        log("player", plr, look)
        L = ch.Layers(terraria, look, cache)
        frames = ch.build_all(L)
        self.sounds = Sounds(terraria, cache)
        self.sounds.enabled = not args.mute

        # --- window ---
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("%dx%d+%d+%d" % (self.W, self.H, self.ox, self.oy))
        self.root.configure(bg=KEY_HEX)
        self.root.attributes("-transparentcolor", KEY_HEX)
        if args.topmost:
            self.root.attributes("-topmost", True)
        self.cv = tk.Canvas(self.root, width=self.W, height=self.H, bg=KEY_HEX, highlightthickness=0, bd=0)
        self.cv.pack()
        self.root.update_idletasks()
        self.hwnd = u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        ex = u32.GetWindowLongW(self.hwnd, -20)
        u32.SetWindowLongW(self.hwnd, -20, ex | 0x80000 | 0x20 | 0x80 | 0x08000000)
        self.place_in_zorder()

        # --- sprites ---
        def scale(im):
            return binarize(im.resize((im.width * S, im.height * S), Image.NEAREST))

        idle0 = frames["idle"][0]
        bbox = idle0.getbbox()
        self.foot_off = (ch.FH - bbox[3]) * S          # empty rows below the feet
        self.fw, self.fh = ch.FW * S, ch.FH * S
        self.hw = 10 * S                                # half hitbox width
        self.body_h = 42 * S
        self.anim = {}
        for k, lst in frames.items():
            self.anim[k] = {1: [to_photo(scale(f)) for f in lst],
                            -1: [to_photo(scale(ImageOps.mirror(f))) for f in lst]}
        # pickaxe, pre-rotated around its handle
        pick = load_texture(os.path.join(terraria, "Content", "Images", "Item_3509.xnb"))
        pick = binarize(pick)
        canvas = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        canvas.alpha_composite(pick, (48 - 3, 48 - 29))   # handle end at centre
        self.pick = {1: {}, -1: {}}
        for ang in range(-180, 181, 10):
            rot = canvas.rotate(ang - 45, resample=Image.NEAREST)
            img = binarize(rot.resize((96 * S, 96 * S), Image.NEAREST))
            self.pick[1][ang] = to_photo(img)
            self.pick[-1][ang] = to_photo(ImageOps.mirror(img))
        self.pick_size = self.pick[1][0].width()
        # crack tiles (4 stages x 6 variants, 16px + 2px pad)
        cr = load_texture(os.path.join(terraria, "Content", "Images", "TileCracks.xnb"))
        self.crack_tiles = [[binarize(cr.crop((c * 18, r * 18, c * 18 + 16, r * 18 + 16)).resize((16 * S, 16 * S), Image.NEAREST))
                             for c in range(6)] for r in range(4)]

        # --- wallpaper for "broken" patches ---
        self.wall = desktop.render_wallpaper((self.W, self.H))

        # --- world ---
        self.dicons = desktop.DesktopIcons()
        self.icons = {}
        self.refresh_icons(force=True)
        self.x = self.W * random.uniform(0.3, 0.7)
        self.y = self.floor_y() - 300               # feet y, falls in
        self.vx = self.vy = 0.0
        self.face = 1
        self.ground = None        # None (air), "floor" or Icon
        self.jump_frames = 0
        self.double_used = False
        self.fuel = self.ROCKET_FUEL
        self.rocketing = False
        self.leg_frame = 0
        self.leg_counter = 0.0
        self.state = "idle"
        self.state_t = 60
        self.goal = None          # Icon to break
        self.plat = None          # Icon platform to jump onto
        self.walk_target = None
        self.swing_t = -1         # swing progress frames, -1 = not swinging
        self.particles = []
        self.patch_items = {}
        self.crack_items = {}
        self.all_broken_at = None
        self.last_refresh = 0
        self.last_z = 0
        self.keys_prev = set()
        self.char_item = self.cv.create_image(0, 0, anchor="nw", image=self.anim["idle"][1][0], tags="char")
        self.pick_item = self.cv.create_image(-500, -500, anchor="center", image=self.pick[1][0], tags="pick", state="hidden")
        self.jump_peak = self.calc_jump_peak()
        log("start S=%d mon=%s work=%s icons=%d peak=%.0f" % (S, self.mon, self.work, len(self.icons), self.jump_peak))

    # ------------------------------------------------------------ environment
    def place_in_zorder(self):
        if self.args.topmost:
            return
        # sit just above the desktop (Progman) and below every normal window
        progman = u32.FindWindowW("Progman", None)
        above = u32.GetWindow(progman, 3)  # GW_HWNDPREV
        if above == self.hwnd:
            return
        flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE|NOMOVE|NOACTIVATE
        if above:
            u32.SetWindowPos(self.hwnd, above, 0, 0, 0, 0, flags)
        else:
            u32.SetWindowPos(self.hwnd, 1, 0, 0, 0, 0, flags)

    def floor_y(self):
        return self.work[3] - self.oy

    def refresh_icons(self, force=False):
        try:
            cur = self.dicons.icons()
        except Exception as e:
            log("icon read fail", e); cur = []
        seen = set()
        new = {}
        for d in cur:
            l, t, r, b = d["rect"]
            l -= self.ox; r -= self.ox; t -= self.oy; b -= self.oy
            if r <= 0 or l >= self.W or b <= 0 or t >= self.H:
                continue
            d = dict(d, rect=(l, t, r, b))
            k = (d["name"], l, t)
            ic = self.icons.get(k) or Icon(d)
            ic.update(d)
            new[k] = ic
            seen.add(k)
        # icons that moved/vanished lose their broken state + overlays
        for k, ic in self.icons.items():
            if k not in new:
                self.remove_overlays(ic)
                if ic is self.goal:
                    self.goal = None
                if ic is self.ground:
                    self.ground = None
                if ic is self.plat:
                    self.plat = None
        self.icons = new

    def remove_overlays(self, ic):
        for store in (self.patch_items, self.crack_items):
            it = store.pop(ic.key, None)
            if it:
                self.cv.delete(it[0])

    def alive_icons(self):
        return [i for i in self.icons.values() if not i.broken]

    # ------------------------------------------------------------ physics
    JUMP_V = 6.51      # Shiny Red Balloon jump speed (vanilla 5.01)

    def _rise(self, v, frames):
        S = self.S; vy = -v * S; y = 0; f = frames
        while vy < 0:
            y += vy
            if f > 0:
                f -= 1
            else:
                vy += 0.4 * S
        return -y

    ROCKET_FUEL = 70   # Rocket Boots thrust frames

    def calc_jump_peak(self):
        # balloon jump + Cloud in a Bottle at the apex + Rocket Boots at the next apex
        S = self.S
        self.single_peak = self._rise(self.JUMP_V, 15)
        vy, y = 0.0, 0.0
        for _ in range(self.ROCKET_FUEL):
            vy = max(vy - 0.55 * S, -5 * S); y += vy
        while vy < 0:
            vy += 0.4 * S; y += vy
        return self.single_peak + self._rise(self.JUMP_V, 11) - y

    def jump(self):
        if self.ground is not None:
            self.vy = -self.JUMP_V * self.S
            self.jump_frames = 15
            self.ground = None
            self.double_used = False

    def double_jump(self):
        if self.ground is None and not self.double_used:
            self.double_used = True
            self.vy = -self.JUMP_V * self.S
            self.jump_frames = 11
            S = self.S
            for k in range(14):   # cloud puff
                c = random.choice([(255, 255, 255), (235, 240, 255), (210, 220, 240)])
                self.add_particle(self.x + random.uniform(-14, 14) * S, self.y + random.uniform(-4, 2) * S,
                                  random.uniform(-1.6, 1.6) * S / 2, random.uniform(0, 1.2) * S / 2,
                                  S * random.choice([2, 3, 4]), c, random.randint(18, 34), grav=0.02)
            self.sounds.play("Item_1")

    def surfaces(self):
        yield ("floor", 0, self.W, self.floor_y())
        for ic in self.icons.values():
            if not ic.broken:
                yield (ic, ic.l, ic.r, ic.t)

    def physics(self):
        S = self.S
        # horizontal
        self.x += self.vx
        if self.x - self.hw < 0:
            self.x = self.hw; self.vx = 0
        if self.x + self.hw > self.W:
            self.x = self.W - self.hw; self.vx = 0
        # still supported?
        if self.ground is not None and self.ground != "floor":
            g = self.ground
            if g.broken or g.key not in self.icons or not (self.x + self.hw > g.l + 2 * S and self.x - self.hw < g.r - 2 * S):
                self.ground = None
        if self.ground is None:
            if self.jump_frames > 0:
                self.jump_frames -= 1
            elif self.rocketing and self.fuel > 0:
                self.fuel -= 1
                self.vy = max(self.vy - 0.55 * S, -5 * S)
                self.rocket_fx()
            else:
                self.rocketing = False
                self.vy = min(self.vy + 0.4 * S, 10 * S)
            ny = self.y + self.vy
            if self.vy >= 0:
                best = None
                for obj, l, r, top in self.surfaces():
                    if self.y <= top + 0.5 and ny >= top and self.x + self.hw > l + 2 * S and self.x - self.hw < r - 2 * S:
                        if best is None or top < best[1]:
                            best = (obj, top)
                if best:
                    ny = best[1]; self.vy = 0; self.ground = best[0]
                    self.on_land()
            if ny < 30 * S:  # don't fly off the top of the screen
                ny = 30 * S; self.vy = max(self.vy, 0); self.jump_frames = 0
            self.y = ny
        else:
            self.y = self.floor_y() if self.ground == "floor" else self.ground.t

    def rocket_fx(self):
        S = self.S
        for k in range(2):
            c = random.choice([(255, 220, 90), (255, 150, 40), (255, 90, 30), (150, 150, 150)])
            self.add_particle(self.x + random.uniform(-7, 5) * S, self.y - random.uniform(0, 3) * S,
                              random.uniform(-0.6, 0.6) * S / 2, random.uniform(1.5, 3.5) * S / 2,
                              S * random.choice([1, 2]), c, random.randint(10, 22), grav=0.0)

    def on_land(self):
        self.fuel = self.ROCKET_FUEL
        self.rocketing = False
        if self.state == "jump":
            self.state = "think"

    # ------------------------------------------------------------ brain
    def reach_ok(self, ic):
        S = self.S
        hx = (self.x - 34 * S, self.x + 34 * S)
        hy = (self.y - 72 * S, self.y + 4 * S)
        return ic.r > hx[0] and ic.l < hx[1] and ic.b > hy[0] and ic.t < hy[1]

    def walk_toward(self, tx, speed=None):
        S = self.S
        spd = speed or 1.7 * S
        dx = tx - self.x
        if abs(dx) < 3 * S:
            self.vx *= 0.5
            return True
        self.face = 1 if dx > 0 else -1
        self.vx += 0.25 * S * self.face
        self.vx = max(-spd, min(spd, self.vx))
        return False

    def pick_goal(self):
        now = time.time()
        cands = [i for i in self.alive_icons() if i.unreachable_until < now]
        if not cands:
            return None
        # prefer close ones (with a little randomness so it isn't robotic)
        cands.sort(key=lambda i: math.hypot(i.cx - self.x, (i.cy - self.y) * 1.3) * random.uniform(0.7, 1.3))
        return cands[0]

    def pick_platform(self, goal):
        """A platform to jump onto that gets us closer to `goal`."""
        S = self.S
        best, bestd = None, None
        cur_d = math.hypot(goal.cx - self.x, goal.cy - self.y)
        for ic in self.alive_icons():
            if ic is goal or ic is self.ground:
                continue
            rise = self.y - ic.t
            if rise < 6 * S or rise > self.jump_peak * 0.85:
                continue
            if abs(ic.cx - self.x) > 260 * S:
                continue
            d = math.hypot(goal.cx - ic.cx, goal.cy - ic.t)
            if d >= cur_d:
                continue
            d += abs(ic.cx - self.x) * 0.3
            if bestd is None or d < bestd:
                best, bestd = ic, d
        return best

    def think(self):
        S = self.S
        st = self.state
        if st == "mine":
            return
        if st == "jump":
            if self.plat is not None:
                if self.plat.broken:
                    self.plat = None
                else:
                    self.walk_toward(self.plat.cx, 2.2 * S)
                    # near the apex and still below the platform -> cloud jump
                    if self.vy > -0.6 * S and self.y > self.plat.t - 2 * S:
                        if not self.double_used:
                            self.double_jump()
                        elif self.fuel > 0:
                            self.rocketing = True
                    if self.rocketing and self.y < self.plat.t - 8 * S:
                        self.rocketing = False
            elif self.vy > -0.3 * S and random.random() < 0.03:
                self.double_jump()
            return
        if self.ground is None:
            self.vx *= 0.98
            return
        if st == "idle":
            self.vx *= 0.7
            self.state_t -= 1
            if self.state_t <= 0:
                self.state = "think"
            return
        if st == "wander":
            if self.walk_toward(self.walk_target) or self.state_t <= 0:
                self.state = "idle"; self.state_t = random.randint(30, 120)
            self.state_t -= 1
            if random.random() < 0.006:
                self.jump()
                self.state = "jump"; self.plat = None
            return
        # ---- think / approach ----
        if self.goal is None or self.goal.broken or self.goal.key not in self.icons:
            self.goal = self.pick_goal()
            self.approach_t = 0
            if self.goal is None:
                # nothing to smash: wander about
                self.state = "wander"; self.state_t = random.randint(120, 400)
                self.walk_target = random.uniform(self.hw, self.W - self.hw)
                return
            log("goal", self.goal.name)
        g = self.goal
        self.approach_t = getattr(self, "approach_t", 0) + 1
        if self.approach_t > 60 * 20:  # 20 s without success: give up on it for a while
            g.unreachable_until = time.time() + 30
            self.goal = None
            return
        if self.reach_ok(g):
            self.vx = 0
            self.face = 1 if g.cx >= self.x else -1
            self.state = "mine"; self.swing_t = 0
            if g.dmg == 0:
                self.grab_icon_pixels(g)
            return
        self.state = "approach"
        if g.b < self.y - 72 * S:            # goal is above us -> climb
            p = self.pick_platform(g)
            if p is None:
                # walk under the goal's column and look again; if already there it's unreachable
                if abs(g.cx - self.x) < 40 * S:
                    g.unreachable_until = time.time() + 20
                    self.goal = None
                else:
                    self.walk_toward(g.cx)
                return
            air_reach = 70 * S
            if abs(p.cx - self.x) > air_reach:
                self.walk_toward(p.cx)
            else:
                self.plat = p
                self.jump(); self.state = "jump"
        else:                                # same height or below: walk to it
            side = g.l - 14 * S if self.x < g.cx else g.r + 14 * S
            if g.t > self.y:                 # below: walk toward it (fall off our ledge)
                side = g.cx
            self.walk_toward(side)
            # stuck against nothing for a bit -> hop
            if abs(self.vx) < 0.3 and random.random() < 0.01:
                self.jump(); self.state = "jump"; self.plat = None

    # ------------------------------------------------------------ mining
    def grab_icon_pixels(self, ic):
        try:
            box = (ic.l + self.ox, ic.t + self.oy, ic.r + self.ox, ic.b + self.oy)
            ic.pixels = ImageGrab.grab(bbox=box).convert("RGB")
        except Exception:
            ic.pixels = None

    def mine_step(self):
        g = self.goal
        if g is None or g.broken or g.key not in self.icons or not self.reach_ok(g) or self.ground is None:
            self.state = "think"; self.swing_t = -1
            return
        self.swing_t += 1
        T = 22
        if self.swing_t == 1:
            self.sounds.play("Item_1")
        if self.swing_t == T // 2:
            self.hit(g)
        if self.swing_t >= T:
            self.swing_t = 0
            if g.broken:
                self.state = "idle"; self.state_t = random.randint(10, 50)
                self.swing_t = -1
                self.goal = None

    def hit(self, ic):
        ic.dmg += 1
        self.sounds.play("dig")
        self.spawn_dust(ic, 6)
        if ic.dmg >= self.HP:
            self.break_icon(ic)
        else:
            self.draw_cracks(ic)

    def draw_cracks(self, ic):
        S = self.S
        stage = min(3, int((ic.dmg / self.HP) * 4))
        w, h = ic.r - ic.l, ic.b - ic.t
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rnd = random.Random(hash(ic.key))
        ts = 16 * S
        for ty in range(0, h, ts):
            for tx in range(0, w, ts):
                img.alpha_composite(self.crack_tiles[stage][rnd.randrange(6)], (tx, ty))
        img = binarize(img.crop((0, 0, w, h)))
        ph = to_photo(img)
        old = self.crack_items.pop(ic.key, None)
        if old:
            self.cv.delete(old[0])
        it = self.cv.create_image(ic.l, ic.t, anchor="nw", image=ph, tags="crack")
        self.crack_items[ic.key] = (it, ph)
        self.restack()

    def break_icon(self, ic):
        ic.broken = True
        self.sounds.play("dig")
        log("broke", ic.name)
        old = self.crack_items.pop(ic.key, None)
        if old:
            self.cv.delete(old[0])
        patch = self.wall.crop((ic.l, ic.t, ic.r, ic.b))
        # keep pixels off the colour key
        ph = ImageTk.PhotoImage(patch)
        it = self.cv.create_image(ic.l, ic.t, anchor="nw", image=ph, tags="patch")
        self.patch_items[ic.key] = (it, ph)
        self.spawn_chunks(ic)
        self.restack()

    def restore_all(self):
        for ic in self.icons.values():
            if ic.broken:
                self.spawn_dust(ic, 10, sparkle=True)
            ic.broken = False; ic.dmg = 0
            self.remove_overlays(ic)
        self.sounds.play("Grab")
        self.all_broken_at = None
        log("restored all icons")

    # ------------------------------------------------------------ particles
    def spawn_chunks(self, ic):
        S = self.S
        px = getattr(ic, "pixels", None)
        cols = []
        if px is not None:
            sm = px.resize((6, 6), Image.BILINEAR)
            cols = [sm.getpixel((x, y)) for y in range(6) for x in range(6)]
        if not cols:
            cols = [(90, 140, 220), (240, 200, 60), (220, 220, 220)]
        for k in range(26):
            c = random.choice(cols)
            if tuple(c) == KEY:
                c = (254, 0, 254)
            sz = random.choice([2, 3, 3, 4]) * S
            x = random.uniform(ic.l, ic.r); y = random.uniform(ic.t, ic.b)
            vx = (x - ic.cx) * 0.08 + random.uniform(-2, 2) * S / 2
            vy = random.uniform(-6, -1.5) * S / 2
            self.add_particle(x, y, vx, vy, sz, c, random.randint(50, 90))

    def spawn_dust(self, ic, n, sparkle=False):
        S = self.S
        for k in range(n):
            if sparkle:
                c = random.choice([(255, 250, 180), (255, 255, 255), (180, 230, 255)])
            else:
                c = random.choice([(151, 107, 75), (120, 84, 58), (180, 140, 100)])
            x = random.uniform(ic.l, ic.r); y = random.uniform(ic.t, ic.b)
            self.add_particle(x, y, random.uniform(-1.5, 1.5) * S / 2, random.uniform(-3, -0.5) * S / 2,
                              S * random.choice([1, 2]), c, random.randint(20, 45), grav=0.15 if not sparkle else -0.02)

    def add_particle(self, x, y, vx, vy, sz, color, life, grav=0.25):
        col = "#%02x%02x%02x" % tuple(color[:3])
        if col == KEY_HEX:
            col = "#fe00fe"
        it = self.cv.create_rectangle(x, y, x + sz, y + sz, fill=col, outline="", tags="fx")
        self.particles.append([it, x, y, vx, vy, sz, life, grav * self.S])

    def update_particles(self):
        floor = self.floor_y()
        keep = []
        for p in self.particles:
            it, x, y, vx, vy, sz, life, g = p
            vy += g; x += vx; y += vy
            if y + sz > floor:
                y = floor - sz; vy *= -0.3; vx *= 0.6
            life -= 1
            if life <= 0:
                self.cv.delete(it); continue
            self.cv.coords(it, x, y, x + sz, y + sz)
            p[1:7] = [x, y, vx, vy, sz, life]
            keep.append(p)
        self.particles = keep

    # ------------------------------------------------------------ drawing
    def restack(self):
        self.cv.tag_raise("crack")
        self.cv.tag_raise("char")
        self.cv.tag_raise("pick")
        self.cv.tag_raise("fx")

    def draw(self):
        S = self.S
        f = self.face
        if self.state == "mine" and self.swing_t >= 0:
            t = self.swing_t / 22
            frames = self.anim["swing"][f]
            img = frames[min(3, int(t * 4))]
        elif self.ground is None:
            img = self.anim["jump"][f][0]
        elif abs(self.vx) > 0.4:
            self.leg_counter += abs(self.vx) / S * 1.3
            if self.leg_counter > 8:
                self.leg_counter = 0
                self.leg_frame = (self.leg_frame + 1) % len(self.anim["walk"][f])
            img = self.anim["walk"][f][self.leg_frame]
        else:
            img = self.anim["idle"][f][0]
        left = self.x - self.fw / 2
        top = self.y + self.foot_off - self.fh
        self.cv.itemconfigure(self.char_item, image=img)
        self.cv.coords(self.char_item, round(left), round(top))
        # pickaxe
        if self.state == "mine" and self.swing_t >= 0:
            t = min(1.0, self.swing_t / 22)
            ang = 140 - 190 * t                    # from up-behind to down-forward
            a10 = int(round(ang / 10.0)) * 10
            a10 = max(-180, min(180, a10))
            if f == -1:
                pass  # mirrored images already
            sx = self.x + f * 2 * S
            sy = top + 24 * S
            self.cv.itemconfigure(self.pick_item, image=self.pick[f][a10], state="normal")
            self.cv.coords(self.pick_item, round(sx), round(sy))
        else:
            self.cv.itemconfigure(self.pick_item, state="hidden")

    # ------------------------------------------------------------ input
    def hotkeys(self):
        ks = u32.GetAsyncKeyState
        down = lambda vk: ks(vk) & 0x8000
        mods = down(0x11) and down(0x10)
        pressed = set()
        if mods:
            for ch_, vk in (("Q", 0x51), ("R", 0x52), ("J", 0x4A)):
                if down(vk):
                    pressed.add(ch_)
        new = pressed - self.keys_prev
        self.keys_prev = pressed
        if "Q" in new:
            self.quit()
        if "R" in new:
            self.restore_all()
        if "J" in new:
            self.jump(); self.state = "jump"; self.plat = None
        # cursor tickles: mouse near the head -> hop
        pt = ctypes.wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        mx, my = pt.x - self.ox, pt.y - self.oy
        if abs(mx - self.x) < 14 * self.S and self.y - 50 * self.S < my < self.y and self.ground is not None \
                and self.state != "mine" and random.random() < 0.08:
            self.jump(); self.state = "jump"; self.plat = None

    # ------------------------------------------------------------ loop
    def tick(self):
        t0 = time.perf_counter()
        try:
            now = time.time()
            if now - self.last_refresh > 1.5:
                self.last_refresh = now
                self.refresh_icons()
                if not self.icons and self.patch_items:
                    for k in list(self.patch_items):
                        self.cv.delete(self.patch_items.pop(k)[0])
            if now - self.last_z > 1.0:
                self.last_z = now
                self.place_in_zorder()
            self.hotkeys()
            if self.state == "mine":
                self.mine_step()
            else:
                self.think()
            if self.ground is not None and self.state not in ("approach", "wander", "jump"):
                self.vx *= 0.75
            self.physics()
            self.update_particles()
            self.draw()
            if self.args.debug and int(now * 4) != getattr(self, "_dbg", 0):
                self._dbg = int(now * 4)
                with open(os.path.join(HERE, "pet_state.txt"), "w") as f:
                    f.write("%d %d %s %d" % (self.x + self.ox, self.y + self.oy, self.state, self.swing_t))
            # everything smashed -> restore after a while
            if self.icons and not self.alive_icons():
                if self.all_broken_at is None:
                    self.all_broken_at = now
                elif now - self.all_broken_at > self.args.respawn:
                    self.restore_all()
        except Exception as e:
            import traceback
            log("tick error", traceback.format_exc())
        dt = (time.perf_counter() - t0) * 1000
        self.root.after(max(1, int(16.7 - dt)), self.tick)

    def quit(self):
        log("quit")
        try:
            self.dicons.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.after(50, self.tick)
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description="Your Terraria character on your desktop, breaking icons (visually).")
    ap.add_argument("--player", help="path to a .plr file (default: most recently played)")
    ap.add_argument("--terraria", help="Terraria install folder")
    ap.add_argument("--scale", type=int, default=0, help="pixel scale (default 2x at 100%% DPI)")
    ap.add_argument("--topmost", action="store_true", help="draw above all windows instead of on the desktop layer")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--debug", action="store_true", help="write position to pet_state.txt")
    ap.add_argument("--respawn", type=float, default=20.0, help="seconds after everything is smashed before icons come back")
    args = ap.parse_args()
    # single instance
    ctypes.windll.kernel32.CreateMutexW(None, False, "TerrariaDesktopPet_single")
    if ctypes.windll.kernel32.GetLastError() == 183:
        return
    Pet(args).run()


if __name__ == "__main__":
    main()
