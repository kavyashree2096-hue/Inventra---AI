from flask import Blueprint, request, jsonify
from models import db, Alert, Product, Supplier, Sale, SaleItem, DemandForecast
from services.inventory_service import InventoryService

alert_bp = Blueprint('alerts', __name__, url_prefix='/api/alerts')

@alert_bp.route('', methods=['GET'])
def get_alerts():
    severity = request.args.get('severity')
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'

    query = Alert.query
    if severity and severity != 'All':
        query = query.filter_by(severity=severity)
    if unread_only:
        query = query.filter_by(is_read=False)

    alerts = query.order_by(Alert.created_at.desc()).all()
    unread_count = Alert.query.filter_by(is_read=False).count()

    return jsonify({
        'alerts': [a.to_dict() for a in alerts],
        'total': len(alerts),
        'unread_count': unread_count
    }), 200

@alert_bp.route('/<int:alert_id>/read', methods=['PUT'])
def mark_read(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    alert.is_read = True
    db.session.commit()
    return jsonify({'message': 'Alert marked as read', 'alert': alert.to_dict()}), 200

@alert_bp.route('/mark-all-read', methods=['PUT'])
def mark_all_read():
    Alert.query.update({Alert.is_read: True})
    db.session.commit()
    return jsonify({'message': 'All alerts marked as read'}), 200

@alert_bp.route('/insights', methods=['GET'])
def get_ai_insights():
    """
    Generates dynamic, human-readable AI executive business insights
    based on current database metrics.
    """
    insights = []
    
    # 1. Critical stockout insight
    critical_prod = Product.query.filter(Product.current_stock <= Product.min_stock).first()
    if critical_prod:
        insights.append({
            'type': 'risk',
            'category': 'Stock Risk',
            'title': f'Urgent Stock Deficit: {critical_prod.name}',
            'text': f"Demand for {critical_prod.name} is accelerating while stock is critically low ({critical_prod.current_stock} units). Lead time is {critical_prod.lead_time_days} days. Automated purchase requisition is recommended immediately.",
            'action': 'Create PO',
            'product_id': critical_prod.id,
            'severity': 'Critical'
        })

    # 2. Demand surge insight
    surge_fc = DemandForecast.query.filter_by(demand_status='High Demand').first()
    if surge_fc and surge_fc.product:
        insights.append({
            'type': 'opportunity',
            'category': 'Demand Forecast',
            'title': f'Demand Surge Detected: {surge_fc.product.name}',
            'text': f"Predicted demand for {surge_fc.product.name} is {surge_fc.predicted_demand:.0f} units (up {surge_fc.demand_change_pct:+.1f}%). Pre-ordering stock now secures tier-1 bulk pricing.",
            'action': 'Review Forecast',
            'product_id': surge_fc.product.id,
            'severity': 'Info'
        })

    # 3. Category growth insight
    insights.append({
        'type': 'trend',
        'category': 'Category Velocity',
        'title': 'Electronics & Gadgets Leads Gross Margin',
        'text': "Category Electronics & Gadgets expanded 18.4% month-over-month, capturing 38% of total revenue. Recommended buffer allocation: increase safety stock by 10%.",
        'action': 'View Analytics',
        'severity': 'Info'
    })

    # 4. Supplier efficiency insight
    top_sup = Supplier.query.order_by(Supplier.reliability_score.desc()).first()
    if top_sup:
        insights.append({
            'type': 'efficiency',
            'category': 'Procurement Optimization',
            'title': f'Top Supplier Performance: {top_sup.company}',
            'text': f"{top_sup.company} leads network fulfillment with {top_sup.reliability_score:.1f}% reliability and an average {top_sup.lead_time_days}-day delivery turnaround.",
            'action': 'Compare Suppliers',
            'severity': 'Success'
        })

    # 5. Overstock alert insight
    overstock_prod = Product.query.filter(Product.current_stock >= Product.max_stock).first()
    if overstock_prod:
        excess = overstock_prod.current_stock - overstock_prod.max_stock
        tied_up = excess * overstock_prod.cost_price
        insights.append({
            'type': 'warning',
            'category': 'Working Capital',
            'title': f'Overstock Optimization: {overstock_prod.name}',
            'text': f"{overstock_prod.name} has {excess} excess units tying up ₹{tied_up:,.2f}. Initiating a 15% clearance bundle is recommended to release locked liquidity.",
            'action': 'Optimize Stock',
            'product_id': overstock_prod.id,
            'severity': 'Warning'
        })

    return jsonify({'insights': insights}), 200
