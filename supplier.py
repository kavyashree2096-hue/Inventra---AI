from datetime import datetime
from .base import db

class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, default=4.5) # out of 5.0
    reliability_score = db.Column(db.Float, default=92.0) # percentage
    delivery_performance_pct = db.Column(db.Float, default=94.0)
    lead_time_days = db.Column(db.Integer, default=5)
    active_status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products_supplied = db.relationship('SupplierProduct', backref='supplier', lazy=True, cascade='all, delete-orphan')
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'company': self.company,
            'contact_person': self.contact_person,
            'email': self.email,
            'phone': self.phone,
            'address': self.address,
            'rating': round(self.rating, 1),
            'reliability_score': round(self.reliability_score, 1),
            'delivery_performance_pct': round(self.delivery_performance_pct, 1),
            'lead_time_days': self.lead_time_days,
            'active_status': self.active_status,
            'products_count': len(self.products_supplied) if self.products_supplied else 0
        }

class SupplierProduct(db.Model):
    __tablename__ = 'supplier_products'

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    min_order_qty = db.Column(db.Integer, default=10)
    lead_time_days = db.Column(db.Integer, default=5)
    is_preferred = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else 'Unknown',
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'unit_price': round(self.unit_price, 2),
            'min_order_qty': self.min_order_qty,
            'lead_time_days': self.lead_time_days,
            'is_preferred': self.is_preferred,
            'supplier_rating': self.supplier.rating if self.supplier else 4.5,
            'reliability_score': self.supplier.reliability_score if self.supplier else 90.0
        }
