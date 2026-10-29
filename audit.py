from datetime import datetime
from .base import db

class AuditSession(db.Model):
    __tablename__ = 'audit_sessions'

    id = db.Column(db.Integer, primary_key=True)
    session_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    warehouse_name = db.Column(db.String(100), default='Central Warehouse')
    auditor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(50), default='In Progress')  # 'In Progress', 'Completed', 'Reconciled'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    auditor = db.relationship('User', foreign_keys=[auditor_id], lazy=True)
    items = db.relationship('AuditSessionItem', backref='session', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        items_list = self.items or []
        total_items = len(items_list)
        matched = sum(1 for it in items_list if it.status == 'Matched')
        shortage = sum(1 for it in items_list if it.status == 'Shortage')
        excess = sum(1 for it in items_list if it.status == 'Excess')
        resolved = sum(1 for it in items_list if it.status == 'Resolved')
        unresolved = sum(1 for it in items_list if it.status in ['Shortage', 'Excess', 'Pending Verification'])

        return {
            'id': self.id,
            'session_code': self.session_code,
            'title': self.title,
            'warehouse_name': self.warehouse_name,
            'auditor_id': self.auditor_id,
            'auditor_name': self.auditor.full_name if self.auditor else 'Auditor Staff',
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'total_items': total_items,
            'matched_items': matched,
            'shortage_items': shortage,
            'excess_items': excess,
            'resolved_items': resolved,
            'unresolved_items': unresolved,
            'items': [it.to_dict() for it in items_list]
        }

class AuditSessionItem(db.Model):
    __tablename__ = 'audit_session_items'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('audit_sessions.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    recorded_stock = db.Column(db.Integer, nullable=False, default=0)
    physical_stock = db.Column(db.Integer, nullable=False, default=0)
    difference = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(50), default='Pending Verification')  # 'Matched', 'Shortage', 'Excess', 'Pending Verification', 'Resolved'
    discrepancy_reason = db.Column(db.String(255), nullable=True)  # 'Theft', 'Damage', 'Data Entry Error', 'Unrecorded Sale', 'Supplier Miscount', 'Other'
    corrective_action = db.Column(db.Text, nullable=True)
    is_adjusted = db.Column(db.Boolean, default=False)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', lazy=True)
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id], lazy=True)

    def calculate_status(self):
        diff = self.physical_stock - self.recorded_stock
        self.difference = diff
        if self.is_adjusted:
            return 'Resolved'
        if diff == 0:
            return 'Matched'
        elif diff < 0:
            return 'Shortage'
        else:
            return 'Excess'

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'product_id': self.product_id,
            'product_sku': self.product.sku if self.product else '',
            'product_name': self.product.name if self.product else 'Unknown',
            'product_image': self.product.image_url if self.product else None,
            'category_name': self.product.category.name if (self.product and self.product.category) else 'General',
            'unit_cost': self.product.cost_price if self.product else 0.0,
            'selling_price': self.product.selling_price if self.product else 0.0,
            'recorded_stock': self.recorded_stock,
            'physical_stock': self.physical_stock,
            'difference': self.difference,
            'discrepancy_value': round(abs(self.difference) * (self.product.cost_price if self.product else 0.0), 2),
            'status': self.status,
            'discrepancy_reason': self.discrepancy_reason,
            'corrective_action': self.corrective_action,
            'is_adjusted': self.is_adjusted,
            'resolved_by_name': self.resolved_by.full_name if self.resolved_by else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class DataUpload(db.Model):
    __tablename__ = 'data_uploads'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), default='csv')
    upload_type = db.Column(db.String(50), default='retail_dataset')
    row_count = db.Column(db.Integer, default=0)
    valid_count = db.Column(db.Integer, default=0)
    invalid_count = db.Column(db.Integer, default=0)
    duplicate_count = db.Column(db.Integer, default=0)
    quality_score = db.Column(db.Float, default=100.0)
    column_mappings = db.Column(db.Text, nullable=True)  # JSON
    summary_metrics = db.Column(db.Text, nullable=True)  # JSON
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    uploaded_by = db.relationship('User', lazy=True)

    def to_dict(self):
        import json
        mappings = {}
        metrics = {}
        try:
            if self.column_mappings:
                mappings = json.loads(self.column_mappings)
            if self.summary_metrics:
                metrics = json.loads(self.summary_metrics)
        except Exception:
            pass

        return {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'upload_type': self.upload_type,
            'row_count': self.row_count,
            'valid_count': self.valid_count,
            'invalid_count': self.invalid_count,
            'duplicate_count': self.duplicate_count,
            'quality_score': round(self.quality_score, 1),
            'column_mappings': mappings,
            'summary_metrics': metrics,
            'uploaded_by_name': self.uploaded_by.full_name if self.uploaded_by else 'System AI',
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class ReportLog(db.Model):
    __tablename__ = 'report_logs'

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(100), nullable=False, index=True)
    report_title = db.Column(db.String(255), nullable=False)
    filters_json = db.Column(db.Text, nullable=True)  # JSON
    export_format = db.Column(db.String(20), default='preview')  # 'csv', 'pdf', 'preview'
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(50), default='Completed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    generated_by = db.relationship('User', lazy=True)

    def to_dict(self):
        import json
        filters = {}
        try:
            if self.filters_json:
                filters = json.loads(self.filters_json)
        except Exception:
            pass

        return {
            'id': self.id,
            'report_type': self.report_type,
            'report_title': self.report_title,
            'filters': filters,
            'export_format': self.export_format,
            'generated_by_name': self.generated_by.full_name if self.generated_by else 'System AI',
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
