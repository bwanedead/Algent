"""
The scene contract: a declarative description of an interactive 3D scene (daily visual kind ``scene3d``).

Data, never code: the site's viewer (``components/Scene3D.tsx``) interprets this JSON with a fixed set of
primitives, so a model (or a human) can describe a scene but cannot ship script. Coordinates are right-handed,
x east, y north, z up, in ``unit`` ("km" or "m"). Colours are palette TOKENS the viewer maps per theme.

Grounding is part of the contract: a ``real`` object (a thing in the world with measured size) must cite a
source, and every size number it carries must appear in that source's ``says`` text (``validate_scene``). An
object that is only a drawing aid says ``real: false`` and the scene must then be flagged ``schematic``.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

Color = Literal["ink", "muted", "paper", "water", "land", "accent", "warn", "cool", "hot", "good"]
Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Vec2 = Annotated[list[float], Field(min_length=2, max_length=2)]

#: Absolute ceilings (the model's own validation); the operator-tunable limits live in ``flags`` and are tighter.
HARD_OBJECTS = 120
HARD_POINTS = 6000


class SceneSource(BaseModel):
    id: str
    label: str
    url: str = ""
    fact_id: str = ""        # a fact of the day's report (``visuals_facts``): its text must hold the numbers
    says: str = ""           # the passage that states the measures this source backs (quote or close paraphrase)


class _Obj(BaseModel):
    id: str
    label: str = ""
    color: Color = "accent"
    opacity: float = Field(1.0, ge=0.05, le=1.0)
    pos: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    lonlat: Vec2 | None = None   # alternative to ``pos`` x,y: converted to scene units about ``Scene.origin``
    rot_z_deg: float = 0.0
    real: bool = True            # a measured thing in the world (needs ``cite``); False = a drawing aid
    cite: str = ""               # a ``SceneSource.id``
    label_dz: float = 0.0        # label height above ``pos``, in scene units


class Box(_Obj):
    type: Literal["box"] = "box"
    size: Vec3                   # length (x), width (y), height (z)


class Cylinder(_Obj):
    type: Literal["cylinder"] = "cylinder"
    radius: float = Field(gt=0)
    height: float = Field(gt=0)
    radius_top: float | None = None    # a frustum when set


class Cone(_Obj):
    type: Literal["cone"] = "cone"
    radius: float = Field(gt=0)
    height: float = Field(gt=0)


class Sphere(_Obj):
    type: Literal["sphere"] = "sphere"
    radius: float = Field(gt=0)


class Capsule(_Obj):
    type: Literal["capsule"] = "capsule"
    radius: float = Field(gt=0)
    length: float = Field(gt=0)        # the straight section; total length is length + 2 * radius, along x


class Extrude(_Obj):
    type: Literal["extrude"] = "extrude"
    profile: Annotated[list[Vec2], Field(min_length=3, max_length=96)]   # closed outline in x,y (scene units)
    depth: float = Field(gt=0)                                          # extruded along z


class Lathe(_Obj):
    type: Literal["lathe"] = "lathe"
    profile: Annotated[list[Vec2], Field(min_length=2, max_length=64)]  # [radius, height] pairs, revolved about z


class Line(_Obj):
    type: Literal["line"] = "line"
    points: Annotated[list[Vec3], Field(min_length=2, max_length=240)]
    style: Literal["line", "dashed", "trajectory"] = "line"
    width: float = Field(2.0, gt=0, le=8)


class Ring(_Obj):
    type: Literal["ring"] = "ring"      # a range ring on the ground plane about ``pos``
    radius: float = Field(gt=0)


class Arrow(_Obj):
    type: Literal["arrow"] = "arrow"
    to: Vec3                            # from ``pos`` to here


class Marker(_Obj):
    type: Literal["marker"] = "marker"  # a labelled point
    real: bool = True


class Terrain(_Obj):
    type: Literal["terrain"] = "terrain"
    size: Vec2                          # x, y extent of the patch
    heights: Annotated[list[list[float]], Field(max_length=64)] = Field(default_factory=list)   # rows of z; [] = flat


class Coast(_Obj):
    type: Literal["coast"] = "coast"    # land from Natural Earth, filled in by the builder from ``bbox_lonlat``
    bbox_lonlat: Annotated[list[float], Field(min_length=4, max_length=4)]    # west, south, east, north
    polygons: list[list[Vec2]] = Field(default_factory=list)                  # rings in scene units
    height: float = Field(0.3, gt=0)                                           # slab height, a drawing aid
    real: bool = False


Obj = Annotated[Union[Box, Cylinder, Cone, Sphere, Capsule, Extrude, Lathe, Line, Ring, Arrow, Marker, Terrain, Coast],
                Field(discriminator="type")]


class CameraPreset(BaseModel):
    id: str
    label: str
    position: Vec3
    target: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])


class Keyframe(BaseModel):
    date: str                                     # YYYY-MM-DD
    cite: str = ""                                # the source for what this day shows
    note: str = ""
    visible: dict[str, bool] = Field(default_factory=dict)
    pos: dict[str, Vec3] = Field(default_factory=dict)
    color: dict[str, Color] = Field(default_factory=dict)


class Timeline(BaseModel):
    frames: Annotated[list[Keyframe], Field(min_length=2, max_length=60)]


class ScaleBar(BaseModel):
    length: float = Field(gt=0)
    label: str


class Origin(BaseModel):
    lon: float
    lat: float


class Scene(BaseModel):
    title: str
    caption: str
    unit: Literal["m", "km"] = "km"
    origin: Origin | None = None
    schematic: bool = False
    ground: Color | None = None                    # a flat plane under everything (the sea, for a coast scene)
    objects: Annotated[list[Obj], Field(min_length=1, max_length=HARD_OBJECTS)]
    cameras: Annotated[list[CameraPreset], Field(max_length=6)] = Field(default_factory=list)
    timeline: Timeline | None = None
    scale_bar: ScaleBar | None = None
    sources: list[SceneSource] = Field(default_factory=list)
    alt: str = ""                                  # text alternative; the builder writes one when empty


# ── geometry helpers shared by validation, the builder and the preview ───────────────────────────
_KM_PER_DEG = 111.32


def lonlat_to_xy(lon: float, lat: float, origin: Origin, unit: str) -> tuple[float, float]:
    k = _KM_PER_DEG * (1000.0 if unit == "m" else 1.0)
    return (lon - origin.lon) * math.cos(math.radians(origin.lat)) * k, (lat - origin.lat) * k


def normalize(scene: Scene) -> Scene:
    """Resolve ``lonlat`` to ``pos`` (x,y) and give a missing camera set a sane default."""
    if scene.origin is not None:
        for o in scene.objects:
            if o.lonlat is not None:
                x, y = lonlat_to_xy(o.lonlat[0], o.lonlat[1], scene.origin, scene.unit)
                o.pos = [round(x, 3), round(y, 3), o.pos[2]]
                o.lonlat = None
    if not scene.cameras:
        r = extent(scene) or 1.0
        scene.cameras = [CameraPreset(id="overview", label="Overview", position=[0.0, -2.3 * r, 1.5 * r]),
                         CameraPreset(id="top", label="From above", position=[0.0, -0.01 * r, 2.8 * r])]
    return scene


def _points(o: _Obj) -> list[list[float]]:
    if isinstance(o, Line):
        return o.points
    if isinstance(o, (Extrude, Lathe)):
        return [[p[0], p[1], 0.0] for p in o.profile]
    return []


def extent(scene: Scene) -> float:
    """Half-size of the scene's footprint (for default cameras and the preview's frame)."""
    r = 0.0
    for o in scene.objects:
        px, py = o.pos[0], o.pos[1]
        if isinstance(o, (Ring, Cylinder, Cone, Sphere, Capsule)):
            r = max(r, abs(px) + getattr(o, "radius", 0), abs(py) + getattr(o, "radius", 0))
        elif isinstance(o, Box):
            r = max(r, abs(px) + o.size[0] / 2, abs(py) + o.size[1] / 2)
        elif isinstance(o, Terrain):
            r = max(r, abs(px) + o.size[0] / 2, abs(py) + o.size[1] / 2)
        elif isinstance(o, Coast):
            r = max([r] + [max(abs(p[0]), abs(p[1])) for ring in o.polygons for p in ring])
        else:
            r = max([r, abs(px), abs(py)] + [max(abs(p[0]), abs(p[1])) for p in _points(o)])
            if isinstance(o, Arrow):
                r = max(r, abs(o.to[0]), abs(o.to[1]))
    return r


def vertex_count(scene: Scene) -> int:
    n = 0
    for o in scene.objects:
        if isinstance(o, Coast):
            n += sum(len(r) for r in o.polygons)
        elif isinstance(o, Terrain):
            n += sum(len(row) for row in o.heights)
        else:
            n += len(_points(o)) + 1
    return n


# ── validation ────────────────────────────────────────────────────────────────────────────────────
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
#: factors between units a source may state a size in and the scene's unit (value_in_scene_unit * f = value_in_source)
_UNIT_FACTORS = (1.0, 1000.0, 0.001, 3.28084, 0.3048, 0.539957, 1.852, 0.621371, 1.60934, 1 / 1852.0, 1852.0)


def _stated(says: str) -> list[float]:
    out = []
    for raw in _NUM.findall(says or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _backed(value: float, stated: list[float]) -> bool:
    v = abs(value)
    if v < 1e-9:
        return True
    return any(abs(v * f - s) <= 0.015 * max(abs(s), 1e-9) + 1e-9 for f in _UNIT_FACTORS for s in stated)


def _sizes(o: _Obj) -> list[tuple[str, float]]:
    """The size numbers of a real object that must be traceable (position and drawing detail are not sizes)."""
    if isinstance(o, Box):
        return [("size", v) for v in o.size]
    if isinstance(o, Cylinder):
        return [("radius", o.radius), ("height", o.height)] + ([("radius_top", o.radius_top)] if o.radius_top else [])
    if isinstance(o, Cone):
        return [("radius", o.radius), ("height", o.height)]
    if isinstance(o, Sphere):
        return [("radius", o.radius)]
    if isinstance(o, Capsule):
        return [("radius", o.radius), ("length", o.length + 2 * o.radius)]
    if isinstance(o, Extrude):
        xs, ys = [p[0] for p in o.profile], [p[1] for p in o.profile]
        length, width = max(xs) - min(xs), max(ys) - min(ys)
        thin = o.depth < 0.05 * max(length, width)     # a slab's thickness is drawing, not a measure
        return ([] if thin else [("depth", o.depth)]) + [("length", length), ("width", width)]
    if isinstance(o, Lathe):
        return [("radius", max(p[0] for p in o.profile)), ("height", max(p[1] for p in o.profile) - min(p[1] for p in o.profile))]
    if isinstance(o, Ring):
        return [("radius", o.radius)]
    if isinstance(o, Line) and o.style == "trajectory":
        return [("apex", max(p[2] for p in o.points))]
    return []


def validate_scene(scene: Scene, fact_text: dict[str, str] | None = None, *, allow_public: bool = False,
                   max_objects: int = HARD_OBJECTS, max_vertices: int = HARD_POINTS) -> list[str]:
    """Every reason this scene may not be published; empty = acceptable. ``fact_text`` maps fact id to its text
    (the day's cited facts). ``allow_public`` admits url-only public-spec sources (a planner ask with a
    ``source_hint``, or a hand-authored scene)."""
    from .visuals_grounding import ungrounded as _ungrounded   # one grounding rule for every daily visual

    facts, bad = fact_text or {}, []
    src = {s.id: s for s in scene.sources}
    ids = [o.id for o in scene.objects]
    if len(ids) != len(set(ids)):
        bad.append("duplicate object ids")
    if len(scene.objects) > max_objects:
        bad.append(f"{len(scene.objects)} objects, limit {max_objects}")
    if vertex_count(scene) > max_vertices:
        bad.append(f"{vertex_count(scene)} vertices, limit {max_vertices}")
    corpus = " ".join(facts.get(s.fact_id, "") for s in scene.sources if s.fact_id)
    for s in scene.sources:
        if s.fact_id:
            if s.fact_id not in facts:
                bad.append(f"source {s.id}: fact {s.fact_id} is not among the day's cited facts")
            elif miss := _ungrounded(s.says, facts[s.fact_id]):
                bad.append(f"source {s.id}: says {miss[:3]} which its fact does not hold")
        elif not (allow_public and s.url.startswith(("http://", "https://")) and s.says.strip()):
            bad.append(f"source {s.id}: neither a cited fact nor an allowed public source with a passage")
    if scene.origin is None and any(o.lonlat for o in scene.objects):
        bad.append("lonlat used without an origin")
    for o in scene.objects:
        if not o.real:
            if not scene.schematic and not isinstance(o, (Coast, Marker, Arrow, Line)):
                bad.append(f"{o.id}: a non-measured {o.type} in a scene not flagged schematic")
            continue
        s = src.get(o.cite)
        if s is None:
            bad.append(f"{o.id}: real object cites no source")
            continue
        stated = _stated(s.says)
        for name, v in _sizes(o):
            if not _backed(v, stated) and not (name.startswith("radius") and _backed(2 * v, stated)):   # a source may give a diameter or beam
                bad.append(f"{o.id}: {name} {v:g} {scene.unit} is not in source {s.id}")
    for text in [scene.title, scene.caption] + [o.label for o in scene.objects]:
        if bad_n := _ungrounded(text, corpus + " " + " ".join(s.says for s in scene.sources)):
            bad.append(f"text {text[:40]!r}: numbers not in any source ({', '.join(bad_n[:3])})")
    if scene.timeline:
        last = ""
        for fr in scene.timeline.frames:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fr.date) or fr.date < last:
                bad.append(f"timeline date {fr.date!r} is not ISO and ascending")
            last = fr.date
            if fr.cite not in src:
                bad.append(f"timeline {fr.date}: cites no source")
            for oid in {*fr.visible, *fr.pos, *fr.color}:
                if oid not in ids:
                    bad.append(f"timeline {fr.date}: unknown object {oid}")
    return bad[:12]


# ── the WIRE schema the model fills ──────────────────────────────────────────────────────────────
# No unions (the house provider rejects oneOf/anyOf, which a discriminated union and every ``X | None`` emit): one flat
# object with a ``type`` and every kind's fields, unused ones left at their empty default, and flat stand-ins for the
# optional blocks. ``from_wire`` builds the strict ``Scene``; an object that is not a valid strict one is dropped.

class ObjWire(BaseModel):
    id: str
    type: Literal["box", "cylinder", "cone", "sphere", "capsule", "extrude", "lathe", "line", "ring", "arrow", "marker",
                  "terrain", "coast"]
    label: str = ""
    color: Color = "accent"
    opacity: float = Field(1.0, ge=0.05, le=1.0)
    pos: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    lonlat: list[float] = Field(default_factory=list)        # [] = unset; else [lon, lat]
    rot_z_deg: float = 0.0
    real: bool = True
    cite: str = ""
    label_dz: float = 0.0
    size: list[float] = Field(default_factory=list)          # box: x,y,z; terrain: x,y
    radius: float = 0.0                                       # cylinder, cone, sphere, capsule, ring
    height: float = 0.0                                       # cylinder, cone
    radius_top: float = 0.0                                   # cylinder frustum; 0 = none
    length: float = 0.0                                       # capsule
    depth: float = 0.0                                        # extrude
    profile: list[list[float]] = Field(default_factory=list)  # extrude (x,y) or lathe (radius,height) pairs
    points: list[list[float]] = Field(default_factory=list)   # line
    style: Literal["line", "dashed", "trajectory"] = "line"
    width: float = 2.0
    to: list[float] = Field(default_factory=list)             # arrow end
    heights: list[list[float]] = Field(default_factory=list)  # terrain rows
    bbox_lonlat: list[float] = Field(default_factory=list)    # coast: west, south, east, north


class SceneWire(BaseModel):
    title: str
    caption: str
    unit: Literal["m", "km"] = "km"
    has_origin: bool = False
    origin_lon: float = 0.0
    origin_lat: float = 0.0
    schematic: bool = False
    has_ground: bool = False
    ground: Color = "water"                                  # used only when ``has_ground``
    objects: list[ObjWire]
    cameras: list[CameraPreset] = Field(default_factory=list)
    frames: list[Keyframe] = Field(default_factory=list)     # [] = no timeline
    scale_bar_length: float = 0.0                            # 0 = no scale bar
    scale_bar_label: str = ""
    sources: list[SceneSource] = Field(default_factory=list)
    alt: str = ""


def _obj_from_wire(w: ObjWire) -> _Obj:
    c = dict(id=w.id, label=w.label, color=w.color, opacity=w.opacity, pos=w.pos, lonlat=w.lonlat or None,
             rot_z_deg=w.rot_z_deg, real=w.real, cite=w.cite, label_dz=w.label_dz)
    t = w.type
    if t == "box":
        return Box(**c, size=w.size)
    if t == "cylinder":
        return Cylinder(**c, radius=w.radius, height=w.height, radius_top=w.radius_top or None)
    if t == "cone":
        return Cone(**c, radius=w.radius, height=w.height)
    if t == "sphere":
        return Sphere(**c, radius=w.radius)
    if t == "capsule":
        return Capsule(**c, radius=w.radius, length=w.length)
    if t == "extrude":
        return Extrude(**c, profile=w.profile, depth=w.depth)
    if t == "lathe":
        return Lathe(**c, profile=w.profile)
    if t == "line":
        return Line(**c, points=w.points, style=w.style, width=w.width)
    if t == "ring":
        return Ring(**c, radius=w.radius)
    if t == "arrow":
        return Arrow(**c, to=w.to)
    if t == "marker":
        return Marker(**c)
    if t == "terrain":
        return Terrain(**c, size=w.size, heights=w.heights)
    return Coast(**c, bbox_lonlat=w.bbox_lonlat)


def from_wire(wire: SceneWire) -> tuple[Scene, list[str]]:
    """The strict scene from what the model filled, plus a line per object that could not be built."""
    notes: list[str] = []
    objs: list[_Obj] = []
    for w in wire.objects[:HARD_OBJECTS]:
        try:
            objs.append(_obj_from_wire(w))
        except Exception as exc:  # noqa: BLE001 - a malformed object is dropped, not the scene
            notes.append(f"{w.type} {w.id!r} dropped: malformed ({type(exc).__name__})")
    scene = Scene(title=wire.title, caption=wire.caption, unit=wire.unit, schematic=wire.schematic,
                  origin=Origin(lon=wire.origin_lon, lat=wire.origin_lat) if wire.has_origin else None,
                  ground=wire.ground if wire.has_ground else None, objects=objs, cameras=wire.cameras,
                  timeline=Timeline(frames=wire.frames) if len(wire.frames) >= 2 else None,
                  scale_bar=ScaleBar(length=wire.scale_bar_length, label=wire.scale_bar_label) if wire.scale_bar_length > 0 else None,
                  sources=wire.sources, alt=wire.alt)
    return scene, notes
