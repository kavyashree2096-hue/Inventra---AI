import os
import io
import csv
import json
import pandas as pd
from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename
from models import db, DataUpload, Product, Category
from services.data_analysis_service import DataAnalysisService
from utils.rbac import role_required, get_current_authenticated_user

data_analysis_bp = Blueprint('data_analysis', __name__, url_prefix='/api/data-analysis')

UPLOAD_TEMP_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'uploads')
os.makedirs(UPLOAD_TEMP_DIR, exist_ok=True)

@data_analysis_bp.route('/upload', methods=['POST'])
@role_required('Admin', 'Manager')
def upload_file_preview():
    """
    Accepts CSV or Excel file, stores securely, parses sample rows, column types,
    and returns column list with intelligent mapping suggestions.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'error': 'Invalid filename'}), 400

    temp_path = os.path.join(UPLOAD_TEMP_DIR, f"temp_{filename}")
    file.save(temp_path)

    try:
        with open(temp_path, 'rb') as f:
            inspection = DataAnalysisService.inspect_file(f, filename)
        inspection['file_token'] = f"temp_{filename}"
        return jsonify(inspection), 200
    except Exception as e:
        return jsonify({'error': f"Failed to parse dataset: {str(e)}"}), 400

@data_analysis_bp.route('/validate', methods=['POST'])
@role_required('Admin', 'Manager')
def validate_dataset():
    """
    Validates uploaded dataset with user-confirmed column mappings,
    detects missing/duplicate/invalid records and computes Data Quality Score.
    """
    data = request.get_json() or {}
    file_token = data.get('file_token')
    mappings = data.get('mappings', {})

    if not file_token:
        return jsonify({'error': 'Missing file_token'}), 400

    temp_path = os.path.join(UPLOAD_TEMP_DIR, file_token)
    if not os.path.exists(temp_path):
        return jsonify({'error': 'Uploaded file session expired. Please re-upload.'}), 400

    try:
        if file_token.lower().endswith('.csv'):
            df = pd.read_csv(temp_path)
        else:
            df = pd.read_excel(temp_path)

        user = get_current_authenticated_user()
        user_id = user.id if user else None

        analysis_res = DataAnalysisService.validate_and_analyze_dataset(
            df=df,
            mappings=mappings,
            filename=file_token.replace('temp_', ''),
            user_id=user_id
        )

        return jsonify(analysis_res), 200
    except Exception as e:
        return jsonify({'error': f"Validation error: {str(e)}"}), 400

@data_analysis_bp.route('/eda', methods=['GET'])
def get_eda():
    """
    Returns descriptive statistics, revenue and quantity distributions,
    category breakdowns, and correlation matrix.
    """
    eda_data = DataAnalysisService.get_system_eda()
    return jsonify(eda_data), 200

@data_analysis_bp.route('/business', methods=['GET'])
def get_business_analysis():
    """
    Returns inventory velocity, stock turnover ratio, fast/slow moving products, and COGS.
    """
    biz_data = DataAnalysisService.get_business_analytics()
    return jsonify(biz_data), 200

@data_analysis_bp.route('/history', methods=['GET'])
def get_upload_history():
    """
    Returns list of analyzed datasets with data quality scores and timestamps.
    """
    uploads = DataUpload.query.order_by(DataUpload.created_at.desc()).limit(20).all()
    return jsonify({'uploads': [u.to_dict() for u in uploads]}), 200

@data_analysis_bp.route('/export', methods=['GET'])
@role_required('Admin', 'Manager')
def export_eda_report():
    """
    Generates CSV export of descriptive statistics and data quality metrics.
    """
    eda = DataAnalysisService.get_system_eda()
    biz = DataAnalysisService.get_business_analytics()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['=== INVENTRA AI EXPLORATORY DATA ANALYSIS (EDA) REPORT ==='])
    writer.writerow(['Metric Category', 'Field', 'Count', 'Mean', 'Median', 'Std Dev', 'Min', 'Max', 'Q1 (25%)', 'Q3 (75%)', 'IQR'])

    stats = eda.get('descriptive_statistics', {})
    for field_name, s in stats.items():
        writer.writerow([
            'Descriptive Stats', field_name, s['count'], s['mean'], s['median'],
            s['std'], s['min'], s['max'], s['q1'], s['q3'], s['iqr']
        ])

    writer.writerow([])
    writer.writerow(['=== BUSINESS ANALYTICS & VELOCITY ==='])
    writer.writerow(['Stock Turnover Ratio', f"{biz.get('stock_turnover_ratio')}x", 'Health', biz.get('turnover_health')])
    writer.writerow(['Cost of Goods Sold (COGS)', f"INR {biz.get('cost_of_goods_sold'):,.2f}"])
    writer.writerow(['Inventory Holding Capital', f"INR {biz.get('inventory_holding_value'):,.2f}"])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=inventra_data_analysis_eda.csv'}
    )
