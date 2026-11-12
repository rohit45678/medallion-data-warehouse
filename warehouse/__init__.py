"""Medallion data warehouse pipeline package.

Layers:
  bronze  - raw, append-only ingestion of source extracts (with CDC ops)
  silver  - cleaned, typed, deduplicated tables + SCD Type-2 customer dimension
  gold    - analytics-ready aggregates
"""
