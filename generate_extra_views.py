"""
generate_extra_views.py
补充 10 个视图，强调视图与视图之间的多层交叉引用：
- 视图A → 表(X,Y,Z) + 视图(B,C)
- 视图B → 表(P,Q) + 视图(D)
- 视图D → 视图(E,F)
- 形成 3 层以上的引用网络
"""
from pathlib import Path

OUT_DIR = Path(__file__).parent / "sample_sql" / "git" / "views"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def write(name, sql):
    path = OUT_DIR / f"{name}.sql"
    path.write_text(sql, encoding="utf-8")
    print(f"  ✓ {name}")


# ══════════════════════════════════════════════════════════════
# 引用网络说明（以 star_ / cross_ 开头的视图形成交叉引用网）：
#
#   cross_v_agg_orders ──────┐
#       ↑ L2                 │ 同时被 cross_v_exec_revenue_consolidated 引用
#   cross_v_agg_marketing ───┼→ cross_v_exec_revenue_consolidated (L3)
#       ↑ L2                 │
#   cross_v_agg_inventory ───┘       ↓ cross_v_exec_kpi_alliance 调用
#
#   cross_v_exec_revenue_consolidated (L3)
#       ├── L2: cross_v_agg_orders
#       ├── L2: cross_v_agg_marketing
#       └── L1: v_base_payment_records
#
#   cross_v_exec_kpi_alliance (L4)
#       ├── L3: cross_v_exec_revenue_consolidated
#       ├── L2: cross_v_agg_inventory
#       └── L1: v_base_loyalty_members
#
#   cross_v_channel_blended (L2)
#       ├── L1: v_base_marketing_spend
#       └── L1: v_base_web_metrics
#
#   cross_v_exec_funnel_analysis (L4)
#       ├── L3: cross_v_agg_orders
#       ├── L2: cross_v_channel_blended
#       └── L1: v_base_user_orders
#
#   cross_v_customer360_nested (L4)
#       ├── L3: cross_v_exec_revenue_consolidated
#       ├── L2: cross_v_agg_inventory
#       └── L1: v_base_loyalty_members
#
# ══════════════════════════════════════════════════════════════

# ── L1 辅助视图（已有 v_base_* 系列，但新增 cross_ 系列专用视图）────────

write("cross_v_agg_orders", """
-- L2: 汇总订单与支付
-- 依赖: L1(v_base_user_orders, v_base_payment_records)
-- 被: L3(cross_v_exec_revenue_consolidated), L3(cross_v_exec_funnel_analysis)
CREATE OR REPLACE VIEW dw.cross_v_agg_orders AS
SELECT o.user_id, o.order_id, o.order_date, o.status,
       o.total_amount,
       p.paid_amount, p.pay_status,
       CASE WHEN p.paid_amount >= o.total_amount THEN 'PAID'
            WHEN p.paid_amount > 0                THEN 'PARTIAL'
            ELSE 'UNPAID' END AS payment_status,
       COALESCE(p.paid_amount, 0) / NULLIF(o.total_amount, 0) AS payment_ratio
FROM dw.v_base_user_orders o
LEFT JOIN dw.v_base_payment_records p ON o.order_id = p.order_id;
""")

write("cross_v_agg_marketing", """
-- L2: 营销渠道汇总
-- 依赖: L1(v_base_marketing_spend)
-- 被: L3(cross_v_exec_revenue_consolidated)
CREATE OR REPLACE VIEW dw.cross_v_agg_marketing AS
SELECT channel_name, channel_type, year, month,
       SUM(spend_amt)       AS total_spend,
       SUM(impressions)     AS total_impressions,
       SUM(clicks)          AS total_clicks,
       SUM(conversions)     AS total_conversions,
       SUM(spend_amt) / NULLIF(SUM(conversions), 0) AS cpa,
       SUM(clicks) * 1.0 / NULLIF(SUM(impressions), 0) AS ctr
FROM dw.v_base_marketing_spend
GROUP BY channel_name, channel_type, year, month;
""")

write("cross_v_agg_inventory", """
-- L2: 库存汇总
-- 依赖: L1(v_base_inventory_stock)
-- 被: L3(cross_v_customer360_nested), L4(cross_v_exec_kpi_alliance)
CREATE OR REPLACE VIEW dw.cross_v_agg_inventory AS
SELECT product_id, product_name,
       COUNT(DISTINCT warehouse_name) AS warehouse_count,
       SUM(stock_qty)     AS total_stock,
       MAX(stock_qty)     AS max_single_warehouse_stock,
       MIN(stock_qty)     AS min_single_warehouse_stock,
       AVG(stock_qty)     AS avg_stock_per_warehouse
FROM dw.v_base_inventory_stock
GROUP BY product_id, product_name;
""")

