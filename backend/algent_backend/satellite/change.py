"""
Change between two chips of one place, in pure Python. A MACHINE SIGNAL about pixels, not an interpretation: it cannot say what changed or why.

``compare`` (two true-colour chips + their scene-classification chips):

1. **Valid pixels.** A pixel counts only when it is clear in BOTH chips (scene class not no-data, saturated, cloud shadow, medium/high cloud, cirrus or
   snow; and not transparent). If the share of valid pixels is under ``MIN_VALID_SHARE`` the pair is **inconclusive**: cloud is not change.
2. **Per-band normalisation.** Each band's median over the valid pixels is subtracted in each chip, which removes the season's and the sun's overall
   brightness shift and leaves what moved relative to the rest of the scene.
3. **Score** = mean absolute difference of the normalised bands over valid pixels, on a 0..1 scale (grey levels / 255).
4. **Changed-pixel fraction**: the share of valid pixels whose own difference sits more than ``Z_ENTER`` robust sigmas above the pair's median pixel
   difference, the sigma being the pair's own MAD (``Z_ENTER`` is the same cut live memory uses). No constant brightness cut.

``judge`` puts the score against THE SITE'S OWN earlier scores (modified z via median and MAD, one grey level the floor of sigma: the data is 8-bit):
fewer than ``MIN_OBS`` earlier observations is **learning** and nothing is flagged; a flagged site is one whose score jumped well above its own normal.

``judge_night`` does the same for the night-light window's brightness, flagging a fall (a blackout) or a rise against the site's own earlier nights.
Every verdict carries its provenance (``basis``, ``method_note``, ``baseline_since``, ``n_obs``) so the site can say how much history it rests on.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from algent_backend.live.memory.flags import Z_ENTER
from algent_backend.live.memory.robust import MAD_TO_SIGMA

from . import flags
from .png import Image

#: Scene classification (SCL) classes that make a pixel unusable: no data, saturated/defective, cloud shadow, medium and high cloud, cirrus, snow/ice.
INVALID_SCL = frozenset({0, 1, 3, 8, 9, 10, 11})
#: The classes that are cloud or its shadow (for the chip's own cloud percentage).
CLOUD_SCL = frozenset({3, 8, 9, 10})
GREY_LEVEL = 1.0 / 255.0

METHOD_OPTICAL = ("Machine change signal, not an interpretation. Mean absolute difference of two Sentinel-2 true-colour chips of the same place after "
                  "per-band median normalisation, over pixels clear of cloud, shadow and no-data in both. Flagged only when it is far outside this "
                  "site's own earlier scores.")
METHOD_NIGHT = ("Machine signal from NASA VIIRS gap-filled night-light imagery: the mean brightness of the window around the site, compared with this "
                "site's own earlier nights. A rendered brightness index, not calibrated radiance; it cannot say why a place went dark.")


def scl_classes(img: Image) -> list[int]:
    """The SCL class of each pixel, from a chip rendered with ``rescale=0,11`` (class = grey * 11 / 255); a transparent pixel is no-data (0)."""
    grey, alpha = img.band(0), img.alpha
    return [0 if alpha is not None and alpha[i] == 0 else round(v * 11 / 255) for i, v in enumerate(grey)]


def chip_quality(classes: list[int]) -> dict[str, float]:
    """Own cloud and no-data share of a chip, in percent of all its pixels."""
    n = max(len(classes), 1)
    return {"cloud_pct": round(100.0 * sum(c in CLOUD_SCL for c in classes) / n, 1), "nodata_pct": round(100.0 * sum(c == 0 for c in classes) / n, 1)}


def _bands(img: Image) -> list[bytes]:
    return [img.band(i) for i in range(min(img.channels, 3))] if img.channels >= 3 else [img.band(0)] * 3


def _mad(xs: list[float], med: float) -> float:
    return median([abs(x - med) for x in xs]) if xs else 0.0


def compare(a: Image, a_scl: list[int], b: Image, b_scl: list[int]) -> dict[str, Any]:
    """The pair's raw numbers (see the module docstring). ``valid_share`` is the fraction of pixels used; score and fraction are None when none are."""
    if (a.width, a.height) != (b.width, b.height) or len(a_scl) != len(b_scl) or len(a_scl) != a.width * a.height:
        raise ValueError("chips differ in size")
    aa, ba = a.alpha, b.alpha
    valid = [i for i in range(len(a_scl))
             if a_scl[i] not in INVALID_SCL and b_scl[i] not in INVALID_SCL and (aa is None or aa[i]) and (ba is None or ba[i])]
    share = len(valid) / max(len(a_scl), 1)
    if len(valid) < 16:
        return {"valid_share": round(share, 3), "score": None, "changed_frac": None}
    diffs: list[list[float]] = []
    for ba_, bb_ in zip(_bands(a), _bands(b)):
        va, vb = [ba_[i] for i in valid], [bb_[i] for i in valid]
        ma, mb = median(va), median(vb)
        diffs.append([abs((y - mb) - (x - ma)) for x, y in zip(va, vb)])
    per_px = [sum(d[k] for d in diffs) / 3.0 for k in range(len(valid))]
    score = sum(per_px) / len(per_px) / 255.0
    med = median(per_px)
    sigma = max(MAD_TO_SIGMA * _mad(per_px, med), 1.0)       # one grey level at least: the data is 8-bit
    cut = med + Z_ENTER * sigma
    return {"valid_share": round(share, 3), "score": round(score, 5), "changed_frac": round(sum(p > cut for p in per_px) / len(per_px), 4)}


def robust_z(x: float, history: list[float], floor: float = GREY_LEVEL) -> tuple[float, float]:
    """(modified z of ``x`` against ``history``, the history's median)."""
    med = median(history)
    return (x - med) / max(MAD_TO_SIGMA * _mad(history, med), floor), med


def provenance(method: str, baseline_since: str | None, n_obs: int) -> dict[str, Any]:
    """What a published number rests on: ours (computed here from the imagery), how, since when our history for the site runs, and from how many looks."""
    return {"basis": "our_computation", "method_note": method, "baseline_since": baseline_since, "n_obs": n_obs}


def judge(pair: dict[str, Any], history: list[float], baseline_since: str | None) -> dict[str, Any]:
    """The verdict on one pair: ``inconclusive`` (too little clear ground), ``learning`` (too little own history), ``changed`` or ``steady``."""
    out: dict[str, Any] = {**pair, **provenance(METHOD_OPTICAL, baseline_since, len(history))}
    if pair["score"] is None or pair["valid_share"] < flags.MIN_VALID_SHARE:
        out.update(label="inconclusive", z=None, usual=None,
                   reason=f"only {round(100 * pair['valid_share'])}% of the ground is clear in both pictures (cloud, shadow or no data)")
        return out
    if len(history) < flags.MIN_OBS:
        out.update(label="learning", z=None, usual=None, reason=f"{len(history)} earlier looks at this site; {flags.MIN_OBS} are needed to judge it against its own normal")
        return out
    z, usual = robust_z(pair["score"], history)
    out.update(z=round(z, 2), usual=round(usual, 5), label="changed" if z >= Z_ENTER else "steady",
               reason=f"score {pair['score']:.3f} against this site's usual {usual:.3f}")
    return out


def night_stats(img: Image) -> dict[str, float]:
    """Mean brightness (0..255 grey of the rendered night image) and the share of lit pixels, over opaque pixels."""
    grey, alpha = img.band(0) if img.channels < 3 else [round(sum(t) / 3) for t in zip(img.band(0), img.band(1), img.band(2))], img.alpha
    vals = [g for i, g in enumerate(grey) if alpha is None or alpha[i]]
    if not vals:
        return {"mean": 0.0, "lit_share": 0.0}
    floor = median(vals)                                         # the dark background of this very picture
    return {"mean": round(sum(vals) / len(vals), 3), "lit_share": round(sum(v > floor for v in vals) / len(vals), 4)}


def judge_night(value: float, history: list[float], baseline_since: str | None) -> dict[str, Any]:
    """The verdict on one night's brightness against the site's own earlier nights: ``dimmer`` / ``brighter`` / ``steady`` / ``learning``."""
    out: dict[str, Any] = {"value": value, **provenance(METHOD_NIGHT, baseline_since, len(history))}
    if len(history) < flags.MIN_OBS:
        out.update(label="learning", z=None, usual=None, reason=f"{len(history)} earlier nights for this site; {flags.MIN_OBS} are needed")
        return out
    z, usual = robust_z(value, history, floor=1.0)               # a grey level of the 8-bit rendering is the least we can tell apart
    out.update(z=round(z, 2), usual=round(usual, 3), label="dimmer" if z <= -Z_ENTER else "brighter" if z >= Z_ENTER else "steady",
               reason=f"mean brightness {value:.1f} against this site's usual {usual:.1f}")
    return out
