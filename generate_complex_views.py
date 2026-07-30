"""
generate_complex_views.py
生成复杂嵌套视图示例 SQL 文件
- 分层结构：L1基础 → L2中间 → L3顶层 → L4深度嵌套
- 视图调用视图，3层以上嵌套
- 多种 SQL 语法：CTE、子查询、UNION/UNION ALL、WINDOW FUNCTION、HAVING、DISTINCT ON 等
"""
from pathlib import Path

OUT_DIR = Path(__file__).parent / "sample_sql" / "git" / "views"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 可用表 ────────────────────────────────────────────────
TABLES = [
    "ods.users_raw", "ods.orders_raw", "ods.order_items_raw", "ods.products_raw",
    "ods.inventories_raw", "ods.warehouses_raw", "ods.suppliers_raw", "ods.payments_raw",
    "ods.shipments_raw", "ods.refunds_raw", "ods.reviews_raw", "ods.promotions_raw",
    "ods.carts_raw", "ods.campaigns_raw", "ods.email_events_raw",
    "dw.users_clean", "dw.orders_clean", "dw.order_items_clean", "dw.products_clean",
    "dw.inventories_clean", "dw.warehouses_clean", "dw.suppliers_clean",
    "dw.payments_clean", "dw.shipments_clean", "dw.refunds_clean",
    "dw.reviews_clean", "dw.promotions_clean", "dw.carts_clean",
    "dim.date_dim", "dim.product_dim", "dim.customer_segment_dim",
    "dim.channel_dim", "dim.currency_dim", "dim.warehouse_dim",
    "dim.supplier_dim", "dim.shipping_method_dim", "dim.promo_dim",
    "fact.sales_fact", "fact.inventory_fact", "fact.marketing_fact",
    "fact.loyalty_fact", "fact.purchase_fact", "fact.return_fact",
    "fact.web_traffic_fact", "fact.subscription_fact",
    "fact.pricing_fact", "fact.budget_fact",
    "dw.product_suppliers", "dw.warehouse_products",
]

# ─── 分层视图定义 ─────────────────────────────────────────
# format: (view_name, layer, deps_tables, deps_views, sql_template)
# deps_tables: 依赖的直接表（层外引用）
# deps_views:   依赖的视图（L1→[], L2→L1视图, L3→L2视图, L4→任意）
#               同一行内 deps_views 指 L-N 的视图

def write(name, sql):
    path = OUT_DIR / f"{name}.sql"
    path.write_text(sql, encoding="utf-8")
    print(f"  ✓ {name}")


# ══════════════════════════════════════════════════════════
# L1 — 基础层：直接 JOIN 2~3 张表，无视图依赖
# ══════════════════════════════════════════════════════════

write("dw_v_base_user_orders", """
-- L1: 基础视图，直接关联 users + orders 两张表
CREATE OR REPLACE VIEW dw.v_base_user_orders AS
SELECT u.user_id, u.user_name, u.email, u.city,
       o.order_id, o.order_date, o.status, o.total_amount
FROM dw.users_clean u
LEFT JOIN dw.orders_clean o ON u.user_id = o.user_id;
""")

write("dw_v_base_order_items", """
-- L1: 基础视图，orders + order_items 两表
CREATE OR REPLACE VIEW dw.v_base_order_items AS
SELECT o.order_id, o.order_date,
       oi.order_item_id, oi.product_id, oi.quantity, oi.unit_price
FROM dw.orders_clean o
JOIN dw.order_items_clean oi ON o.order_id = oi.order_id;
""")

write("dw_v_base_product_suppliers", """
-- L1: 基础视图，products + product_suppliers + suppliers
CREATE OR REPLACE VIEW dw.v_base_product_suppliers AS
SELECT p.product_id, p.product_name, p.category, p.price,
       s.supplier_id, s.supplier_name, s.country
FROM dw.products_clean p
LEFT JOIN dw.product_suppliers ps ON p.product_id = ps.product_id
LEFT JOIN dw.suppliers_clean s ON ps.supplier_id = s.supplier_id;
""")

write("dw_v_base_inventory_stock", """
-- L1: 基础视图，products + warehouse_products + warehouses
CREATE OR REPLACE VIEW dw.v_base_inventory_stock AS
SELECT p.product_id, p.product_name,
       w.warehouse_id, w.warehouse_name, w.city,
       wp.quantity AS stock_qty, wp.last_updated
FROM dw.products_clean p
JOIN dw.warehouse_products wp ON p.product_id = wp.product_id
JOIN dw.warehouses_clean w ON wp.warehouse_id = w.warehouse_id;
""")

write("dw_v_base_payment_records", """
-- L1: 基础视图，orders + payments 两表
CREATE OR REPLACE VIEW dw.v_base_payment_records AS
SELECT o.order_id, o.user_id, o.total_amount,
       p.payment_id, p.payment_method, p.amount AS paid_amount, p.status AS pay_status
FROM dw.orders_clean o
LEFT JOIN dw.payments_clean p ON o.order_id = p.order_id;
""")

write("dw_v_base_shipment_status", """
-- L1: 基础视图，orders + shipments + shipping_method
CREATE OR REPLACE VIEW dw.v_base_shipment_status AS
SELECT o.order_id, o.user_id,
       sh.shipment_id, sh.shipping_method_id,
       sm.method_name, sm.carrier, sh.ship_date, sh.delivery_date, sh.status AS ship_status
FROM dw.orders_clean o
LEFT JOIN dw.shipments_clean sh ON o.order_id = sh.order_id
LEFT JOIN dim.shipping_method_dim sm ON sh.shipping_method_id = sm.shipping_method_id;
""")

write("dw_v_base_refund_records", """
-- L1: 基础视图，orders + refunds + order_items
CREATE OR REPLACE VIEW dw.v_base_refund_records AS
SELECT o.order_id, o.user_id,
       r.refund_id, r.refund_amount, r.reason, r.refund_date,
       oi.order_item_id, oi.product_id
FROM dw.orders_clean o
JOIN dw.refunds_clean r ON o.order_id = r.order_id
LEFT JOIN dw.order_items_clean oi ON r.order_item_id = oi.order_item_id;
""")

write("dw_v_base_product_reviews", """
-- L1: 基础视图，products + reviews + users
CREATE OR REPLACE VIEW dw.v_base_product_reviews AS
SELECT p.product_id, p.product_name, p.category,
       r.review_id, r.user_id, r.rating, r.review_text, r.created_at,
       u.user_name
FROM dw.products_clean p
JOIN dw.reviews_clean r ON p.product_id = r.product_id
LEFT JOIN dw.users_clean u ON r.user_id = u.user_id;
""")

