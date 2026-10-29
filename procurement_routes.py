import random
from datetime import datetime
from flask import Blueprint, request, jsonify
from models import (
    db, PurchaseRequisition, PurchaseRequisitionItem, PurchaseOrder,
    PurchaseOrderItem, Delivery, Product, Category, Supplier, ProcurementRecommendation, AuditLog
)
from services.procurement_service import ProcurementService
from utils.rbac import role_required

procurement_bp = Blueprint('procurement', __name__, url_prefix='/api/procurement')

@procurement_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    data = ProcurementService.get_procurement_dashboard_data()
    return jsonify(data), 200

@procurement_bp.route('/recommendations', methods=['GET'])
def get_recommendations():
    recs = ProcurementRecommendation.query.filter_by(status='Open').all()
    if not recs:
        ProcurementService.generate_procurement_recommendations()
        recs = ProcurementRecommendation.query.filter_by(status='Open').all()
    return jsonify({'recommendations': [r.to_dict() for r in recs]}), 200

@procurement_bp.route('/recommendations/generate', methods=['POST'])
@role_required('Admin', 'Manager')
def generate_recommendations():
    recs = ProcurementService.generate_procurement_recommendations()
    return jsonify({'message': f'Generated {len(recs)} procurement recommendations!', 'recommendations': recs}), 200

# Purchase Requisitions
@procurement_bp.route('/requisitions', methods=['GET'])
def get_requisitions():
    reqs = PurchaseRequisition.query.order_by(PurchaseRequisition.requested_date.desc()).all()
    return jsonify({'requisitions': [r.to_dict() for r in reqs]}), 200

@procurement_bp.route('/requisitions', methods=['POST'])
def create_requisition():
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'Requisition must have at least one product item'}), 400

    req_num = f"REQ-{datetime.utcnow().strftime('%Y%m%d')}-{random.randint(100, 999)}"
    req = PurchaseRequisition(
        requisition_number=req_num,
        requested_by_id=data.get('user_id'),
        reason=data.get('reason', 'Stock replenishment'),
        priority=data.get('priority', 'Medium'),
        status='Pending'
    )
    db.session.add(req)
    db.session.flush()

    for it in items:
        prod = Product.query.get(it['product_id'])
        if prod:
            qty = int(it['quantity'])
            cost = qty * prod.cost_price
            db.session.add(PurchaseRequisitionItem(
                requisition_id=req.id,
                product_id=prod.id,
                quantity=qty,
                estimated_cost=cost
            ))

    db.session.commit()
    return jsonify({'message': 'Requisition created successfully', 'requisition': req.to_dict()}), 201

@procurement_bp.route('/requisitions/<int:req_id>/status', methods=['PUT'])
def update_requisition_status(req_id):
    req = PurchaseRequisition.query.get_or_404(req_id)
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ['Approved', 'Rejected', 'Converted to PO']:
        return jsonify({'error': 'Invalid status'}), 400

    req.status = new_status
    req.approval_notes = data.get('notes', '')

    # If converted to PO, create purchase order
    po_created = None
    if new_status == 'Converted to PO':
        items_payload = [{'product_id': it.product_id, 'quantity': it.quantity} for it in req.items]
        # Choose supplier of first item
        first_prod = req.items[0].product if req.items else None
        sup_id = 1
        if first_prod and first_prod.supplier_links:
            sup_id = first_prod.supplier_links[0].supplier_id

        po_created = ProcurementService.create_purchase_order({
            'supplier_id': sup_id,
            'items': items_payload,
            'notes': f"Converted from requisition {req.requisition_number}"
        })

    db.session.commit()
    return jsonify({'message': f'Requisition {new_status}', 'requisition': req.to_dict(), 'po': po_created}), 200

# Purchase Orders
@procurement_bp.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    status = request.args.get('status')
    query = PurchaseOrder.query
    if status and status != 'All':
        query = query.filter_by(status=status)
    pos = query.order_by(PurchaseOrder.order_date.desc()).all()
    return jsonify({'purchase_orders': [p.to_dict() for p in pos]}), 200

@procurement_bp.route('/purchase-orders', methods=['POST'])
@role_required('Admin', 'Manager')
def create_purchase_order():
    data = request.get_json() or {}
    try:
        po_data = ProcurementService.create_purchase_order(data)
        return jsonify({'message': 'Purchase Order created successfully', 'purchase_order': po_data}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@procurement_bp.route('/purchase-orders/<int:po_id>/status', methods=['PUT'])
def update_purchase_order_status(po_id):
    data = request.get_json() or {}
    new_status = data.get('status')
    notes = data.get('notes')

    if not new_status:
        return jsonify({'error': 'Status is required'}), 400

    po_data = ProcurementService.update_po_status(po_id, new_status, notes=notes)
    if not po_data:
        return jsonify({'error': 'Purchase Order not found'}), 404

    return jsonify({
        'message': f'Purchase Order status updated to {new_status}' + (' (Inventory automatically replenished!)' if new_status == 'Received' else ''),
        'purchase_order': po_data
    }), 200

@procurement_bp.route('/analytics', methods=['GET'])
@procurement_bp.route('/cost-analytics', methods=['GET'])
def get_analytics():
    data = ProcurementService.get_procurement_cost_analytics()
    return jsonify(data), 200

# Category-Wise Product Management
@procurement_bp.route('/products', methods=['GET'])
def get_procurement_products():
    """
    Returns products organized by category with procurement statuses,
    suggested reorder quantities, and estimated replenishment costs.
    Formula: Suggested Procurement Quantity = MAX(0, Target Stock Level - Available Stock)
    """
    category_id = request.args.get('category_id', type=int)
    search = request.args.get('search', '').strip().lower()
    status_filter = request.args.get('status')
    sort_by = request.args.get('sort_by', 'status') # 'name', 'stock', 'status', 'cost'
    order = request.args.get('order', 'asc')

    query = Product.query
    if category_id:
        query = query.filter_by(category_id=category_id)

    products = query.all()

    # Get active open PO product IDs
    open_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['Ordered', 'In Transit', 'Pending Approval'])).all()
    open_po_prod_ids = set()
    for po in open_pos:
        for it in po.items:
            open_po_prod_ids.add(it.product_id)

    # Get recently received product IDs
    received_pos = PurchaseOrder.query.filter_by(status='Received').all()
    received_prod_ids = set()
    for po in received_pos:
        for it in po.items:
            received_prod_ids.add(it.product_id)

    product_rows = []
    for p in products:
        # Search match
        if search:
            if search not in p.name.lower() and search not in p.sku.lower() and search != str(p.id):
                continue

        # Status rules
        if p.current_stock <= 0:
            proc_status = 'Out of Stock'
        elif p.id in open_po_prod_ids:
            proc_status = 'Pending Procurement'
        elif p.current_stock <= p.safety_stock:
            proc_status = 'Low Stock'
        elif p.current_stock <= p.reorder_point:
            proc_status = 'Reorder Required'
        elif p.id in received_prod_ids:
            proc_status = 'Procurement Completed'
        else:
            proc_status = 'Sufficient Stock'

        if status_filter and status_filter != 'All' and proc_status != status_filter:
            continue

        target_stock = p.max_stock or 100
        # Basic formula: MAX(0, Target Stock Level - Available Stock)
        # Enhanced formula factoring lead-time demand:
        daily_velocity = 3.5
        suggested_qty = max(0, target_stock - p.current_stock)
        est_proc_cost = round(suggested_qty * (p.cost_price or 0.0), 2)

        supplier_name = "Primary Vendor"
        if p.supplier_links and p.supplier_links[0].supplier:
            supplier_name = p.supplier_links[0].supplier.company

        product_rows.append({
            'product_id': p.id,
            'sku': p.sku,
            'name': p.name,
            'category_id': p.category_id,
            'category_name': p.category.name if p.category else 'Uncategorized',
            'brand': p.warehouse or 'Central Depo',
            'current_stock': p.current_stock,
            'min_stock': p.min_stock,
            'safety_stock': p.safety_stock,
            'reorder_point': p.reorder_point,
            'target_stock': target_stock,
            'supplier_name': supplier_name,
            'unit_cost': round(p.cost_price, 2),
            'selling_price': round(p.selling_price, 2),
            'suggested_quantity': suggested_qty,
            'estimated_cost': est_proc_cost,
            'procurement_status': proc_status,
            'image_url': p.image_url,
            'lead_time_days': p.lead_time_days
        })

    # Sorting
    if sort_by == 'name':
        product_rows.sort(key=lambda x: x['name'].lower(), reverse=(order == 'desc'))
    elif sort_by == 'stock':
        product_rows.sort(key=lambda x: x['current_stock'], reverse=(order == 'desc'))
    elif sort_by == 'cost':
        product_rows.sort(key=lambda x: x['estimated_cost'], reverse=(order == 'desc'))
    else: # status
        status_priority = {'Out of Stock': 0, 'Reorder Required': 1, 'Low Stock': 2, 'Pending Procurement': 3, 'Sufficient Stock': 4, 'Procurement Completed': 5}
        product_rows.sort(key=lambda x: status_priority.get(x['procurement_status'], 9), reverse=(order == 'desc'))

    return jsonify({
        'products': product_rows,
        'total': len(product_rows)
    }), 200

