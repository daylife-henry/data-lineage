"""
generate_multi_ref_views.py
生成高复杂度视图：每个视图同时引用【多个表 + 多个视图】
- 视图 ↔ 视图 多层交叉依赖
- 视图 ↔ 表 多路引用
- 强调"同一层内视图相互引用" + "跨越多层引用"
"""
from pathlib import Path

OUT_DIR = Path(__file__).parent / "sample_sql" / "git" / "views"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 基础表 ────────────────────────────────────────────────
TABLES = [
    "dw.users_clean", "dw.orders_clean", "dw.order_items_clean", "dw.products_clean",
    "dw.inventories_clean", "dw.warehouses_clean", "dw.suppliers_clean",
    "dw.payments_clean", "dw.shipments_clean", "dw.refunds_clean",
    "dw.reviews_clean", "dw.promotions_clean", "dw.carts_clean",
    "dw.product_suppliers", "dw.warehouse_products",
    "dim.date_dim", "dim.product_dim", "dim.customer_segment_dim",
    "dim.channel_dim", "dim.currency_dim", "dim.warehouse_dim",
    "dim.supplier_dim", "dim.shipping_method_dim", "dim.promo_dim",
    "fact.sales_fact", "fact.inventory_fact", "fact.marketing_fact",
    "fact.loyalty_fact", "fact.purchase_fact", "fact.return_fact",
    "fact.web_traffic_fact", "fact.subscription_fact",
    "fact.pricing_fact", "fact.budget_fact",
]


def write(name, sql):
    path = OUT_DIR / f"{name}.sql"
    path.write_text(sql, encoding="utf-8")
    print(f"  ✓ {name}")


# ══════════════════════════════════════════════════════════
# 阶段一：L1 — 基础层，同时引用 3~5 张表
# ══════════════════════════════════════════════════════════

# L1.1: users + orders + payments → 用户付款全貌
write("dw_l1_user_pay", """
CREATE OR REPLACE VIEW dw.dw_l1_user_pay AS
SELECT u.user_id, u.user_name, u.city, u.email,
       o.order_id, o.order_date, o.status, o.total_amount,
       p.payment_id, p.payment_method, p.amount AS paid_amount, p.status AS pay_status
FROM dw.users_clean u
JOIN dw.orders_clean o ON u.user_id = o.user_id
LEFT JOIN dw.payments_clean p ON o.order_id = p.order_id;
""")

# L1.2: orders + order_items + products + suppliers → 商品供应链
write("dw_l1_prod_scm", """
CREATE OR REPLACE VIEW dw.dw_l1_prod_scm AS
SELECT oi.order_item_id, oi.order_id, oi.product_id, oi.quantity, oi.unit_price,
       p.product_name, p.category, p.price,
       s.supplier_id, s.supplier_name, s.country
FROM dw.order_items_clean oi
JOIN dw.products_clean p ON oi.product_id = p.product_id
LEFT JOIN dw.product_suppliers ps ON p.product_id = ps.product_id
LEFT JOIN dw.suppliers_clean s ON ps.supplier_id = s.supplier_id;
""")

# L1.3: products + inventories + warehouses → 库存分布
write("dw_l1_inv_loc", """
CREATE OR REPLACE VIEW dw.dw_l1_inv_loc AS
SELECT p.product_id, p.product_name, p.category,
       w.warehouse_id, w.warehouse_name, w.city,
       wp.quantity AS stock_qty, wp.last_updated
FROM dw.products_clean p
JOIN dw.warehouse_products wp ON p.product_id = wp.product_id
JOIN dw.warehouses_clean w ON wp.warehouse_id = w.warehouse_id;
""")

# L1.4: orders + shipments + shipping_method → 物流状态
write("dw_l1_ship_track", """
CREATE OR REPLACE VIEW dw.dw_l1_ship_track AS
SELECT o.order_id, o.user_id, o.order_date,
       sh.shipment_id, sh.shipping_method_id,
       sm.method_name, sm.carrier, sh.ship_date, sh.delivery_date, sh.status AS ship_status
FROM dw.orders_clean o
JOIN dw.shipments_clean sh ON o.order_id = sh.order_id
JOIN dim.shipping_method_dim sm ON sh.shipping_method_id = sm.shipping_method_id;
""")

# L1.5: orders + refunds + order_items → 退款明细
write("dw_l1_refund_det", """
CREATE OR REPLACE VIEW dw.dw_l1_refund_det AS
SELECT o.order_id, o.user_id, o.order_date,
       r.refund_id, r.refund_amount, r.reason, r.refund_date,
       oi.order_item_id, oi.product_id, oi.quantity, oi.unit_price
FROM dw.orders_clean o
JOIN dw.refunds_clean r ON o.order_id = r.order_id
JOIN dw.order_items_clean oi ON r.order_item_id = oi.order_item_id;
""")

