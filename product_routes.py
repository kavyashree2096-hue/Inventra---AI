from flask import Blueprint, request, jsonify
from models import db, Product, Category, SupplierProduct, DemandForecast, SaleItem, AuditLog

product_bp = Blueprint('products', __name__, url_prefix='/api/products')

@product_bp.route('', methods=['GET'])
def get_products():
    category_id = request.args.get('category_id', type=int)
    status = request.args.get('status')
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'name') # name, stock_asc, stock_desc, price_asc, price_desc

    query = Product.query

    if category_id:
        query = query.filter_by(category_id=category_id)
    if status and status != 'All':
        query = query.filter_by(status=status)
    if search:
        query = query.filter(
            (Product.name.ilike(f'%{search}%')) |
            (Product.sku.ilike(f'%{search}%')) |
            (Product.description.ilike(f'%{search}%'))
        )

    if sort_by == 'stock_asc':
        query = query.order_by(Product.current_stock.asc())
    elif sort_by == 'stock_desc':
        query = query.order_by(Product.current_stock.desc())
    elif sort_by == 'price_asc':
        query = query.order_by(Product.selling_price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.selling_price.desc())
    else:
        query = query.order_by(Product.name.asc())

    products = query.all()
    return jsonify({'products': [p.to_dict() for p in products], 'total': len(products)}), 200

@product_bp.route('/<int:product_id>', methods=['GET'])
def get_product(product_id):
    product = Product.query.get_or_404(product_id)
    product_data = product.to_dict()

    # Associated suppliers
    suppliers = [sp.to_dict() for sp in product.supplier_links]
    
    # Associated forecasts
    forecasts = [f.to_dict() for f in product.forecasts[:8]]

    # Sales metrics
    total_sold = db.session.query(db.func.sum(SaleItem.quantity))\
        .filter_by(product_id=product.id).scalar() or 0
    total_rev = db.session.query(db.func.sum(SaleItem.total_price))\
        .filter_by(product_id=product.id).scalar() or 0.0

    product_data['suppliers'] = suppliers
    product_data['forecasts'] = forecasts
    product_data['total_units_sold'] = total_sold
    product_data['total_revenue_generated'] = round(float(total_rev), 2)

    return jsonify({'product': product_data}), 200

@product_bp.route('', methods=['POST'])
def create_product():
    data = request.get_json() or {}
    required = ['name', 'sku', 'category_id', 'selling_price', 'cost_price']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Field {field} is required'}), 400

    if Product.query.filter_by(sku=data['sku']).first():
        return jsonify({'error': 'Product with this SKU already exists'}), 409

    product = Product(
        sku=data['sku'],
        name=data['name'],
        description=data.get('description', ''),
        category_id=data['category_id'],
        image_url=data.get('image_url', 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=60'),
        selling_price=float(data['selling_price']),
        cost_price=float(data['cost_price']),
        current_stock=int(data.get('current_stock', 0)),
        min_stock=int(data.get('min_stock', 10)),
        max_stock=int(data.get('max_stock', 150)),
        safety_stock=int(data.get('safety_stock', 15)),
        reorder_point=int(data.get('reorder_point', 25)),
        warehouse=data.get('warehouse', 'Central Distribution Hub (North)'),
        lead_time_days=int(data.get('lead_time_days', 4)),
        unit=data.get('unit', 'Units')
    )
    product.status = product.compute_status()
    db.session.add(product)
    db.session.commit()

    return jsonify({'message': 'Product created successfully', 'product': product.to_dict()}), 201

@product_bp.route('/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json() or {}

    fields = ['name', 'description', 'category_id', 'image_url', 'selling_price',
              'cost_price', 'current_stock', 'min_stock', 'max_stock',
              'safety_stock', 'reorder_point', 'warehouse', 'lead_time_days', 'unit']

    for field in fields:
        if field in data:
            setattr(product, field, data[field])

    product.status = product.compute_status()
    db.session.commit()
    return jsonify({'message': 'Product updated successfully', 'product': product.to_dict()}), 200

@product_bp.route('/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted successfully'}), 200

# Category endpoints
@product_bp.route('/categories', methods=['GET'])
def get_categories():
    categories = Category.query.all()
    return jsonify({'categories': [c.to_dict() for c in categories]}), 200
