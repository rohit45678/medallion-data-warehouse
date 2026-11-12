#!/usr/bin/env python3
"""Medallion data warehouse CLI.

Usage:
  python main.py generate          write the sample source extracts
  python main.py run --batch 1     load batch 1 (bronze -> silver -> gold)
  python main.py run --batch 2     load the batch-2 CDC delta on top
  python main.py show dim          print the SCD Type-2 customer dimension
  python main.py show gold         print the gold tables
  python main.py reset             delete the warehouse database

Typical demo:
  python main.py generate && python main.py run --batch 1 && python main.py run --batch 2
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from warehouse import bronze, generate as gen, gold, silver
from warehouse.db import DEFAULT_DB, connect


def _print_table(conn, title, query):
    rows = conn.execute(query).fetchall()
    print(f"\n== {title} ({len(rows)} rows) ==")
    if not rows:
        print("(empty)")
        return
    cols = rows[0].keys()
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join("" if r[c] is None else str(r[c]) for c in cols))


def cmd_generate(_args):
    for path in gen.generate():
        print(f"wrote {os.path.relpath(path)}")


def cmd_run(args):
    conn = connect(args.db)
    counts = bronze.load_batch(conn, args.batch)
    print(f"bronze: {counts}")
    print(f"silver: {silver.build_silver(conn)}")
    print(f"gold:   {gold.build_gold(conn)}")
    _print_table(conn, "dim_customers (SCD Type-2)",
                 "SELECT customer_key, customer_id, tenant_id, name, city, tier,"
                 " effective_from, effective_to, is_current FROM dim_customers"
                 " ORDER BY customer_id, effective_from")
    _print_table(conn, "gold_revenue_by_tenant_month",
                 "SELECT * FROM gold_revenue_by_tenant_month")
    conn.close()


def cmd_show(args):
    conn = connect(args.db)
    if args.what == "dim":
        _print_table(conn, "dim_customers (SCD Type-2)",
                     "SELECT * FROM dim_customers ORDER BY customer_id, effective_from")
    else:
        _print_table(conn, "gold_revenue_by_tenant_month",
                     "SELECT * FROM gold_revenue_by_tenant_month")
        _print_table(conn, "gold_top_products", "SELECT * FROM gold_top_products")
        _print_table(conn, "gold_customer_snapshot", "SELECT * FROM gold_customer_snapshot")
    conn.close()


def cmd_reset(args):
    if os.path.exists(args.db):
        os.remove(args.db)
        print(f"removed {args.db}")
    else:
        print("nothing to reset")


def main():
    parser = argparse.ArgumentParser(description="Medallion data warehouse pipeline")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("generate", help="write sample source extracts").set_defaults(fn=cmd_generate)

    p_run = sub.add_parser("run", help="load a batch through bronze/silver/gold")
    p_run.add_argument("--batch", type=int, required=True)
    p_run.set_defaults(fn=cmd_run)

    p_show = sub.add_parser("show", help="inspect a layer")
    p_show.add_argument("what", choices=["dim", "gold"])
    p_show.set_defaults(fn=cmd_show)

    sub.add_parser("reset", help="delete the warehouse database").set_defaults(fn=cmd_reset)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
