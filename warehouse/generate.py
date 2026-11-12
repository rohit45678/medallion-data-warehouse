"""Sample source-data generator.

Writes deterministic source extracts under sample_data/:

  batch1/customers.csv       full customer snapshot (batch 1)
  batch1/orders.csv          full order extract (batch 1)
  batch2/customers_delta.csv CDC delta: inserts / updates / deletes (op column)
  batch2/orders_delta.csv    CDC delta: new orders + one status update

The batch-2 customer delta deliberately contains:
  * C002 - city change (Austin -> Denver)          -> SCD2 must version this row
  * C007 - tier change (Standard -> Premium)       -> SCD2 must version this row
  * C009 - delete                                  -> SCD2 must close this row
  * C011 - brand-new customer                      -> SCD2 must open a new row

The batch-2 order delta flips order O1004 to 'cancelled', which must reduce
gold revenue for acme / 2026-02 once batch 2 is loaded.
"""

import csv
import os

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")

CUSTOMERS_B1 = [
    # customer_id, tenant_id, name, email, city, tier, updated_at
    ("C001", "acme", "Alice Johnson", "alice@example.com", "New York", "Premium", "2025-12-20"),
    ("C002", "acme", "Bob Smith", "bob@example.com", "Austin", "Standard", "2025-12-21"),
    ("C003", "acme", "Carol White", "carol@example.com", "Chicago", "Standard", "2025-12-21"),
    ("C004", "acme", "David Brown", "david@example.com", "Seattle", "Premium", "2025-12-22"),
    ("C005", "acme", "Emma Davis", "emma@example.com", "Miami", "Standard", "2025-12-22"),
    ("C006", "northwind", "Frank Miller", "frank@example.com", "Boston", "Standard", "2025-12-20"),
    ("C007", "northwind", "Grace Lee", "grace@example.com", "Denver", "Standard", "2025-12-21"),
    ("C008", "northwind", "Henry Wilson", "henry@example.com", "Portland", "Premium", "2025-12-23"),
    ("C009", "northwind", "Ivy Chen", "ivy@example.com", "San Jose", "Standard", "2025-12-23"),
    ("C010", "northwind", "Jack Taylor", "jack@example.com", "Atlanta", "Standard", "2025-12-24"),
]

CUSTOMERS_B2_DELTA = [
    # op, customer_id, tenant_id, name, email, city, tier, updated_at
    ("U", "C002", "acme", "Bob Smith", "bob@example.com", "Denver", "Standard", "2026-02-10"),
    ("U", "C007", "northwind", "Grace Lee", "grace@example.com", "Denver", "Premium", "2026-02-11"),
    ("D", "C009", "northwind", "Ivy Chen", "ivy@example.com", "San Jose", "Standard", "2026-02-12"),
    ("I", "C011", "acme", "Karen Adams", "karen@example.com", "Phoenix", "Premium", "2026-02-12"),
]

ORDERS_B1 = [
    # order_id, tenant_id, customer_id, product, quantity, unit_price, order_date, status
    ("O1001", "acme", "C001", "Widget", 2, "50.00", "2026-01-05", "completed"),
    ("O1002", "acme", "C002", "Gadget", 1, "120.00", "2026-01-12", "completed"),
    ("O1003", "acme", "C003", "Widget", 5, "50.00", "2026-01-20", "completed"),
    ("O1004", "acme", "C001", "Gizmo", 3, "30.00", "2026-02-03", "completed"),
    ("O1005", "acme", "C004", "Gadget", 2, "120.00", "2026-02-14", "completed"),
    ("O1006", "northwind", "C006", "Widget", 4, "50.00", "2026-01-08", "completed"),
    ("O1007", "northwind", "C007", "Gizmo", 2, "30.00", "2026-01-15", "completed"),
    ("O1008", "northwind", "C008", "Gadget", 1, "120.00", "2026-02-02", "completed"),
    ("O1009", "northwind", "C009", "Widget", 1, "50.00", "2026-02-09", "completed"),
    ("O1010", "northwind", "C010", "Gizmo", 6, "30.00", "2026-02-18", "completed"),
]

ORDERS_B2_DELTA = [
    # op, order_id, tenant_id, customer_id, product, quantity, unit_price, order_date, status
    ("U", "O1004", "acme", "C001", "Gizmo", 3, "30.00", "2026-02-03", "cancelled"),
    ("I", "O1011", "acme", "C011", "Gadget", 1, "120.00", "2026-03-02", "completed"),
    ("I", "O1012", "acme", "C002", "Widget", 3, "50.00", "2026-03-05", "completed"),
    ("I", "O1013", "northwind", "C007", "Widget", 2, "50.00", "2026-03-04", "completed"),
    ("I", "O1014", "northwind", "C010", "Gadget", 2, "120.00", "2026-03-09", "completed"),
]

CUSTOMER_FIELDS = ["customer_id", "tenant_id", "name", "email", "city", "tier", "updated_at"]
CUSTOMER_DELTA_FIELDS = ["op"] + CUSTOMER_FIELDS
ORDER_FIELDS = ["order_id", "tenant_id", "customer_id", "product", "quantity",
                "unit_price", "order_date", "status"]
ORDER_DELTA_FIELDS = ["op"] + ORDER_FIELDS


def _write(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        writer.writerows(rows)


def generate(base=BASE):
    """Write all sample source extracts. Returns list of files written."""
    files = []
    specs = [
        ("batch1/customers.csv", CUSTOMER_FIELDS, CUSTOMERS_B1),
        ("batch1/orders.csv", ORDER_FIELDS, ORDERS_B1),
        ("batch2/customers_delta.csv", CUSTOMER_DELTA_FIELDS, CUSTOMERS_B2_DELTA),
        ("batch2/orders_delta.csv", ORDER_DELTA_FIELDS, ORDERS_B2_DELTA),
    ]
    for rel, fields, rows in specs:
        path = os.path.join(base, rel)
        _write(path, fields, rows)
        files.append(path)
    return files
