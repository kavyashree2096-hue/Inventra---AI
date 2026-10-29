from datetime import datetime, timedelta
import random
from flask import Blueprint, jsonify, request
from models import (
    db, Product, Category, Sale, SaleItem, Store,
    PurchaseOrder, Alert, DemandForecast, ReorderRecommendation,
    ProcurementRecommendation, InventoryMovement
)
from services.inventory_service import InventoryService
from services.procurement_service import ProcurementService
from utils.rbac import get_current_authenticated_user

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')

@dashboard_bp.route('/stats', methods=['GET'])
def get_dashboard_stats():
    # 1. Product & Inventory Totals
    products = Product.query.all()
    total_products = len(products)
    current_inventory_units = sum(p.current_stock for p in products)
    inventory_value = sum(p.current_stock * p.cost_price for p in products)

    # 2. Sales & Revenue
    total_revenue = db.session.query(db.func.sum(Sale.net_amount)).scalar() or 0.0
    total_orders = Sale.query.count()
    total_units_sold = db.session.query(db.func.sum(SaleItem.quantity)).scalar() or 0

    # 3. Inventory Health & Statuses
    health = InventoryService.get_inventory_health()
    low_stock_count = health['low_stock_items']
    critical_stock_count = health['critical_items']
    stock_out_count = health['stock_outs']
    overstock_count = health['overstock_items']

    # 4. Fast & Slow Movers
    fast_movers = InventoryService.get_fast_moving_products(50)
    slow_movers = InventoryService.get_slow_moving_products(50)

    # 5. Forecast & Reorder metrics
    total_pred_demand = db.session.query(db.func.sum(DemandForecast.predicted_demand))\
        .filter(DemandForecast.forecast_period == 'weekly').scalar() or 0.0
    
    pending_procurement = ProcurementRecommendation.query.filter_by(status='Open').count()
    open_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['Draft', 'Pending Approval', 'Approved', 'Ordered', 'In Transit'])).count()

    critical_alerts_count = Alert.query.filter_by(is_read=False, severity='Critical').count()
    total_unread_alerts = Alert.query.filter_by(is_read=False).count()

    # 6. Privacy Shield: Mask confidential enterprise financials for Staff
    current_user = get_current_authenticated_user()
    user_role = current_user.role if current_user else 'Public'
    privacy_masked = (user_role == 'Staff')

    return jsonify({
        'kpis': {
            'total_sales_units': total_units_sold,
            'total_revenue': None if privacy_masked else round(float(total_revenue), 2),
            'total_orders': total_orders,
            'total_products': total_products,
            'current_inventory_units': current_inventory_units,
            'inventory_value': None if privacy_masked else round(float(inventory_value), 2),
            'predicted_demand_units': round(float(total_pred_demand), 1),
            'low_stock_products': low_stock_count + critical_stock_count,
            'stock_out_risk': stock_out_count,
            'overstock_products': overstock_count,
            'fast_moving_products': len(fast_movers),
            'slow_moving_products': len(slow_movers),
            'pending_procurement': pending_procurement,
            'open_purchase_orders': open_pos,
            'critical_alerts': critical_alerts_count,
            'total_unread_alerts': total_unread_alerts,
            'inventory_health_score': health['score'],
            'inventory_health_status': health['status']
        },
        'health_breakdown': health,
        'privacy_shield': {
            'is_financial_masked': privacy_masked,
            'user_role': user_role,
            'mode_name': 'Operational Floor View' if privacy_masked else 'Executive Financial View',
            'explanation': 'Confidential revenue and total valuation are masked for Staff roles according to company data privacy policy.' if privacy_masked else 'Full financial analytics unlocked.'
        }
    }), 200