write("cross_v_agg_loyalty", """
-- L2: 会员积分汇总
-- 依赖: L1(v_base_loyalty_members)
-- 被: L3(cross_v_exec_revenue_consolidated), L4(cross_v_customer360_nested)
CREATE OR REPLACE VIEW dw.cross_v_agg_loyalty AS
SELECT tier, segment_name,
       COUNT(DISTINCT user_id)         AS member_count,
       SUM(points_earned)             AS total_points_earned,
       SUM(points_redeemed)           AS total_points_redeemed,
       SUM(points_balance)            AS total_points_balance,
       AVG(points_balance)            AS avg_points_balance,
       ROUND(SUM(points_redeemed) * 100.0 / NULLIF(SUM(points_earned), 0), 2) AS redemption_rate
FROM dw.v_base_loyalty_members
GROUP BY tier, segment_name;
""")

write("cross_v_channel_blended", """
-- L2: 渠道综合 ROI + 跨引用营销+网站数据
-- 依赖: L1(v_base_marketing_spend, v_base_web_metrics)
-- 被: L4(cross_v_exec_funnel_analysis)
CREATE OR REPLACE VIEW dw.cross_v_channel_blended AS
SELECT ms.year, ms.month, ms.channel_name, ms.channel_type,
       ms.total_spend, ms.total_conversions,
       ms.total_clicks, ms.total_impressions,
       ms.cpa, ms.ctr,
       wm.total_sessions, wm.avg_bounce_rate,
       ROUND(ms.total_conversions * 100.0 / NULLIF(wm.total_sessions, 0), 2) AS conv_rate_per_session
FROM dw.cross_v_agg_marketing ms
LEFT JOIN dw.v_base_web_metrics wm ON ms.year = wm.year AND ms.month = wm.month;
""")

write("cross_v_product_affinity", """
-- L2: 商品关联分析
-- 依赖: L1(v_base_order_items, v_base_product_reviews)
-- 被: L3(cross_v_exec_product_intelligence)
CREATE OR REPLACE VIEW dw.cross_v_product_affinity AS
SELECT oi.product_id,
       COUNT(DISTINCT oi.order_id)       AS order_count,
       SUM(oi.quantity * oi.unit_price) AS total_revenue,
       COUNT(DISTINCT r.user_id)        AS reviewer_count,
       AVG(r.rating)                    AS avg_rating
FROM dw.v_base_order_items oi
LEFT JOIN dw.v_base_product_reviews r ON oi.product_id = r.product_id
GROUP BY oi.product_id;
""")


# ── L3 ────────────────────────────────────────────────────────

write("cross_v_exec_revenue_consolidated", """
-- L3: 整合收入视图，同时引用 3 个 L2 视图 + L1 表
-- 依赖: L2(cross_v_agg_orders, cross_v_agg_marketing, cross_v_agg_loyalty)
--       L1(v_base_payment_records)
-- 被: L4(cross_v_customer360_nested), L4(cross_v_exec_kpi_alliance)
CREATE OR REPLACE VIEW dw.cross_v_exec_revenue_consolidated AS
SELECT co.year, co.month,
       SUM(co.total_amount)         AS total_gmv,
       SUM(co.paid_amount)          AS total_paid,
       SUM(co.total_amount) - SUM(co.paid_amount) AS unpaid_amount,
       cm.total_spend               AS marketing_spend,
       cm.total_conversions         AS marketing_conversions,
       cm.cpa                       AS cost_per_acquisition,
       cl.member_count              AS active_members,
       cl.total_points_redeemed     AS points_redeemed,
       ROUND(SUM(co.paid_amount) / NULLIF(cl.member_count, 0), 2) AS revenue_per_member,
       CASE WHEN SUM(co.paid_amount) > SUM(cm.total_spend) THEN 'PROFITABLE'
            ELSE 'LOSS' END         AS profit_status
FROM dw.cross_v_agg_orders       co
JOIN dw.cross_v_agg_marketing    cm ON co.year = cm.year AND co.month = cm.month
JOIN dw.cross_v_agg_loyalty      cl ON 1=1
GROUP BY co.year, co.month, cm.total_spend, cm.total_conversions, cm.cpa,
         cl.member_count, cl.total_points_redeemed;
""")

