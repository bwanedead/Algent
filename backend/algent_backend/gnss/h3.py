"""
H3 cell centres in pure Python — just enough of Uber's H3 to turn a GPSJam cell id into a latitude/longitude (no h3 package on the server).

``center(index)`` decodes a hexagonal cell index to the (lat, lon) of its centre. It is a port of the library's cell-to-face-IJK and
face-IJK-to-lat/lng path (Apache-2.0, https://github.com/uber/h3), with the constant tables in ``h3_tables.py``. The twelve pentagon base cells
(and any cell that descends from them) are not decoded: ``center`` returns None for them, never a guess. Verified against known cells in
``tests/test_gnss.py``.
"""

from __future__ import annotations

import math

from .h3_tables import BASE_CELLS, FACE_AXES_AZ, FACE_CENTER, FACE_NEIGHBORS

_SQRT7 = math.sqrt(7.0)
_SQRT3_2 = 0.8660254037844386
_RES0_U_GNOMONIC = 0.381966011250105
_AP7_ROT = 0.333473172251832115336
_EPS = 1e-16
_MAX_DIM = {0: 2, 2: 14, 4: 98, 6: 686, 8: 4802, 10: 33614, 12: 235298, 14: 1647086, 16: 11529602}
_UNIT = {0: 1, 2: 7, 4: 49, 6: 343, 8: 2401, 10: 16807, 12: 117649, 14: 823543, 16: 5764801}
_DIGIT = {0: (0, 0, 0), 1: (0, 0, 1), 2: (0, 1, 0), 3: (0, 1, 1), 4: (1, 0, 0), 5: (1, 0, 1), 6: (1, 1, 0)}
_Ijk = tuple[int, int, int]


def _norm(i: int, j: int, k: int) -> _Ijk:
    if i < 0:
        j, k, i = j - i, k - i, 0
    if j < 0:
        i, k, j = i - j, k - j, 0
    if k < 0:
        i, j, k = i - k, j - k, 0
    m = min(i, j, k)
    return (i - m, j - m, k - m) if m > 0 else (i, j, k)


def _comb(c: _Ijk, iv: _Ijk, jv: _Ijk, kv: _Ijk) -> _Ijk:
    return _norm(*(c[0] * iv[n] + c[1] * jv[n] + c[2] * kv[n] for n in range(3)))


def _down_ap7(c: _Ijk) -> _Ijk:
    return _comb(c, (3, 0, 1), (1, 3, 0), (0, 1, 3))


def _down_ap7r(c: _Ijk) -> _Ijk:
    return _comb(c, (3, 1, 0), (0, 3, 1), (1, 0, 3))


def _rot_ccw(c: _Ijk) -> _Ijk:
    return _comb(c, (1, 1, 0), (0, 1, 1), (1, 0, 1))


def _lround(x: float) -> int:
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def _up_ap7r(c: _Ijk) -> _Ijk:
    i, j = c[0] - c[2], c[1] - c[2]
    return _norm(_lround((2 * i + j) / 7.0), _lround((3 * j - i) / 7.0), 0)


def _class3(res: int) -> bool:
    return res % 2 == 1


def _overage(face: int, c: _Ijk, res: int) -> tuple[int, _Ijk, bool]:
    """Move an address that spilled past its face's edge onto the neighbouring face (Class II grids only); True if it moved."""
    i, j, k = c
    if i + j + k <= _MAX_DIM[res]:
        return face, c, False
    quadrant = 3 if (k > 0 and j > 0) else 2 if k > 0 else 1
    nface, (ti, tj, tk), rot = FACE_NEIGHBORS[face][quadrant]
    for _ in range(rot):
        i, j, k = _rot_ccw((i, j, k))
    s = _UNIT[res]
    return nface, _norm(i + ti * s, j + tj * s, k + tk * s), True


def _to_latlng(face: int, c: _Ijk, res: int) -> tuple[float, float]:
    x, y = (c[0] - c[2]) - 0.5 * (c[1] - c[2]), (c[1] - c[2]) * _SQRT3_2
    fc = FACE_CENTER[face]
    r = math.hypot(x, y)
    if r < _EPS:
        p = fc
    else:
        theta = math.atan2(y, x)
        for _ in range(res):
            r /= _SQRT7
        r = math.atan(r * _RES0_U_GNOMONIC)
        if _class3(res):
            theta = (theta + _AP7_ROT) % math.tau
        theta = (FACE_AXES_AZ[face][0] - theta) % math.tau
        n = (-fc[0] * fc[2], -fc[1] * fc[2], 1.0 - fc[2] * fc[2])                     # north pole projected onto the tangent plane at fc
        nl = math.sqrt(sum(a * a for a in n))
        n = tuple(a / nl for a in n)
        e = (n[1] * fc[2] - n[2] * fc[1], n[2] * fc[0] - n[0] * fc[2], n[0] * fc[1] - n[1] * fc[0])      # east = north x p
        d = tuple(math.cos(theta) * n[a] + math.sin(theta) * e[a] for a in range(3))
        p = tuple(math.cos(r) * fc[a] + math.sin(r) * d[a] for a in range(3))
        pl = math.sqrt(sum(a * a for a in p))
        p = tuple(a / pl for a in p)
    return math.degrees(math.asin(max(-1.0, min(1.0, p[2])))), math.degrees(math.atan2(p[1], p[0]))


def center(index: str | int) -> tuple[float, float] | None:
    """(lat, lon) of the centre of an H3 cell, or None for an invalid index or a pentagon-descended cell."""
    try:
        h = int(index, 16) if isinstance(index, str) else int(index)
    except ValueError:
        return None
    res, base = (h >> 52) & 0xF, (h >> 45) & 0x7F
    if not 0 <= res <= 15 or base >= len(BASE_CELLS) or (h >> 59) != 1:
        return None
    face, home, pent = BASE_CELLS[base]
    if pent:
        return None
    c = home
    for r in range(1, res + 1):
        c = _down_ap7(c) if _class3(r) else _down_ap7r(c)
        d = _DIGIT[(h >> ((15 - r) * 3)) & 7] if ((h >> ((15 - r) * 3)) & 7) != 7 else None
        if d is None:
            return None
        c = _norm(c[0] + d[0], c[1] + d[1], c[2] + d[2])
    orig, rr = c, res
    if res > 0 and home != (0, 0, 0):                      # a base cell whose home address is the face origin lies wholly on its face
        if _class3(rr):
            c, rr = _down_ap7r(c), rr + 1
        face2, c2, moved = _overage(face, c, rr)
        if moved:
            face, c = face2, (_up_ap7r(c2) if rr != res else c2)
        else:
            c = orig if rr != res else c
    return _to_latlng(face, c, res)
