from flask import Blueprint, request, jsonify
from models import db, Supplier, SupplierProduct
from services.supplier_service import SupplierService

supplier_bp = Blueprint('suppliers', __name__, url_prefix='/api/suppliers')

@supplier_bp.route('', methods=['GET'])
def get_suppliers():
    suppliers = SupplierService.get_all_suppliers()
    return jsonify({'suppliers': suppliers, 'total': len(suppliers)}), 200

@supplier_bp.route('/<int:supplier_id>', methods=['GET'])
def get_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    data = supplier.to_dict()
    data['products'] = [sp.to_dict() for sp in supplier.products_supplied]
    return jsonify({'supplier': data}), 200

@supplier_bp.route('', methods=['POST'])
def create_supplier():
    data = request.get_json() or {}
    required = ['name', 'company', 'email']
    for f in required:
        if f not in data:
            return jsonify({'error': f'Field {f} is required'}), 400

    supplier = Supplier(
        name=data['name'],
        company=data['company'],
        contact_person=data.get('contact_person', ''),
        email=data['email'],
        phone=data.get('phone', ''),
        address=data.get('address', ''),
        rating=float(data.get('rating', 4.5)),
        reliability_score=float(data.get('reliability_score', 90.0)),
        lead_time_days=int(data.get('lead_time_days', 5)),
        active_status=bool(data.get('active_status', True))
    )
    db.session.add(supplier)
    db.session.commit()
    return jsonify({'message': 'Supplier created successfully', 'supplier': supplier.to_dict()}), 201

@supplier_bp.route('/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.get_json() or {}

    fields = ['name', 'company', 'contact_person', 'email', 'phone', 'address',
              'rating', 'reliability_score', 'lead_time_days', 'active_status']
    for f in fields:
        if f in data:
            setattr(supplier, f, data[f])

    db.session.commit()
    return jsonify({'message': 'Supplier updated successfully', 'supplier': supplier.to_dict()}), 200

@supplier_bp.route('/compare/<int:product_id>', methods=['GET'])
def compare_suppliers(product_id):
    comparison = SupplierService.compare_suppliers_for_product(product_id)
    if not comparison:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'comparison': comparison}), 200
