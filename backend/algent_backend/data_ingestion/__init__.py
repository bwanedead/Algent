"""
``data_ingestion`` — the mechanical, pre-LLM data layer.

This package owns the deterministic side of getting external data into Algent:
fetching raw datasets, parsing them into typed records, and computing stats
digests over them. No model is in this loop. It is intentionally generic — the
mechanical machinery here is not news-specific and may serve broader research
workflows in other domains over time.

Domain-specific processing lives one level down (e.g. ``news_production``); the
agentic side that *consumes* these digests lives in ``agent_system``.
"""
