import io
import csv
from datetime import datetime
from flask import Blueprint, request, jsonify, Response
from models import db, AuditSession, AuditSessionItem, AuditLog, Product, Category, User
from services.audit_service import AuditService
from utils.rbac import role_required, get_current_authenticated_user

audit_bp = Blueprint('audit', __name__, url_prefix='/api/audit')

@audit_bp.route('/summary', methods=['GET'])
def get_summary():
    """
    Returns audit KPI summary cards and health breakdown.
    """
    AuditService.seed_initial_audit_data()
    summary = AuditService.get_audit_summary()
    return jsonify(summary), 200

@audit_bp.route('/sessions', methods=['GET'])
def get_sessions():
    """
    List all inventory audit sessions.
    """
    AuditService.seed_initial_audit_data()
    status_filter = request.args.get('status')
    query = AuditSession.query
    if status_filter and status_filter != 'All':
        query = query.filter_by(status=status_filter)

    sessions = query.order_by(AuditSession.created_at.desc()).all()
    return jsonify({'sessions': [s.to_dict() for s in sessions]}), 200

@audit_bp.route('/sessions/<int:session_id>', methods=['GET'])
def get_session_detail(session_id):
    """
    Returns complete session detail with all item verification records.
    """
    session = AuditSession.query.get_or_404(session_id)
    return jsonify({'session': session.to_dict()}), 200

@audit_bp.route('/sessions', methods=['POST'])
@role_required('Admin', 'Manager')
def create_session():
    """
    Creates a new inventory audit session with snapshot of stock records.
    """
    data = request.get_json() or {}
    user = get_current_authenticated_user()
    user_id = user.id if user else None

    session_data = AuditService.create_audit_session(data, user_id=user_id)
    return jsonify({'message': 'Audit session initiated successfully', 'session': session_data}), 201

@audit_bp.route('/sessions/<int:session_id>/items/<int:item_id>', methods=['PUT'])
@role_required('Admin', 'Manager', 'Staff')
def update_item_count(session_id, item_id):
    """
    Updates physical verified stock quantity for an item.
    Formula: Stock Difference = Actual Stock - Recorded Stock
    """
    data = request.get_json() or {}
    if 'physical_stock' not in data:
        return jsonify({'error': 'physical_stock count is required'}), 400

    user = get_current_authenticated_user()
    user_id = user.id if user else None

    item_data = AuditService.update_session_item(
        item_id=item_id,
        physical_stock=int(data['physical_stock']),
        reason=data.get('discrepancy_reason'),
        corrective_action=data.get('corrective_action'),
        user_id=user_id
    )

    if not item_data:
        return jsonify({'error': 'Audit item not found'}), 404

    return jsonify({'message': 'Verified count updated', 'item': item_data}), 200

