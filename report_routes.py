from flask import Blueprint, request, jsonify, Response
from models import db, ReportLog
from services.report_service import ReportService
from utils.rbac import role_required, get_current_authenticated_user

report_bp = Blueprint('reports', __name__, url_prefix='/api/reports')

@report_bp.route('/types', methods=['GET'])
def get_report_types():
    """
    Returns list of all 10 supported report types with categories and descriptions.
    """
    return jsonify({'report_types': ReportService.REPORT_CATALOG}), 200

@report_bp.route('/summary', methods=['GET'])
def get_summary_report():
    data = ReportService.get_management_summary()
    current_user = get_current_authenticated_user()
    if current_user and current_user.role == 'Staff':
        if 'financial_overview' in data:
            data['financial_overview']['total_sales_value'] = 'Protected (Manager+)'
            data['financial_overview']['inventory_holding_cost'] = 'Protected (Manager+)'
            data['financial_overview']['gross_profit_margin'] = 'Protected (Manager+)'
        data['privacy_shield_active'] = True
    return jsonify({'report': data}), 200

@report_bp.route('/generate', methods=['POST'])
@role_required('Admin', 'Manager')
def generate_report():
    """
    Generates preview payload for any selected report type.
    """
    data = request.get_json() or {}
    report_type = data.get('report_type', 'revenue_analysis')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    category_id = data.get('category_id')
    product_id = data.get('product_id')

    user = get_current_authenticated_user()
    user_id = user.id if user else None

    rep_payload = ReportService.generate_report(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        product_id=product_id,
        user_id=user_id
    )

    return jsonify({'report': rep_payload}), 200

@report_bp.route('/export', methods=['GET'])
@role_required('Admin', 'Manager')
def export_csv_report():
    """
    Exports certified CSV for any of the 10 report types.
    """
    report_type = request.args.get('type', 'revenue_analysis')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)
    product_id = request.args.get('product_id', type=int)

    csv_content = ReportService.export_csv(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        product_id=product_id
    )

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=inventra_{report_type}_report.csv'}
    )

@report_bp.route('/history', methods=['GET'])
def get_report_history():
    """
    Returns history of generated reports.
    """
    history = ReportLog.query.order_by(ReportLog.created_at.desc()).limit(20).all()
    return jsonify({'history': [h.to_dict() for h in history]}), 200