# L1.6: products + reviews + users → 产品口碑
write("dw_l1_prod_rvw", """
CREATE OR REPLACE VIEW dw.dw_l1_prod_rvw AS
SELECT p.product_id, p.product_name, p.category, p.price,
       rv.review_id, rv.user_id, rv.rating, rv.review_text, rv.created_at,
       u.user_name, u.city
FROM dw.products_clean p
JOIN dw.reviews_clean rv ON p.product_id = rv.product_id
JOIN dw.users_clean u ON rv.user_id = u.user_id;
""")

# L1.7: users + loyalty_fact + segment + date → 会员分析
write("dw_l1_member_ana", """
CREATE OR REPLACE VIEW dw.dw_l1_member_ana AS
SELECT u.user_id, u.user_name, u.city,
       l.tier, l.points_balance, l.points_earned, l.points_redeemed, l.enroll_date,
       cs.segment_name,
       d.year, d.month, d.quarter
FROM dw.users_clean u
JOIN fact.loyalty_fact l ON u.user_id = l.user_sk
JOIN dim.customer_segment_dim cs ON l.user_sk = cs.customer_sk
JOIN dim.date_dim d ON l.enroll_date = d.full_date;
""")

# L1.8: sales_fact + date_dim + product_dim → 销售事实
write("dw_l1_sales_fact", """
CREATE OR REPLACE VIEW dw.dw_l1_sales_fact AS
SELECT d.date_sk, d.full_date, d.year, d.month, d.quarter, d.week,
       pf.order_sk, pf.net_sales, pf.quantity_sold, pf.discount_amt,
       pd.product_id, pd.product_name, pd.category
FROM fact.sales_fact pf
JOIN dim.date_dim d ON pf.date_sk = d.date_sk
JOIN dim.product_dim pd ON pf.product_sk = pd.product_sk;
""")

# L1.9: marketing_fact + channel_dim + date_dim → 营销归因
write("dw_l1_mkt_attrib", """
CREATE OR REPLACE VIEW dw.dw_l1_mkt_attrib AS
SELECT d.year, d.month, d.quarter,
       c.channel_name, c.channel_type,
       m.spend_amt, m.impressions, m.clicks, m.conversions,
       m.roi_score, m.attributed_revenue
FROM fact.marketing_fact m
JOIN dim.channel_dim c ON m.channel_sk = c.channel_sk
JOIN dim.date_dim d ON m.date_sk = d.date_sk;
""")

# L1.10: web_traffic_fact + date_dim → 网站分析
write("dw_l1_web_ana", """
CREATE OR REPLACE VIEW dw.dw_l1_web_ana AS
SELECT d.full_date, d.month, d.year,
       t.session_id, t.user_id, t.page_views, t.sessions,
       t.bounce_rate, t.avg_session_duration, t.conversions AS web_conversions
FROM fact.web_traffic_fact t
JOIN dim.date_dim d ON t.date_sk = d.date_sk;
""")


# ══════════════════════════════════════════════════════════
# 阶段二：L2 — 中间层，同时引用【多张表 + 多视图】
#   视图互相引用，形成"同一层视图交叉依赖"
# ══════════════════════════════════════════════════════════

# L2.1: 用户分析视图，同时引用 L1_users_pay + L1_ship_track + L1_member_ana + users表
write("dw_l2_user_profile", """
-- 引用 3 个 L1 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l2_user_profile AS
SELECT up.user_id, up.user_name, up.city,
       up.total_amount AS total_order_amt, up.pay_status,
       st.ship_status, st.carrier, st.avg_delivery_days,
       ma.tier, ma.points_balance, ma.segment_name,
       u.email
FROM dw.dw_l1_user_pay up
JOIN dw.dw_l1_ship_track st ON up.user_id = st.user_id
JOIN dw.dw_l1_member_ana ma ON up.user_id = ma.user_id
JOIN dw.users_clean u ON up.user_id = u.user_id;
""")

# L2.2: 商品综合视图，同时引用 L1_prod_scm + L1_inv_loc + L1_prod_rvw + products表
write("dw_l2_prod_overview", """
-- 引用 3 个 L1 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l2_prod_overview AS
SELECT ps.product_id, ps.product_name, ps.category,
       ps.supplier_name, ps.country,
       il.stock_qty, il.warehouse_name,
       rv.avg_rating, rv.total_reviews,
       p.price, p.is_active
FROM dw.dw_l1_prod_scm ps
JOIN dw.dw_l1_inv_loc il ON ps.product_id = il.product_id
JOIN dw.dw_l1_prod_rvw rv ON ps.product_id = rv.product_id
JOIN dw.products_clean p ON ps.product_id = p.product_id;
""")

# L2.3: 渠道 ROI 综合，同时引用 L1_mkt_attrib + L1_web_ana + L1_sales_fact + channel_dim
write("dw_l2_channel_roi", """
-- 引用 3 个 L1 视图 + 1 张维度表
CREATE OR REPLACE VIEW dw.dw_l2_channel_roi AS
SELECT ma.channel_name, ma.channel_type,
       ma.year, ma.month,
       ma.spend_amt, ma.impressions, ma.clicks, ma.conversions, ma.attributed_revenue,
       wa.sessions, wa.page_views, wa.bounce_rate,
       sf.net_sales, sf.quantity_sold,
       c.cost_per_click, c.conversion_rate
FROM dw.dw_l1_mkt_attrib ma
JOIN dw.dw_l1_web_ana wa ON ma.year = wa.year AND ma.month = wa.month
JOIN dw.dw_l1_sales_fact sf ON ma.year = sf.year AND ma.month = sf.month
JOIN dim.channel_dim c ON ma.channel_name = c.channel_name;
""")