@dashboard_bp.route('/telemetry', methods=['GET'])
def get_live_telemetry():
    """
    Real-time telemetry stream providing live inventory flux, recent transaction events,
    and simulated live sensor signals for unique UI/UX live-sync animations.
    """
    now = datetime.utcnow()
    recent_movements = InventoryMovement.query.order_by(InventoryMovement.timestamp.desc()).limit(6).all()
    
    events = []
    for m in recent_movements:
        prod_name = m.product.name if m.product else 'Stock SKU'
        events.append({
            'id': m.id,
            'type': m.movement_type,
            'text': f"{m.movement_type.title()}: {m.quantity} units of {prod_name}",
            'time': m.timestamp.strftime('%H:%M:%S') if m.timestamp else now.strftime('%H:%M:%S'),
            'badge': 'inflow' if m.movement_type == 'PURCHASE_RECEIPT' else 'audit'
        })
    
    # If no movements, supply contextual retail ticker items
    if not events:
        events = [
            {'id': 1, 'type': 'TELEMETRY', 'text': 'North Hub: Shelf sensor scan confirmed 100% SKU sync', 'time': now.strftime('%H:%M:%S'), 'badge': 'sync'},
            {'id': 2, 'type': 'FORECAST', 'text': 'Gradient Boosting regressor validated weekly horizon', 'time': now.strftime('%H:%M:%S'), 'badge': 'ml'},
            {'id': 3, 'type': 'ALERT', 'text': 'Dynamic safety stock threshold active across 4 stores', 'time': now.strftime('%H:%M:%S'), 'badge': 'guard'}
        ]

    return jsonify({
        'status': 'online',
        'server_time': now.isoformat(),
        'heartbeat_ms': random.randint(18, 42),
        'active_nodes': 4,
        'events': events
    }), 200

@dashboard_bp.route('/charts', methods=['GET'])
def get_dashboard_charts():
    # 1. Sales & Revenue Trend (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_sales = db.session.query(
        db.func.date(Sale.sale_date).label('day'),
        db.func.sum(Sale.net_amount).label('revenue'),
        db.func.count(Sale.id).label('orders')
    ).filter(Sale.sale_date >= thirty_days_ago)\
     .group_by(db.func.date(Sale.sale_date))\
     .order_by('day').all()

    sales_trend = [
        {
            'date': str(row.day),
            'revenue': round(float(row.revenue or 0), 2),
            'orders': int(row.orders or 0)
        }
        for row in daily_sales
    ]

    # 2. Category-wise Sales & Inventory Breakdown
    categories = Category.query.all()
    category_analytics = []
    for cat in categories:
        cat_rev = db.session.query(db.func.sum(SaleItem.total_price))\
            .join(Product, SaleItem.product_id == Product.id)\
            .filter(Product.category_id == cat.id).scalar() or 0.0

        cat_stock = sum(p.current_stock for p in cat.products) if cat.products else 0
        cat_val = sum(p.current_stock * p.cost_price for p in cat.products) if cat.products else 0

        category_analytics.append({
            'category': cat.name,
            'revenue': round(float(cat_rev), 2),
            'stock_units': cat_stock,
            'inventory_value': round(float(cat_val), 2)
        })

    # 3. Actual vs Predicted Demand Comparison
    forecasts = db.session.query(
        DemandForecast.product_id,
        Product.name,
        DemandForecast.predicted_demand,
        DemandForecast.actual_demand
    ).join(Product, DemandForecast.product_id == Product.id)\
     .filter(DemandForecast.actual_demand.isnot(None))\
     .limit(8).all()

    actual_vs_predicted = [
        {
            'product': row.name[:18] + '...' if len(row.name) > 20 else row.name,
            'predicted': round(float(row.predicted_demand), 1),
            'actual': round(float(row.actual_demand), 1)
        }
        for row in forecasts
    ]

    # 4. Stock Status Distribution
    products = Product.query.all()
    status_counts = {}
    for p in products:
        st = p.status or p.compute_status()
        status_counts[st] = status_counts.get(st, 0) + 1

    stock_distribution = [{'status': k, 'count': v} for k, v in status_counts.items()]

    # 5. Top 6 Product Sales Velocity vs Stock
    fast_movers = InventoryService.get_fast_moving_products(6)
    velocity_comparison = [
        {
            'name': fm['name'][:16] + '..',
            'units_sold': fm['units_sold_30d'],
            'current_stock': fm['current_stock'],
            'recommended_reorder': fm['recommended_reorder_qty']
        }
        for fm in fast_movers
    ]

    # 6. Procurement Spend by Month and Supplier
    proc_analytics = ProcurementService.get_procurement_cost_analytics()

    return jsonify({
        'sales_trend': sales_trend,
        'category_analytics': category_analytics,
        'actual_vs_predicted': actual_vs_predicted,
        'stock_distribution': stock_distribution,
        'velocity_comparison': velocity_comparison,
        'procurement_analytics': proc_analytics
    }), 200