@procurement_bp.route('/products/<int:product_id>/category', methods=['PUT'])
@role_required('Admin', 'Manager')
def update_product_category(product_id):
    """
    Allows authorized users to map or reclassify a product to a category.
    """
    prod = Product.query.get_or_404(product_id)
    data = request.get_json() or {}
    new_cat_id = data.get('category_id')

    cat = Category.query.get(new_cat_id)
    if not cat:
        return jsonify({'error': 'Invalid category ID'}), 400

    old_cat_name = prod.category.name if prod.category else 'None'
    prod.category_id = cat.id
    db.session.commit()

    log = AuditLog(
        action='PRODUCT_CATEGORY_MAPPED',
        entity='Product',
        entity_id=str(prod.id),
        details=f"Mapped product {prod.sku} ({prod.name}) from category '{old_cat_name}' to '{cat.name}'."
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({'message': f"Product mapped to '{cat.name}' successfully", 'product': prod.to_dict()}), 200

@procurement_bp.route('/summary', methods=['GET'])
def get_procurement_summary():
    """
    Procurement summary KPI cards based on persistent data.
    """
    products = Product.query.all()
    total_products = len(products)
    reorder_required = sum(1 for p in products if p.current_stock <= p.reorder_point)
    out_of_stock = sum(1 for p in products if p.current_stock <= 0)

    pending_reqs = PurchaseRequisition.query.filter_by(status='Pending').count()
    approved_reqs = PurchaseRequisition.query.filter_by(status='Approved').count()
    ordered_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['Ordered', 'In Transit'])).count()

    # Calculate total estimated procurement cost for items requiring reorder
    total_est_cost = sum(
        max(0, p.max_stock - p.current_stock) * p.cost_price
        for p in products if p.current_stock <= p.reorder_point
    )

    return jsonify({
        'total_products': total_products,
        'products_requiring_reorder': reorder_required,
        'out_of_stock_products': out_of_stock,
        'pending_procurement_requests': pending_reqs,
        'approved_procurement_requests': approved_reqs,
        'ordered_products': ordered_pos,
        'estimated_procurement_cost': round(total_est_cost, 2)
    }), 200