# L2.4: 会员价值视图，引用 L1_member_ana + L1_user_pay + loyalty_fact + customer_segment_dim
write("dw_l2_member_value", """
-- 引用 2 个 L1 视图 + 2 张表
CREATE OR REPLACE VIEW dw.dw_l2_member_value AS
SELECT ma.user_id, ma.user_name, ma.city,
       ma.tier, ma.points_balance, ma.points_earned, ma.points_redeemed,
       ma.segment_name,
       up.total_orders, up.total_amount AS lifetime_spend, up.pay_status,
       l.annual_points_limit, l.upgrade_threshold,
       cs.retention_rate, cs.avg_order_value
FROM dw.dw_l1_member_ana ma
JOIN dw.dw_l1_user_pay up ON ma.user_id = up.user_id
JOIN fact.loyalty_fact l ON ma.user_id = l.user_sk
JOIN dim.customer_segment_dim cs ON ma.user_id = cs.customer_sk;
""")

# L2.5: 物流绩效视图，引用 L1_ship_track + L1_user_pay + L1_refund_det + shipping_method_dim
write("dw_l2_ship_perf", """
-- 引用 3 个 L1 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l2_ship_perf AS
SELECT st.shipment_id, st.order_id, st.carrier, st.method_name,
       st.ship_date, st.delivery_date, st.ship_status,
       up.user_name, up.city, up.pay_status,
       rd.refund_amount, rd.reason,
       sm.avg_delivery_days AS target_days, sm.cost_per_shipment
FROM dw.dw_l1_ship_track st
JOIN dw.dw_l1_user_pay up ON st.user_id = up.user_id
JOIN dw.dw_l1_refund_det rd ON st.order_id = rd.order_id
JOIN dim.shipping_method_dim sm ON st.shipping_method_id = sm.shipping_method_id;
""")

# L2.6: 退款分析视图，引用 L1_refund_det + L1_prod_scm + L1_user_pay + refunds表
write("dw_l2_refund_ana", """
-- 引用 3 个 L1 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l2_refund_ana AS
SELECT rd.order_id, rd.refund_id, rd.refund_amount, rd.reason, rd.refund_date,
       rd.product_name, rd.category,
       rd.quantity AS refunded_qty, rd.unit_price,
       up.user_name, up.city, up.pay_status,
       r.is_disputed, r.refund_processing_days
FROM dw.dw_l1_refund_det rd
JOIN dw.dw_l1_prod_scm ps ON rd.product_id = ps.product_id
JOIN dw.dw_l1_user_pay up ON rd.user_id = up.user_id
JOIN dw.refunds_clean r ON rd.refund_id = r.refund_id;
""")

# L2.7: 产品评分趋势，引用 L1_prod_rvw + L1_sales_fact + L1_mkt_attrib + reviews表
write("dw_l2_prod_rating_trend", """
-- 引用 3 个 L1 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l2_prod_rating_trend AS
SELECT rv.product_id, rv.product_name, rv.category,
       rv.avg_rating, rv.total_reviews, rv.positive_pct,
       sf.total_revenue, sf.quantity_sold,
       ma.attributed_revenue, ma.roi_score,
       r.is_verified, r.last_review_date
FROM dw.dw_l1_prod_rvw rv
JOIN dw.dw_l1_sales_fact sf ON rv.product_id = sf.product_id
JOIN dw.dw_l1_mkt_attrib ma ON sf.year = ma.year AND sf.month = ma.month
JOIN dw.reviews_clean r ON rv.product_id = r.product_id;
""")

# L2.8: 实时销售看板，引用 L1_sales_fact + L1_mkt_attrib + L1_web_ana + date_dim
write("dw_l2_sales_realtime", """
-- 引用 3 个 L1 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l2_sales_realtime AS
SELECT d.full_date, d.year, d.month, d.quarter, d.day_of_week,
       sf.net_sales, sf.quantity_sold, sf.discount_amt,
       ma.spend_amt, ma.conversions, ma.attributed_revenue,
       wa.sessions, wa.page_views, wa.web_conversions,
       d.is_holiday, d.is_weekend
FROM dw.dw_l1_sales_fact sf
JOIN dw.dw_l1_mkt_attrib ma ON sf.year = ma.year AND sf.month = ma.month
JOIN dw.dw_l1_web_ana wa ON sf.year = wa.year AND sf.month = wa.month
JOIN dim.date_dim d ON sf.date_sk = d.date_sk;
""")


# ══════════════════════════════════════════════════════════
# 阶段三：L3 — 上层视图，跨层引用 + 同层交叉引用
#   同时引用 L2 视图 + L1 视图 + 表，3~5 个来源
# ══════════════════════════════════════════════════════════

