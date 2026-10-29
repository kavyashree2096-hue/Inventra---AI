from datetime import datetime
from .base import db

class Warehouse(db.Model):
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    capacity_units = db.Column(db.Integer, default=50000)
    status = db.Column(db.String(30), default='Active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'location': self.location,
            'capacity_units': self.capacity_units,
            'status': self.status
        }

class InventoryItem(db.Model):
    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity_on_hand = db.Column(db.Integer, default=0, nullable=False)
    quantity_reserved = db.Column(db.Integer, default=0, nullable=False)
    quantity_incoming = db.Column(db.Integer, default=0, nullable=False)
    last_restocked_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = db.relationship('Product', backref='inventory_records', lazy=True)
    warehouse = db.relationship('Warehouse', backref='inventory_items', lazy=True)

    def to_dict(self):
        available = max(0, self.quantity_on_hand - self.quantity_reserved)
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'warehouse_id': self.warehouse_id,
            'warehouse_name': self.warehouse.name if self.warehouse else 'Central',
            'quantity_on_hand': self.quantity_on_hand,
            'quantity_reserved': self.quantity_reserved,
            'quantity_incoming': self.quantity_incoming,
            'available_quantity': available,
            'last_restocked_at': self.last_restocked_at.isoformat() if self.last_restocked_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class InventoryMovement(db.Model):
    __tablename__ = 'inventory_movements'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    movement_type = db.Column(db.String(50), nullable=False) # 'IN', 'OUT', 'ADJUSTMENT', 'TRANSFER', 'PO_RECEIPT'
    quantity = db.Column(db.Integer, nullable=False)
    previous_quantity = db.Column(db.Integer, default=0)
    new_quantity = db.Column(db.Integer, default=0)
    reference_id = db.Column(db.String(100), nullable=True)
    reference_type = db.Column(db.String(50), nullable=True) # 'PurchaseOrder', 'Sale', 'Manual'
    note = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    product = db.relationship('Product', backref='movements', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_image': self.product.image_url if self.product else None,
            'movement_type': self.movement_type,
            'quantity': self.quantity,
            'previous_quantity': self.previous_quantity,
            'new_quantity': self.new_quantity,
            'reference_id': self.reference_id,
            'reference_type': self.reference_type,
            'note': self.note,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }
