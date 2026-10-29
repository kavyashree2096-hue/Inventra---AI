from flask import Blueprint, request, jsonify
from models import db, User, AuditLog, SystemSetting
from utils.seed_data import seed_database
from utils.rbac import role_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/users', methods=['GET'])
@role_required('Admin')
def get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200

@admin_bp.route('/users/<int:user_id>/role', methods=['PUT'])
@role_required('Admin')
def update_user_role(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    new_role = data.get('role')
    new_status = data.get('status')

    if new_role and new_role in ['Admin', 'Manager', 'Staff']:
        user.role = new_role
    if new_status and new_status in ['Active', 'Inactive']:
        user.status = new_status

    db.session.commit()
    return jsonify({'message': 'User updated successfully', 'user': user.to_dict()}), 200

@admin_bp.route('/audit-logs', methods=['GET'])
@role_required('Admin')
def get_audit_logs():
    limit = request.args.get('limit', 100, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return jsonify({'logs': [l.to_dict() for l in logs]}), 200

@admin_bp.route('/settings', methods=['GET'])
@role_required('Admin')
def get_settings():
    settings = SystemSetting.query.all()
    data = {s.key: s.value for s in settings}
    # Defaults
    if 'model_name' not in data:
        data['model_name'] = 'Random Forest + Gradient Boosting'
    if 'ollama_model' not in data:
        data['ollama_model'] = 'llama3.2'
    if 'auto_reorder_enabled' not in data:
        data['auto_reorder_enabled'] = 'true'
    if 'currency' not in data:
        data['currency'] = '₹ (INR)'

    return jsonify({'settings': data}), 200

@admin_bp.route('/settings', methods=['POST'])
@role_required('Admin')
def save_settings():
    data = request.get_json() or {}
    for k, v in data.items():
        s = SystemSetting.query.get(k)
        if s:
            s.value = str(v)
        else:
            db.session.add(SystemSetting(key=k, value=str(v)))
    db.session.commit()
    return jsonify({'message': 'Settings updated successfully'}), 200

@admin_bp.route('/seed-reset', methods=['POST'])
@role_required('Admin')
def reset_seed():
    """
    Clears tables and reseeds fresh retail demo data.
    Restricted to System Administrators only.
    """
    try:
        db.drop_all()
        db.create_all()
        seed_database()
        return jsonify({'message': 'System database successfully re-initialized and seeded!'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
