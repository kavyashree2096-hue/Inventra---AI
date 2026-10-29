from datetime import datetime
from .base import db

class Store(db.Model):
    __tablename__ = 'stores'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    city = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sales = db.relationship('Sale', backref='store', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'city': self.city,
            'location': self.location
        }

class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    total_amount = db.Column(db.Float, default=0.0, nullable=False)
    discount_amount = db.Column(db.Float, default=0.0)
    net_amount = db.Column(db.Float, default=0.0, nullable=False)
    payment_method = db.Column(db.String(50), default='Credit Card')
    status = db.Column(db.String(30), default='Completed')

    items = db.relationship('SaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'store_id': self.store_id,
            'store_name': self.store.name if self.store else 'Unknown',
            'sale_date': self.sale_date.isoformat() if self.sale_date else None,
            'total_amount': round(self.total_amount, 2),
            'discount_amount': round(self.discount_amount, 2),
            'net_amount': round(self.net_amount, 2),
            'payment_method': self.payment_method,
            'status': self.status,
            'item_count': len(self.items) if self.items else 0
        }

class SaleItem(db.Model):
    __tablename__ = 'sale_items'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'sale_id': self.sale_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'quantity': self.quantity,
            'unit_price': round(self.unit_price, 2),
            'cost_price': round(self.cost_price, 2),
            'total_price': round(self.total_price, 2)
        }