# L3.1: 用户360视图，同时引用 4 个 L2 视图 + L1 视图 + 表
write("dw_l3_user360", """
-- 引用 4 个 L2 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l3_user360 AS
SELECT up.user_id, up.user_name, up.city, up.email,
       up.total_order_amt, up.pay_status,
       mp.tier, mp.points_balance, mp.lifetime_spend, mp.segment_name,
       cp.channel_name AS preferred_channel, cp.attributed_revenue AS channel_revenue,
       pp.stock_qty AS interested_product_stock,
       sf.net_sales AS purchase_volume
FROM dw.dw_l2_user_profile up
JOIN dw.dw_l2_member_value mp ON up.user_id = mp.user_id
JOIN dw.dw_l2_channel_roi cp ON up.city = cp.channel_type
JOIN dw.dw_l2_prod_overview pp ON up.user_id = pp.product_id
JOIN dw.dw_l1_sales_fact sf ON up.user_id = sf.product_id
JOIN dw.users_clean u ON up.user_id = u.user_id;
""")

# L3.2: 产品竞争力分析，引用 3 个 L2 视图 + 2 个 L1 视图 + 表
write("dw_l3_prod_competitiveness", """
-- 引用 3 个 L2 视图 + 2 张表
CREATE OR REPLACE VIEW dw.dw_l3_prod_competitiveness AS
SELECT po.product_id, po.product_name, po.category,
       po.supplier_name, po.stock_qty, po.avg_rating, po.price,
       cr.attributed_revenue AS mkt_revenue, cr.roi_score,
       prt.total_revenue AS sales_revenue, prt.quantity_sold,
       sf.net_sales AS fact_sales,
       p.competitor_avg_price, p.price_index
FROM dw.dw_l2_prod_overview po
JOIN dw.dw_l2_channel_roi cr ON po.category = cr.channel_type
JOIN dw.dw_l2_prod_rating_trend prt ON po.product_id = prt.product_id
JOIN dw.dw_l1_sales_fact sf ON po.product_id = sf.product_id
JOIN dw.products_clean p ON po.product_id = p.product_id;
""")

# L3.3: 营销效率评估，引用 4 个 L2 视图 + L1 视图 + 表
write("dw_l3_mkt_efficiency", """
-- 引用 4 个 L2 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l3_mkt_efficiency AS
SELECT cr.channel_name, cr.channel_type,
       cr.year, cr.month,
       cr.spend_amt, cr.impressions, cr.clicks, cr.conversions, cr.attributed_revenue,
       wa.sessions, wa.page_views, wa.bounce_rate,
       rt.total_revenue AS prod_revenue, rt.avg_rating,
       sf.net_sales, sf.quantity_sold,
       sp.refund_rate, sp.avg_delivery_days
FROM dw.dw_l2_channel_roi cr
JOIN dw.dw_l2_web_ana wa ON cr.year = wa.year AND cr.month = wa.month
JOIN dw.dw_l2_prod_rating_trend rt ON cr.channel_type = rt.category
JOIN dw.dw_l1_sales_fact sf ON cr.year = sf.year AND cr.month = sf.month
JOIN dw.dw_l2_ship_perf sp ON cr.channel_type = sp.method_name;
""")

# L3.4: 会员忠诚度健康度，引用 4 个 L2 视图 + L1 视图 + 表
write("dw_l3_loyalty_health", """
-- 引用 4 个 L2 视图 + 1 张表
CREATE OR REPLACE VIEW dw.dw_l3_loyalty_health AS
SELECT mv.user_id, mv.user_name, mv.tier, mv.points_balance,
       mv.points_earned, mv.points_redeemed, mv.segment_name, mv.lifetime_spend,
       up.pay_status, up.total_order_amt,
       sp.refund_rate, sp.avg_delivery_days, sp.carrier,
       cr.attributed_revenue AS channel_revenue,
       rt.positive_pct AS review_sentiment
FROM dw.dw_l2_member_value mv
JOIN dw.dw_l2_user_profile up ON mv.user_id = up.user_id
JOIN dw.dw_l2_ship_perf sp ON mv.user_id = sp.order_id
JOIN dw.dw_l2_channel_roi cr ON mv.segment_name = cr.channel_name
JOIN dw.dw_l2_prod_rating_trend rt ON mv.user_id = rt.product_id;
""")

# L3.5: 退款根因分析，引用 3 个 L2 视图 + 2 个 L1 视图 + 表
write("dw_l3_refund_root_cause", """
-- 引用 3 个 L2 视图 + 2 张表
CREATE OR REPLACE VIEW dw.dw_l3_refund_root_cause AS
SELECT ra.refund_id, ra.order_id, ra.refund_amount, ra.reason,
       ra.product_name, ra.category, ra.refunded_qty,
       ra.user_name, ra.city, ra.pay_status,
       pp.price, pp.avg_rating, pp.stock_qty,
       sp.ship_status, sp.carrier, sp.delivery_date,
       sf.discount_amt, sf.net_sales
FROM dw.dw_l2_refund_ana ra
JOIN dw.dw_l2_prod_overview pp ON ra.product_id = pp.product_id
JOIN dw.dw_l2_ship_perf sp ON ra.order_id = sp.order_id
JOIN dw.dw_l1_sales_fact sf ON ra.order_id = sf.order_sk
JOIN dw.refunds_clean r ON ra.refund_id = r.refund_id;
""")