write("dw_v_base_loyalty_members", """
-- L1: 基础视图，users + loyalty_fact + customer_segment
CREATE OR REPLACE VIEW dw.v_base_loyalty_members AS
SELECT u.user_id, u.user_name, u.email,
       l.tier, l.points_balance, l.points_earned, l.points_redeemed,
       cs.segment_name
FROM dw.users_clean u
JOIN fact.loyalty_fact l ON u.user_id = l.user_sk
LEFT JOIN dim.customer_segment_dim cs ON l.user_sk = cs.customer_sk;
""")

write("dw_v_base_daily_sales_fact", """
-- L1: 基础视图，sales_fact + date_dim 两表
CREATE OR REPLACE VIEW dw.v_base_daily_sales_fact AS
SELECT d.date_sk, d.full_date, d.year, d.month, d.week,
       f.order_sk, f.net_sales, f.quantity_sold, f.discount_amt
FROM fact.sales_fact f
JOIN dim.date_dim d ON f.date_sk = d.date_sk;
""")

write("dw_v_base_marketing_spend", """
-- L1: 基础视图，marketing_fact + channel_dim + date_dim
CREATE OR REPLACE VIEW dw.v_base_marketing_spend AS
SELECT d.year, d.month, d.quarter,
       c.channel_name, c.channel_type,
       m.spend_amt, m.impressions, m.clicks, m.conversions
FROM fact.marketing_fact m
JOIN dim.channel_dim c ON m.channel_sk = c.channel_sk
JOIN dim.date_dim d ON m.date_sk = d.date_sk;
""")

write("dw_v_base_web_metrics", """
-- L1: 基础视图，web_traffic_fact + date_dim
CREATE OR REPLACE VIEW dw.v_base_web_metrics AS
SELECT d.full_date, d.month, d.year,
       t.session_id, t.page_views, t.sessions, t.bounce_rate, t.avg_session_duration
FROM fact.web_traffic_fact t
JOIN dim.date_dim d ON t.date_sk = d.date_sk;
""")

write("dw_v_base_subscription_status", """
-- L1: 基础视图，users + subscription_fact + product_dim
CREATE OR REPLACE VIEW dw.v_base_subscription_status AS
SELECT u.user_id, u.user_name,
       s.subscription_id, s.plan_type, s.start_date, s.end_date,
       s.mrr, s.churn_risk, s.auto_renew,
       pd.product_name
FROM dw.users_clean u
JOIN fact.subscription_fact s ON u.user_id = s.user_sk
LEFT JOIN dim.product_dim pd ON s.product_id = pd.product_sk;
""")

write("dw_v_base_pricing_snapshot", """
-- L1: 基础视图，pricing_fact + product_dim + date_dim
CREATE OR REPLACE VIEW dw.v_base_pricing_snapshot AS
SELECT d.full_date, d.year, d.month,
       p.product_sk, p.product_name, p.category,
       pr.base_price, pr.competitor_avg_price, pr.price_index
FROM fact.pricing_fact pr
JOIN dim.date_dim d ON pr.date_sk = d.date_sk
JOIN dim.product_dim p ON pr.product_sk = p.product_sk;
""")

write("dw_v_base_budget_vs_actual", """
-- L1: 基础视图，budget_fact + date_dim + product_dim
CREATE OR REPLACE VIEW dw.v_base_budget_vs_actual AS
SELECT d.year, d.month, d.quarter,
       p.product_name, p.category,
       b.budget_amount, b.actual_amount,
       b.budget_amount - b.actual_amount AS variance
FROM fact.budget_fact b
JOIN dim.date_dim d ON b.date_sk = d.date_sk
JOIN dim.product_dim p ON b.product_sk = p.product_sk;
""")


# ══════════════════════════════════════════════════════════
# L2 — 中间层：引用 L1 视图 + 少量表
# ══════════════════════════════════════════════════════════

write("dw_v_inter_user_order_summary", """
-- L2: 引用 L1(v_base_user_orders, v_base_payment_records) + dim.date_dim
CREATE OR REPLACE VIEW dw.v_inter_user_order_summary AS
SELECT uo.user_id, uo.user_name,
       COUNT(DISTINCT uo.order_id) AS total_orders,
       SUM(uo.total_amount)        AS total_spent,
       MAX(uo.order_date)          AS last_order_date,
       pd.paid_amount               AS total_paid,
       d.quarter
FROM dw.v_base_user_orders uo
LEFT JOIN dw.v_base_payment_records pd ON uo.order_id = pd.order_id
LEFT JOIN dim.date_dim d ON uo.order_date = d.full_date
GROUP BY uo.user_id, uo.user_name, pd.paid_amount, d.quarter;
""")

write("dw_v_inter_product_sales_summary", """
-- L2: 引用 L1(v_base_order_items, v_base_product_suppliers) + dim.date_dim
CREATE OR REPLACE VIEW dw.v_inter_product_sales_summary AS
SELECT oi.product_id, ps.product_name, ps.category,
       ps.supplier_name, ps.country,
       d.year, d.month,
       SUM(oi.quantity)             AS total_qty,
       SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM dw.v_base_order_items oi
JOIN dw.v_base_product_suppliers ps ON oi.product_id = ps.product_id
LEFT JOIN dim.date_dim d ON oi.order_date = d.full_date
GROUP BY oi.product_id, ps.product_name, ps.category, ps.supplier_name, ps.country, d.year, d.month;
""")

write("dw_v_inter_inventory_alert", """
-- L2: 引用 L1(v_base_inventory_stock) + dim.product_dim
CREATE OR REPLACE VIEW dw.v_inter_inventory_alert AS
SELECT inv.product_id, inv.product_name,
       inv.warehouse_name, inv.city,
       inv.stock_qty,
       pd.reorder_point, pd.safety_stock,
       CASE WHEN inv.stock_qty <= pd.reorder_point THEN 'REORDER'
            WHEN inv.stock_qty <= pd.safety_stock   THEN 'LOW'
            ELSE 'OK' END AS stock_status
FROM dw.v_base_inventory_stock inv
JOIN dim.product_dim pd ON inv.product_id = pd.product_id;
""")

write("dw_v_inter_customer_payment_behavior", """
-- L2: 引用 L1(v_base_payment_records) + dw.users_clean
CREATE OR REPLACE VIEW dw.v_inter_customer_payment_behavior AS
SELECT u.user_id, u.user_name, u.city,
       COUNT(p.order_id)       AS payment_count,
       SUM(p.paid_amount)      AS total_paid,
       AVG(p.paid_amount)      AS avg_payment,
       MAX(CASE p.pay_status WHEN 'COMPLETED' THEN 1 ELSE 0 END) AS has_paid
FROM dw.v_base_payment_records p
JOIN dw.users_clean u ON p.user_id = u.user_id
GROUP BY u.user_id, u.user_name, u.city;
""")

