"""
Calibration policies: a versioned map applied AFTER a mind has committed its probability, so a systematic lean (the production research mind says "under 20%" and is
right 44% of the time) can be corrected without a single new model call. Policy kind ``calibration``; each is content-addressed and stored write-once like any other
(``policies.make``); a protocol may carry one, and ``split`` finds the raw protocol whose stored runs it re-reads.

  calibration/identity@1     the control: p unchanged
  calibration/platt@1        Platt scaling on logit(p): p' = sigmoid(a * logit(p) + b), a ridge-regularised logistic fit pulled toward (a=1, b=0), so a handful of
                             questions can only nudge the map; fitted on the protocol's OWN past lab forecasts
  calibration/platt-live@1   the same, but the fit also uses the live bots' resolved forecasts (optionally only some strategies): a much larger sample, from another
                             mind family, so it is an explicit separate policy and never the default

NO PEEKING. A map for a question whose cutoff is T is fitted only on observations whose outcome was resolved STRICTLY BEFORE T (``Pool.before``), so the question's own
outcome, and every outcome decided after T, cannot reach it; an observation with no known resolution time is never used. With too little data (``min_n`` observations, or
fewer than ``min_class`` of either outcome) the map is the identity and says why (``Map.reason``): the board counts how many forecasts were really recalibrated.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from . import flags, policies, store
from .contracts import PolicyVersion, Protocol

EPS = 0.001


@dataclass(frozen=True)
class Obs:
    """One resolved forecast usable for fitting: the probability said, what happened, and WHEN it became known."""

    p: float
    o: int
    resolved_at: str
    key: str = ""


@dataclass(frozen=True)
class Map:
    a: float
    b: float
    n: int                              # observations the fit used (0 for the identity)
    fitted: bool
    reason: str
    kind: str = "fitted"             # fitted | identity | too_few | one_sided | no_time: why a forecast was or was not really recalibrated

    def __call__(self, p: float) -> float:
        if not self.fitted:
            return p
        return min(flags.CALIB_P_MAX, max(flags.CALIB_P_MIN, _sigmoid(self.a * _logit(p) + self.b)))


def _logit(p: float) -> float:
    p = min(1 - EPS, max(EPS, p))
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def _nll(pts: list[tuple[float, int]], a: float, b: float, lam: float) -> float:
    total = lam / 2 * ((a - 1) ** 2 + b ** 2)
    for x, y in pts:
        z = a * x + b
        total += math.log1p(math.exp(-abs(z))) + max(z, 0.0) - y * z            # the stable log(1 + e^z) - y z
    return total


def fit_platt(obs: Iterable[Obs], lam: float) -> tuple[float, float]:
    """Ridge-penalised logistic regression of the outcome on logit(p): minimise NLL + lam/2 * ((a - 1)^2 + b^2) by Newton steps with a backtracking line search (the
    logits of a lean forecaster are nearly constant, which makes a plain Newton step overshoot). The slope is kept in [0, A_MAX] (a negative slope would invert the
    forecaster on noise); when it hits a bound the intercept is refitted with the slope fixed there."""
    pts = [(_logit(o.p), o.o) for o in obs]
    a, b = 1.0, 0.0
    for _ in range(100):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in pts:
            q = _sigmoid(a * x + b)
            r = q * (1 - q)
            ga, gb, haa, hab, hbb = ga + (q - y) * x, gb + (q - y), haa + r * x * x, hab + r * x, hbb + r
        ga, gb, haa, hbb = ga + lam * (a - 1), gb + lam * b, haa + lam, hbb + lam
        det = haa * hbb - hab * hab
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        f0, step = _nll(pts, a, b, lam), 1.0
        while step > 1e-6 and _nll(pts, a - step * da, b - step * db, lam) > f0 + 1e-12:
            step /= 2
        a, b = a - step * da, b - step * db
        if abs(step * da) < 1e-9 and abs(step * db) < 1e-9:
            break
    if not 0.0 <= a <= flags.CALIB_A_MAX:
        a = min(flags.CALIB_A_MAX, max(0.0, a))
        for _ in range(100):
            g = sum(_sigmoid(a * x + b) - y for x, y in pts) + lam * b
            h = sum(_sigmoid(a * x + b) * (1 - _sigmoid(a * x + b)) for x, _ in pts) + lam
            step = 1.0
            while step > 1e-6 and _nll(pts, a, b - step * g / h, lam) > _nll(pts, a, b, lam) + 1e-12:
                step /= 2
            b -= step * g / h
            if abs(step * g / h) < 1e-9:
                break
    return a, b


def identity_map(obs: list[Obs], params: dict[str, Any]) -> Map:
    return Map(1.0, 0.0, 0, False, "identity policy", "identity")


def platt_map(obs: list[Obs], params: dict[str, Any]) -> Map:
    n, yes = len(obs), sum(o.o for o in obs)
    if n < int(params["min_n"]):
        return Map(1.0, 0.0, n, False, f"only {n} resolved before the cutoff, needs {params['min_n']}: left as said", "too_few")
    if min(yes, n - yes) < int(params["min_class"]):
        return Map(1.0, 0.0, n, False, f"{yes} of {n} resolved yes, needs {params['min_class']} of each outcome: left as said", "one_sided")
    a, b = fit_platt(obs, float(params["lam"]))
    return Map(round(a, 4), round(b, 4), n, True, f"fitted on {n} resolved forecasts: a={a:.2f}, b={b:+.2f}")


MAPS = {("identity", 1): identity_map, ("platt", 1): platt_map, ("platt-live", 1): platt_map}


def _platt_params(sources: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"lam": flags.CALIB_LAMBDA, "min_n": flags.CALIB_MIN_FIT, "min_class": flags.CALIB_MIN_CLASS, "sources": sources, **(extra or {})}


def identity() -> PolicyVersion:
    return policies.make("calibration", "identity", 1, {"sources": []}, identity_map)


def platt() -> PolicyVersion:
    return policies.make("calibration", "platt", 1, _platt_params(["lab"]), [platt_map, fit_platt])


def platt_live(strategies: tuple[str, ...] = ()) -> PolicyVersion:
    """Fit on the protocol's own lab forecasts AND the live bots' resolved forecasts (``strategies`` empty = every strategy)."""
    return policies.make("calibration", "platt-live", 1, _platt_params(["lab", "live"], {"live_strategies": sorted(strategies)}), [platt_map, fit_platt])


def all_policies(live_strategies: tuple[str, ...] = ()) -> list[PolicyVersion]:
    return [identity(), platt(), platt_live(live_strategies)]


def named(name: str, live_strategies: tuple[str, ...] = ()) -> PolicyVersion:
    for pv in all_policies(live_strategies):
        if pv.name == name:
            return pv
    raise KeyError(f"unknown calibration policy {name!r}")


class Pool:
    """Observations ordered by resolution time. ``before(T)`` is the strict past of T; maps are memoised per (policy, prefix) so scoring a thousand forecasts fits
    each distinct history once."""

    def __init__(self, obs: Iterable[Obs]):
        timed = sorted(((t, o) for o in obs if (t := store.parse_time(o.resolved_at)) is not None), key=lambda x: (x[0], x[1].key))
        self._t = [t for t, _ in timed]
        self._obs = [o for _, o in timed]
        self._memo: dict[tuple[str, int], Map] = {}

    def __len__(self) -> int:
        return len(self._obs)

    def before(self, as_of: str) -> list[Obs]:
        t = store.parse_time(as_of)
        return [] if t is None else self._obs[: bisect_left(self._t, t)]

    def map_for(self, pv: PolicyVersion, as_of: str) -> Map:
        t = store.parse_time(as_of)
        if t is None:
            return Map(1.0, 0.0, 0, False, "no usable cutoff time", "no_time")
        k = bisect_left(self._t, t)
        if (pv.digest, k) not in self._memo:
            self._memo[(pv.digest, k)] = MAPS[(pv.name, pv.version)](self._obs[:k], pv.params)
        return self._memo[(pv.digest, k)]


class Fitter:
    """The pools a policy may fit on, by source name (``lab``: the protocol's own forecasts; ``live``: the live bots'). A policy names its sources; the maps it gets
    are fitted on their union, strictly before the question's cutoff."""

    def __init__(self, lab: Iterable[Obs] = (), live: Iterable[Obs] = ()):
        self._pools = {"lab": list(lab), "live": list(live)}
        self._cache: dict[tuple[str, ...], Pool] = {}

    def _pool(self, sources: tuple[str, ...]) -> Pool:
        if sources not in self._cache:
            self._cache[sources] = Pool(o for s in sources for o in self._pools[s])
        return self._cache[sources]

    def map_for(self, pv: PolicyVersion, as_of: str) -> Map:
        return self._pool(tuple(sorted(pv.params.get("sources", [])))).map_for(pv, as_of)

    def apply(self, pv: PolicyVersion, p: float, as_of: str) -> tuple[float, Map]:
        m = self.map_for(pv, as_of)
        return m(p), m


def base_id(proto: Protocol) -> str:
    """The id this composition has WITHOUT its calibration policy: the protocol whose stored runs it re-reads (calibration needs no new model call)."""
    return store.digest({k: v.digest for k, v in sorted(proto.policies.items()) if k != "calibration"})


def split(proto: Protocol) -> tuple[Protocol, PolicyVersion | None]:
    """(the raw protocol that runs, the calibration policy applied after it or None)."""
    cal = proto.policies.get("calibration")
    if cal is None:
        return proto, None
    bid = base_id(proto)
    try:
        return policies.load_protocol(bid), cal
    except KeyError:
        return policies.compose(f"{proto.name}/raw", [p for k, p in proto.policies.items() if k != "calibration"], parent=proto.parent), cal
