from flask import Blueprint, request, jsonify
from models import db, DemandForecast, ModelMetric
from services.forecasting_service import ForecastingService
from services.reorder_service import ReorderService
from utils.rbac import role_required

forecast_bp = Blueprint('forecasts', __name__, url_prefix='/api/forecasts')

@forecast_bp.route('', methods=['GET'])
def get_forecasts():
    period = request.args.get('period', 'weekly') # daily, weekly, monthly
    status = request.args.get('status')
    product_id = request.args.get('product_id', type=int)

    query = DemandForecast.query.filter_by(forecast_period=period)
    if product_id:
        query = query.filter_by(product_id=product_id)
    if status and status != 'All':
        query = query.filter_by(demand_status=status)

    forecasts = query.order_by(DemandForecast.predicted_demand.desc()).all()
    return jsonify({
        'forecasts': [f.to_dict() for f in forecasts],
        'total': len(forecasts)
    }), 200

@forecast_bp.route('/models', methods=['GET'])
def get_models():
    metrics = ModelMetric.query.all()
    if not metrics:
        metrics_data = ForecastingService.retrain_models()
        metrics = ModelMetric.query.all()

    return jsonify({
        'models': [m.to_dict() for m in metrics]
    }), 200

@forecast_bp.route('/retrain', methods=['POST'])
@role_required('Admin', 'Manager')
def retrain_models():
    try:
        metrics = ForecastingService.retrain_models()
        count = ForecastingService.generate_all_forecasts()
        reorders = ReorderService.calculate_reorder_recommendations()
        return jsonify({
            'message': f'Forecasting models retrained successfully! Generated {count} forecasts and {len(reorders)} reorder recommendations.',
            'metrics': metrics
        }), 200
    except Exception as e:
        return jsonify({'error': f'Retraining failed: {str(e)}'}), 500

@forecast_bp.route('/reorders', methods=['GET'])
def get_reorders():
    reorders = ReorderService.get_all_reorders()
    return jsonify({'reorders': reorders, 'total': len(reorders)}), 200

@forecast_bp.route('/reorders/refresh', methods=['POST'])
@role_required('Admin', 'Manager')
def refresh_reorders():
    reorders = ReorderService.calculate_reorder_recommendations()
    return jsonify({
        'message': f'Calculated {len(reorders)} reorder recommendations!',
        'reorders': reorders
    }), 200
