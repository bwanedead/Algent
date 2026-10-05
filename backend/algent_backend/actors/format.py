"""Human-readable figures for the plain-text surfaces (evidence block, CLI). The site formats its own."""

from __future__ import annotations

_STEPS = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k"))


def compact(value: float) -> str:
    """12345678 -> '12.3M'; small numbers keep their digits."""
    for size, suffix in _STEPS:
        if abs(value) >= size:
            n = value / size
            return f"{n:.0f}{suffix}" if abs(n) >= 100 else f"{n:.1f}{suffix}".replace(".0" + suffix, suffix)
    return f"{value:,.0f}" if abs(value) >= 10 else f"{value:.1f}"


def figure(value: float, unit: str) -> str:
    if unit == "usd":
        return "$" + compact(value)
    if unit == "pct":
        return f"{value:.1f}%"
    if unit == "twh":
        return f"{compact(value)} TWh"
    if unit == "kwh":
        return f"{value / 1000:,.1f} MWh/person"
    if unit == "km2":
        return f"{compact(value)} km²"
    return compact(value)            # people, persons, number
