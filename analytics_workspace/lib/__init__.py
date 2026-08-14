"""Shared analytics helpers for the newsroom worker (charts, maps, short animations).

Use from a scratch folder via the workspace venv::

    from pathlib import Path
    import sys
    ROOT = Path(__file__).resolve().parents[1]  # analytics_workspace/
    sys.path.insert(0, str(ROOT))
    from lib.charts import line_chart
    from lib.maps import country_points_map
"""

from __future__ import annotations

__all__ = ["theme", "charts", "maps", "animate", "insight"]