@procurement_bp.route('/charts', methods=['GET'])
def get_procurement_charts():
    """
    Returns 5 interactive charts for the Procurement Hub.
    """
    products = Product.query.all()
    categories = Category.query.all()

    # 1. Products requiring reorder by category
    cat_reorder = {}
    for c in categories:
        cat_reorder[c.name] = sum(1 for p in c.products if p.current_stock <= p.reorder_point)
    reorder_by_category = [{'category': k, 'count': v} for k, v in cat_reorder.items()]

    # 2. Current stock versus target stock (for top 10 products requiring stock)
    needy_products = sorted(products, key=lambda p: max(0, p.max_stock - p.current_stock), reverse=True)[:8]
    stock_vs_target = [
        {
            'name': (p.name[:18] + '..') if len(p.name) > 18 else p.name,
            'current_stock': p.current_stock,
            'target_stock': p.max_stock,
            'deficit': max(0, p.max_stock - p.current_stock)
        }
        for p in needy_products
    ]

    # 3. Procurement requests by status
    pos = PurchaseOrder.query.all()
    status_counts = {}
    for po in pos:
        status_counts[po.status] = status_counts.get(po.status, 0) + 1
    requests_by_status = [{'status': k, 'count': v} for k, v in status_counts.items()]

    # 4. Estimated procurement cost by category
    cat_cost = {}
    for c in categories:
        cat_cost[c.name] = sum(
            max(0, p.max_stock - p.current_stock) * p.cost_price
            for p in c.products if p.current_stock <= p.reorder_point
        )
    cost_by_category = [{'category': k, 'cost': round(v, 2)} for k, v in cat_cost.items()]

    # 5. Products with highest replenishment requirements
    top_replenishment = [
        {
            'name': p.name,
            'sku': p.sku,
            'category': p.category.name if p.category else 'General',
            'suggested_quantity': max(0, p.max_stock - p.current_stock),
            'estimated_cost': round(max(0, p.max_stock - p.current_stock) * p.cost_price, 2)
        }
        for p in needy_products[:6]
    ]

    return jsonify({
        'reorder_by_category': reorder_by_category,
        'stock_vs_target': stock_vs_target,
        'requests_by_status': requests_by_status,
        'cost_by_category': cost_by_category,
        'highest_replenishment': top_replenishment
    }), 200

@procurement_bp.route('/purchase-orders/<int:po_id>/receive', methods=['POST'])
@role_required('Admin', 'Manager')
def receive_purchase_order_goods(po_id):
    """
    Validated receiving operation: Updates inventory stock, creates inventory movement,
    and records audit log.
    """
    data = request.get_json() or {}
    po = PurchaseOrder.query.get_or_404(po_id)

    if po.status == 'Received':
        return jsonify({'error': 'Purchase order has already been fully received.'}), 400

    po_data = ProcurementService.update_po_status(po_id, 'Received', notes=data.get('notes', 'Shipment inspected and received on floor.'))
    return jsonify({
        'message': f"PO {po.po_number} received! Warehouse inventory automatically replenished.",
        'purchase_order': po_data
    }), 200

@procurement_bp.route('/purchase-orders/<int:po_id>/cancel', methods=['POST'])
@role_required('Admin', 'Manager')
def cancel_purchase_order(po_id):
    """
    Cancels purchase order and records explicit cancellation reason.
    """
    data = request.get_json() or {}
    reason = data.get('reason')
    if not reason:
        return jsonify({'error': 'Cancellation reason is required'}), 400

    po = PurchaseOrder.query.get_or_404(po_id)
    po.status = 'Cancelled'
    po.notes = f"{po.notes or ''}\nCancelled Reason: {reason}".strip()

    log = AuditLog(
        action='PO_CANCELLED',
        entity='PurchaseOrder',
        entity_id=str(po.id),
        details=f"PO {po.po_number} cancelled. Reason: {reason}"
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({'message': f"PO {po.po_number} has been cancelled.", 'purchase_order': po.to_dict()}), 200

@procurement_bp.route('/export', methods=['GET'])
@role_required('Admin', 'Manager')
def export_procurement_csv():
    """
    Exports comprehensive procurement report to CSV.
    """
    import io, csv
    from flask import Response
    products = Product.query.all()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Product ID', 'Product SKU', 'Product Name', 'Category', 'Current Stock',
        'Target Stock', 'Suggested Qty', 'Supplier Name', 'Unit Cost (INR)',
        'Estimated Procurement Cost (INR)', 'Procurement Status'
    ])

    for p in products:
        target = p.max_stock or 100
        qty = max(0, target - p.current_stock)
        cost = round(qty * p.cost_price, 2)
        sup = p.supplier_links[0].supplier.company if (p.supplier_links and p.supplier_links[0].supplier) else 'Primary Supplier'
        stat = 'Out of Stock' if p.current_stock <= 0 else ('Reorder Required' if p.current_stock <= p.reorder_point else 'Sufficient Stock')

        writer.writerow([
            p.id, p.sku, p.name, p.category.name if p.category else 'General',
            p.current_stock, target, qty, sup, p.cost_price, cost, stat
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=inventra_procurement_report.csv'}
    )
