"""Minimal XNB Texture2D reader (XNA 4.0, LZX-compressed or raw) -> PIL.Image.

Reads textures straight from the user's own Terraria install; nothing is copied or shipped.
LZX decoder follows the libmspack / MonoGame LzxDecoder logic.
"""
import struct
from PIL import Image

# ---------------- LZX ----------------
_EXTRA_BITS = []
_POS_BASE = []
j = 0
for i in range(0, 52, 2):
    _EXTRA_BITS += [j, j]
    if i != 0 and j < 17:
        j += 1
j = 0
for i in range(52):
    _POS_BASE.append(j)
    j += 1 << _EXTRA_BITS[i]
del i, j


class _Bits:
    __slots__ = ("d", "p", "buf", "n")

    def __init__(self, data):
        self.d, self.p, self.buf, self.n = data, 0, 0, 0

    def _fill(self, need):
        while self.n < need:
            if self.p + 1 < len(self.d):
                w = self.d[self.p] | (self.d[self.p + 1] << 8)
            else:
                w = 0
            self.p += 2
            self.buf = ((self.buf << 16) | w) & 0xFFFFFFFFFFFF
            self.n += 16

    def peek(self, k):
        self._fill(k)
        return (self.buf >> (self.n - k)) & ((1 << k) - 1)

    def drop(self, k):
        self.n -= k

    def read(self, k):
        if k == 0:
            return 0
        v = self.peek(k)
        self.n -= k
        return v

    def align(self):
        # discard bits up to the next 16-bit boundary
        self.n -= self.n % 16


def _make_table(lens):
    """Return (table, maxbits); table[peek(maxbits)] = (sym << 5) | len."""
    maxb = max(lens) if lens else 0
    if maxb == 0:
        return [0], 1
    table = [0] * (1 << maxb)
    code = 0
    for L in range(1, maxb + 1):
        for sym, l in enumerate(lens):
            if l == L:
                shift = maxb - L
                start = code << shift
                v = (sym << 5) | L
                for k in range(start, start + (1 << shift)):
                    table[k] = v
                code += 1
        code <<= 1
    return table, maxb


def _sym(bits, tbl):
    table, maxb = tbl
    v = table[bits.peek(maxb)]
    bits.drop(v & 31)
    return v >> 5


class Lzx:
    def __init__(self, window_bits=16):
        self.wsize = 1 << window_bits
        self.win = bytearray(self.wsize)
        self.wpos = 0
        posn_slots = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}[window_bits]
        self.main_n = 256 + posn_slots * 8
        self.main_len = [0] * self.main_n
        self.len_len = [0] * 249
        self.R = [1, 1, 1]
        self.header = False
        self.btype = 0
        self.bremain = 0
        self.main_t = self.len_t = self.al_t = None

    def _read_lens(self, bits, lens, first, last):
        pre = [bits.read(4) for _ in range(20)]
        pt = _make_table(pre)
        x = first
        while x < last:
            z = _sym(bits, pt)
            if z == 17:
                y = bits.read(4) + 4
                for _ in range(y):
                    lens[x] = 0; x += 1
            elif z == 18:
                y = bits.read(5) + 20
                for _ in range(y):
                    lens[x] = 0; x += 1
            elif z == 19:
                y = bits.read(1) + 4
                z = _sym(bits, pt)
                z = lens[x] - z
                if z < 0: z += 17
                for _ in range(y):
                    lens[x] = z; x += 1
            else:
                z = lens[x] - z
                if z < 0: z += 17
                lens[x] = z; x += 1

    def decompress(self, chunk, out_len):
        bits = _Bits(chunk)
        out = bytearray()
        win, wmask = self.win, self.wsize - 1
        R = self.R
        if not self.header:
            if bits.read(1):
                bits.read(16); bits.read(16)  # intel e8 filesize (unused for XNB)
            self.header = True
        togo = out_len
        while togo > 0:
            if self.bremain == 0:
                if self.btype == 3 and (self._ublen & 1):
                    bits.p += 1  # pad byte after odd uncompressed block
                self.btype = bits.read(3)
                hi = bits.read(16); lo = bits.read(8)
                self.bremain = self._ublen = (hi << 8) | lo
                if self.btype == 2:
                    al = [bits.read(3) for _ in range(8)]
                    self.al_t = _make_table(al)
                if self.btype in (1, 2):
                    self._read_lens(bits, self.main_len, 0, 256)
                    self._read_lens(bits, self.main_len, 256, self.main_n)
                    self.main_t = _make_table(self.main_len)
                    self._read_lens(bits, self.len_len, 0, 249)
                    self.len_t = _make_table(self.len_len)
                elif self.btype == 3:
                    bits.align()
                    # bit buffer may hold up to one prefetched word -> rewind
                    bits.p -= bits.n // 8
                    bits.n = 0; bits.buf = 0
                    R[0], R[1], R[2] = struct.unpack_from("<III", chunk, bits.p)
                    bits.p += 12
                else:
                    raise ValueError("bad LZX block type %d" % self.btype)
            run = min(self.bremain, togo)
            start = self.wpos
            if self.btype == 3:
                for k in range(run):
                    win[self.wpos] = chunk[bits.p]; bits.p += 1
                    self.wpos = (self.wpos + 1) & wmask
            else:
                aligned = self.btype == 2
                wpos = self.wpos
                while run > 0:
                    me = _sym(bits, self.main_t)
                    if me < 256:
                        win[wpos] = me; wpos = (wpos + 1) & wmask; run -= 1
                        continue
                    me -= 256
                    ml = me & 7
                    if ml == 7:
                        ml += _sym(bits, self.len_t)
                    ml += 2
                    mo = me >> 3
                    if mo > 2:
                        if not aligned:
                            if mo != 3:
                                eb = _EXTRA_BITS[mo]
                                mo = _POS_BASE[mo] - 2 + bits.read(eb)
                            else:
                                mo = 1
                        else:
                            eb = _EXTRA_BITS[mo]
                            mo = _POS_BASE[mo] - 2
                            if eb > 3:
                                mo += bits.read(eb - 3) << 3
                                mo += _sym(bits, self.al_t)
                            elif eb == 3:
                                mo += _sym(bits, self.al_t)
                            elif eb > 0:
                                mo += bits.read(eb)
                            else:
                                mo = 1
                        R[2] = R[1]; R[1] = R[0]; R[0] = mo
                    elif mo == 0:
                        mo = R[0]
                    elif mo == 1:
                        mo = R[1]; R[1] = R[0]; R[0] = mo
                    else:
                        mo = R[2]; R[2] = R[0]; R[0] = mo
                    src = (wpos - mo) & wmask
                    run -= ml
                    for _ in range(ml):
                        win[wpos] = win[src]
                        wpos = (wpos + 1) & wmask
                        src = (src + 1) & wmask
                self.wpos = wpos
            # copy produced bytes (a match may overrun the block; count what was really produced)
            end = self.wpos
            produced = (end - start) & wmask
            togo -= produced
            self.bremain -= produced
            if end >= start:
                out += win[start:end]
            else:
                out += win[start:] + win[:end]
        return bytes(out[:out_len])


