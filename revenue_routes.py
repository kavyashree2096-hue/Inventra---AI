import io
import csv
from flask import Blueprint, request, jsonify, Response
from services.revenue_service import RevenueService
from utils.rbac import role_required, get_current_authenticated_user

revenue_bp = Blueprint('revenue', __name__, url_prefix='/api/revenue')

@revenue_bp.route('/summary', methods=['GET'])
def get_revenue_summary():
    """
    Returns overall portfolio revenue metrics, KPI cards, and profit margins.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)

    summary = RevenueService.get_overall_summary(start_date, end_date, category_id)

    # Privacy Shield check
    current_user = get_current_authenticated_user()
    if current_user and current_user.role == 'Staff':
        summary['gross_profit'] = 'Protected (Manager+)'
        summary['profit_margin_pct'] = 'Protected (Manager+)'
        summary['privacy_shield_active'] = True

    return jsonify(summary), 200

@revenue_bp.route('/product/<int:product_id>', methods=['GET'])
def get_product_revenue(product_id):
    """
    Returns deep-dive revenue metrics for a specific single product.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    data = RevenueService.get_single_product_summary(product_id, start_date, end_date)
    if not data:
        return jsonify({'error': 'Product not found'}), 404

    current_user = get_current_authenticated_user()
    if current_user and current_user.role == 'Staff':
        data['gross_profit'] = 'Protected (Manager+)'
        data['profit_margin_pct'] = 'Protected (Manager+)'

    return jsonify(data), 200

@revenue_bp.route('/charts', methods=['GET'])
def get_revenue_charts():
    """
    Returns data points for 10 interactive charts.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)
    product_id = request.args.get('product_id', type=int)
    aggregation = request.args.get('aggregation', 'monthly')

    charts = RevenueService.get_revenue_charts(
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        product_id=product_id,
        aggregation=aggregation
    )
    return jsonify(charts), 200

@revenue_bp.route('/table', methods=['GET'])
def get_revenue_table():
    """
    Returns searchable, sortable list of all product revenue figures.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)
    search = request.args.get('search')

    rows = RevenueService.get_revenue_table(start_date, end_date, category_id, search)
    return jsonify({'products': rows, 'total': len(rows)}), 200

@revenue_bp.route('/insights', methods=['GET'])
def get_revenue_insights():
    """
    Returns automated data-driven revenue observations and recommendations.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)

    insights = RevenueService.get_revenue_insights(start_date, end_date, category_id)
    return jsonify({'insights': insights}), 200

@revenue_bp.route('/export', methods=['GET'])
@role_required('Admin', 'Manager')
def export_revenue_csv():
    """
    Generates CSV export of product revenue analysis table.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)

    rows = RevenueService.get_revenue_table(start_date, end_date, category_id)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Product SKU', 'Product Name', 'Category', 'Units Sold', 'Gross Sales (INR)',
        'Net Revenue (INR)', 'Revenue Contribution (%)', 'Average Selling Price (INR)',
        'Gross Profit (INR)', 'Profit Margin (%)', 'Current Stock'
    ])

    for r in rows:
        writer.writerow([
            r['sku'],
            r['name'],
            r['category'],
            r['units_sold'],
            r['gross_sales'],
            r['net_revenue'],
            r['revenue_contribution_pct'],
            r['average_selling_price'],
            r['gross_profit'],
            r['profit_margin_pct'],
            r['current_stock']
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=inventra_revenue_analysis.csv'}
    )