write("dw_v_inter_shipment_delivery_perf", """
-- L2: 引用 L1(v_base_shipment_status) + dim.date_dim
CREATE OR REPLACE VIEW dw.v_inter_shipment_delivery_perf AS
SELECT ss.shipping_method_id, ss.method_name, ss.carrier,
       d.year, d.month,
       COUNT(ss.order_id)        AS total_shipments,
       SUM(CASE WHEN ss.ship_status = 'DELIVERED' THEN 1 ELSE 0 END) AS delivered,
       AVG(DATEDIFF(ss.delivery_date, ss.ship_date)) AS avg_days_to_deliver
FROM dw.v_base_shipment_status ss
LEFT JOIN dim.date_dim d ON ss.ship_date = d.full_date
GROUP BY ss.shipping_method_id, ss.method_name, ss.carrier, d.year, d.month;
""")

write("dw_v_inter_loyalty_tier_analysis", """
-- L2: 引用 L1(v_base_loyalty_members) + dim.date_dim
CREATE OR REPLACE VIEW dw.v_inter_loyalty_tier_analysis AS
SELECT lm.tier, lm.segment_name,
       d.year, d.quarter,
       COUNT(DISTINCT lm.user_id)  AS member_count,
       SUM(lm.points_earned)       AS total_points_earned,
       SUM(lm.points_redeemed)     AS total_points_redeemed,
       AVG(lm.points_balance)      AS avg_points_balance
FROM dw.v_base_loyalty_members lm
LEFT JOIN dim.date_dim d ON 1=1
GROUP BY lm.tier, lm.segment_name, d.year, d.quarter;
""")

write("dw_v_inter_marketing_channel_roi", """
-- L2: 引用 L1(v_base_marketing_spend) + fact.sales_fact
CREATE OR REPLACE VIEW dw.v_inter_marketing_channel_roi AS
SELECT ms.channel_name, ms.channel_type,
       ms.year, ms.month,
       SUM(ms.spend_amt)       AS total_spend,
       SUM(ms.conversions)     AS total_conversions,
       SUM(ms.clicks)          AS total_clicks,
       SUM(ms.impressions)     AS total_impressions,
       SUM(sf.net_sales)       AS attributed_sales,
       CASE WHEN SUM(ms.spend_amt) > 0
            THEN SUM(sf.net_sales) / SUM(ms.spend_amt)
            ELSE 0 END         AS roi
FROM dw.v_base_marketing_spend ms
LEFT JOIN fact.sales_fact sf ON ms.year = sf.date_sk
GROUP BY ms.channel_name, ms.channel_type, ms.year, ms.month;
""")

write("dw_v_inter_web_session_quality", """
-- L2: 引用 L1(v_base_web_metrics) + fact.sales_fact
CREATE OR REPLACE VIEW dw.v_inter_web_session_quality AS
SELECT wm.month, wm.year,
       SUM(wm.page_views)       AS total_page_views,
       SUM(wm.sessions)        AS total_sessions,
       AVG(wm.bounce_rate)     AS avg_bounce_rate,
       AVG(wm.avg_session_duration) AS avg_session_sec,
       SUM(sf.net_sales)       AS session_attributed_sales
FROM dw.v_base_web_metrics wm
LEFT JOIN fact.sales_fact sf ON wm.full_date = sf.date_sk
GROUP BY wm.month, wm.year;
""")

write("dw_v_inter_subscription_churn_risk", """
-- L2: 引用 L1(v_base_subscription_status) + dw.users_clean
CREATE OR REPLACE VIEW dw.v_inter_subscription_churn_risk AS
SELECT u.user_id, u.user_name, u.city,
       ss.subscription_id, ss.plan_type, ss.mrr,
       ss.churn_risk, ss.auto_renew,
       CASE WHEN ss.end_date < CURRENT_DATE THEN 'EXPIRED'
            WHEN ss.churn_risk > 0.7        THEN 'HIGH RISK'
            WHEN ss.churn_risk > 0.3        THEN 'MEDIUM RISK'
            ELSE 'LOW RISK' END AS churn_label
FROM dw.v_base_subscription_status ss
JOIN dw.users_clean u ON ss.user_id = u.user_id;
""")

write("dw_v_inter_price_competitiveness", """
-- L2: 引用 L1(v_base_pricing_snapshot) + dim.product_dim
CREATE OR REPLACE VIEW dw.v_inter_price_competitiveness AS
SELECT ps.product_name, ps.category,
       ps.year, ps.month,
       AVG(ps.base_price)            AS avg_price,
       AVG(ps.competitor_avg_price)   AS avg_competitor_price,
       AVG(ps.price_index)            AS avg_price_index,
       CASE WHEN AVG(ps.price_index) > 1.1 THEN 'OVERPRICED'
            WHEN AVG(ps.price_index) < 0.9 THEN 'UNDERPRICED'
            ELSE 'COMPETITIVE' END     AS price_position
FROM dw.v_base_pricing_snapshot ps
GROUP BY ps.product_name, ps.category, ps.year, ps.month;
""")


# ══════════════════════════════════════════════════════════
# L3 — 顶层：引用 L2 视图 + L1 视图 + 表，3层嵌套
# ══════════════════════════════════════════════════════════

write("dw_v_top_customer_lifetime_value", """
-- L3: 3层嵌套
-- L3(v_top_customer_lifetime_value) → L2(v_inter_user_order_summary) → L1(v_base_user_orders)
-- L3(v_top_customer_lifetime_value) → L2(v_inter_marketing_channel_roi)
-- L3(v_top_customer_lifetime_value) → L1(v_base_loyalty_members)
CREATE OR REPLACE VIEW dw.v_top_customer_lifetime_value AS
SELECT uos.user_id, uos.user_name,
       uos.total_orders, uos.total_spent, uos.last_order_date,
       mcr.channel_name  AS preferred_channel,
       mcr.roi           AS marketing_roi,
       lm.tier, lm.points_balance,
       CASE WHEN uos.total_orders >= 10 THEN 'VIP'
            WHEN uos.total_orders >= 5  THEN 'ACTIVE'
            ELSE 'CASUAL' END AS customer_type
FROM dw.v_inter_user_order_summary uos
LEFT JOIN dw.v_inter_marketing_channel_roi mcr ON uos.user_id = mcr.year
LEFT JOIN dw.v_base_loyalty_members lm ON uos.user_id = lm.user_id;
""")

write("dw_v_top_product_performance_dashboard", """
-- L3: 3层嵌套
-- L3 → L2(v_inter_product_sales_summary) → L1(v_base_order_items, v_base_product_suppliers)
-- L3 → L2(v_inter_inventory_alert) → L1(v_base_inventory_stock)
-- L3 → L1(v_base_pricing_snapshot)
CREATE OR REPLACE VIEW dw.v_top_product_performance_dashboard AS
SELECT pss.product_id, pss.product_name, pss.category,
       pss.supplier_name, pss.country,
       pss.total_qty, pss.total_revenue,
       ia.stock_status, ia.stock_qty,
       pp.avg_price_index,
       CASE WHEN pss.total_revenue > 100000 THEN 'TOP PERFORMER'
            WHEN pss.total_revenue > 10000  THEN 'GROWING'
            ELSE 'STANDARD' END AS performance_tier
FROM dw.v_inter_product_sales_summary pss
JOIN dw.v_inter_inventory_alert ia ON pss.product_id = ia.product_id
LEFT JOIN dw.v_base_pricing_snapshot pp ON pss.product_id = pp.product_sk
GROUP BY pss.product_id, pss.product_name, pss.category, pss.supplier_name, pss.country,
         pss.total_qty, pss.total_revenue, ia.stock_status, ia.stock_qty, pp.avg_price_index;
""")

