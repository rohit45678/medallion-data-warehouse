#!/usr/bin/env python3
"""Plain-assert test suite (no pytest dependency).

Run:  python tests/run_tests.py
Each test builds a throwaway database in a temp directory, loads both sample
batches through the real pipeline, and checks the warehouse behaviour.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warehouse import bronze, generate, gold, silver
from warehouse.db import connect


def build_full_pipeline():
    generate.generate()
    tmp = tempfile.mkdtemp()
    conn = connect(os.path.join(tmp, "test.db"))
    bronze.load_batch(conn, 1)
    bronze.load_batch(conn, 2)
    silver.build_silver(conn)
    gold.build_gold(conn)
    return conn


def test_scd2_versions_changed_customer():
    """C002 moved Austin -> Denver in batch 2: exactly two dim rows, old one
    closed on the batch-2 date, new one current."""
    conn = build_full_pipeline()
    rows = conn.execute(
        "SELECT city, effective_from, effective_to, is_current FROM dim_customers "
        "WHERE customer_id = 'C002' ORDER BY effective_from").fetchall()
    assert len(rows) == 2, f"C002 should have 2 versions, got {len(rows)}"
    old, new = rows
    assert old["city"] == "Austin" and old["is_current"] == 0
    assert old["effective_to"] == "2026-03-01", old["effective_to"]
    assert new["city"] == "Denver" and new["is_current"] == 1 and new["effective_to"] is None
    conn.close()


def test_scd2_tier_change_and_delete_and_insert():
    conn = build_full_pipeline()
    # C007 tier Standard -> Premium: two versions, current one Premium.
    rows = conn.execute(
        "SELECT tier, is_current FROM dim_customers WHERE customer_id = 'C007' "
        "ORDER BY effective_from").fetchall()
    assert [ (r["tier"], r["is_current"]) for r in rows ] == [("Standard", 0), ("Premium", 1)]
    # C009 deleted in batch 2: one version, closed, not current, absent from silver snapshot.
    rows = conn.execute(
        "SELECT is_current, effective_to FROM dim_customers WHERE customer_id = 'C009'").fetchall()
    assert len(rows) == 1 and rows[0]["is_current"] == 0 and rows[0]["effective_to"] == "2026-03-01"
    assert conn.execute(
        "SELECT COUNT(*) FROM silver_customers WHERE customer_id = 'C009'").fetchone()[0] == 0
    # C011 inserted in batch 2: single current row effective from batch-2 date.
    rows = conn.execute(
        "SELECT effective_from, is_current FROM dim_customers WHERE customer_id = 'C011'").fetchall()
    assert len(rows) == 1 and rows[0]["effective_from"] == "2026-03-01" and rows[0]["is_current"] == 1
    # Unchanged customer C001 has exactly one version.
    assert conn.execute(
        "SELECT COUNT(*) FROM dim_customers WHERE customer_id = 'C001'").fetchone()[0] == 1
    conn.close()


def test_gold_revenue_matches_hand_computed():
    """Expected revenue recomputed by hand from the sample orders (completed
    only; O1004 was cancelled by the batch-2 CDC update):
      acme      2026-01: O1001 100 + O1002 120 + O1003 250 = 470
      acme      2026-02: O1005 240                          = 240
      acme      2026-03: O1011 120 + O1012 150              = 270
      northwind 2026-01: O1006 200 + O1007 60               = 260
      northwind 2026-02: O1008 120 + O1009 50 + O1010 180   = 350
      northwind 2026-03: O1013 100 + O1014 240              = 340
    """
    conn = build_full_pipeline()
    got = {(r["tenant_id"], r["month"]): r["revenue"] for r in conn.execute(
        "SELECT * FROM gold_revenue_by_tenant_month").fetchall()}
    expected = {
        ("acme", "2026-01"): 470.0, ("acme", "2026-02"): 240.0, ("acme", "2026-03"): 270.0,
        ("northwind", "2026-01"): 260.0, ("northwind", "2026-02"): 350.0,
        ("northwind", "2026-03"): 340.0,
    }
    assert got == expected, f"gold revenue mismatch:\n got={got}\n exp={expected}"
    conn.close()


def test_bronze_is_raw_and_append_only():
    conn = build_full_pipeline()
    # 10 snapshot rows (batch 1) + 4 CDC rows (batch 2) preserved verbatim.
    assert conn.execute("SELECT COUNT(*) FROM bronze_customers").fetchone()[0] == 14
    assert conn.execute("SELECT COUNT(*) FROM bronze_orders").fetchone()[0] == 15
    ops = {r[0] for r in conn.execute(
        "SELECT DISTINCT _source_op FROM bronze_customers WHERE _batch_id = 2")}
    assert ops == {"U", "D", "I"}, ops
    conn.close()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} tests passed")
