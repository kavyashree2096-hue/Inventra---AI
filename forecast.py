from datetime import datetime
from .base import db

class DemandForecast(db.Model):
    __tablename__ = 'demand_forecasts'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=True)
    forecast_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    forecast_period = db.Column(db.String(20), default='weekly') # daily, weekly, monthly
    predicted_demand = db.Column(db.Float, nullable=False)
    actual_demand = db.Column(db.Float, nullable=True)
    demand_change_pct = db.Column(db.Float, default=0.0)
    demand_status = db.Column(db.String(30), default='Normal Demand') # High Demand, Normal Demand, Low Demand
    confidence_score = db.Column(db.Float, default=0.92) # e.g. 0.94
    recommended_action = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'current_stock': self.product.current_stock if self.product else 0,
            'safety_stock': self.product.safety_stock if self.product else 0,
            'forecast_date': self.forecast_date.strftime('%Y-%m-%d') if self.forecast_date else None,
            'forecast_period': self.forecast_period,
            'predicted_demand': round(self.predicted_demand, 1),
            'actual_demand': round(self.actual_demand, 1) if self.actual_demand is not None else None,
            'demand_change_pct': round(self.demand_change_pct, 1),
            'demand_status': self.demand_status,
            'confidence_score': round(self.confidence_score * 100, 1),
            'recommended_action': self.recommended_action
        }

class ModelMetric(db.Model):
    __tablename__ = 'model_metrics'

    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(100), nullable=False) # 'Random Forest Regressor', 'Gradient Boosting', 'XGBoost'
    mae = db.Column(db.Float, nullable=False)
    rmse = db.Column(db.Float, nullable=False)
    mape = db.Column(db.Float, nullable=False) # e.g. 8.4%
    r2_score = db.Column(db.Float, default=0.91)
    trained_at = db.Column(db.DateTime, default=datetime.utcnow)
    parameters = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'model_name': self.model_name,
            'mae': round(self.mae, 2),
            'rmse': round(self.rmse, 2),
            'mape': round(self.mape, 2),
            'r2_score': round(self.r2_score, 3) if self.r2_score else 0.91,
            'trained_at': self.trained_at.isoformat() if self.trained_at else None,
            'parameters': self.parameters
        }

class ReorderRecommendation(db.Model):
    __tablename__ = 'reorder_recommendations'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    current_stock = db.Column(db.Integer, nullable=False)
    predicted_demand = db.Column(db.Float, nullable=False)
    safety_stock = db.Column(db.Integer, default=15)
    reorder_point = db.Column(db.Integer, default=25)
    reorder_quantity = db.Column(db.Integer, nullable=False)
    reorder_date = db.Column(db.DateTime, default=datetime.utcnow)
    priority = db.Column(db.String(30), default='Medium') # Critical, High, Medium, Low
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='Pending') # Pending, Processed, Dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'category_name': self.product.category.name if self.product and self.product.category else 'General',
            'current_stock': self.current_stock,
            'safety_stock': self.safety_stock,
            'reorder_point': self.reorder_point,
            'predicted_demand': round(self.predicted_demand, 1),
            'reorder_quantity': self.reorder_quantity,
            'reorder_date': self.reorder_date.strftime('%Y-%m-%d') if self.reorder_date else None,
            'priority': self.priority,
            'reason': self.reason,
            'status': self.status,
            'lead_time_days': self.product.lead_time_days if self.product else 3
        }

class ProcurementRecommendation(db.Model):
    __tablename__ = 'procurement_recommendations'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    recommended_supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    current_stock = db.Column(db.Integer, default=0)
    predicted_demand = db.Column(db.Float, default=0.0)
    safety_stock = db.Column(db.Integer, default=15)
    recommended_quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    estimated_cost = db.Column(db.Float, nullable=False)
    priority = db.Column(db.String(30), default='High') # Critical, High, Medium, Low
    lead_time_days = db.Column(db.Integer, default=4)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='Open') # Open, PO Created, Ignored
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.relationship('Supplier', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'category_name': self.product.category.name if self.product and self.product.category else 'General',
            'current_stock': self.current_stock,
            'predicted_demand': round(self.predicted_demand, 1),
            'safety_stock': self.safety_stock,
            'recommended_quantity': self.recommended_quantity,
            'unit_cost': round(self.unit_cost, 2),
            'estimated_cost': round(self.estimated_cost, 2),
            'priority': self.priority,
            'lead_time_days': self.lead_time_days,
            'reason': self.reason,
            'status': self.status,
            'supplier_id': self.recommended_supplier_id,
            'supplier_name': self.supplier.name if self.supplier else 'Best Available Supplier',
            'supplier_rating': self.supplier.rating if self.supplier else 4.5
        }