write("dw_v_top_marketing_attribution", """
-- L3: 3层嵌套，marketing_fact + L2(loyalty + channel_roi) + L1(web_metrics)
CREATE OR REPLACE VIEW dw.v_top_marketing_attribution AS
SELECT mc.year, mc.month, mc.channel_name, mc.channel_type,
       mc.total_spend, mc.conversions, mc.roi,
       lm.member_count         AS loyalty_members_reached,
       wsq.total_sessions      AS web_sessions,
       wsq.avg_bounce_rate      AS bounce_rate,
       CASE WHEN mc.roi > 5   THEN 'EXCELLENT'
            WHEN mc.roi > 2   THEN 'GOOD'
            WHEN mc.roi > 0   THEN 'BREAKEVEN'
            ELSE 'NEGATIVE' END AS roi_tier
FROM dw.v_inter_marketing_channel_roi mc
LEFT JOIN dw.v_inter_loyalty_tier_analysis lm ON mc.year = lm.year
LEFT JOIN dw.v_inter_web_session_quality wsq ON mc.year = wsq.year AND mc.month = wsq.month;
""")

write("dw_v_top_shipment_fulfillment_score", """
-- L3: 3层嵌套，shipments + L2(delivery_perf) + L1(payment_records)
CREATE OR REPLACE VIEW dw.v_top_shipment_fulfillment_score AS
SELECT sdp.method_name, sdp.carrier, sdp.year, sdp.month,
       sdp.total_shipments, sdp.delivered,
       ROUND(sdp.delivered * 100.0 / NULLIF(sdp.total_shipments, 0), 2) AS delivery_rate,
       sdp.avg_days_to_deliver,
       pr.total_paid               AS paid_orders,
       CASE WHEN ROUND(sdp.delivered * 100.0 / NULLIF(sdp.total_shipments, 0), 2) >= 95 THEN 'A'
            WHEN ROUND(sdp.delivered * 100.0 / NULLIF(sdp.total_shipments, 0), 2) >= 85 THEN 'B'
            WHEN ROUND(sdp.delivered * 100.0 / NULLIF(sdp.total_shipments, 0), 2) >= 70 THEN 'C'
            ELSE 'D' END AS fulfillment_grade
FROM dw.v_inter_shipment_delivery_perf sdp
LEFT JOIN dw.v_base_payment_records pr ON 1=1
GROUP BY sdp.method_name, sdp.carrier, sdp.year, sdp.month,
         sdp.total_shipments, sdp.delivered, sdp.avg_days_to_deliver, pr.total_paid;
""")

write("dw_v_top_customer_risk_segments", """
-- L3: 3层嵌套，loyalty + subscription_churn + payment_behavior
CREATE OR REPLACE VIEW dw.v_top_customer_risk_segments AS
SELECT cr.user_id, cr.user_name, cr.city,
       scr.churn_label,
       pb.payment_count, pb.total_paid,
       lm.tier, lm.points_balance,
       CASE WHEN scr.churn_risk > 0.7 AND pb.total_paid < 100 THEN 'HIGH RISK'
            WHEN scr.churn_risk > 0.3 OR pb.payment_count < 2  THEN 'MEDIUM RISK'
            ELSE 'LOW RISK' END AS overall_risk
FROM dw.v_inter_subscription_churn_risk scr
JOIN dw.v_inter_customer_payment_behavior pb ON scr.user_id = pb.user_id
JOIN dw.v_base_loyalty_members lm ON scr.user_id = lm.user_id;
""")

write("dw_v_top_business_health_score", """
-- L3: 3层嵌套，整合多个 L2 视图形成综合评分
-- L2(marketing_channel_roi, loyalty_tier_analysis, web_session_quality)
CREATE OR REPLACE VIEW dw.v_top_business_health_score AS
SELECT mc.year, mc.month,
       mc.total_spend, mc.conversions, mc.roi,
       lm.member_count     AS loyalty_members,
       lm.total_points_earned,
       wsq.total_sessions  AS web_sessions,
       wsq.avg_bounce_rate,
       (mc.roi * 20) + (lm.member_count / 100.0) + (wsq.total_sessions / 10000.0) AS health_score,
       CASE WHEN mc.roi > 3 AND lm.member_count > 100 THEN 'HEALTHY'
            WHEN mc.roi > 1 AND lm.member_count > 50  THEN 'GROWING'
            ELSE 'NEEDS ATTENTION' END AS health_label
FROM dw.v_inter_marketing_channel_roi mc
JOIN dw.v_inter_loyalty_tier_analysis lm ON mc.year = lm.year AND mc.month = lm.month
JOIN dw.v_inter_web_session_quality wsq ON mc.year = wsq.year AND mc.month = wsq.month;
""")


# ══════════════════════════════════════════════════════════
# L4 — 深度嵌套层：4层以上 + 高级 SQL 语法
#   - CTE (WITH 子句)
#   - 子查询 (IN / EXISTS / FROM 子查询)
#   - UNION / UNION ALL
#   - 窗口函数 (ROW_NUMBER / RANK / LAG / SUM OVER)
#   - HAVING, DISTINCT ON, CROSS JOIN, LATERAL
# ══════════════════════════════════════════════════════════

write("dw_v_l4_exec_customer360_with_cte", """
-- L4: 4层嵌套 + CTE
-- L4 → L3(v_top_customer_lifetime_value) → L2 → L1
-- L4 → L2(v_inter_customer_payment_behavior)
-- L4 → L2(v_inter_inventory_alert)
-- 语法亮点: WITH CTE, LATERAL JOIN, window function
CREATE OR REPLACE VIEW dw.v_l4_exec_customer360_with_cte AS
WITH base_cte AS (
    SELECT user_id, user_name, total_orders, total_spent, tier,
           ROW_NUMBER() OVER (PARTITION BY tier ORDER BY total_spent DESC) AS rn
    FROM dw.v_top_customer_lifetime_value
),
payment_summary AS (
    SELECT user_id, total_paid, payment_count
    FROM dw.v_inter_customer_payment_behavior
)
SELECT b.user_id, b.user_name, b.total_orders, b.total_spent, b.tier,
       p.total_paid, p.payment_count,
       b.total_spent + COALESCE(p.total_paid, 0) AS ltv_composite
FROM base_cte b
LEFT JOIN payment_summary p ON b.user_id = p.user_id
WHERE b.rn <= 100;
""")

