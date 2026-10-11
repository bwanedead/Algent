"""
A static still of a scene (PNG) for no-JS readers, link previews and X: the same primitives drawn with
matplotlib's 3D projection from the scene's first camera. Approximate by design; the viewer is the real thing.

The backend's own environment has no matplotlib (it lives in the analytics workspace venv, with the article
analytics stack), so ``render`` runs THIS FILE as a script under that interpreter. The drawing code therefore
reads the plain scene JSON and imports nothing from the backend: ``python scene_preview.py scene.json out.png``.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

#: palette token -> colour on the still (paper theme; the viewer owns its per-theme map)
PAPER = {"ink": "#1b1b1b", "muted": "#8a8a8a", "paper": "#f4f1ea", "water": "#9ec5e0", "land": "#d9d2bf",
         "accent": "#b3361b", "warn": "#d98e04", "cool": "#2f6f9f", "hot": "#c8321e", "good": "#3d7a4a"}
SEGMENTS = 24
TIMEOUT_S = 90


def _extent(objs: list[dict]) -> float:
    r = 0.0
    for o in objs:
        x, y = o.get("pos", [0, 0, 0])[:2]
        rad = o.get("radius") or 0.0
        half = (o.get("size") or [0, 0, 0])
        r = max(r, abs(x) + max(rad, half[0] / 2), abs(y) + max(rad, half[1] / 2))
        for ring in o.get("polygons") or []:
            r = max([r] + [max(abs(p[0]), abs(p[1])) for p in ring])
        for p in (o.get("points") or []) + (o["profile"] if o["type"] == "extrude" else []):
            r = max(r, abs(x + p[0]), abs(y + p[1]))
        if o["type"] == "arrow":
            r = max(r, abs(o["to"][0]), abs(o["to"][1]))
    return r or 1.0


def _profile(o: dict) -> list[list[float]]:
    t = o["type"]
    if t == "cylinder":
        return [[o["radius"], 0.0], [o.get("radius_top") if o.get("radius_top") is not None else o["radius"], o["height"]]]
    if t == "cone":
        return [[o["radius"], 0.0], [0.0, o["height"]]]
    if t == "sphere":
        return [[o["radius"] * math.sin(a), o["radius"] * (1 - math.cos(a))] for a in [math.pi * i / 10 for i in range(11)]]
    return o["profile"] if t == "lathe" else []


def draw(scene: dict, out: Path, size: tuple[int, int] = (1200, 675)) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np

    objs = scene["objects"]
    fig = Figure(figsize=(size[0] / 100, size[1] / 100), dpi=100, facecolor=PAPER["paper"])
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0.0, 0.06, 1.0, 0.86), projection="3d")
    ax.set_facecolor(PAPER["paper"])
    r = _extent(objs) * 1.15
    top_z = r * 0.05
    if scene.get("ground"):
        ax.add_collection3d(Poly3DCollection([[(-r, -r, 0), (r, -r, 0), (r, r, 0), (-r, r, 0)]],
                                             facecolors=PAPER[scene["ground"]], alpha=0.55, linewidths=0))
    th = np.linspace(0, 2 * np.pi, SEGMENTS + 1)
    for o in objs:
        t, (x0, y0, z0) = o["type"], o.get("pos", [0, 0, 0])
        c, a = PAPER.get(o.get("color", "accent"), PAPER["accent"]), o.get("opacity", 1.0)
        if t == "coast":
            for ring in o.get("polygons") or []:
                ax.add_collection3d(Poly3DCollection([[(p[0], p[1], 0.0) for p in ring]], facecolors=PAPER["land"],
                                                     edgecolors=PAPER["muted"], linewidths=0.6, alpha=0.9))
            continue
        if t == "box":
            sx, sy, sz = o["size"]
            vs = [(x0 + dx * sx / 2, y0 + dy * sy / 2, z0 + dz * sz) for dx in (-1, 1) for dy in (-1, 1) for dz in (0, 1)]
            faces = [[0, 1, 3, 2], [4, 5, 7, 6], [0, 1, 5, 4], [2, 3, 7, 6], [0, 2, 6, 4], [1, 3, 7, 5]]
            ax.add_collection3d(Poly3DCollection([[vs[i] for i in f] for f in faces], facecolors=c, edgecolors=PAPER["ink"],
                                                 linewidths=0.4, alpha=a))
            top_z = max(top_z, z0 + sz)
        elif t == "capsule":
            half, rad0 = o["length"] / 2, o["radius"]
            u = np.linspace(-half - rad0, half + rad0, 28)
            rad = np.array([rad0 if abs(v) <= half else math.sqrt(max(rad0 ** 2 - (abs(v) - half) ** 2, 0)) for v in u])
            ax.plot_surface(x0 + np.outer(u, np.ones_like(th)), y0 + np.outer(rad, np.cos(th)),
                            z0 + np.outer(rad, np.sin(th)) + rad0, color=c, alpha=a, linewidth=0)
            top_z = max(top_z, z0 + 2 * rad0)
        elif t in ("cylinder", "cone", "sphere", "lathe"):
            prof = _profile(o)
            ax.plot_surface(x0 + np.array([[p[0] * math.cos(q) for q in th] for p in prof]),
                            y0 + np.array([[p[0] * math.sin(q) for q in th] for p in prof]),
                            z0 + np.array([[p[1]] * len(th) for p in prof]), color=c, alpha=a, linewidth=0)
            top_z = max(top_z, z0 + max(p[1] for p in prof))
        elif t == "extrude":
            ring = [(x0 + p[0], y0 + p[1]) for p in o["profile"]]
            n = len(ring)
            top, bot = [(x, y, z0 + o["depth"]) for x, y in ring], [(x, y, z0) for x, y in ring]
            sides = [[bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]] for i in range(n)]
            ax.add_collection3d(Poly3DCollection(sides + [top, bot], facecolors=c, edgecolors=PAPER["ink"], linewidths=0.3, alpha=a))
            top_z = max(top_z, z0 + o["depth"])
        elif t == "line":
            pts = np.array(o["points"]) + np.array(o.get("pos", [0, 0, 0]))
            ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], color=c, linewidth=o.get("width", 2) * 0.8, alpha=a,
                    linestyle="--" if o.get("style") == "dashed" else "-")
            top_z = max(top_z, float(pts[:, 2].max()))
            x0, y0, z0 = pts[len(pts) // 2]
        elif t == "ring":
            ax.plot(x0 + o["radius"] * np.cos(th), y0 + o["radius"] * np.sin(th), np.full_like(th, z0), color=c, linewidth=1.4, linestyle="--")
        elif t == "arrow":
            ax.plot([x0, o["to"][0]], [y0, o["to"][1]], [z0, o["to"][2]], color=c, linewidth=2.4)
            ax.scatter([o["to"][0]], [o["to"][1]], [o["to"][2]], color=c, marker="^", s=40)
        elif t == "marker":
            ax.scatter([x0], [y0], [z0], color=c, s=36)
        elif t == "terrain" and o.get("heights"):
            h = np.array(o["heights"])
            X, Y = np.meshgrid(np.linspace(-o["size"][0] / 2, o["size"][0] / 2, h.shape[1]),
                               np.linspace(-o["size"][1] / 2, o["size"][1] / 2, h.shape[0]))
            ax.plot_surface(x0 + X, y0 + Y, z0 + h, color=PAPER["land"], alpha=0.9, linewidth=0)
            top_z = max(top_z, z0 + float(h.max()))
        if o.get("label"):
            ax.text(x0, y0, z0 + o.get("label_dz", 0.0), o["label"], color=PAPER["ink"], fontsize=8)
    ax.set_xlim(-r, r)
    ax.set_ylim(-r, r)
    ax.set_zlim(0, max(top_z, r * 0.25))
    ax.set_box_aspect((1, 1, max(0.15, min(0.6, top_z / (2 * r)))), zoom=1.3)
    cams = scene.get("cameras") or []
    if cams:
        dx, dy, dz = (cams[0]["position"][i] - cams[0]["target"][i] for i in range(3))
        ax.view_init(elev=math.degrees(math.atan2(dz, math.hypot(dx, dy))), azim=math.degrees(math.atan2(dy, dx)))
    ax.set_axis_off()
    fig.text(0.02, 0.95, scene["title"], fontsize=15, color=PAPER["ink"], weight="bold", va="center")
    bar = scene.get("scale_bar")
    note = ("Schematic, not to exact detail. " if scene.get("schematic") else "") + (f"Scale: {bar['label']}. " if bar else "")
    fig.text(0.02, 0.03, note + "Interactive version on Ohmega Monster", fontsize=9, color=PAPER["muted"])
    fig.savefig(str(out), format="png", facecolor=fig.get_facecolor())


def interpreters() -> list[str]:
    """Pythons to try: the analytics workspace venv (where matplotlib is installed), then this one."""
    ws = Path(__file__).resolve().parents[5] / "analytics_workspace" / ".venv"
    found = [str(p) for p in (ws / "Scripts" / "python.exe", ws / "bin" / "python") if p.is_file()]
    return found + [sys.executable]


def render(scene: dict) -> bytes:
    """PNG bytes of the scene's still (``scene`` is its JSON dict). Raises RuntimeError with the reason on failure."""
    last = "no interpreter"
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "scene.json", Path(tmp) / "scene.png"
        src.write_text(json.dumps(scene), encoding="utf-8")
        for exe in interpreters():
            try:
                done = subprocess.run([exe, "-I", str(Path(__file__).resolve()), str(src), str(out)], capture_output=True, text=True,
                                      timeout=TIMEOUT_S)
            except (OSError, subprocess.SubprocessError) as exc:
                last = f"{type(exc).__name__}: {exc}"
                continue
            if done.returncode == 0 and out.is_file():
                return out.read_bytes()
            lines = (done.stderr or "").strip().splitlines()
            last = lines[-1] if lines else f"exit {done.returncode}"
    raise RuntimeError(f"preview render failed: {last[:160]}")


if __name__ == "__main__":
    draw(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2]))
