"""Build the user's Terraria character sprite frames from their own .plr save + their own game textures."""
import os, struct, json, glob
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from PIL import Image, ImageChops
from xnb import load_texture

PLR_KEY = "h3y_gUyZ".encode("utf-16-le")  # Terraria's public player-file key
FW, FH = 40, 56

DEFAULT_LOOK = dict(name="Guide", hair=0, skinVariant=0,
                    hairColor=(215, 90, 55), skinColor=(255, 125, 90), eyeColor=(105, 90, 75),
                    shirtColor=(175, 165, 140), underShirtColor=(160, 180, 215),
                    pantsColor=(255, 230, 175), shoeColor=(160, 105, 60))


def _read_str(b, p):
    n = s = 0
    while True:
        c = b[p]; p += 1
        n |= (c & 0x7F) << s; s += 7
        if not c & 0x80:
            break
    return b[p:p + n].decode("utf-8", "replace"), p + n


def read_player(path):
    data = open(path, "rb").read()
    d = Cipher(algorithms.AES(PLR_KEY), modes.CBC(PLR_KEY)).decryptor()
    b = d.update(data) + d.finalize()
    ver = struct.unpack_from("<i", b, 0)[0]
    look = dict(DEFAULT_LOOK)
    p = 24 if ver >= 135 else 4
    look["name"], p = _read_str(b, p)
    p += 1          # difficulty
    p += 8          # play time
    look["hair"] = struct.unpack_from("<i", b, p)[0]; p += 4
    p += 1          # hair dye
    p += 3          # hideVisibleAccessory (2) + hideMisc (1)
    look["skinVariant"] = b[p]; p += 1
    # Remaining fields before the colours vary by version. Colours are seven RGB triplets that
    # directly follow the PvE/PvP death counters; find them by scanning for the stat block
    # (life, lifeMax, mana, manaMax) and then the death counters.
    life, lifemax, mana, manamax = struct.unpack_from("<iiii", b, p + 1)
    if 0 <= life <= 1000 and 100 <= lifemax <= 600:
        p += 1  # one extra byte in 1.4.5 (v>=300ish)
    p += 16
    # bools/ints until deaths; v319 layout: 15 bytes then int32 deathsPVE, int32 deathsPVP
    skip = {319: 15}.get(ver)
    if skip is None:
        # best-effort: newest known layout
        skip = 19
    p += skip + 8
    names = ["hairColor", "skinColor", "eyeColor", "shirtColor", "underShirtColor", "pantsColor", "shoeColor"]
    for i, n in enumerate(names):
        look[n] = tuple(b[p + i * 3:p + i * 3 + 3])
    look["version"] = ver
    return look


def find_player():
    docs = os.path.join(os.path.expanduser("~"), "Documents", "My Games", "Terraria", "Players")
    fs = sorted(glob.glob(os.path.join(docs, "*.plr")), key=os.path.getmtime, reverse=True)
    return fs[0] if fs else None


