from datetime import datetime
from .base import db

class PurchaseRequisition(db.Model):
    __tablename__ = 'purchase_requisitions'

    id = db.Column(db.Integer, primary_key=True)
    requisition_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    requested_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='Pending') # Pending, Approved, Rejected, Converted to PO
    reason = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(30), default='Medium') # Critical, High, Medium, Low
    approval_notes = db.Column(db.Text, nullable=True)

    requested_by = db.relationship('User', backref='requisitions', lazy=True)
    items = db.relationship('PurchaseRequisitionItem', backref='requisition', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        total_est = sum(item.estimated_cost for item in self.items) if self.items else 0
        return {
            'id': self.id,
            'requisition_number': self.requisition_number,
            'requested_by_id': self.requested_by_id,
            'requested_by_name': self.requested_by.full_name if self.requested_by else 'System AI',
            'requested_date': self.requested_date.isoformat() if self.requested_date else None,
            'status': self.status,
            'reason': self.reason,
            'priority': self.priority,
            'approval_notes': self.approval_notes,
            'items_count': len(self.items) if self.items else 0,
            'total_estimated_cost': round(total_est, 2),
            'items': [item.to_dict() for item in self.items] if self.items else []
        }

class PurchaseRequisitionItem(db.Model):
    __tablename__ = 'purchase_requisition_items'

    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('purchase_requisitions.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    estimated_cost = db.Column(db.Float, default=0.0)

    product = db.relationship('Product', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'requisition_id': self.requisition_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'quantity': self.quantity,
            'estimated_cost': round(self.estimated_cost, 2)
        }

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_delivery = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='Draft') # Draft, Pending Approval, Approved, Ordered, In Transit, Received, Cancelled, Delayed
    total_amount = db.Column(db.Float, default=0.0, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')
    delivery = db.relationship('Delivery', backref='purchase_order', uselist=False, lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'po_number': self.po_number,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else 'Unknown',
            'supplier_company': self.supplier.company if self.supplier else 'Unknown',
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'expected_delivery': self.expected_delivery.isoformat() if self.expected_delivery else None,
            'status': self.status,
            'total_amount': round(self.total_amount, 2),
            'notes': self.notes,
            'items_count': len(self.items) if self.items else 0,
            'items': [item.to_dict() for item in self.items] if self.items else [],
            'delivery': self.delivery.to_dict() if self.delivery else None
        }

class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)

    product = db.relationship('Product', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'po_id': self.po_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else 'Unknown',
            'product_sku': self.product.sku if self.product else '',
            'product_image': self.product.image_url if self.product else None,
            'quantity': self.quantity,
            'unit_price': round(self.unit_price, 2),
            'total_price': round(self.total_price, 2)
        }

class Delivery(db.Model):
    __tablename__ = 'deliveries'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    delivery_date = db.Column(db.DateTime, nullable=True) # scheduled/expected
    actual_delivery_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='Scheduled') # Scheduled, Shipped, In Transit, Delivered, Delayed, Cancelled
    delay_days = db.Column(db.Integer, default=0)
    received_qty = db.Column(db.Integer, default=0)
    damaged_qty = db.Column(db.Integer, default=0)
    tracking_number = db.Column(db.String(100), nullable=True)
    carrier = db.Column(db.String(100), default='Express Freight')
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'po_id': self.po_id,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None,
            'actual_delivery_date': self.actual_delivery_date.isoformat() if self.actual_delivery_date else None,
            'status': self.status,
            'delay_days': self.delay_days,
            'received_qty': self.received_qty,
            'damaged_qty': self.damaged_qty,
            'tracking_number': self.tracking_number,
            'carrier': self.carrier,
            'notes': self.notes
        }
