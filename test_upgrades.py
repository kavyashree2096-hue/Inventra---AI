import json
import unittest
from app import create_app
from models import (
    db, User, Product, Category, Sale, SaleItem, AuditLog,
    AuditSession, AuditSessionItem, PurchaseOrder, InventoryItem
)

class InventraAiUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Get admin token for role_required endpoints
        admin = User.query.filter_by(role='Admin').first()
        self.assertIsNotNone(admin, "Admin user must exist")
        res = self.client.post('/api/auth/login', json={
            'email': admin.email,
            'password': 'admin123'
        })
        data = res.get_json()
        self.token = data.get('token') or data.get('access_token')
        self.headers = {'Authorization': f"Bearer {self.token}"}

    def tearDown(self):
        self.app_context.pop()

    def test_01_health_check(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'healthy')
        print("PASS: Health check verified")

    def test_02_procurement_hub_endpoints(self):
        # 1. Summary
        res = self.client.get('/api/procurement/summary')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('total_products', data)
        self.assertIn('products_requiring_reorder', data)
        self.assertIn('estimated_procurement_cost', data)
        print(f"PASS: Procurement Summary (Total: {data['total_products']}, Reorder: {data['products_requiring_reorder']}, Est Cost: INR {data['estimated_procurement_cost']})")

        # 2. Category-wise products
        res = self.client.get('/api/procurement/products?category_id=1&sort_by=stock&order=asc')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('products', data)
        self.assertGreater(len(data['products']), 0)
        p = data['products'][0]
        self.assertIn('suggested_quantity', p)
        self.assertIn('estimated_cost', p)
        self.assertIn('procurement_status', p)
        print(f"PASS: Procurement Category Products (Returned {len(data['products'])} items for category 1, sample suggested qty: {p['suggested_quantity']})")

        # 3. Charts
        res = self.client.get('/api/procurement/charts')
        self.assertEqual(res.status_code, 200)
        c_data = res.get_json()
        self.assertIn('reorder_by_category', c_data)
        self.assertIn('stock_vs_target', c_data)
        self.assertIn('requests_by_status', c_data)
        self.assertIn('cost_by_category', c_data)
        self.assertIn('highest_replenishment', c_data)
        print("PASS: Procurement Charts (5/5 interactive chart datasets returned)")

        # 4. CSV Export
        res = self.client.get('/api/procurement/export', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Product SKU', res.data)
        print("PASS: Procurement CSV Export verified")

    def test_03_global_search_endpoints(self):
        # Search by product name
        res = self.client.get('/api/search?q=Headphones')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(data['total_matches'], 0)
        self.assertIn('products', data['results'])
        print(f"PASS: Global Search for 'Headphones' ({data['total_matches']} total matches across catalog)")

        # Search by SKU
        res = self.client.get('/api/search?q=SKU-TECH-001')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(len(data['results']['products']), 0)
        print(f"PASS: Global Search by SKU ({data['results']['products'][0]['title']})")

        # Search by category
        res = self.client.get('/api/search?q=Electronics')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(data['total_matches'], 0)
        print("PASS: Global Search for category keyword verified")

    def test_04_audit_operations_endpoints(self):
        # 1. Summary
        res = self.client.get('/api/audit/summary')
        self.assertEqual(res.status_code, 200)
        sum_data = res.get_json()
        self.assertIn('total_sessions', sum_data)
        self.assertIn('products_verified', sum_data)
        print(f"PASS: Audit Summary (Sessions: {sum_data['total_sessions']}, Products Verified: {sum_data['products_verified']})")

        # 2. Sessions list
        res = self.client.get('/api/audit/sessions')
        self.assertEqual(res.status_code, 200)
        sess_data = res.get_json()
        self.assertGreater(len(sess_data['sessions']), 0)
        sess_id = sess_data['sessions'][0]['id']
        print(f"PASS: Audit Sessions list ({len(sess_data['sessions'])} sessions found, ID: {sess_id})")

        # 3. Session detail
        res = self.client.get(f'/api/audit/sessions/{sess_id}')
        self.assertEqual(res.status_code, 200)
        detail = res.get_json()['session']
        self.assertGreater(len(detail['items']), 0)
        first_item = detail['items'][0]
        print(f"PASS: Audit Session detail ({len(detail['items'])} items checked)")

        # 4. Update physical count (Enter Count)
        item_id = first_item['id']
        res = self.client.put(
            f'/api/audit/sessions/{sess_id}/items/{item_id}',
            headers=self.headers,
            json={'physical_stock': first_item['recorded_stock'] - 1, 'discrepancy_reason': 'Transit breakage'}
        )
        self.assertEqual(res.status_code, 200)
        updated_it = res.get_json()['item']
        self.assertEqual(updated_it['difference'], -1)
        self.assertEqual(updated_it['status'], 'Shortage')
        print(f"PASS: Audit Item Physical Count update (Diff: {updated_it['difference']}, Status: {updated_it['status']})")

        # 5. Authorized reconciliation
        res = self.client.post(
            f'/api/audit/sessions/{sess_id}/resolve-item/{item_id}',
            headers=self.headers,
            json={'corrective_action': 'Reconciled broken floor unit'}
        )
        self.assertEqual(res.status_code, 200)
        resolved_it = res.get_json()['item']
        self.assertEqual(resolved_it['status'], 'Resolved')
        self.assertTrue(resolved_it['is_adjusted'])
        print(f"PASS: Authorized Audit Reconciliation (Item status: {resolved_it['status']}, is_adjusted: {resolved_it['is_adjusted']})")

        # 6. Sales audit
        res = self.client.get('/api/audit/sales-audit')
        self.assertEqual(res.status_code, 200)
        sales_aud = res.get_json()
        self.assertIn('total_sales_inspected', sales_aud)
        self.assertIn('audit_health_rating', sales_aud)
        print(f"PASS: Sales Audit (Inspected {sales_aud['total_sales_inspected']} sales, Health: {sales_aud['audit_health_rating']})")

        # 7. System activity logs
        res = self.client.get('/api/audit/activity-logs')
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()
        self.assertGreater(logs['total'], 0)
        print(f"PASS: System Activity Logs ({logs['total']} events recorded)")

        # 8. Audit charts
        res = self.client.get('/api/audit/charts')
        self.assertEqual(res.status_code, 200)
        c_data = res.get_json()
        self.assertIn('shortage_vs_excess', c_data)
        self.assertIn('status_distribution', c_data)
        self.assertIn('category_breakdown', c_data)
        print("PASS: Audit Visualizations (Charts returned)")

    def test_05_revenue_analysis_endpoints(self):
        # 1. Overall Summary
        res = self.client.get('/api/revenue/summary')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('total_revenue', data)
        self.assertIn('gross_profit', data)
        self.assertIn('profit_margin_pct', data)
        self.assertGreater(data['total_revenue'], 0)
        print(f"PASS: Overall Revenue Summary (Total Revenue: INR {data['total_revenue']:,.2f}, Gross Profit: INR {data['gross_profit']:,.2f}, Margin: {data['profit_margin_pct']}%)")

        # 2. Single-product revenue
        prod = Product.query.first()
        res = self.client.get(f'/api/revenue/product/{prod.id}')
        self.assertEqual(res.status_code, 200)
        p_data = res.get_json()
        self.assertIn('total_revenue', p_data)
        self.assertIn('share_of_business_pct', p_data)
        print(f"PASS: Single Product Revenue for '{prod.name}' (Revenue: INR {p_data['total_revenue']:,.2f}, Business Share: {p_data['share_of_business_pct']}%)")

        # 3. Revenue charts (10 charts data points)
        res = self.client.get(f'/api/revenue/charts?product_id={prod.id}&aggregation=monthly')
        self.assertEqual(res.status_code, 200)
        c_data = res.get_json()
        self.assertIn('revenue_over_time', c_data)
        self.assertIn('top_products', c_data)
        self.assertIn('category_revenue', c_data)
        self.assertIn('revenue_by_dow', c_data)
        self.assertIn('volume_vs_revenue', c_data)
        print(f"PASS: Revenue Charts (Time series: {len(c_data['revenue_over_time'])} periods, Top products: {len(c_data['top_products'])})")

        # 4. Table & Insights
        res = self.client.get('/api/revenue/table')
        self.assertEqual(res.status_code, 200)
        t_data = res.get_json()
        self.assertGreater(t_data['total'], 0)

        res = self.client.get('/api/revenue/insights')
        self.assertEqual(res.status_code, 200)
        ins_data = res.get_json()
        self.assertGreater(len(ins_data['insights']), 0)
        print(f"PASS: Revenue Table & Insights ({t_data['total']} items listed, {len(ins_data['insights'])} data-driven insights generated)")

    def test_06_data_analysis_eda_endpoints(self):
        # 1. EDA
        res = self.client.get('/api/data-analysis/eda')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('descriptive_statistics', data)
        self.assertIn('revenue_distribution', data)
        self.assertIn('correlation_matrix', data)
        stats = data['descriptive_statistics']
        self.assertIn('total_price', stats)
        print(f"PASS: EDA Statistics (Mean Order: INR {stats['total_price']['mean']}, Median: INR {stats['total_price']['median']}, IQR: INR {stats['total_price']['iqr']})")

        # 2. Business Analytics
        res = self.client.get('/api/data-analysis/business')
        self.assertEqual(res.status_code, 200)
        biz = res.get_json()
        self.assertIn('stock_turnover_ratio', biz)
        self.assertIn('cost_of_goods_sold', biz)
        print(f"PASS: Business Analysis (Turnover: {biz['stock_turnover_ratio']}x, COGS: INR {biz['cost_of_goods_sold']:,.2f})")

    def test_07_all_ten_report_types_generation_and_export(self):
        report_types = [
            'inventory_audit',
            'sales_audit',
            'system_activity',
            'procurement',
            'revenue_analysis',
            'single_product',
            'all_products_performance',
            'data_quality',
            'eda',
            'inventory_performance'
        ]

        # Verify report catalog
        res = self.client.get('/api/reports/types')
        self.assertEqual(res.status_code, 200)
        cat = res.get_json()['report_types']
        self.assertEqual(len(cat), 10, "Must have exactly 10 supported report types")
        print("PASS: Verified 10/10 Report Catalog definitions")

        # Test generation and CSV export for every single report type
        for idx, r_type in enumerate(report_types, 1):
            # 1. Generate preview payload
            res = self.client.post(
                '/api/reports/generate',
                headers=self.headers,
                json={'report_type': r_type, 'product_id': 1}
            )
            self.assertEqual(res.status_code, 200, f"Report {r_type} generation failed")
            rep = res.get_json()['report']
            self.assertIn('kpis', rep)
            self.assertIn('table', rep)
            self.assertIn('findings', rep)
            self.assertIn('recommendations', rep)
            self.assertIn('data_limitations', rep)

            # 2. Export CSV
            res_csv = self.client.get(
                f'/api/reports/export?type={r_type}&product_id=1',
                headers=self.headers
            )
            self.assertEqual(res_csv.status_code, 200, f"Report {r_type} CSV export failed")
            self.assertGreater(len(res_csv.data), 50, f"CSV content for {r_type} was empty")

            print(f"PASS: Report {idx}/10 [{r_type}] - Preview Generated ({len(rep['kpis'])} KPIs, {len(rep['table']['rows'])} rows) & CSV Exported ({len(res_csv.data)} bytes)")

if __name__ == '__main__':
    unittest.main()
