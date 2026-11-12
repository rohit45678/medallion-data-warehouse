"""Gold layer: analytics-ready aggregates built from silver.

  gold_revenue_by_tenant_month  completed-order revenue per tenant per month
  gold_top_products             product revenue/units per tenant (ranked)
  gold_customer_snapshot        current customers per tenant and tier
"""


def build_gold(conn):
    conn.execute("DROP TABLE IF EXISTS gold_revenue_by_tenant_month")
    conn.execute(
        "CREATE TABLE gold_revenue_by_tenant_month AS "
        "SELECT tenant_id, substr(order_date, 1, 7) AS month, "
        "       COUNT(*) AS orders, ROUND(SUM(amount), 2) AS revenue "
        "FROM silver_orders WHERE status = 'completed' "
        "GROUP BY tenant_id, month ORDER BY tenant_id, month")

    conn.execute("DROP TABLE IF EXISTS gold_top_products")
    conn.execute(
        "CREATE TABLE gold_top_products AS "
        "SELECT tenant_id, product, SUM(quantity) AS units, "
        "       ROUND(SUM(amount), 2) AS revenue "
        "FROM silver_orders WHERE status = 'completed' "
        "GROUP BY tenant_id, product ORDER BY tenant_id, revenue DESC")

    conn.execute("DROP TABLE IF EXISTS gold_customer_snapshot")
    conn.execute(
        "CREATE TABLE gold_customer_snapshot AS "
        "SELECT tenant_id, tier, COUNT(*) AS customers "
        "FROM silver_customers GROUP BY tenant_id, tier ORDER BY tenant_id, tier")

    conn.commit()
    return {
        "gold_revenue_by_tenant_month": conn.execute(
            "SELECT COUNT(*) FROM gold_revenue_by_tenant_month").fetchone()[0],
        "gold_top_products": conn.execute(
            "SELECT COUNT(*) FROM gold_top_products").fetchone()[0],
        "gold_customer_snapshot": conn.execute(
            "SELECT COUNT(*) FROM gold_customer_snapshot").fetchone()[0],
    }