def _decompress_xnb(payload, out_size):
    lzx = Lzx(16)
    out = bytearray()
    p = 0
    while p < len(payload) and len(out) < out_size:
        hi = payload[p]
        if hi == 0xFF:
            frame = (payload[p + 1] << 8) | payload[p + 2]
            block = (payload[p + 3] << 8) | payload[p + 4]
            p += 5
        else:
            frame = 0x8000
            block = (payload[p] << 8) | payload[p + 1]
            p += 2
        if block == 0 or frame == 0:
            break
        out += lzx.decompress(payload[p:p + block], frame)
        p += block
    return bytes(out)


# ---------------- XNB container ----------------
def _read7(b, p):
    v = s = 0
    while True:
        c = b[p]; p += 1
        v |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return v, p


def load_texture(path):
    raw = open(path, "rb").read()
    if raw[:3] != b"XNB":
        raise ValueError("not an XNB: %s" % path)
    flags = raw[5]
    if flags & 0x80:
        size = struct.unpack_from("<I", raw, 10)[0]
        body = _decompress_xnb(raw[14:], size)
    else:
        body = raw[10:]
    n, p = _read7(body, 0)
    for _ in range(n):
        sl, p = _read7(body, p)
        p += sl + 4
    _, p = _read7(body, p)  # shared resources
    _, p = _read7(body, p)  # type id
    fmt, w, h, mips = struct.unpack_from("<iIII", body, p); p += 16
    if fmt != 0:
        raise ValueError("unsupported surface format %d" % fmt)
    dsize = struct.unpack_from("<I", body, p)[0]; p += 4
    img = Image.frombytes("RGBA", (w, h), body[p:p + dsize])
    # XNA content is premultiplied; un-premultiply for tinting
    px = img.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if 0 < a < 255:
                px[x, y] = (min(255, r * 255 // a), min(255, g * 255 // a), min(255, b * 255 // a), a)
    return img


if __name__ == "__main__":
    import sys, os
    for f in sys.argv[2:]:
        im = load_texture(f)
        o = os.path.join(sys.argv[1], os.path.basename(f)[:-4] + ".png")
        im.save(o)
        print(o, im.size)


def load_sound_wav(path, out_wav):
    """XNB SoundEffect -> .wav file (PCM, as stored)."""
    raw = open(path, "rb").read()
    if raw[5] & 0x80:
        size = struct.unpack_from("<I", raw, 10)[0]
        body = _decompress_xnb(raw[14:], size)
    else:
        body = raw[10:]
    n, p = _read7(body, 0)
    for _ in range(n):
        sl, p = _read7(body, p)
        p += sl + 4
    _, p = _read7(body, p)
    _, p = _read7(body, p)
    fsz = struct.unpack_from("<I", body, p)[0]; p += 4
    fmt = body[p:p + fsz]; p += fsz
    dsz = struct.unpack_from("<I", body, p)[0]; p += 4
    data = body[p:p + dsz]
    fmt16 = fmt[:16]
    wav = b"RIFF" + struct.pack("<I", 4 + 8 + 16 + 8 + len(data)) + b"WAVE"
    wav += b"fmt " + struct.pack("<I", 16) + fmt16 + b"data" + struct.pack("<I", len(data)) + data
    open(out_wav, "wb").write(wav)
