from datetime import datetime
from .base import db

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('Product', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'product_count': len(self.products) if self.products else 0
        }

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    selling_price = db.Column(db.Float, nullable=False, default=0.0)
    cost_price = db.Column(db.Float, nullable=False, default=0.0)
    
    current_stock = db.Column(db.Integer, default=0, nullable=False)
    min_stock = db.Column(db.Integer, default=10, nullable=False)
    max_stock = db.Column(db.Integer, default=200, nullable=False)
    safety_stock = db.Column(db.Integer, default=15, nullable=False)
    reorder_point = db.Column(db.Integer, default=25, nullable=False)
    
    warehouse = db.Column(db.String(100), default='Central Warehouse')
    lead_time_days = db.Column(db.Integer, default=3)
    unit = db.Column(db.String(20), default='Units')
    status = db.Column(db.String(50), default='Healthy') # Healthy, Low Stock, Critical, Stock-Out, Overstock, Slow Moving, Fast Moving
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    images = db.relationship('ProductImage', backref='product', lazy=True, cascade='all, delete-orphan')
    supplier_links = db.relationship('SupplierProduct', backref='product', lazy=True, cascade='all, delete-orphan')
    sale_items = db.relationship('SaleItem', backref='product', lazy=True)
    forecasts = db.relationship('DemandForecast', backref='product', lazy=True)
    reorder_recs = db.relationship('ReorderRecommendation', backref='product', lazy=True)
    procurement_recs = db.relationship('ProcurementRecommendation', backref='product', lazy=True)

    def compute_status(self):
        if self.current_stock <= 0:
            return 'Stock-Out'
        elif self.current_stock <= (self.safety_stock / 2):
            return 'Critical'
        elif self.current_stock <= self.reorder_point:
            return 'Low Stock'
        elif self.current_stock >= self.max_stock:
            return 'Overstock'
        return 'Healthy'

    def to_dict(self):
        return {
            'id': self.id,
            'sku': self.sku,
            'name': self.name,
            'description': self.description,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else 'Uncategorized',
            'image_url': self.image_url or 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=60',
            'selling_price': round(self.selling_price, 2),
            'cost_price': round(self.cost_price, 2),
            'margin_pct': round(((self.selling_price - self.cost_price) / self.selling_price * 100), 1) if self.selling_price > 0 else 0,
            'current_stock': self.current_stock,
            'min_stock': self.min_stock,
            'max_stock': self.max_stock,
            'safety_stock': self.safety_stock,
            'reorder_point': self.reorder_point,
            'warehouse': self.warehouse,
            'lead_time_days': self.lead_time_days,
            'unit': self.unit,
            'status': self.status or self.compute_status(),
            'inventory_value': round(self.current_stock * self.cost_price, 2),
            'retail_value': round(self.current_stock * self.selling_price, 2),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class ProductImage(db.Model):
    __tablename__ = 'product_images'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