# ══════════════════════════════════════════════════════════
# 阶段四：L4 — 深度嵌套，引用 5~6 个来源（混合 L3/L2/L1/表）
#   强调多视图交叉引用 + 复杂 SQL 语法
# ══════════════════════════════════════════════════════════

# L4.1: 执行层用户价值评分，引用 5 个 L2/L3 视图 + 3 张表
write("dw_l4_exec_user_value_score", """
-- 引用 3 个 L2 视图 + 2 张表 + CTE
CREATE OR REPLACE VIEW dw.dw_l4_exec_user_value_score AS
WITH score_base AS (
    SELECT up.user_id, up.user_name, up.city,
           up.total_order_amt, up.pay_status,
           mv.tier, mv.points_balance, mv.lifetime_spend, mv.segment_name,
           sf.net_sales, sf.quantity_sold, sf.discount_amt,
           sp.refund_rate, sp.carrier, sp.avg_delivery_days
    FROM dw.dw_l2_user_profile up
    JOIN dw.dw_l2_member_value mv ON up.user_id = mv.user_id
    JOIN dw.dw_l1_sales_fact sf ON up.user_id = sf.user_id
    JOIN dw.dw_l2_ship_perf sp ON up.order_id = sp.order_id
    JOIN dw.users_clean u ON up.user_id = u.user_id
    JOIN dim.customer_segment_dim cs ON up.user_id = cs.customer_sk
)
SELECT user_id, user_name, city,
       total_order_amt, tier, points_balance, lifetime_spend,
       net_sales, quantity_sold,
       refund_rate, avg_delivery_days,
       CASE WHEN lifetime_spent > 50000 AND refund_rate < 0.05 THEN 'PLATINUM'
            WHEN lifetime_spent > 10000 AND refund_rate < 0.1  THEN 'GOLD'
            WHEN refund_rate > 0.2 THEN 'AT_RISK'
            ELSE 'STANDARD' END AS value_tier
FROM score_base;
""")

# L4.2: 跨渠道归因漏斗，引用 5 个 L2/L3 视图 + 4 张表 + UNION ALL
write("dw_l4_exec_cross_channel_funnel", """
-- 引用 4 个 L2 视图 + 2 张表 + UNION ALL
CREATE OR REPLACE VIEW dw.dw_l4_exec_cross_channel_funnel AS
SELECT 'MARKETING' AS stage, cr.channel_name, cr.year, cr.month,
       cr.spend_amt AS input, cr.conversions AS output,
       ROUND(cr.attributed_revenue / NULLIF(cr.spend_amt, 0), 2) AS roas,
       cr.attributed_revenue
FROM dw.dw_l2_channel_roi cr
WHERE cr.attributed_revenue > 0
UNION ALL
SELECT 'WEB' AS stage, wa.month AS channel_name, wa.year, wa.month,
       wa.sessions AS input, wa.web_conversions AS output,
       ROUND(wa.web_conversions * 10 / NULLIF(wa.sessions, 0), 2) AS roas,
       wa.web_conversions * 50 AS attributed_revenue
FROM dw.dw_l2_sales_realtime wa
UNION ALL
SELECT 'MEMBER' AS stage, mv.tier AS channel_name, d.year, d.month,
       COUNT(*) AS input, SUM(up.pay_status) AS output,
       ROUND(SUM(up.total_order_amt) / COUNT(*), 2) AS roas,
       SUM(up.total_order_amt) AS attributed_revenue
FROM dw.dw_l2_member_value mv
JOIN dw.dw_l2_user_profile up ON mv.user_id = up.user_id
JOIN dim.date_dim d ON 1=1
GROUP BY mv.tier, d.year, d.month;
""")

# L4.3: 产品生命周期评分，引用 4 个 L2 视图 + 3 张表 + 窗口函数
write("dw_l4_exec_product_lifecycle", """
-- 引用 4 个 L2 视图 + 2 张表 + 窗口函数
CREATE OR REPLACE VIEW dw.dw_l4_exec_product_lifecycle AS
WITH plc_base AS (
    SELECT po.product_id, po.product_name, po.category,
           po.supplier_name, po.stock_qty, po.avg_rating, po.price,
           prt.total_revenue AS sales_rev, prt.quantity_sold, prt.positive_pct,
           cr.attributed_revenue AS mkt_rev, cr.roi_score,
           sf.net_sales, sf.discount_amt,
           ra.refund_rate, ra.refund_amount
    FROM dw.dw_l2_prod_overview po
    JOIN dw.dw_l2_prod_rating_trend prt ON po.product_id = prt.product_id
    JOIN dw.dw_l2_channel_roi cr ON po.category = cr.channel_type
    JOIN dw.dw_l1_sales_fact sf ON po.product_id = sf.product_id
    JOIN dw.dw_l2_refund_ana ra ON po.product_id = ra.product_id
    JOIN dw.products_clean p ON po.product_id = p.product_id
)
SELECT product_id, product_name, category,
       stock_qty, avg_rating, price,
       sales_rev, mkt_rev, roi_score, net_sales,
       refund_rate, refund_amount,
       ROW_NUMBER() OVER (PARTITION BY category ORDER BY sales_rev DESC) AS cat_rank,
       DENSE_RANK() OVER (ORDER BY roi_score DESC) AS roi_rank,
       CASE WHEN refund_rate > 0.2 OR stock_qty < 10 THEN 'END_OF_LIFE'
            WHEN roi_score > 5 AND sales_rev > 50000 THEN 'GROWTH'
            WHEN sales_rev > 10000 THEN 'MATURITY'
            ELSE 'INTRODUCTION' END AS lifecycle_stage
FROM plc_base;
""")

