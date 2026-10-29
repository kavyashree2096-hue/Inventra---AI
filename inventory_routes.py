from flask import Blueprint, request, jsonify
from models import db, Product, Warehouse, InventoryItem, InventoryMovement, AuditLog
from services.inventory_service import InventoryService
from utils.rbac import role_required

inventory_bp = Blueprint('inventory', __name__, url_prefix='/api/inventory')

@inventory_bp.route('', methods=['GET'])
def get_inventory():
    category_id = request.args.get('category_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)
    search = request.args.get('search', '').strip()

    query = Product.query
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        query = query.filter(
            (Product.name.ilike(f'%{search}%')) |
            (Product.sku.ilike(f'%{search}%'))
        )

    products = query.all()
    results = []
    for p in products:
        item = p.to_dict()
        inv_item = InventoryItem.query.filter_by(product_id=p.id).first()
        item['warehouse_name'] = inv_item.warehouse.name if (inv_item and inv_item.warehouse) else 'Central Distribution Hub'
        item['incoming_stock'] = inv_item.quantity_incoming if inv_item else 0
        item['reserved_stock'] = inv_item.quantity_reserved if inv_item else 0
        results.append(item)

    return jsonify({'inventory': results, 'total': len(results)}), 200

@inventory_bp.route('/health', methods=['GET'])
def get_inventory_health():
    data = InventoryService.get_inventory_health()
    return jsonify(data), 200

@inventory_bp.route('/fast-moving', methods=['GET'])
def get_fast_moving():
    limit = request.args.get('limit', 10, type=int)
    data = InventoryService.get_fast_moving_products(limit)
    return jsonify({'products': data}), 200

@inventory_bp.route('/slow-moving', methods=['GET'])
def get_slow_moving():
    limit = request.args.get('limit', 10, type=int)
    data = InventoryService.get_slow_moving_products(limit)
    return jsonify({'products': data}), 200

@inventory_bp.route('/stockouts', methods=['GET'])
def get_stockouts():
    data = InventoryService.get_stockout_predictions()
    return jsonify({'risks': data}), 200

@inventory_bp.route('/overstock', methods=['GET'])
def get_overstock():
    data = InventoryService.get_overstock_detection()
    return jsonify({'items': data}), 200

@inventory_bp.route('/movements', methods=['GET'])
def get_movements():
    movements = InventoryMovement.query.order_by(InventoryMovement.timestamp.desc()).limit(50).all()
    return jsonify({'movements': [m.to_dict() for m in movements]}), 200

@inventory_bp.route('/adjust', methods=['POST'])
@role_required('Admin', 'Manager')
def adjust_stock():
    data = request.get_json() or {}
    product_id = data.get('product_id')
    new_quantity = data.get('new_quantity')
    reason = data.get('reason', 'Manual physical audit adjustment')

    if product_id is None or new_quantity is None:
        return jsonify({'error': 'Product ID and new quantity are required'}), 400

    product = Product.query.get_or_404(product_id)
    prev_qty = product.current_stock
    product.current_stock = int(new_quantity)
    product.status = product.compute_status()

    # Movement
    diff = int(new_quantity) - prev_qty
    movement = InventoryMovement(
        product_id=product.id,
        movement_type='ADJUSTMENT',
        quantity=abs(diff),
        previous_quantity=prev_qty,
        new_quantity=product.current_stock,
        reference_id='AUDIT-ADJUST',
        reference_type='Manual',
        note=f"{reason} (Change: {diff:+d})"
    )
    db.session.add(movement)

    # Audit log
    log = AuditLog(
        action='STOCK_ADJUSTMENT',
        entity='Product',
        entity_id=str(product.id),
        details=f"Stock adjusted for {product.name} from {prev_qty} to {new_quantity}. Reason: {reason}"
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'message': 'Inventory successfully adjusted',
        'product': product.to_dict()
    }), 200