write("dw_v_l4_exec_revenue_waterfall_union", """
-- L4: 4层嵌套 + UNION ALL + 子查询
-- L4 → L3(v_top_product_performance_dashboard) → L2 → L1
-- L4 → L2(v_inter_marketing_channel_roi)
-- 语法亮点: UNION ALL, 子查询 IN, 多层聚合
CREATE OR REPLACE VIEW dw.v_l4_exec_revenue_waterfall_union AS
SELECT 'PRODUCT' AS revenue_source, category AS source_name,
       SUM(total_revenue) AS revenue
FROM dw.v_top_product_performance_dashboard
GROUP BY category
UNION ALL
SELECT 'MARKETING' AS revenue_source, channel_name AS source_name,
       SUM(attributed_sales) AS revenue
FROM dw.v_inter_marketing_channel_roi
WHERE roi > 0
GROUP BY channel_name
UNION ALL
SELECT 'SUBSCRIPTION' AS revenue_source, plan_type AS source_name,
       SUM(mrr) AS revenue
FROM dw.v_inter_subscription_churn_risk
WHERE churn_risk < 0.5
GROUP BY plan_type;
""")

write("dw_v_l4_exec_churn_predictor_window", """
-- L4: 4层嵌套 + 窗口函数 LAG/OVER + 子查询
-- L4 → L3(v_top_customer_risk_segments) → L2 → L1
-- L4 → L2(v_inter_loyalty_tier_analysis)
-- 语法亮点: LAG(), SUM() OVER(), PARTITION BY, 同比/环比
CREATE OR REPLACE VIEW dw.v_l4_exec_churn_predictor_window AS
WITH ranked_churn AS (
    SELECT user_id, user_name, overall_risk, tier, points_balance,
           DENSE_RANK() OVER (PARTITION BY overall_risk ORDER BY points_balance DESC) AS risk_rank
    FROM dw.v_top_customer_risk_segments
),
churn_trend AS (
    SELECT tier, segment_name,
           year, quarter,
           member_count,
           LAG(member_count) OVER (PARTITION BY tier ORDER BY quarter) AS prev_quarter_members,
           member_count - LAG(member_count) OVER (PARTITION BY tier ORDER BY quarter) AS qoq_change
    FROM dw.v_inter_loyalty_tier_analysis
)
SELECT rc.user_id, rc.user_name, rc.overall_risk, rc.tier, rc.risk_rank,
       ct.quarter, ct.member_count, ct.qoq_change,
       CASE WHEN rc.overall_risk = 'HIGH RISK' AND ct.qoq_change < 0 THEN 'URGENT ACTION'
            ELSE 'MONITOR' END AS action_flag
FROM ranked_churn rc
JOIN churn_trend ct ON rc.tier = ct.tier;
""")

write("dw_v_l4_exec_inventory_restock_subquery", """
-- L4: 4层嵌套 + 子查询(EXISTS/IN) + HAVING
-- L4 → L3(v_top_product_performance_dashboard) → L2 → L1
-- L4 → L2(v_inter_inventory_alert)
-- 语法亮点: 子查询 IN, HAVING, CROSS JOIN, 多条件聚合
CREATE OR REPLACE VIEW dw.v_l4_exec_inventory_restock_subquery AS
SELECT ia.product_id, ia.product_name, ia.warehouse_name,
       ia.stock_qty, ia.stock_status,
       pd.performance_tier, pd.total_revenue,
       pp.avg_price_index,
       (ia.stock_qty * pp.avg_price_index) AS stock_value_index
FROM dw.v_inter_inventory_alert ia
JOIN dw.v_top_product_performance_dashboard pd ON ia.product_id = pd.product_id
CROSS JOIN (
    SELECT AVG(price_index) AS avg_price_index FROM dw.v_base_pricing_snapshot
) pp
WHERE ia.stock_status IN ('REORDER', 'LOW')
  AND pd.total_revenue > 5000
  AND EXISTS (
      SELECT 1 FROM dw.v_inter_marketing_channel_roi m
      WHERE m.conversions > 100
  )
HAVING ia.stock_qty < 50
ORDER BY pd.total_revenue DESC;
""")

write("dw_v_l4_exec_marketing_multitouch_attribution", """
-- L4: 4层嵌套 + 多窗口函数 + CTE + UNION
-- L4 → L3(v_top_marketing_attribution) → L2 → L1
-- L4 → L2(v_inter_web_session_quality)
-- L4 → L2(v_inter_loyalty_tier_analysis)
-- 语法亮点: 多个窗口函数 OVER(), RANK(), DENSE_RANK(), CTE, 多源 JOIN
CREATE OR REPLACE VIEW dw.v_l4_exec_marketing_multitouch_attribution AS
WITH attribution_base AS (
    SELECT ma.year, ma.month, ma.channel_name, ma.channel_type,
           ma.spend, ma.conversions, ma.roi,
           wsq.sessions, wsq.bounce_rate,
           lm.member_count,
           RANK() OVER (PARTITION BY ma.year, ma.channel_type ORDER BY ma.roi DESC) AS roi_rank,
           DENSE_RANK() OVER (PARTITION BY ma.year ORDER BY ma.spend DESC) AS spend_rank,
           SUM(ma.conversions) OVER (PARTITION BY ma.year) AS annual_conversions,
           SUM(ma.spend) OVER (PARTITION BY ma.year, ma.quarter) AS quarterly_spend
    FROM dw.v_top_marketing_attribution ma
    JOIN dw.v_inter_web_session_quality wsq ON ma.year = wsq.year AND ma.month = wsq.month
    JOIN dw.v_inter_loyalty_tier_analysis lm ON ma.year = lm.year AND ma.month = lm.month
)
SELECT year, month, channel_name, channel_type,
       spend, conversions, roi,
       sessions, bounce_rate, member_count,
       roi_rank, spend_rank, annual_conversions, quarterly_spend,
       CASE WHEN roi_rank = 1 THEN 'TOP PERFORMER'
            WHEN spend_rank = 1 THEN 'BIGGEST SPENDER'
            ELSE 'STANDARD' END AS channel_classification
FROM attribution_base
QUALIFY roi_rank <= 3;
""")

