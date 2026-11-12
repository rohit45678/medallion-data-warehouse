# Medallion Data Warehouse
Multi-tenant data warehouse built on the medallion architecture with incremental change-data-capture (CDC) ingestion and SCD Type-2 history tracking for analytics-ready gold tables.
**Tech stack:** SQL, Python, CDC, Data Modeling, ETL/ELT
**Highlights:** bronze/silver/gold layering; incremental CDC pipelines; SCD Type-2 dimension history; multi-tenant isolation.

Implemented end-to-end in Python 3 + SQLite (standard library only — no installs needed). Two tenants (`acme`, `northwind`) are carried through every layer so tenant isolation is visible in the data itself.

## Features

- **Bronze** — raw, append-only landing tables. Source values are stored verbatim (all TEXT) with lineage columns `_batch_id`, `_loaded_at`, and `_source_op` (the CDC operation: `I`/`U`/`D`).
- **Silver** — cleaned, typed, deduplicated tables. Orders are merged by primary key (latest CDC op wins) and enriched with a computed line `amount`. Customers are conformed into an **SCD Type-2 dimension** (`effective_from` / `effective_to` / `is_current`) so every historical version is preserved.
- **Gold** — analytics-ready aggregates: revenue by tenant by month, top products per tenant, and a current-customer snapshot by tenant and tier.
- **Incremental CDC** — batch 1 is a full snapshot; batch 2 is a delta file with inserts, updates, and a delete. Silver is rebuilt by replaying batches in order, so loading batch 2 on top of batch 1 produces exactly the history a real incremental pipeline would.
- **Deterministic runs** — batch snapshot dates are fixed constants, so the pipeline output is byte-for-byte reproducible and testable.

## Architecture

```
sample_data/                warehouse.db (SQLite)
  batch1/customers.csv  ─┐
  batch1/orders.csv     ─┼─► bronze_* ─► silver_orders
  batch2/*_delta.csv    ─┘   (raw,        dim_customers (SCD-2)
                              append-only) silver_customers
                                                │
                                                ▼
                              gold_revenue_by_tenant_month
                              gold_top_products
                              gold_customer_snapshot
```

The batch-2 customer delta is designed to exercise every SCD-2 path: C002 changes city (Austin → Denver), C007 changes tier (Standard → Premium), C009 is deleted, C011 is newly inserted. The batch-2 order delta cancels order O1004, which visibly reduces gold revenue for acme / 2026-02 from 330.00 to 240.00.

## How to run

```bash
python main.py generate        # write the sample source extracts
python main.py run --batch 1   # load batch 1: bronze -> silver -> gold
python main.py run --batch 2   # apply the batch-2 CDC delta
python main.py show dim        # inspect the SCD Type-2 dimension
python main.py show gold       # inspect the gold tables
python main.py reset           # delete warehouse.db and start over
```

## Sample output

After `run --batch 2`, the SCD Type-2 dimension shows the versioned history:

```
customer_id | name        | city   | tier     | effective_from | effective_to | is_current
C002        | Bob Smith   | Austin | Standard | 2026-01-01     | 2026-03-01   | 0
C002        | Bob Smith   | Denver | Standard | 2026-03-01     |              | 1
C007        | Grace Lee   | Denver | Standard | 2026-01-01     | 2026-03-01   | 0
C007        | Grace Lee   | Denver | Premium  | 2026-03-01     |              | 1
C009        | Ivy Chen    | San Jose | Standard | 2026-01-01   | 2026-03-01   | 0   <- deleted
C011        | Karen Adams | Phoenix | Premium | 2026-03-01     |              | 1   <- inserted
```

Gold revenue by tenant and month (completed orders only):

```
tenant_id | month   | orders | revenue
acme      | 2026-01 | 3      | 470.0
acme      | 2026-02 | 1      | 240.0
acme      | 2026-03 | 2      | 270.0
northwind | 2026-01 | 2      | 260.0
northwind | 2026-02 | 3      | 350.0
northwind | 2026-03 | 2      | 340.0
```

## Tests

```bash
python tests/run_tests.py
```

Plain-assert suite (no pytest needed) covering: SCD-2 versioning of a changed record, tier-change / delete / insert handling, gold revenue totals against hand-computed expectations, and bronze raw/append-only guarantees.

## Project layout

```
main.py               CLI entry point (generate / run / show / reset)
warehouse/
  generate.py         deterministic sample source-data generator
  bronze.py           raw append-only ingestion with CDC ops
  silver.py           cleaning, dedupe, SCD Type-2 dimension build
  gold.py             aggregate table builds
  db.py               SQLite helpers + batch configuration
sample_data/          source extracts (batch1 snapshots, batch2 CDC deltas)
tests/run_tests.py    end-to-end pipeline tests
```
