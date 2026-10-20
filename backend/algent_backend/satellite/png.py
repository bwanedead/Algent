"""
Pure-Python PNG decode (and a tiny encoder for tests): no numpy, no PIL. Handles what the imagery services return: non-interlaced,
8-bit grey / grey+alpha / RGB / RGBA / palette. A chip is a few hundred pixels square, so a row-by-row pass is plenty.
"""

from __future__ import annotations

import struct
import zlib
from typing import NamedTuple

_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Image(NamedTuple):
    width: int
    height: int
    channels: int               # after palette expansion: 1 grey, 2 grey+alpha, 3 RGB, 4 RGBA
    pixels: bytes               # row-major, ``channels`` bytes per pixel

    def band(self, i: int) -> bytes:
        return self.pixels[i::self.channels]

    @property
    def alpha(self) -> bytes | None:
        return self.band(self.channels - 1) if self.channels in (2, 4) else None


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    stride = width * bpp
    out = bytearray(stride * height)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ft = raw[pos]
        row = bytearray(raw[pos + 1: pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                ul = prev[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + _paeth(left, prev[i], ul)) & 255
        elif ft != 0:
            raise ValueError(f"bad PNG filter {ft}")
        out[y * stride:(y + 1) * stride] = row
        prev = row
    return bytes(out)


def decode(data: bytes) -> Image:
    """Decode a PNG. Raises ValueError for anything else (a non-image error page, 16-bit, interlaced)."""
    if data[:8] != _SIG:
        raise ValueError("not a PNG")
    pos, idat, palette, hdr = 8, bytearray(), b"", None
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8: pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if hdr is None or not idat:
        raise ValueError("truncated PNG")
    w, h, depth, ctype, _comp, _filt, interlace = hdr
    if depth != 8 or interlace or ctype not in _CHANNELS:
        raise ValueError(f"unsupported PNG (depth {depth}, type {ctype}, interlace {interlace})")
    bpp = _CHANNELS[ctype]
    px = _unfilter(zlib.decompress(bytes(idat)), w, h, bpp)
    if ctype == 3:
        exp = bytearray()
        for v in px:
            exp += palette[3 * v: 3 * v + 3] or b"\0\0\0"
        return Image(w, h, 3, bytes(exp))
    return Image(w, h, bpp, px)


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode(width: int, height: int, channels: int, pixels: bytes) -> bytes:
    """Encode 8-bit raw pixels (filter 0). For fixtures and tests; real chips come from the services as PNG already."""
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    stride = width * channels
    raw = b"".join(b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(height))
    return _SIG + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, ctype, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")