write("dw_v_l4_exec_cohort_retention_matrix", """
-- L4: 4层嵌套 + 复杂窗口 + CTE + 子查询
-- L4 → L3(v_top_customer_lifetime_value) → L2 → L1
-- L4 → L2(v_inter_loyalty_tier_analysis)
-- L4 → L1(v_base_payment_records)
-- 语法亮点: CTE, 窗口函数 NTILE, LAG, SUM OVER, 多表 UNION, QUALIFY
CREATE OR REPLACE VIEW dw.v_l4_exec_cohort_retention_matrix AS
WITH cohort_base AS (
    SELECT u.user_id, u.user_name,
           pd.paid_amount,
           lm.tier, lm.points_balance,
           NTILE(4) OVER (ORDER BY pd.paid_amount DESC) AS spend_quartile,
           ROW_NUMBER() OVER (PARTITION BY lm.tier ORDER BY pd.paid_amount DESC) AS tier_rn
    FROM dw.users_clean u
    JOIN dw.v_base_payment_records pd ON u.user_id = pd.user_id
    JOIN dw.v_base_loyalty_members lm ON u.user_id = lm.user_id
),
cohort_aggregation AS (
    SELECT tier, spend_quartile,
           COUNT(*) AS cohort_size,
           SUM(paid_amount) AS total_revenue,
           AVG(paid_amount) AS avg_revenue_per_user,
           LAG(SUM(paid_amount)) OVER (PARTITION BY tier ORDER BY spend_quartile) AS prev_quartile_revenue,
           SUM(paid_amount) - LAG(SUM(paid_amount)) OVER (PARTITION BY tier ORDER BY spend_quartile) AS revenue_delta
    FROM cohort_base
    GROUP BY tier, spend_quartile
),
final_output AS (
    SELECT tier, spend_quartile, cohort_size, total_revenue, avg_revenue_per_user,
           revenue_delta,
           CASE WHEN revenue_delta > 0 THEN 'IMPROVING'
                WHEN revenue_delta < 0 THEN 'DECLINING'
                ELSE 'STABLE' END AS trend
    FROM cohort_aggregation
)
SELECT * FROM final_output
UNION ALL
SELECT 'ALL' AS tier, spend_quartile, SUM(cohort_size), SUM(total_revenue),
       AVG(avg_revenue_per_user), SUM(revenue_delta),
       'AGGREGATE' AS trend
FROM final_output
GROUP BY spend_quartile;
""")

write("dw_v_l4_exec_product_affinity_analysis", """
-- L4: 4层嵌套 + CTE + 子查询 + 窗口函数 + UNION ALL
-- L4 → L3(v_top_product_performance_dashboard) → L2 → L1
-- L4 → L2(v_inter_customer_payment_behavior)
-- L4 → L1(v_base_order_items, v_base_product_reviews)
-- 语法亮点: CTE, 子查询(EXISTS/IN), 窗口函数 RANK, CROSS APPLY 概念
CREATE OR REPLACE VIEW dw.v_l4_exec_product_affinity_analysis AS
WITH product_metrics AS (
    SELECT oi.product_id,
           SUM(oi.quantity)                  AS total_units,
           SUM(oi.quantity * oi.unit_price)  AS total_revenue,
           COUNT(DISTINCT oi.order_id)       AS order_count,
           RANK() OVER (ORDER BY SUM(oi.quantity * oi.unit_price) DESC) AS revenue_rank
    FROM dw.v_base_order_items oi
    GROUP BY oi.product_id
),
review_signals AS (
    SELECT product_id,
           COUNT(*)         AS review_count,
           AVG(rating)      AS avg_rating,
           SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) AS positive_reviews
    FROM dw.v_base_product_reviews
    GROUP BY product_id
),
customer_overlap AS (
    SELECT oi1.product_id AS product_a, oi2.product_id AS product_b,
           COUNT(DISTINCT oi1.order_id) AS co_orders
    FROM dw.v_base_order_items oi1
    JOIN dw.v_base_order_items oi2 ON oi1.order_id = oi2.order_id AND oi1.product_id < oi2.product_id
    GROUP BY oi1.product_id, oi2.product_id
)
SELECT pd.product_name, pd.category, pd.supplier_name,
       pm.total_units, pm.total_revenue, pm.order_count, pm.revenue_rank,
       rs.avg_rating, rs.positive_reviews,
       co.co_orders,
       CASE WHEN rs.positive_reviews > 10 AND pm.revenue_rank <= 20 THEN 'HIGHLIGHT'
            WHEN rs.avg_rating >= 4.5 THEN 'TOP RATED'
            ELSE 'STANDARD' END AS product_tag
FROM dw.v_top_product_performance_dashboard pd
JOIN product_metrics pm ON pd.product_id = pm.product_id
JOIN review_signals rs ON pd.product_id = rs.product_id
LEFT JOIN customer_overlap co ON pd.product_id = co.product_a
WHERE pm.revenue_rank <= 50;
""")


# ══════════════════════════════════════════════════════════
# 补充层：更多视图补足到 50 个，覆盖不同业务场景
# ══════════════════════════════════════════════════════════

write("dw_v_finance_revenue_by_segment", """
-- L2: 引用 L2(v_inter_loyalty_tier_analysis) + L1(v_base_payment_records)
CREATE OR REPLACE VIEW dw.v_finance_revenue_by_segment AS
SELECT lt.tier, lt.segment_name, lt.year, lt.quarter,
       lt.member_count,
       SUM(pd.paid_amount) AS total_revenue
FROM dw.v_inter_loyalty_tier_analysis lt
LEFT JOIN dw.v_base_payment_records pd ON lt.member_count > 0
GROUP BY lt.tier, lt.segment_name, lt.year, lt.quarter, lt.member_count;
""")

write("dw_v_operations_warehouse_capacity", """
-- L2: 引用 L1(v_base_inventory_stock) + dim.warehouse_dim
CREATE OR REPLACE VIEW dw.v_operations_warehouse_capacity AS
SELECT inv.warehouse_name, inv.city,
       wd.capacity, wd.utilization_pct,
       SUM(inv.stock_qty) AS total_stock,
       wd.capacity - SUM(inv.stock_qty) AS remaining_capacity
FROM dw.v_base_inventory_stock inv
JOIN dim.warehouse_dim wd ON inv.warehouse_id = wd.warehouse_sk
GROUP BY inv.warehouse_name, inv.city, wd.capacity, wd.utilization_pct;
""")

write("dw_v_hr_employee_sales_performance", """
-- L2: 引用 L1(v_base_user_orders) + dw.users_clean
CREATE OR REPLACE VIEW dw.v_hr_employee_sales_performance AS
SELECT u.city,
       COUNT(DISTINCT uo.user_id) AS active_users,
       SUM(uo.total_amount)        AS total_gmv
FROM dw.v_base_user_orders uo
JOIN dw.users_clean u ON uo.user_id = u.user_id
GROUP BY u.city;
""")

write("dw_v_supply_supplier_scorecard", """
-- L2: 引用 L1(v_base_product_suppliers) + L1(v_base_order_items)
CREATE OR REPLACE VIEW dw.v_supply_supplier_scorecard AS
SELECT ps.supplier_id, ps.supplier_name, ps.country,
       ps.product_id, ps.product_name,
       SUM(oi.quantity)             AS total_ordered_qty,
       SUM(oi.quantity * oi.unit_price) AS total_order_value,
       RANK() OVER (PARTITION BY ps.supplier_id ORDER BY SUM(oi.quantity * oi.unit_price) DESC) AS value_rank
FROM dw.v_base_product_suppliers ps
JOIN dw.v_base_order_items oi ON ps.product_id = oi.product_id
GROUP BY ps.supplier_id, ps.supplier_name, ps.country, ps.product_id, ps.product_name;
""")