# L4.4: 退款风险预测，引用 5 个 L2 视图 + 4 张表 + 窗口 LAG
write("dw_l4_exec_refund_risk_predict", """
-- 引用 5 个 L2 视图 + 2 张表 + 窗口 LAG
CREATE OR REPLACE VIEW dw.dw_l4_exec_refund_risk_predict AS
WITH risk_base AS (
    SELECT up.user_id, up.user_name, up.city,
           up.total_order_amt, up.pay_status,
           mv.tier, mv.points_balance, mv.lifetime_spent,
           ra.refund_amount AS last_refund_amt, ra.refund_rate,
           sp.ship_status, sp.carrier, sp.avg_delivery_days,
           sf.discount_amt, sf.net_sales,
           cr.attributed_revenue,
           rt.positive_pct
    FROM dw.dw_l2_user_profile up
    JOIN dw.dw_l2_member_value mv ON up.user_id = mv.user_id
    JOIN dw.dw_l2_refund_ana ra ON up.user_id = ra.user_id
    JOIN dw.dw_l2_ship_perf sp ON up.order_id = sp.order_id
    JOIN dw.dw_l1_sales_fact sf ON up.user_id = sf.user_id
    JOIN dw.dw_l2_channel_roi cr ON up.city = cr.channel_type
    JOIN dw.dw_l2_prod_rating_trend rt ON up.user_id = rt.product_id
)
SELECT user_id, user_name, city,
       tier, points_balance, lifetime_spent,
       last_refund_amt, refund_rate,
       avg_delivery_days, ship_status, carrier,
       attributed_revenue, positive_pct,
       LAG(refund_rate) OVER (PARTITION BY tier ORDER BY lifetime_spent DESC) AS prev_refund_rate,
       CASE WHEN refund_rate > 0.3 THEN 'HIGH RISK'
            WHEN refund_rate > 0.15 THEN 'MEDIUM RISK'
            WHEN ship_status = 'DELAYED' THEN 'MONITOR'
            ELSE 'LOW RISK' END AS risk_label
FROM risk_base;
""")

# L4.5: 综合业务健康仪表板，引用 6 个视图 + 5 张表 + CTE + 多窗口
write("dw_l4_exec_biz_health_dashboard", """
-- 引用 5 个 L2/L3 视图 + 3 张表 + CTE + 多窗口函数
CREATE OR REPLACE VIEW dw.dw_l4_exec_biz_health_dashboard AS
WITH biz_kpi AS (
    SELECT d.year, d.month, d.quarter,
           SUM(sf.net_sales) AS total_revenue,
           SUM(sf.quantity_sold) AS total_units,
           SUM(sf.discount_amt) AS total_discount,
           SUM(mk.spend_amt) AS total_marketing_spend,
           SUM(mk.attributed_revenue) AS attributed_revenue,
           SUM(wa.sessions) AS total_sessions,
           SUM(wa.web_conversions) AS total_conversions,
           SUM(mv.points_redeemed) AS total_points_redeemed,
           COUNT(DISTINCT mv.user_id) AS active_members,
           AVG(sf.discount_amt / NULLIF(sf.net_sales, 0)) AS avg_discount_rate
    FROM dw.dw_l1_sales_fact sf
    JOIN dim.date_dim d ON sf.date_sk = d.date_sk
    JOIN dw.dw_l1_mkt_attrib mk ON sf.year = mk.year AND sf.month = mk.month
    JOIN dw.dw_l1_web_ana wa ON sf.year = wa.year AND sf.month = wa.month
    JOIN dw.dw_l1_member_ana mv ON sf.year = mv.year
    GROUP BY d.year, d.month, d.quarter
),
health_calc AS (
    SELECT year, month, quarter,
           total_revenue,
           LAG(total_revenue) OVER (ORDER BY year, month) AS prev_revenue,
           total_revenue - LAG(total_revenue) OVER (ORDER BY year, month) AS mom_delta,
           attributed_revenue / NULLIF(total_marketing_spend, 0) AS mkt_roi,
           total_conversions * 100.0 / NULLIF(total_sessions, 0) AS conversion_rate,
           active_members,
           total_points_redeemed,
           avg_discount_rate,
           ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rev_rank_in_quarter,
           DENSE_RANK() OVER (PARTITION BY year ORDER BY total_revenue DESC) AS rev_rank_in_year
    FROM biz_kpi
)
SELECT year, month, quarter,
       total_revenue, mom_delta, mkt_roi, conversion_rate,
       active_members, total_points_redeemed, avg_discount_rate,
       rev_rank_in_quarter, rev_rank_in_year,
       CASE WHEN mom_delta > 0 AND mkt_roi > 3 THEN 'EXCELLENT'
            WHEN mom_delta > 0 AND mkt_roi > 1 THEN 'GROWING'
            WHEN conversion_rate > 0.05 THEN 'EFFICIENT'
            WHEN avg_discount_rate > 0.2 THEN 'OVER_DISCOUNTED'
            ELSE 'NEEDS_REVIEW' END AS health_status
FROM health_calc;
""")


