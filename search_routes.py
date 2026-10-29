from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from models import (
    db, Product, Category, InventoryItem, PurchaseOrder,
    Supplier, Sale, AuditLog, AuditSession
)
from utils.rbac import get_current_authenticated_user

search_bp = Blueprint('search', __name__, url_prefix='/api/search')

@search_bp.route('', methods=['GET'])
def global_search():
    """
    Global search across products, categories, inventory, procurement, suppliers,
    revenue/sales, audit records, and reports.
    Supports partial matching, case-insensitivity, category filters, and role-based clearance.
    """
    query_str = (request.args.get('q') or '').strip()
    category_filter = request.args.get('category')
    record_type = request.args.get('type', 'all') # 'all', 'products', 'procurement', 'audit', 'sales'
    limit = min(request.args.get('limit', 8, type=int), 25)

    if not query_str or len(query_str) < 1:
        return jsonify({
            'query': query_str,
            'total_matches': 0,
            'results': {
                'products': [],
                'categories': [],
                'procurement': [],
                'suppliers': [],
                'sales': [],
                'audit': [],
                'reports': []
            },
            'suggestions': []
        }), 200

    q_pattern = f"%{query_str}%"
    results = {}
    suggestions = []

    current_user = get_current_authenticated_user()
    user_role = current_user.role if current_user else 'Staff'
    can_view_audit = user_role in ['Admin', 'Manager']

    # 1. Products Search
    if record_type in ['all', 'products']:
        p_query = Product.query.filter(
            or_(
                Product.name.ilike(q_pattern),
                Product.sku.ilike(q_pattern),
                Product.description.ilike(q_pattern)
            )
        )
        if category_filter:
            p_query = p_query.join(Category).filter(Category.name.ilike(f"%{category_filter}%"))
        products = p_query.limit(limit).all()

        results['products'] = [
            {
                'id': p.id,
                'title': p.name,
                'subtitle': f"SKU: {p.sku} • Stock: {p.current_stock} units • ₹{p.selling_price}",
                'category': p.category.name if p.category else 'General',
                'badge': p.status or p.compute_status(),
                'image': p.image_url,
                'route': f"/products/{p.id}",
                'type': 'Product'
            }
            for p in products
        ]
        for p in products[:3]:
            suggestions.append(p.name)

    # 2. Categories Search
    if record_type in ['all', 'categories']:
        cats = Category.query.filter(
            or_(
                Category.name.ilike(q_pattern),
                Category.description.ilike(q_pattern)
            )
        ).limit(limit).all()

        results['categories'] = [
            {
                'id': c.id,
                'title': c.name,
                'subtitle': f"{len(c.products)} active products in department",
                'route': f"/procurement?category={c.id}",
                'type': 'Category'
            }
            for c in cats
        ]

    # 3. Procurement & Purchase Orders
    if record_type in ['all', 'procurement']:
        pos = PurchaseOrder.query.filter(
            or_(
                PurchaseOrder.po_number.ilike(q_pattern),
                PurchaseOrder.notes.ilike(q_pattern),
                PurchaseOrder.status.ilike(q_pattern)
            )
        ).limit(limit).all()

        results['procurement'] = [
            {
                'id': po.id,
                'title': f"PO #{po.po_number}",
                'subtitle': f"Supplier: {po.supplier.company if po.supplier else 'Unknown'} • ₹{po.total_amount:,.2f}",
                'badge': po.status,
                'route': "/procurement",
                'type': 'Procurement'
            }
            for po in pos
        ]

    # 4. Suppliers
    if record_type in ['all', 'suppliers']:
        sups = Supplier.query.filter(
            or_(
                Supplier.name.ilike(q_pattern),
                Supplier.company.ilike(q_pattern),
                Supplier.address.ilike(q_pattern)
            )
        ).limit(limit).all()

        results['suppliers'] = [
            {
                'id': s.id,
                'title': s.company,
                'subtitle': f"Contact: {s.name} • Lead Time: {s.lead_time_days}d",
                'badge': f"Rating: {s.rating}★",
                'route': "/suppliers",
                'type': 'Supplier'
            }
            for s in sups
        ]

    # 5. Sales & Invoices
    if record_type in ['all', 'sales']:
        sales = Sale.query.filter(
            or_(
                Sale.invoice_number.ilike(q_pattern),
                Sale.payment_method.ilike(q_pattern)
            )
        ).limit(limit).all()

        results['sales'] = [
            {
                'id': s.id,
                'title': f"Invoice #{s.invoice_number}",
                'subtitle': f"Net: ₹{s.net_amount:,.2f} • {s.payment_method} • {s.sale_date.strftime('%Y-%m-%d') if s.sale_date else ''}",
                'badge': s.status,
                'route': "/revenue",
                'type': 'Sale'
            }
            for s in sales
        ]

    # 6. Audit Records (ROLE RESTRICTED: Admin or Manager only)
    if record_type in ['all', 'audit']:
        if can_view_audit:
            # Audit Sessions & Audit Logs
            audit_sessions = AuditSession.query.filter(
                or_(
                    AuditSession.session_code.ilike(q_pattern),
                    AuditSession.title.ilike(q_pattern),
                    AuditSession.warehouse_name.ilike(q_pattern)
                )
            ).limit(4).all()

            audit_logs = AuditLog.query.filter(
                or_(
                    AuditLog.action.ilike(q_pattern),
                    AuditLog.details.ilike(q_pattern),
                    AuditLog.entity.ilike(q_pattern)
                )
            ).limit(4).all()

            audit_items = []
            for a in audit_sessions:
                audit_items.append({
                    'id': a.id,
                    'title': f"Audit Session: {a.session_code}",
                    'subtitle': f"{a.title} • Status: {a.status} • {a.warehouse_name}",
                    'badge': a.status,
                    'route': "/audit",
                    'type': 'Audit Session'
                })
            for l in audit_logs:
                audit_items.append({
                    'id': l.id,
                    'title': f"Log: {l.action}",
                    'subtitle': f"{l.details[:70]}..." if l.details and len(l.details) > 70 else (l.details or ''),
                    'badge': l.entity,
                    'route': "/audit?tab=activity",
                    'type': 'System Log'
                })
            results['audit'] = audit_items
        else:
            results['audit'] = []

    # 7. Reports matching query
    if record_type in ['all', 'reports']:
        standard_reports = [
            {'title': 'Inventory Audit Report', 'desc': 'Physical stock counts vs recorded discrepancies', 'route': '/reports?type=inventory_audit'},
            {'title': 'Sales Audit Report', 'desc': 'Data consistency and invoice line audits', 'route': '/reports?type=sales_audit'},
            {'title': 'Procurement Report', 'desc': 'Replenishment suggestions and supplier purchase orders', 'route': '/reports?type=procurement'},
            {'title': 'Revenue Analysis Report', 'desc': 'Gross and net profit margins by catalog SKU', 'route': '/reports?type=revenue_analysis'},
            {'title': 'Single Product Revenue Report', 'desc': 'Deep-dive transactional velocity by product', 'route': '/reports?type=single_product'},
            {'title': 'Exploratory Data Analysis Report', 'desc': 'Statistical quartiles and distribution curves', 'route': '/reports?type=eda'},
            {'title': 'Data Quality Report', 'desc': 'Dataset integrity score, missing values, and outliers', 'route': '/reports?type=data_quality'}
        ]
        matched_reports = [
            {
                'id': idx + 1,
                'title': r['title'],
                'subtitle': r['desc'],
                'route': r['route'],
                'type': 'Report'
            }
            for idx, r in enumerate(standard_reports)
            if query_str.lower() in r['title'].lower() or query_str.lower() in r['desc'].lower()
        ]
        results['reports'] = matched_reports[:limit]

    total_matches = sum(len(items) for items in results.values())

    return jsonify({
        'query': query_str,
        'total_matches': total_matches,
        'results': results,
        'suggestions': list(dict.fromkeys(suggestions))[:5]
    }), 200