write("dw_v_analytics_conversion_funnel", """
-- L3: 3层嵌套: web_metrics + marketing + orders
CREATE OR REPLACE VIEW dw.v_analytics_conversion_funnel AS
SELECT wm.year, wm.month,
       SUM(wm.sessions)            AS sessions,
       SUM(ms.clicks)              AS clicks,
       SUM(ms.conversions)         AS conversions,
       SUM(COALESCE(uo.total_orders, 0)) AS orders_placed,
       ROUND(SUM(ms.conversions) * 100.0 / NULLIF(SUM(wm.sessions), 0), 2) AS session_to_click_rate,
       ROUND(SUM(uo.total_orders) * 100.0 / NULLIF(SUM(ms.conversions), 0), 2) AS click_to_order_rate
FROM dw.v_base_web_metrics wm
JOIN dw.v_base_marketing_spend ms ON wm.year = ms.year AND wm.month = ms.month
LEFT JOIN dw.v_inter_user_order_summary uo ON wm.year = uo.user_id
GROUP BY wm.year, wm.month;
""")

write("dw_v_analytics_weekly_trend_window", """
-- L3: 窗口函数: LAG, SUM OVER, ROW_NUMBER
CREATE OR REPLACE VIEW dw.v_analytics_weekly_trend_window AS
SELECT d.year, d.quarter,
       SUM(f.net_sales)                           AS weekly_revenue,
       LAG(SUM(f.net_sales)) OVER (PARTITION BY d.year ORDER BY d.quarter) AS prev_quarter_revenue,
       SUM(f.net_sales) - LAG(SUM(f.net_sales)) OVER (PARTITION BY d.year ORDER BY d.quarter) AS revenue_delta,
       SUM(SUM(f.net_sales)) OVER (PARTITION BY d.year ORDER BY d.quarter ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumm_revenue
FROM fact.sales_fact f
JOIN dim.date_dim d ON f.date_sk = d.date_sk
GROUP BY d.year, d.quarter;
""")

write("dw_v_analytics_product_pareto", """
-- L3: 帕累托分析
CREATE OR REPLACE VIEW dw.v_analytics_product_pareto AS
WITH ranked_products AS (
    SELECT p.product_name, p.category,
           SUM(oi.quantity * oi.unit_price) AS revenue,
           ROW_NUMBER() OVER (ORDER BY SUM(oi.quantity * oi.unit_price) DESC) AS rev_rank
    FROM dw.v_base_order_items oi
    JOIN dw.products_clean p ON oi.product_id = p.product_id
    GROUP BY p.product_name, p.category
)
SELECT rp.product_name, rp.category, rp.revenue, rp.rev_rank,
       ROUND(100.0 * rp.rev_rank / (SELECT COUNT(*) FROM ranked_products), 2) AS top_pct,
       CASE WHEN rp.rev_rank <= 20 THEN 'A'
            WHEN rp.rev_rank <= 50 THEN 'B'
            ELSE 'C' END AS pareto_class
FROM ranked_products rp
QUALIFY rp.rev_rank <= 30;
""")

write("dw_v_customer_repeat_purchase_analysis", """
-- L3: 重复购买分析
CREATE OR REPLACE VIEW dw.v_customer_repeat_purchase_analysis AS
SELECT u.user_id, u.user_name,
       COUNT(DISTINCT o.order_id)   AS order_count,
       SUM(o.total_amount)         AS lifetime_value,
       MAX(o.order_date) - MIN(o.order_date) AS customer_tenure_days,
       CASE WHEN COUNT(DISTINCT o.order_id) >= 5 THEN 'LOYAL'
            WHEN COUNT(DISTINCT o.order_id) >= 2 THEN 'REPEAT'
            ELSE 'ONE-TIME' END AS purchase_type
FROM dw.v_base_user_orders o
JOIN dw.users_clean u ON o.user_id = u.user_id
GROUP BY u.user_id, u.user_name;
""")

write("dw_v_channel_blended_roi", """
-- L3: 渠道综合 ROI
CREATE OR REPLACE VIEW dw.v_channel_blended_roi AS
SELECT ma.channel_name, ma.year,
       SUM(ma.total_spend)        AS spend,
       SUM(ma.conversions)        AS conversions,
       SUM(pd.total_paid)         AS attributed_revenue,
       CASE WHEN SUM(ma.total_spend) > 0
            THEN SUM(pd.total_paid) / SUM(ma.total_spend)
            ELSE 0 END            AS blended_roi
FROM dw.v_inter_marketing_channel_roi ma
CROSS JOIN dw.v_inter_customer_payment_behavior pd
GROUP BY ma.channel_name, ma.year;
""")

write("dw_v_returns_refund_rate", """
-- L2: 退货退款率分析
CREATE OR REPLACE VIEW dw.v_returns_refund_rate AS
SELECT oi.product_id, p.product_name, p.category,
       COUNT(DISTINCT oi.order_id)       AS total_orders,
       COUNT(DISTINCT r.refund_id)        AS refund_count,
       ROUND(COUNT(DISTINCT r.refund_id) * 100.0 / NULLIF(COUNT(DISTINCT oi.order_id), 0), 2) AS refund_rate_pct,
       SUM(r.refund_amount)              AS total_refund_amount
FROM dw.v_base_order_items oi
LEFT JOIN dw.v_base_refund_records r ON oi.order_item_id = r.order_item_id
JOIN dw.products_clean p ON oi.product_id = p.product_id
GROUP BY oi.product_id, p.product_name, p.category
HAVING COUNT(DISTINCT r.refund_id) > 0
ORDER BY refund_rate_pct DESC;
""")


# ══════════════════════════════════════════════════════════
# 再补充 8 个，确保总数 50+
# ══════════════════════════════════════════════════════════

write("dw_v_subscription_mrr_trend", """
-- L3: 订阅 MRR 趋势 + 窗口
CREATE OR REPLACE VIEW dw.v_subscription_mrr_trend AS
SELECT u.user_id, u.user_name,
       ss.subscription_id, ss.plan_type, ss.mrr,
       ss.churn_risk,
       LAG(ss.mrr) OVER (PARTITION BY ss.plan_type ORDER BY ss.subscription_id) AS prev_mrr,
       ss.mrr - LAG(ss.mrr) OVER (PARTITION BY ss.plan_type ORDER BY ss.subscription_id) AS mrr_delta
FROM dw.v_inter_subscription_churn_risk ss
JOIN dw.users_clean u ON ss.user_id = u.user_id;
""")

