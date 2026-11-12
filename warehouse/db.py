"""SQLite helpers and pipeline constants."""

import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "warehouse.db")
SAMPLE_DATA = os.path.join(ROOT, "sample_data")

# Snapshot ("as of") date for each batch. SCD-2 effective dates come from here,
# which keeps pipeline runs deterministic and testable.
BATCH_DATES = {1: "2026-01-01", 2: "2026-03-01"}

# Source file(s) per batch: (relative path, bronze table, has_op_column)
BATCH_FILES = {
    1: [("batch1/customers.csv", "bronze_customers", False),
        ("batch1/orders.csv", "bronze_orders", False)],
    2: [("batch2/customers_delta.csv", "bronze_customers", True),
        ("batch2/orders_delta.csv", "bronze_orders", True)],
}


def connect(db_path=DEFAULT_DB):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