# ══════════════════════════════════════════════════════════
# 阶段五：交叉依赖强化层 — 视图互相引用，形成闭环
# ══════════════════════════════════════════════════════════

# L5.1: 引用 L4_exec_user_value_score + L3_user360 + L2_prod_overview + 表
write("dw_l5_vip_customer_journey", """
-- L5: 引用 L4 + L3 + L2 + 表，形成"4层深度依赖 + 同层交叉"
CREATE OR REPLACE VIEW dw.dw_l5_vip_customer_journey AS
SELECT uv.user_id, uv.user_name, uv.city, uv.value_tier,
       u360.tier, u360.points_balance, u360.lifetime_spend,
       u360.preferred_channel, u360.channel_revenue,
       po.product_name, po.category, po.price, po.avg_rating,
       po.stock_qty,
       sf.net_sales, sf.quantity_sold, sf.discount_amt,
       sp.ship_status, sp.carrier, sp.avg_delivery_days
FROM dw.dw_l4_exec_user_value_score uv
JOIN dw.dw_l3_user360 u360 ON uv.user_id = u360.user_id
JOIN dw.dw_l2_prod_overview po ON uv.user_id = po.product_id
JOIN dw.dw_l1_sales_fact sf ON uv.user_id = sf.user_id
JOIN dw.dw_l2_ship_perf sp ON uv.order_id = sp.order_id
JOIN dw.users_clean u ON uv.user_id = u.user_id
JOIN dim.customer_segment_dim cs ON uv.user_id = cs.customer_sk
WHERE uv.value_tier IN ('PLATINUM', 'GOLD');
""")

# L5.2: 引用 L4_exec_cross_channel_funnel + L3_mkt_efficiency + L2_channel_roi + 表
write("dw_l5_channel_attribution_graph", """
-- L5: 引用 L4 + L3 + L2 + 表，多渠道归因图谱
CREATE OR REPLACE VIEW dw.dw_l5_channel_attribution_graph AS
SELECT cf.stage, cf.channel_name, cf.year, cf.month,
       cf.input, cf.output, cf.roas, cf.attributed_revenue,
       me.spend_amt, me.conversions AS me_conversions, me.attributed_revenue AS me_attr_rev,
       cr.attributed_revenue AS cr_mkt_rev, cr.roi_score,
       wa.sessions, wa.page_views, wa.bounce_rate,
       sf.net_sales, sf.quantity_sold,
       d.quarter, d.is_holiday
FROM dw.dw_l4_exec_cross_channel_funnel cf
JOIN dw.dw_l3_mkt_efficiency me ON cf.channel_name = me.channel_name
JOIN dw.dw_l2_channel_roi cr ON cf.channel_name = cr.channel_name
JOIN dw.dw_l2_sales_realtime wa ON cf.year = wa.year AND cf.month = wa.month
JOIN dw.dw_l1_sales_fact sf ON cf.year = sf.year AND cf.month = sf.month
JOIN dim.date_dim d ON cf.year = d.year AND cf.month = d.month;
""")

# L5.3: 引用 L4_exec_product_lifecycle + L3_prod_competitiveness + L2_prod_overview + 表
write("dw_l5_prod_innovation_pipeline", """
-- L5: 产品创新漏斗，引用 L4 + L3 + L2 + 表
CREATE OR REPLACE VIEW dw.dw_l5_prod_innovation_pipeline AS
SELECT plc.product_id, plc.product_name, plc.category,
       plc.lifecycle_stage, plc.cat_rank, plc.roi_rank,
       plc.stock_qty, plc.avg_rating, plc.price,
       plc.sales_rev, plc.mkt_rev, plc.roi_score,
       plc.refund_rate,
       pc.competitor_avg_price, pc.price_index,
       po.supplier_name, po.stock_qty AS po_stock,
       sf.net_sales, sf.discount_amt,
       ma.attributed_revenue, ma.conversions
FROM dw.dw_l4_exec_product_lifecycle plc
JOIN dw.dw_l3_prod_competitiveness pc ON plc.product_id = pc.product_id
JOIN dw.dw_l2_prod_overview po ON plc.product_id = po.product_id
JOIN dw.dw_l1_sales_fact sf ON plc.product_id = sf.product_id
JOIN dw.dw_l1_mkt_attrib ma ON sf.year = ma.year AND sf.month = ma.month
JOIN dw.products_clean p ON plc.product_id = p.product_id
JOIN dim.product_dim pd ON plc.product_id = pd.product_id
WHERE plc.lifecycle_stage IN ('INTRODUCTION', 'GROWTH');
""")

