"""Bronze layer: raw, append-only ingestion.

Source extracts land exactly as received (every value stored as TEXT) plus
lineage columns:
  _batch_id   pipeline batch that delivered the row
  _loaded_at  batch snapshot date (deterministic)
  _source_op  CDC operation from the source delta: I / U / D
              (batch-1 full extracts default to 'I')
"""

import csv
import os

from .db import BATCH_DATES, BATCH_FILES, SAMPLE_DATA

BRONZE_SCHEMA = {
    "bronze_customers": ["customer_id", "tenant_id", "name", "email", "city", "tier", "updated_at"],
    "bronze_orders": ["order_id", "tenant_id", "customer_id", "product", "quantity",
                      "unit_price", "order_date", "status"],
}


def ensure_bronze(conn):
    for table, cols in BRONZE_SCHEMA.items():
        coldefs = ", ".join(f"{c} TEXT" for c in cols)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ("
            f"{coldefs}, _batch_id INTEGER, _loaded_at TEXT, _source_op TEXT)"
        )


def load_batch(conn, batch_id):
    """Append one batch's source files to bronze. Idempotent per batch:
    re-running a batch first removes that batch's earlier bronze rows."""
    if batch_id not in BATCH_FILES:
        raise ValueError(f"unknown batch {batch_id}; known: {sorted(BATCH_FILES)}")
    ensure_bronze(conn)
    loaded_at = BATCH_DATES[batch_id]
    counts = {}
    for rel_path, table, has_op in BATCH_FILES[batch_id]:
        path = os.path.join(SAMPLE_DATA, rel_path)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} missing - run `python main.py generate` first")
        conn.execute(f"DELETE FROM {table} WHERE _batch_id = ?", (batch_id,))
        cols = BRONZE_SCHEMA[table]
        placeholders = ", ".join("?" for _ in cols)
        n = 0
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                op = row["op"] if has_op else "I"
                values = [row[c] for c in cols]
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(cols)}, _batch_id, _loaded_at, _source_op) "
                    f"VALUES ({placeholders}, ?, ?, ?)",
                    (*values, batch_id, loaded_at, op),
                )
                n += 1
        counts[table] = n
    conn.commit()
    return counts
