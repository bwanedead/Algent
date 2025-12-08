"""
Metric calculators and aggregators.

Design metrics to be composable so experiments can plug them together. Keep
interfaces thin (e.g., `compute(state) -> MetricResult`).
"""


def available_metrics() -> list[str]:
    """Placeholder for metric discovery."""
    # TODO: wire into registry or module scanning.
    return []