@audit_bp.route('/sessions/<int:session_id>/resolve-item/<int:item_id>', methods=['POST'])
@role_required('Admin', 'Manager')
def resolve_item(session_id, item_id):
    """
    Authorized reconciliation: Updates physical inventory stock and creates audit log.
    Requires Admin or Manager role.
    """
    data = request.get_json() or {}
    action = data.get('corrective_action', 'Authorized inventory physical adjustment')
    user = get_current_authenticated_user()
    user_id = user.id if user else None

    try:
        resolved_item = AuditService.resolve_discrepancy(item_id, authorized_user_id=user_id, corrective_action=action)
        return jsonify({
            'message': 'Discrepancy resolved and inventory adjusted in system!',
            'item': resolved_item
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@audit_bp.route('/sessions/<int:session_id>/import-csv', methods=['POST'])
@role_required('Admin', 'Manager')
def import_csv_counts(session_id):
    """
    Imports physically counted stock numbers from CSV.
    Expected CSV columns: sku (or product_id), physical_stock, reason (optional)
    """
    session = AuditSession.query.get_or_404(session_id)
    if 'file' not in request.files:
        return jsonify({'error': 'No CSV file provided'}), 400

    file = request.files['file']
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        rows = list(reader)
    except Exception as e:
        return jsonify({'error': f"Failed to read CSV: {str(e)}"}), 400

    updated = 0
    errors = []
    items_by_sku = {it.product.sku.lower(): it for it in session.items if it.product}

    for idx, r in enumerate(rows):
        r_norm = {k.lower().strip() if k else '': v for k, v in r.items()}
        sku = str(r_norm.get('sku', '') or r_norm.get('product_sku', '')).strip().lower()
        qty_str = r_norm.get('physical_stock') or r_norm.get('actual_stock') or r_norm.get('quantity')

        if not sku or not qty_str:
            errors.append(f"Row {idx+1}: Missing SKU or physical stock quantity.")
            continue

        try:
            qty = int(qty_str)
        except ValueError:
            errors.append(f"Row {idx+1}: Invalid quantity '{qty_str}'.")
            continue

        item = items_by_sku.get(sku)
        if not item:
            errors.append(f"Row {idx+1}: SKU '{sku}' not part of this audit session.")
            continue

        item.physical_stock = qty
        item.difference = qty - item.recorded_stock
        item.status = 'Matched' if item.difference == 0 else ('Shortage' if item.difference < 0 else 'Excess')
        if r_norm.get('reason'):
            item.discrepancy_reason = r_norm.get('reason')
        updated += 1

    db.session.commit()
    return jsonify({
        'message': f"Imported {updated} physical verified counts.",
        'updated_count': updated,
        'warnings': errors[:10]
    }), 200

@audit_bp.route('/sales-audit', methods=['GET'])
def get_sales_audit():
    """
    Runs automated sales transaction validation audit.
    """
    result = AuditService.perform_sales_audit()
    return jsonify(result), 200

@audit_bp.route('/activity-logs', methods=['GET'])
def get_activity_logs():
    """
    Returns system activity audit logs with search, entity filters, and pagination.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    action_filter = request.args.get('action')
    entity_filter = request.args.get('entity')
    search = request.args.get('search')

    query = AuditLog.query
    if action_filter and action_filter != 'All':
        query = query.filter_by(action=action_filter)
    if entity_filter and entity_filter != 'All':
        query = query.filter_by(entity=entity_filter)
    if search:
        query = query.filter(AuditLog.details.ilike(f"%{search}%"))

    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'logs': [l.to_dict() for l in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': pagination.page
    }), 200

@audit_bp.route('/charts', methods=['GET'])
def get_audit_charts():
    """
    Returns datasets for all 5 audit visualizations.
    """
    data = AuditService.get_audit_charts_data()
    return jsonify(data), 200

@audit_bp.route('/export', methods=['GET'])
@role_required('Admin', 'Manager')
def export_audit_csv():
    """
    Generates CSV export of audit records.
    """
    session_id = request.args.get('session_id', type=int)
    output = io.StringIO()
    writer = csv.writer(output)

    if session_id:
        session = AuditSession.query.get_or_404(session_id)
        writer.writerow(['Session Code', 'Title', 'Product SKU', 'Product Name', 'Category', 'Recorded Stock', 'Physical Stock', 'Difference', 'Status', 'Reason', 'Corrective Action', 'Resolution Status'])
        for it in session.items:
            writer.writerow([
                session.session_code,
                session.title,
                it.product.sku if it.product else '',
                it.product.name if it.product else '',
                it.product.category.name if (it.product and it.product.category) else '',
                it.recorded_stock,
                it.physical_stock,
                it.difference,
                it.status,
                it.discrepancy_reason or '',
                it.corrective_action or '',
                'Resolved' if it.is_adjusted else 'Unresolved'
            ])
        filename = f"audit_session_{session.session_code}.csv"
    else:
        # Export all items
        writer.writerow(['Audit Code', 'Product SKU', 'Product Name', 'Recorded Stock', 'Physical Stock', 'Difference', 'Status', 'Reason', 'Corrective Action'])
        items = AuditSessionItem.query.all()
        for it in items:
            writer.writerow([
                it.session.session_code if it.session else '',
                it.product.sku if it.product else '',
                it.product.name if it.product else '',
                it.recorded_stock,
                it.physical_stock,
                it.difference,
                it.status,
                it.discrepancy_reason or '',
                it.corrective_action or ''
            ])
        filename = "inventory_audit_master.csv"

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f"attachment;filename={filename}"}
    )