# L5.4: 引用 L4_exec_refund_risk_predict + L3_refund_root_cause + L2_refund_ana + 表
write("dw_l5_refund_prevention_system", """
-- L5: 退款预防系统，引用 L4 + L3 + L2 + 表
CREATE OR REPLACE VIEW dw.dw_l5_refund_prevention_system AS
SELECT rp.user_id, rp.user_name, rp.city, rp.risk_label,
       rp.tier, rp.points_balance, rp.last_refund_amt, rp.refund_rate,
       rp.avg_delivery_days, rp.ship_status, rp.carrier,
       rp.attributed_revenue, rp.positive_pct,
       rc.refund_id, rc.refund_amount AS rc_refund_amt, rc.reason,
       rc.product_name, rc.category, rc.price, rc.avg_rating,
       ra.refund_rate AS ra_refund_rate, ra.refund_amount AS ra_total_refund,
       sf.net_sales, sf.quantity_sold, sf.discount_amt,
       po.stock_qty, po.supplier_name,
       u.email, u.city AS user_city
FROM dw.dw_l4_exec_refund_risk_predict rp
JOIN dw.dw_l3_refund_root_cause rc ON rp.user_id = rc.user_id
JOIN dw.dw_l2_refund_ana ra ON rp.user_id = ra.user_id
JOIN dw.dw_l1_sales_fact sf ON rp.user_id = sf.user_id
JOIN dw.dw_l2_prod_overview po ON rp.user_id = po.product_id
JOIN dw.users_clean u ON rp.user_id = u.user_id
JOIN dw.refunds_clean r ON rc.refund_id = r.refund_id
WHERE rp.risk_label IN ('HIGH RISK', 'MEDIUM RISK');
""")

# L5.5: 引用 L4_exec_biz_health_dashboard + L3_loyalty_health + L2_member_value + 表
write("dw_l5_exec_strategic_dashboard", """
-- L5: 执行层战略仪表板，引用 L4 + L3 + L2 + 表，综合最高层级
CREATE OR REPLACE VIEW dw.dw_l5_exec_strategic_dashboard AS
WITH strategic_base AS (
    SELECT bh.year, bh.month, bh.quarter,
           bh.total_revenue, bh.mom_delta, bh.mkt_roi, bh.conversion_rate,
           bh.active_members, bh.total_points_redeemed, bh.avg_discount_rate,
           bh.health_status,
           lh.user_id, lh.user_name, lh.tier, lh.points_balance,
           lh.lifetime_spent, lh.segment_name,
           lh.pay_status, lh.channel_revenue,
           mv.refund_rate AS mv_refund_rate, mv.avg_delivery_days,
           mv.carrier,
           sf.net_sales AS sf_revenue, sf.quantity_sold,
           cr.attributed_revenue AS mkt_rev, cr.roi_score,
           wa.sessions, wa.page_views, wa.bounce_rate
    FROM dw.dw_l4_exec_biz_health_dashboard bh
    JOIN dw.dw_l3_loyalty_health lh ON bh.year = lh.user_id
    JOIN dw.dw_l2_member_value mv ON lh.user_id = mv.user_id
    JOIN dw.dw_l1_sales_fact sf ON lh.user_id = sf.user_id
    JOIN dw.dw_l2_channel_roi cr ON lh.segment_name = cr.channel_name
    JOIN dw.dw_l1_web_ana wa ON sf.year = wa.year AND sf.month = wa.month
    JOIN dw.users_clean u ON lh.user_id = u.user_id
    JOIN dim.customer_segment_dim cs ON lh.user_id = cs.customer_sk
)
SELECT year, month, quarter,
       total_revenue, mom_delta, mkt_roi, conversion_rate,
       active_members, total_points_redeemed, avg_discount_rate,
       health_status,
       tier, points_balance, lifetime_spent, segment_name,
       mv_refund_rate, avg_delivery_days, carrier,
       sf_revenue, mkt_rev, roi_score,
       sessions, page_views, bounce_rate,
       DENSE_RANK() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS quarter_rev_rank,
       CASE WHEN health_status = 'EXCELLENT' AND mv_refund_rate < 0.05 THEN 'STRATEGIC_INVEST'
            WHEN health_status = 'GROWING' AND roi_score > 2 THEN 'EXPAND'
            WHEN mv_refund_rate > 0.2 THEN 'FIX_REFUND'
            ELSE 'MONITOR' END AS action_priority
FROM strategic_base;
""")


print(f"\n生成完成，共 {len(list(OUT_DIR.glob('*.sql')))} 个视图文件")
print("每个视图同时引用【多个表 + 多个视图】，形成复杂交叉依赖网络")
