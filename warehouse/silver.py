"""Silver layer: cleaned, typed, deduplicated tables + SCD Type-2 dimension.

Rebuild strategy: silver is rebuilt from bronze on every run by replaying the
batches in order. Customer snapshots are reconstructed batch by batch (full
snapshot for batch 1, CDC ops applied for later batches) and each snapshot is
merged into dim_customers with proper SCD Type-2 versioning, so history is
identical whether batches are loaded together or incrementally.
"""

TRACKED_CUSTOMER_ATTRS = ("name", "email", "city", "tier")


def _replay_customer_snapshots(conn):
    """Return {batch_id: {customer_id: row_dict}} - the customer state after
    each batch, reconstructed from bronze."""
    from .db import BATCH_DATES
    snapshots = {}
    current = {}
    batches = [r[0] for r in conn.execute(
        "SELECT DISTINCT _batch_id FROM bronze_customers ORDER BY _batch_id")]
    for batch_id in batches:
        rows = conn.execute(
            "SELECT * FROM bronze_customers WHERE _batch_id = ? ORDER BY rowid",
            (batch_id,)).fetchall()
        for row in rows:
            cid = row["customer_id"]
            if row["_source_op"] == "D":
                current.pop(cid, None)
            else:
                current[cid] = {
                    "customer_id": cid,
                    "tenant_id": row["tenant_id"],
                    "name": row["name"].strip(),
                    "email": row["email"].strip().lower(),
                    "city": row["city"].strip(),
                    "tier": row["tier"].strip(),
                }
        snapshots[batch_id] = dict(current)
    return snapshots


def _merge_snapshot_into_dim(conn, snapshot, effective_date):
    """One SCD Type-2 merge step: close changed/deleted rows, open new rows."""
    current_rows = {
        r["customer_id"]: r for r in conn.execute(
            "SELECT * FROM dim_customers WHERE is_current = 1").fetchall()
    }
    # Deletes + attribute changes: close the existing current row.
    for cid, old in current_rows.items():
        new = snapshot.get(cid)
        if new is None or any(old[a] != new[a] for a in TRACKED_CUSTOMER_ATTRS):
            conn.execute(
                "UPDATE dim_customers SET effective_to = ?, is_current = 0 "
                "WHERE customer_key = ?",
                (effective_date, old["customer_key"]))
    # Inserts + new versions of changed rows.
    for cid, new in snapshot.items():
        old = current_rows.get(cid)
        if old is None or any(old[a] != new[a] for a in TRACKED_CUSTOMER_ATTRS):
            conn.execute(
                "INSERT INTO dim_customers (customer_id, tenant_id, name, email, city, tier,"
                " effective_from, effective_to, is_current) VALUES (?,?,?,?,?,?,?,NULL,1)",
                (cid, new["tenant_id"], new["name"], new["email"], new["city"],
                 new["tier"], effective_date))


def build_silver(conn):
    from .db import BATCH_DATES
    conn.execute("DROP TABLE IF EXISTS dim_customers")
    conn.execute(
        "CREATE TABLE dim_customers ("
        " customer_key INTEGER PRIMARY KEY AUTOINCREMENT,"
        " customer_id TEXT NOT NULL, tenant_id TEXT NOT NULL,"
        " name TEXT, email TEXT, city TEXT, tier TEXT,"
        " effective_from TEXT NOT NULL, effective_to TEXT, is_current INTEGER NOT NULL)"
    )
    snapshots = _replay_customer_snapshots(conn)
    for batch_id in sorted(snapshots):
        _merge_snapshot_into_dim(conn, snapshots[batch_id], BATCH_DATES[batch_id])

    # Current customer snapshot table (silver conformed view of "now").
    conn.execute("DROP TABLE IF EXISTS silver_customers")
    conn.execute(
        "CREATE TABLE silver_customers AS "
        "SELECT customer_id, tenant_id, name, email, city, tier "
        "FROM dim_customers WHERE is_current = 1")

    # Orders: replay bronze ops in batch order, dedupe by order_id (latest op
    # wins), then type + enrich with line amount.
    orders = {}
    batches = [r[0] for r in conn.execute(
        "SELECT DISTINCT _batch_id FROM bronze_orders ORDER BY _batch_id")]
    for batch_id in batches:
        rows = conn.execute(
            "SELECT * FROM bronze_orders WHERE _batch_id = ? ORDER BY rowid",
            (batch_id,)).fetchall()
        for row in rows:
            oid = row["order_id"]
            if row["_source_op"] == "D":
                orders.pop(oid, None)
            else:
                orders[oid] = row
    conn.execute("DROP TABLE IF EXISTS silver_orders")
    conn.execute(
        "CREATE TABLE silver_orders ("
        " order_id TEXT PRIMARY KEY, tenant_id TEXT, customer_id TEXT, product TEXT,"
        " quantity INTEGER, unit_price REAL, amount REAL, order_date TEXT, status TEXT)")
    for row in orders.values():
        qty = int(row["quantity"])
        price = float(row["unit_price"])
        conn.execute(
            "INSERT INTO silver_orders VALUES (?,?,?,?,?,?,?,?,?)",
            (row["order_id"], row["tenant_id"], row["customer_id"], row["product"].strip(),
             qty, price, round(qty * price, 2), row["order_date"], row["status"].strip().lower()))
    conn.commit()
    return {
        "dim_customers_rows": conn.execute("SELECT COUNT(*) FROM dim_customers").fetchone()[0],
        "silver_customers_rows": conn.execute("SELECT COUNT(*) FROM silver_customers").fetchone()[0],
        "silver_orders_rows": conn.execute("SELECT COUNT(*) FROM silver_orders").fetchone()[0],
    }