def find_terraria():
    cands = [r"E:\SteamLibrary\steamapps\common\Terraria",
             r"C:\Program Files (x86)\Steam\steamapps\common\Terraria"]
    vdf = r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"
    if os.path.exists(vdf):
        import re
        for m in re.finditer(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="ignore").read()):
            cands.append(os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps", "common", "Terraria"))
    for c in cands:
        if os.path.exists(os.path.join(c, "Content", "Images", "Player_0_0.xnb")):
            return c
    return None


class Layers:
    def __init__(self, terraria, look, cache_dir):
        self.look = look
        self.img = os.path.join(terraria, "Content", "Images")
        self.cache = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._t = {}

    def tex(self, name):
        if name not in self._t:
            cp = os.path.join(self.cache, name + ".png")
            if os.path.exists(cp):
                im = Image.open(cp).convert("RGBA")
            else:
                im = load_texture(os.path.join(self.img, name + ".xnb"))
                im.save(cp)
            self._t[name] = im
        return self._t[name]

    def piece(self, name, col, row, color=None):
        t = self.tex(name)
        im = t.crop((col * FW, row * FH, col * FW + FW, row * FH + FH))
        if im.size != (FW, FH):
            im = im.crop((0, 0, FW, FH))
        if color:
            tint = Image.new("RGBA", im.size, tuple(color) + (255,))
            im = ImageChops.multiply(im, tint)
        return im


# Leg frame indices in the 20-frame vertical strips: 0 idle, 5 jump, 6..19 walk
WALK_FRAMES = list(range(6, 20))
# head/torso bob (pixels up) for walk frames, from Terraria's walk cycle
BOB = {7: 2, 8: 2, 9: 2, 14: 2, 15: 2, 16: 2}


def build_frame(L, leg_frame, arm_front=(7, 0), arm_back=(8, 0), torso_col=0):
    lk = L.look
    sv = lk["skinVariant"]
    pf = "Player_%d_" % sv
    skin, shirt, under = lk["skinColor"], lk["shirtColor"], lk["underShirtColor"]
    frame = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    bob = BOB.get(leg_frame, 0)

    def put(im, dy=0):
        frame.alpha_composite(im, (0, -dy))

    # back arm
    put(L.piece(pf + "7", *arm_back, color=skin), bob)
    put(L.piece(pf + "8", *arm_back, color=under), bob)
    put(L.piece(pf + "9", *arm_back, color=skin), bob)
    # legs
    put(L.piece(pf + "10", 0, leg_frame, color=skin))
    put(L.piece(pf + "11", 0, leg_frame, color=lk["pantsColor"]))
    put(L.piece(pf + "12", 0, leg_frame, color=lk["shoeColor"]))
    # torso
    put(L.piece(pf + "3", torso_col, 0, color=skin), bob)
    put(L.piece(pf + "6", torso_col, 0, color=shirt), bob)
    # head
    put(L.piece(pf + "0", 0, 0, color=skin), bob)
    put(L.piece(pf + "1", 0, 0), bob)
    put(L.piece(pf + "2", 0, 0, color=lk["eyeColor"]), bob)
    hair_id = lk["hair"] + 1
    try:
        put(L.piece("Player_Hair_%d" % hair_id, 0, 0, color=lk["hairColor"]), bob)
    except FileNotFoundError:
        pass
    # front arm + shoulder
    put(L.piece(pf + "7", *arm_front, color=skin), bob)
    put(L.piece(pf + "4", *arm_front, color=under), bob)
    put(L.piece(pf + "5", *arm_front, color=skin), bob)
    put(L.piece(pf + "6", torso_col, 2, color=shirt), bob)
    return frame


def build_all(L):
    frames = {"idle": [build_frame(L, 0)], "jump": [build_frame(L, 5, arm_front=(4, 0), arm_back=(8, 0))]}
    walk = []
    # front arm swings forward/back across the cycle using the row-1 poses
    swing = [(7, 0), (7, 1), (7, 2), (7, 3), (7, 2), (7, 1), (7, 0)]
    for i, lf in enumerate(WALK_FRAMES):
        walk.append(build_frame(L, lf))
    frames["walk"] = walk
    # swing attack (pickaxe-style) arm frames
    frames["swing"] = [build_frame(L, 0, arm_front=(c, 0)) for c in (3, 4, 5, 6)]
    return frames


if __name__ == "__main__":
    import sys
    plr = find_player(); ter = find_terraria()
    look = read_player(plr) if plr else dict(DEFAULT_LOOK)
    print(json.dumps(look))
    L = Layers(ter, look, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache"))
    fr = build_all(L)
    allf = fr["idle"] + fr["jump"] + fr["walk"] + fr["swing"]
    sheet = Image.new("RGBA", (FW * len(allf), FH), (70, 130, 180, 255))
    for i, f in enumerate(allf):
        sheet.alpha_composite(f, (i * FW, 0))
    out = sys.argv[1] if len(sys.argv) > 1 else "preview.png"
    sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST).save(out)
    print("wrote", out)