write("dw_v_pricing_elasticity_analysis", """
-- L4: 价格弹性分析，子查询 + 窗口
CREATE OR REPLACE VIEW dw.v_pricing_elasticity_analysis AS
WITH price_vol AS (
    SELECT product_id, AVG(base_price) AS avg_price, STDDEV(base_price) AS price_stddev
    FROM dw.v_base_pricing_snapshot
    GROUP BY product_id
    HAVING STDDEV(base_price) > 0
),
sales_vol AS (
    SELECT product_id, SUM(quantity_sold) AS total_qty_sold
    FROM dw.v_base_daily_sales_fact
    GROUP BY product_id
)
SELECT pv.product_id, ps.product_name, ps.category,
       pv.avg_price, pv.price_stddev,
       sv.total_qty_sold,
       CASE WHEN pv.price_stddev > 0 AND sv.total_qty_sold > 100 THEN 'ELASTIC'
            ELSE 'INELASTIC' END AS price_sensitivity
FROM price_vol pv
JOIN sales_vol sv ON pv.product_id = sv.product_id
JOIN dw.products_clean ps ON pv.product_id = ps.product_id;
""")

write("dw_v_shipping_carrier_comparison", """
-- L3: 承运商对比
CREATE OR REPLACE VIEW dw.v_shipping_carrier_comparison AS
SELECT sdp.carrier, sdp.year,
       sdp.total_shipments, sdp.delivered,
       ROUND(sdp.delivered * 100.0 / NULLIF(sdp.total_shipments, 0), 2) AS delivery_rate,
       sdp.avg_days_to_deliver,
       RANK() OVER (PARTITION BY sdp.year ORDER BY sdp.delivered * 1.0 / NULLIF(sdp.total_shipments, 0) DESC) AS carrier_rank
FROM dw.v_inter_shipment_delivery_perf sdp
QUALIFY carrier_rank <= 5;
""")

write("dw_v_loyalty_redemption_analysis", """
-- L3: 积分兑换分析
CREATE OR REPLACE VIEW dw.v_loyalty_redemption_analysis AS
SELECT tier, segment_name,
       SUM(points_earned)       AS total_earned,
       SUM(points_redeemed)     AS total_redeemed,
       SUM(points_balance)      AS total_balance,
       ROUND(SUM(points_redeemed) * 100.0 / NULLIF(SUM(points_earned), 0), 2) AS redemption_rate,
       DENSE_RANK() OVER (ORDER BY SUM(points_redeemed) DESC) AS redemption_rank
FROM dw.v_base_loyalty_members
GROUP BY tier, segment_name;
""")

write("dw_v_budget_variance_forecast", """
-- L3: 预算差异预测
CREATE OR REPLACE VIEW dw.v_budget_variance_forecast AS
SELECT b.year, b.month, b.product_name, b.category,
       b.budget_amount, b.actual_amount, b.variance,
       CASE WHEN b.variance < 0 THEN 'OVER BUDGET'
            WHEN b.variance > 0 THEN 'UNDER BUDGET'
            ELSE 'ON BUDGET' END AS budget_status,
       ABS(b.variance) / NULLIF(b.budget_amount, 0) AS variance_pct
FROM fact.budget_fact b
JOIN dim.product_dim pd ON b.product_sk = pd.product_sk
QUALIFY variance_pct > 0.05;
""")

write("dw_v_cross_channel_customer_journey", """
-- L4: 跨渠道客户旅程，子查询 + 窗口
CREATE OR REPLACE VIEW dw.v_cross_channel_customer_journey AS
WITH journey AS (
    SELECT user_id,
           channel_name, spend_amt, conversions,
           order_seq,
           LAG(channel_name) OVER (PARTITION BY user_id ORDER BY order_seq) AS prev_channel
    FROM (
        SELECT ms.user_id, ms.channel_name, ms.spend_amt, ms.conversions,
               ROW_NUMBER() OVER (PARTITION BY ms.user_id ORDER BY ms.year, ms.month) AS order_seq
        FROM dw.v_inter_marketing_channel_roi ms
    ) sub
)
SELECT user_id, prev_channel, channel_name,
       COUNT(*) AS touch_count,
       SUM(spend_amt) AS total_spend, SUM(conversions) AS total_conversions
FROM journey
WHERE prev_channel IS NOT NULL
GROUP BY user_id, prev_channel, channel_name;
""")

write("dw_v_product_lifecycle_stage", """
-- L3: 产品生命周期阶段
CREATE OR REPLACE VIEW dw.v_product_lifecycle_stage AS
SELECT ps.product_name, ps.category, ps.year, ps.month,
       ps.total_qty, ps.total_revenue,
       ia.stock_status,
       RANK() OVER (PARTITION BY ps.category ORDER BY ps.total_revenue DESC) AS category_rank,
       CASE WHEN ps.total_revenue > 50000 THEN 'GROWTH'
            WHEN ps.total_revenue > 10000 THEN 'MATURITY'
            ELSE 'INTRODUCTION' END AS lifecycle_stage
FROM dw.v_inter_product_sales_summary ps
JOIN dw.v_inter_inventory_alert ia ON ps.product_id = ia.product_id
QUALIFY category_rank <= 10;
""")

write("dw_v_executive_kpi_dashboard", """
-- L4: 高管 KPI 仪表板，4层 + CTE + 多个窗口
CREATE OR REPLACE VIEW dw.v_executive_kpi_dashboard AS
WITH kpi_finance AS (
    SELECT year, month,
           SUM(net_sales) AS total_revenue,
           LAG(SUM(net_sales)) OVER (ORDER BY year, month) AS prev_revenue,
           SUM(net_sales) - LAG(SUM(net_sales)) OVER (ORDER BY year, month) AS mom_delta
    FROM dw.v_base_daily_sales_fact
    GROUP BY year, month
),
kpi_marketing AS (
    SELECT year, month,
           SUM(spend_amt) AS total_spend, SUM(conversions) AS total_conversions
    FROM dw.v_base_marketing_spend
    GROUP BY year, month
),
kpi_loyalty AS (
    SELECT year, quarter,
           COUNT(DISTINCT user_id) AS members, SUM(points_redeemed) AS points_redeemed
    FROM dw.v_base_loyalty_members
    GROUP BY year, quarter
)
SELECT kf.year, kf.month,
       kf.total_revenue, kf.mom_delta,
       km.total_spend, km.total_conversions,
       kl.members, kl.points_redeemed,
       ROUND(kf.total_revenue / NULLIF(km.total_spend, 0), 2) AS revenue_per_dollar,
       ROUND(kf.total_revenue / NULLIF(kl.members, 0), 2) AS revenue_per_member
FROM kpi_finance kf
JOIN kpi_marketing km ON kf.year = km.year AND kf.month = km.month
JOIN kpi_loyalty kl ON kf.year = kl.year
QUALIFY kf.year = 2025;
""")

print(f"\n生成完成，共 {len(list(OUT_DIR.glob('*.sql')))} 个视图文件")
