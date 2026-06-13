"""
Discovery agents — survey information sources to find items worth deeper work.

A discovery agent does not write the final piece; it scans its sources and
returns candidate topics for downstream research/brief agents. ``base/`` holds
the shared machinery (output contracts, the discovery loop, the discovery prompt
layer); each specialty (``general/``, later ``breaking_news/``, ...) composes it.
"""
