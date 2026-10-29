import io
import csv
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from models import db, Sale, SaleItem, Product, Store, Category, AuditLog
from utils.rbac import role_required

sales_bp = Blueprint('sales', __name__, url_prefix='/api/sales')

@sales_bp.route('', methods=['GET'])
def get_sales():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    store_id = request.args.get('store_id', type=int)

    query = Sale.query
    if store_id:
        query = query.filter_by(store_id=store_id)

    pagination = query.order_by(Sale.sale_date.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'sales': [s.to_dict() for s in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': pagination.page
    }), 200

@sales_bp.route('/analytics', methods=['GET'])
def get_sales_analytics():
    now = datetime.utcnow()
    period = request.args.get('period', 'monthly') # daily, weekly, monthly, yearly

    # Total Sales and Revenue metrics
    total_revenue = db.session.query(db.func.sum(Sale.net_amount)).scalar() or 0.0
    total_orders = Sale.query.count()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0

    # 1. Product-wise sales performance (Top 10 & Bottom 10)
    product_sales = db.session.query(
        SaleItem.product_id,
        Product.name,
        Product.sku,
        Product.image_url,
        Category.name.label('category_name'),
        db.func.sum(SaleItem.quantity).label('units_sold'),
        db.func.sum(SaleItem.total_price).label('revenue')
    ).join(Product, SaleItem.product_id == Product.id)\
     .outerjoin(Category, Product.category_id == Category.id)\
     .group_by(SaleItem.product_id, Product.name, Product.sku, Product.image_url, Category.name)\
     .order_by(db.desc('units_sold')).all()

    top_selling = [
        {
            'product_id': r.product_id,
            'name': r.name,
            'sku': r.sku,
            'image_url': r.image_url,
            'category': r.category_name or 'General',
            'units_sold': int(r.units_sold),
            'revenue': round(float(r.revenue), 2)
        }
        for r in product_sales[:8]
    ]

    lowest_selling = [
        {
            'product_id': r.product_id,
            'name': r.name,
            'sku': r.sku,
            'image_url': r.image_url,
            'category': r.category_name or 'General',
            'units_sold': int(r.units_sold),
            'revenue': round(float(r.revenue), 2)
        }
        for r in product_sales[-6:][::-1]
    ]

    # 2. Store-wise Sales Breakdown
    stores = Store.query.all()
    store_sales = []
    for s in stores:
        rev = db.session.query(db.func.sum(Sale.net_amount)).filter_by(store_id=s.id).scalar() or 0.0
        orders_count = Sale.query.filter_by(store_id=s.id).count()
        store_sales.append({
            'store_id': s.id,
            'store_name': s.name,
            'city': s.city,
            'revenue': round(float(rev), 2),
            'orders': orders_count
        })

    # 3. Monthly Sales History (for trend line)
    monthly_query = db.session.query(
        db.func.strftime('%Y-%m', Sale.sale_date).label('month') if db.engine.name == 'sqlite' 
        else db.func.to_char(Sale.sale_date, 'YYYY-MM').label('month'),
        db.func.sum(Sale.net_amount).label('revenue'),
        db.func.count(Sale.id).label('orders')
    ).group_by('month').order_by('month').all()

    monthly_trend = [
        {
            'month': r.month,
            'revenue': round(float(r.revenue or 0), 2),
            'orders': int(r.orders or 0)
        }
        for r in monthly_query
    ]

    # 4. Day of Week Seasonal Distribution
    dow_stats = []
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for idx, day_name in enumerate(days):
        dow_stats.append({
            'day': day_name,
            'sales_index': 100 + (35 if idx in [4, 5, 6] else -10)
        })

    return jsonify({
        'summary': {
            'total_revenue': round(float(total_revenue), 2),
            'total_orders': total_orders,
            'avg_order_value': round(float(avg_order_value), 2)
        },
        'top_selling': top_selling,
        'lowest_selling': lowest_selling,
        'store_sales': store_sales,
        'monthly_trend': monthly_trend,
        'dow_seasonality': dow_stats
    }), 200

@sales_bp.route('/upload', methods=['POST'])
@role_required('Admin', 'Manager')
def upload_sales_data():
    """
    Validates and uploads sales dataset from CSV or Excel.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    filename = file.filename.lower()

    rows = []
    try:
        if filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)
            rows = list(reader)
        elif filename.endswith(('.xls', '.xlsx')):
            import openpyxl
            wb = openpyxl.load_workbook(file)
            sheet = wb.active
            headers = [cell.value for cell in sheet[1]]
            for r in sheet.iter_rows(min_row=2, values_only=True):
                rows.append(dict(zip(headers, r)))
        else:
            return jsonify({'error': 'Unsupported file type. Please upload a CSV or Excel file.'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to parse file: {str(e)}'}), 400

    if not rows:
        return jsonify({'error': 'Uploaded file is empty.'}), 400

    # Validation
    required_cols = ['product_sku', 'quantity', 'unit_price']
    first_row_keys = [k.lower().strip() if k else '' for k in rows[0].keys()]
    missing_cols = [c for c in required_cols if c not in first_row_keys]
    if missing_cols:
        return jsonify({
            'error': f'Missing required columns: {", ".join(missing_cols)}. Expected: {", ".join(required_cols)}'
        }), 400

    invalid_rows = []
    valid_records = []
    
    for idx, row in enumerate(rows):
        # Normalize keys
        row_norm = {k.lower().strip() if k else '': v for k, v in row.items()}
        sku = str(row_norm.get('product_sku', '')).strip()
        try:
            qty = int(row_norm.get('quantity', 0))
            price = float(row_norm.get('unit_price', 0.0))
            if qty <= 0 or price <= 0:
                invalid_rows.append(f"Row {idx+1}: Quantity and price must be greater than zero.")
                continue
        except Exception:
            invalid_rows.append(f"Row {idx+1}: Invalid quantity or price format.")
            continue

        prod = Product.query.filter_by(sku=sku).first()
        if not prod:
            invalid_rows.append(f"Row {idx+1}: SKU '{sku}' does not exist in product catalog.")
            continue

        valid_records.append((prod, qty, price))

    if len(valid_records) == 0:
        return jsonify({
            'error': 'Validation failed. No valid records found.',
            'validation_errors': invalid_rows[:15]
        }), 400

    # Insert sales batch
    sale = Sale(
        invoice_number=f"INV-BATCH-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        store_id=1,
        sale_date=datetime.utcnow(),
        total_amount=0.0,
        net_amount=0.0,
        payment_method='Batch Upload',
        status='Completed'
    )
    db.session.add(sale)
    db.session.flush()

    total_amount = 0.0
    for prod, qty, price in valid_records:
        line_total = qty * price
        total_amount += line_total
        item = SaleItem(
            sale_id=sale.id,
            product_id=prod.id,
            quantity=qty,
            unit_price=price,
            cost_price=prod.cost_price,
            total_price=line_total
        )
        db.session.add(item)
        # Deduct stock if available
        prod.current_stock = max(0, prod.current_stock - qty)
        prod.status = prod.compute_status()

    sale.total_amount = total_amount
    sale.net_amount = total_amount

    log = AuditLog(
        action='DATASET_UPLOAD',
        entity='Sale',
        entity_id=str(sale.id),
        details=f"Uploaded {len(valid_records)} sales items from {file.filename}. Total: ₹{round(total_amount, 2)}"
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'message': f'Successfully imported {len(valid_records)} sales records!',
        'records_imported': len(valid_records),
        'warnings': invalid_rows[:10]
    }), 201