write("cross_v_exec_product_intelligence", """
-- L3: 商品智能分析，同时引用 3 个 L2 视图 + L2(v_base_product_suppliers)
-- 依赖: L2(cross_v_product_affinity, cross_v_agg_inventory, cross_v_agg_orders)
--       L1(v_base_product_suppliers)
-- 被: L4(cross_v_exec_kpi_alliance)
CREATE OR REPLACE VIEW dw.cross_v_exec_product_intelligence AS
SELECT ps.product_id, ps.product_name, ps.category,
       ps.supplier_name, ps.country,
       pa.order_count, pa.total_revenue, pa.avg_rating,
       ai.total_stock, ai.warehouse_count,
       ao.paid_amount    AS total_product_revenue,
       RANK() OVER (PARTITION BY ps.category ORDER BY pa.total_revenue DESC) AS category_revenue_rank,
       CASE WHEN ai.total_stock > 0 AND pa.total_revenue / ai.total_stock > 500 THEN 'HIGH TURNS'
            WHEN pa.avg_rating >= 4.5 THEN 'TOP RATED'
            WHEN ai.total_stock < 10 THEN 'LOW STOCK RISK'
            ELSE 'STANDARD' END AS product_flag
FROM dw.v_base_product_suppliers  ps
JOIN dw.cross_v_product_affinity  pa  ON ps.product_id = pa.product_id
JOIN dw.cross_v_agg_inventory     ai  ON ps.product_id = ai.product_id
LEFT JOIN dw.cross_v_agg_orders   ao  ON ps.product_id = ao.order_id
GROUP BY ps.product_id, ps.product_name, ps.category, ps.supplier_name, ps.country,
         pa.order_count, pa.total_revenue, pa.avg_rating,
         ai.total_stock, ai.warehouse_count, ao.paid_amount;
""")


# ── L4 ────────────────────────────────────────────────────────

write("cross_v_exec_funnel_analysis", """
-- L4: 完整转化漏斗，同时引用 L3 + L2 + L1 三层
-- 依赖: L3(cross_v_exec_revenue_consolidated)
--       L2(cross_v_channel_blended)
--       L1(v_base_user_orders)
CREATE OR REPLACE VIEW dw.cross_v_exec_funnel_analysis AS
SELECT rc.year, rc.month,
       rc.total_gmv, rc.total_paid, rc.unpaid_amount,
       cb.total_sessions, cb.total_clicks, cb.total_conversions,
       cb.conv_rate_per_session,
       uo.user_id,
       COUNT(DISTINCT uo.order_id)   AS user_order_count,
       SUM(uo.total_amount)          AS user_gmv,
       MAX(rc.total_gmv)             OVER (PARTITION BY rc.year) AS annual_gmv,
       ROUND(MAX(rc.total_gmv) * 100.0 / NULLIF(SUM(cb.total_sessions), 0), 4) AS revenue_per_1000_sessions
FROM dw.cross_v_exec_revenue_consolidated rc
JOIN dw.cross_v_channel_blended cb ON rc.year = cb.year AND rc.month = cb.month
LEFT JOIN dw.v_base_user_orders uo ON rc.year = uo.order_id
GROUP BY rc.year, rc.month, rc.total_gmv, rc.total_paid, rc.unpaid_amount,
         cb.total_sessions, cb.total_clicks, cb.total_conversions,
         cb.conv_rate_per_session, uo.user_id;
""")

write("cross_v_customer360_nested", """
-- L4: 最深嵌套客户360，同时引用 L3 + L2 + L1 + L2
-- 依赖: L3(cross_v_exec_revenue_consolidated)
--       L2(cross_v_agg_inventory, cross_v_agg_loyalty)
--       L1(v_base_loyalty_members)
CREATE OR REPLACE VIEW dw.cross_v_customer360_nested AS
WITH customer_finance AS (
    SELECT user_id,
           SUM(total_amount)  AS lifetime_gmv,
           SUM(paid_amount)   AS lifetime_paid,
           COUNT(order_id)    AS lifetime_orders,
           MAX(order_date)   AS last_order_date,
           DENSE_RANK() OVER (ORDER BY SUM(paid_amount) DESC) AS gmv_rank
    FROM dw.cross_v_agg_orders
    GROUP BY user_id
),
customer_inventory_affinity AS (
    SELECT u.user_id, u.user_name,
           SUM(ai.total_stock * COALESCE(cf.lifetime_gmv, 0)) AS inventory_value_affinity
    FROM dw.users_clean u
    CROSS JOIN dw.cross_v_agg_inventory ai
    LEFT JOIN customer_finance cf ON u.user_id = cf.user_id
    GROUP BY u.user_id, u.user_name
)
SELECT cf.user_id,
       cf.lifetime_gmv, cf.lifetime_paid, cf.lifetime_orders,
       cf.last_order_date, cf.gmv_rank,
       cl.tier, cl.segment_name, cl.redemption_rate,
       rc.marketing_spend, rc.marketing_conversions, rc.revenue_per_member,
       cia.inventory_value_affinity,
       CASE WHEN cf.lifetime_orders >= 10 AND cl.tier = 'GOLD' THEN 'VIP ELITE'
            WHEN cf.lifetime_orders >= 5  AND cl.tier IN ('GOLD','SILVER') THEN 'LOYAL'
            WHEN cl.redemption_rate >= 30 THEN 'ACTIVE REDEEMER'
            WHEN cia.inventory_value_affinity > 1000000 THEN 'HIGH VALUE'
            ELSE 'STANDARD' END AS customer_segment_tag
FROM customer_finance cf
JOIN dw.cross_v_agg_loyalty cl ON 1=1
JOIN dw.cross_v_exec_revenue_consolidated rc ON cf.lifetime_gmv > 0
JOIN dw.v_base_loyalty_members lm ON cf.user_id = lm.user_id
JOIN customer_inventory_affinity cia ON cf.user_id = cia.user_id
QUALIFY cf.gmv_rank <= 1000;
""")

write("cross_v_exec_kpi_alliance", """
-- L4: KPI 联盟视图，引用 2 个 L3 + 2 个 L2 + L1
-- 依赖: L3(cross_v_exec_revenue_consolidated, cross_v_exec_product_intelligence)
--       L2(cross_v_channel_blended, cross_v_agg_inventory)
--       L1(v_base_loyalty_members)
-- 语法亮点: 多源 L3 视图交叉, 窗口函数, CASE WHEN
CREATE OR REPLACE VIEW dw.cross_v_exec_kpi_alliance AS
WITH revenue_kpi AS (
    SELECT year, month,
           total_gmv, total_paid, unpaid_amount,
           marketing_spend, marketing_conversions,
           revenue_per_member, profit_status,
           ROW_NUMBER() OVER (PARTITION BY year ORDER BY total_gmv DESC) AS best_month_rank,
           LAG(total_gmv) OVER (PARTITION BY year ORDER BY month) AS prev_month_gmv
    FROM dw.cross_v_exec_revenue_consolidated
),
product_kpi AS (
    SELECT category,
           SUM(total_revenue)       AS category_revenue,
           AVG(avg_rating)          AS avg_category_rating,
           COUNT(*)                 AS product_count
    FROM dw.cross_v_exec_product_intelligence
    GROUP BY category
),
marketing_kpi AS (
    SELECT year, month, channel_name,
           total_spend, total_conversions, conv_rate_per_session,
           RANK() OVER (PARTITION BY year ORDER BY total_conversions DESC) AS top_channel_rank
    FROM dw.cross_v_channel_blended
),
loyalty_kpi AS (
    SELECT tier,
           SUM(member_count)    AS tier_members,
           SUM(total_points_redeemed) AS tier_points_redeemed
    FROM dw.cross_v_agg_loyalty
    GROUP BY tier
)
SELECT rk.year, rk.month,
       rk.total_gmv, rk.total_paid,
       rk.marketing_spend, rk.marketing_conversions, rk.revenue_per_member, rk.profit_status,
       rk.best_month_rank, rk.prev_month_gmv,
       rk.total_gmv - rk.prev_month_gmv AS mom_growth,
       pk.category, pk.category_revenue, pk.avg_category_rating,
       mk.channel_name AS top_channel, mk.total_conversions AS top_channel_conversions,
       lk.tier_members, lk.tier_points_redeemed,
       (rk.total_gmv / NULLIF(rk.marketing_spend, 0)) AS roi,
       CASE WHEN rk.profit_status = 'PROFITABLE' AND rk.best_month_rank = 1 THEN 'TOP MONTH'
            WHEN pk.avg_category_rating >= 4.5 THEN 'HIGH QUALITY PORTFOLIO'
            ELSE 'STANDARD' END AS overall_kpi_flag
FROM revenue_kpi rk
CROSS JOIN product_kpi pk
JOIN marketing_kpi mk ON rk.year = mk.year AND mk.top_channel_rank = 1
JOIN loyalty_kpi lk ON 1=1
QUALIFY rk.year = 2025 AND rk.best_month_rank <= 3;
""")

print(f"\n生成完成，views 目录现有 {len(list(OUT_DIR.glob('*.sql')))} 个视图文件")
