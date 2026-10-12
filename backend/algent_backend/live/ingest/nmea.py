"""
A small AIS (NMEA ``!AIVDM``) decoder — just the message types the ship board needs, pure functions, no I/O.

  1, 2, 3   Class A position          18, 19  Class B position (19 also carries type and name)
  5         Class A static (type, name, destination)      24  Class B static (part A: name, part B: type)
  27        long-range position (satellite-style, coarse)

``Decoder.feed(line)`` takes one raw line (a tag block before the ``!`` is ignored; multi-sentence messages are reassembled) and
returns ``None`` or a dict: ``{"kind": "pos", "mmsi", "lat", "lon", "sog", "cog", "heading", ...}`` / ``{"kind": "static", "mmsi",
"type", "name", "dest"}``. Values that the ship reports as "not available" come back as ``None``. Checksums are not verified: a
corrupt sentence decodes to nonsense positions that the range checks below throw away.
"""

from __future__ import annotations

from typing import Any

_MAX_PENDING = 256


def _bits(payload: str, pad: int) -> tuple[int, int]:
    """(the payload as one big integer, its bit length) from 6-bit ASCII armouring."""
    n = 0
    for ch in payload:
        v = ord(ch) - 48
        n = (n << 6) | (v - 8 if v > 40 else v)
    length = len(payload) * 6 - pad
    return n >> pad if pad else n, length


class _Bits:
    def __init__(self, payload: str, pad: int) -> None:
        self.n, self.len = _bits(payload, pad)

    def u(self, start: int, width: int) -> int:
        if start + width > self.len:
            raise IndexError
        return (self.n >> (self.len - start - width)) & ((1 << width) - 1)

    def i(self, start: int, width: int) -> int:
        v = self.u(start, width)
        return v - (1 << width) if v >> (width - 1) else v

    def text(self, start: int, chars: int) -> str:
        out = []
        for k in range(chars):
            if start + 6 * (k + 1) > self.len:
                break
            v = self.u(start + 6 * k, 6)
            out.append(chr(v + 64) if v < 32 else chr(v))
        return "".join(out).replace("@", " ").strip()


def _position(mmsi: int, lat: float, lon: float, sog: float | None, cog: float | None, heading: int | None) -> dict[str, Any] | None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"kind": "pos", "mmsi": mmsi, "lat": lat, "lon": lon, "sog": sog, "cog": cog,
            "heading": heading if heading is not None and heading < 360 else None}


def decode(payload: str, pad: int = 0) -> dict[str, Any] | None:
    b = _Bits(payload, pad)
    try:
        t = b.u(0, 6)
        mmsi = b.u(8, 30)
        if t in (1, 2, 3):
            lon, lat = b.i(61, 28) / 600000, b.i(89, 27) / 600000
            sog, cog = b.u(50, 10), b.u(116, 12)
            if lat == 91 or lon == 181:
                return None
            return _position(mmsi, lat, lon, sog / 10 if sog < 1023 else None, cog / 10 if cog < 3600 else None, b.u(128, 9))
        if t in (18, 19):
            lon, lat = b.i(57, 28) / 600000, b.i(85, 27) / 600000
            sog, cog = b.u(46, 10), b.u(112, 12)
            if lat == 91 or lon == 181:
                return None
            pos = _position(mmsi, lat, lon, sog / 10 if sog < 1023 else None, cog / 10 if cog < 3600 else None, b.u(124, 9))
            if pos and t == 19:
                pos.update(name=b.text(143, 20), type=b.u(263, 8) or None)
            return pos
        if t == 27:
            lon, lat = b.i(44, 18) / 600, b.i(62, 17) / 600
            sog, cog = b.u(79, 6), b.u(85, 9)
            if lat == 91 or lon == 181:
                return None
            return _position(mmsi, lat, lon, float(sog) if sog < 63 else None, float(cog) if cog < 360 else None, None)
        if t == 5:
            return {"kind": "static", "mmsi": mmsi, "type": b.u(232, 8) or None, "name": b.text(112, 20), "dest": b.text(302, 20)}
        if t == 24:
            part = b.u(38, 2)
            if part == 0:
                return {"kind": "static", "mmsi": mmsi, "type": None, "name": b.text(40, 20), "dest": ""}
            if part == 1:
                return {"kind": "static", "mmsi": mmsi, "type": b.u(40, 8) or None, "name": "", "dest": ""}
    except IndexError:
        return None
    return None


class Decoder:
    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], list[str | None]] = {}

    def feed(self, line: str) -> dict[str, Any] | None:
        at = line.find("!")
        if at < 0:
            return None
        fields = line[at:].split("*")[0].split(",")
        if len(fields) < 7 or not fields[0].endswith("VDM"):
            return None
        try:
            total, num = int(fields[1]), int(fields[2])
            pad = int(fields[6] or 0)
        except ValueError:
            return None
        payload, key = fields[5], (fields[3], fields[4])
        if total == 1:
            return decode(payload, pad)
        if num == 1:
            if len(self._pending) >= _MAX_PENDING:
                self._pending.clear()
            self._pending[key] = [payload] + [None] * (total - 1)
            return None
        parts = self._pending.get(key)
        if parts is None or num > len(parts) or parts[num - 1] is not None:
            return None
        parts[num - 1] = payload
        if num == total and all(p is not None for p in parts):
            del self._pending[key]
            return decode("".join(parts), pad)     # type: ignore[arg-type]  (all parts present)
        return None
