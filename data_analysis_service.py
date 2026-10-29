import os
import io
import csv
import json
import math
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import func
from models import db, Product, Category, Sale, SaleItem, InventoryItem, DataUpload, AuditLog

class DataAnalysisService:

    @staticmethod
    def inspect_file(file_storage, filename):
        """
        Parses uploaded CSV or Excel file, returns column preview, types, and suggested mappings.
        """
        lower_name = filename.lower()
        if lower_name.endswith('.csv'):
            df = pd.read_csv(file_storage)
        elif lower_name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_storage)
        else:
            raise ValueError("Unsupported format. Please upload a CSV or Excel file (.csv, .xlsx, .xls).")

        total_rows = len(df)
        columns = list(df.columns)

        # Detect types
        col_meta = []
        for col in columns:
            dtype_str = str(df[col].dtype)
            sample_val = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
            inferred = 'numeric' if ('int' in dtype_str or 'float' in dtype_str) else ('datetime' if 'date' in col.lower() or 'time' in col.lower() else 'string')
            null_count = int(df[col].isna().sum())

            col_meta.append({
                'column': col,
                'type': inferred,
                'raw_type': dtype_str,
                'sample': sample_val,
                'null_count': null_count,
                'null_pct': round((null_count / total_rows * 100), 1) if total_rows > 0 else 0
            })

        # Suggest standard retail mappings
        mapping_suggestions = {}
        for c in columns:
            cl = c.lower().strip()
            if any(k in cl for k in ['sku', 'product_id', 'productid', 'item_id', 'code']):
                mapping_suggestions['product_id'] = c
            elif any(k in cl for k in ['product_name', 'item_name', 'name', 'title', 'description']):
                if 'product_name' not in mapping_suggestions:
                    mapping_suggestions['product_name'] = c
            elif any(k in cl for k in ['category', 'department', 'group', 'type']):
                mapping_suggestions['category'] = c
            elif any(k in cl for k in ['date', 'time', 'timestamp', 'sale_date']):
                mapping_suggestions['date'] = c
            elif any(k in cl for k in ['invoice', 'order_id', 'transaction', 'trans_id']):
                mapping_suggestions['transaction_id'] = c
            elif any(k in cl for k in ['quantity', 'qty', 'units', 'sold']):
                mapping_suggestions['quantity'] = c
            elif any(k in cl for k in ['price', 'unit_price', 'rate', 'selling_price', 'mrp']):
                mapping_suggestions['unit_price'] = c
            elif any(k in cl for k in ['total', 'line_total', 'amount', 'net_amount', 'revenue']):
                mapping_suggestions['line_total'] = c
            elif any(k in cl for k in ['cost', 'cost_price', 'unit_cost', 'cogs']):
                mapping_suggestions['cost'] = c

        sample_rows = df.head(10).replace({np.nan: None}).to_dict(orient='records')

        return {
            'filename': filename,
            'total_rows': total_rows,
            'total_columns': len(columns),
            'columns': col_meta,
            'suggested_mappings': mapping_suggestions,
            'sample_data': sample_rows
        }

    @staticmethod
    def validate_and_analyze_dataset(df, mappings, filename='uploaded_dataset.csv', user_id=None):
        """
        Runs comprehensive data quality analysis, outlier detection, and computes Data Quality Score.
        Formula:
        Score = 100 - (missing_pct * 0.35 + invalid_pct * 0.45 + duplicate_pct * 0.20)
        """
        total_rows = len(df)
        total_cols = len(df.columns)

        # 1. Missing values
        missing_cells = int(df.isna().sum().sum())
        total_cells = total_rows * total_cols if total_rows > 0 else 1
        missing_pct = round((missing_cells / total_cells) * 100, 2)

        # 2. Duplicate rows
        trans_col = mappings.get('transaction_id')
        if trans_col and trans_col in df.columns:
            duplicate_count = int(df.duplicated(subset=[trans_col]).sum())
        else:
            duplicate_count = int(df.duplicated().sum())
        duplicate_pct = round((duplicate_count / total_rows) * 100, 2) if total_rows > 0 else 0

        # 3. Invalid numeric values & negative checks
        invalid_rows = 0
        qty_col = mappings.get('quantity')
        price_col = mappings.get('unit_price')

        if qty_col and qty_col in df.columns:
            qty_invalid = ((pd.to_numeric(df[qty_col], errors='coerce') <= 0) | df[qty_col].isna()).sum()
            invalid_rows += int(qty_invalid)

        if price_col and price_col in df.columns:
            price_invalid = ((pd.to_numeric(df[price_col], errors='coerce') <= 0) | df[price_col].isna()).sum()
            invalid_rows += int(price_invalid)

        invalid_pct = round((invalid_rows / (total_rows * 2)) * 100, 2) if total_rows > 0 else 0
        valid_count = max(0, total_rows - invalid_rows - duplicate_count)

        # Data Quality Score calculation
        quality_score = max(0.0, min(100.0, 100.0 - (missing_pct * 0.35 + invalid_pct * 0.45 + duplicate_pct * 0.20)))

        # Outlier Detection on Quantity & Price (IQR method)
        outliers = []
        if qty_col and qty_col in df.columns:
            q_num = pd.to_numeric(df[qty_col], errors='coerce').dropna()
            if len(q_num) > 10:
                q25, q75 = np.percentile(q_num, [25, 75])
                iqr = q75 - q25
                upper_bound = q75 + 1.5 * iqr
                qty_outliers = q_num[q_num > upper_bound]
                if not qty_outliers.empty:
                    outliers.append({
                        'field': 'Quantity',
                        'count': int(len(qty_outliers)),
                        'threshold': round(float(upper_bound), 1),
                        'max_detected': round(float(qty_outliers.max()), 1),
                        'note': f"Values exceeding {round(upper_bound, 1)} units classified as statistical outliers (potential wholesale orders or bulk batches)."
                    })

        if price_col and price_col in df.columns:
            p_num = pd.to_numeric(df[price_col], errors='coerce').dropna()
            if len(p_num) > 10:
                q25, q75 = np.percentile(p_num, [25, 75])
                iqr = q75 - q25
                upper_bound = q75 + 1.5 * iqr
                price_outliers = p_num[p_num > upper_bound]
                if not price_outliers.empty:
                    outliers.append({
                        'field': 'Price',
                        'count': int(len(price_outliers)),
                        'threshold': round(float(upper_bound), 2),
                        'max_detected': round(float(price_outliers.max()), 2),
                        'note': f"Prices exceeding ₹{round(upper_bound, 2)} detected in catalog (premium luxury or hardware category items)."
                    })

        # Save record in DataUpload model
        summary_payload = {
            'missing_cells': missing_cells,
            'missing_pct': missing_pct,
            'duplicate_count': duplicate_count,
            'duplicate_pct': duplicate_pct,
            'invalid_rows': invalid_rows,
            'quality_score': round(quality_score, 1),
            'outliers': outliers
        }

        upload_entry = DataUpload(
            filename=filename,
            file_type='csv' if filename.lower().endswith('.csv') else 'xlsx',
            row_count=total_rows,
            valid_count=valid_count,
            invalid_count=invalid_rows,
            duplicate_count=duplicate_count,
            quality_score=round(quality_score, 1),
            column_mappings=json.dumps(mappings),
            summary_metrics=json.dumps(summary_payload),
            uploaded_by_id=user_id,
            created_at=datetime.utcnow()
        )
        db.session.add(upload_entry)

        log = AuditLog(
            user_id=user_id,
            action='DATASET_ANALYZED',
            entity='DataUpload',
            entity_id=str(upload_entry.id),
            details=f"Analyzed {filename}: {total_rows} rows, Data Quality Score: {round(quality_score, 1)}/100."
        )
        db.session.add(log)
        db.session.commit()

        return {
            'upload_id': upload_entry.id,
            'filename': filename,
            'total_rows': total_rows,
            'total_columns': total_cols,
            'valid_rows': valid_count,
            'invalid_rows': invalid_rows,
            'duplicate_rows': duplicate_count,
            'missing_values_count': missing_cells,
            'missing_values_pct': missing_pct,
            'data_quality_score': round(quality_score, 1),
            'rating': 'High Integrity' if quality_score >= 85 else ('Moderate Integrity' if quality_score >= 65 else 'Low Integrity (Requires Cleansing)'),
            'outliers': outliers,
            'formula_used': 'Data Quality Score = 100 - (missing_pct * 0.35 + invalid_pct * 0.45 + duplicate_pct * 0.20)'
        }

    @staticmethod
    def get_system_eda():
        """
        Calculates descriptive statistics and exploratory distributions over the persistent retail database.
        """
        # Pull products & sales data into pandas for robust EDA
        sales_items = db.session.query(
            SaleItem.quantity, SaleItem.unit_price, SaleItem.cost_price, SaleItem.total_price,
            Product.name.label('product_name'), Category.name.label('category_name'),
            Sale.sale_date
        ).join(Product, SaleItem.product_id == Product.id)\
         .outerjoin(Category, Product.category_id == Category.id)\
         .join(Sale, SaleItem.sale_id == Sale.id).all()

        if not sales_items:
            return {'message': 'No transaction data available for EDA'}

        df = pd.DataFrame([
            {
                'quantity': row.quantity,
                'unit_price': row.unit_price,
                'cost_price': row.cost_price,
                'total_price': row.total_price,
                'product_name': row.product_name,
                'category_name': row.category_name or 'General',
                'sale_date': row.sale_date
            }
            for row in sales_items
        ])

        # 1. Descriptive stats for numeric fields
        num_cols = ['quantity', 'unit_price', 'total_price']
        stats_summary = {}

        for col in num_cols:
            s = df[col].dropna()
            stats_summary[col] = {
                'count': int(len(s)),
                'mean': round(float(s.mean()), 2),
                'median': round(float(s.median()), 2),
                'min': round(float(s.min()), 2),
                'max': round(float(s.max()), 2),
                'std': round(float(s.std()), 2),
                'q1': round(float(s.quantile(0.25)), 2),
                'q3': round(float(s.quantile(0.75)), 2),
                'iqr': round(float(s.quantile(0.75) - s.quantile(0.25)), 2)
            }

        # 2. Revenue Distribution Bins (Histogram)
        rev_vals = df['total_price'].dropna().tolist()
        min_rev, max_rev = min(rev_vals), max(rev_vals)
        bin_count = 8
        bin_width = max(1.0, (max_rev - min_rev) / bin_count)
        rev_histogram = []
        for i in range(bin_count):
            b_start = round(min_rev + i * bin_width, 1)
            b_end = round(b_start + bin_width, 1)
            cnt = sum(1 for v in rev_vals if b_start <= v < b_end or (i == bin_count - 1 and v == b_end))
            rev_histogram.append({
                'bin': f"₹{b_start:.0f} - ₹{b_end:.0f}",
                'count': cnt
            })

        # 3. Quantity Distribution Bins
        qty_counts = df['quantity'].value_counts().sort_index().head(8)
        qty_distribution = [
            {'quantity': f"{int(k)} units", 'count': int(v)}
            for k, v in qty_counts.items()
        ]

        # 4. Category Comparison
        cat_grp = df.groupby('category_name').agg({
            'total_price': ['sum', 'mean', 'count'],
            'quantity': 'sum'
        })
        cat_grp.columns = ['revenue', 'avg_ticket', 'transactions', 'units']
        category_comparison = [
            {
                'category': idx,
                'revenue': round(float(row['revenue']), 2),
                'avg_ticket': round(float(row['avg_ticket']), 2),
                'transactions': int(row['transactions']),
                'units': int(row['units'])
            }
            for idx, row in cat_grp.reset_index().iterrows()
        ]

        # 5. Correlation Matrix
        corr_matrix = {}
        for c1 in num_cols:
            corr_matrix[c1] = {}
            for c2 in num_cols:
                corr_matrix[c1][c2] = round(float(df[c1].corr(df[c2])), 3)

        # 6. Outlier Visualization Points
        # Top 10 revenue transactions
        top_tx = df.sort_values(by='total_price', ascending=False).head(10)
        outlier_points = [
            {
                'product': row['product_name'][:25],
                'category': row['category_name'],
                'quantity': int(row['quantity']),
                'price': round(float(row['unit_price']), 2),
                'revenue': round(float(row['total_price']), 2)
            }
            for idx, row in top_tx.iterrows()
        ]

        return {
            'total_observations': len(df),
            'descriptive_statistics': stats_summary,
            'revenue_distribution': rev_histogram,
            'quantity_distribution': qty_distribution,
            'category_comparison': category_comparison,
            'correlation_matrix': corr_matrix,
            'outlier_points': outlier_points
        }

    @staticmethod
    def get_business_analytics():
        """
        Analyzes retail velocity, stock turnover, inventory movement, and catalog efficiency.
        Stock Turnover Formula = Cost of Goods Sold (COGS) / Average Inventory Value
        """
        # 1. Total COGS and Inventory Value
        cogs_total = db.session.query(
            func.sum(SaleItem.quantity * SaleItem.cost_price)
        ).scalar() or 0.0

        current_inventory_val = db.session.query(
            func.sum(Product.current_stock * Product.cost_price)
        ).scalar() or 1.0

        stock_turnover_ratio = round(cogs_total / current_inventory_val, 2) if current_inventory_val > 0 else 0.0

        # 2. Slow moving products (units sold <= 15 and stock >= 25)
        sales_by_prod = dict(db.session.query(
            SaleItem.product_id, func.sum(SaleItem.quantity)
        ).group_by(SaleItem.product_id).all())

        all_products = Product.query.all()
        slow_movers = []
        fast_movers = []

        for p in all_products:
            sold = sales_by_prod.get(p.id, 0)
            item_data = {
                'id': p.id,
                'sku': p.sku,
                'name': p.name,
                'category': p.category.name if p.category else 'General',
                'current_stock': p.current_stock,
                'units_sold': sold,
                'cost_price': p.cost_price,
                'holding_value': round(p.current_stock * p.cost_price, 2)
            }
            if sold < 40 and p.current_stock >= 30:
                slow_movers.append(item_data)
            elif sold >= 80:
                fast_movers.append(item_data)

        slow_movers.sort(key=lambda x: x['holding_value'], reverse=True)
        fast_movers.sort(key=lambda x: x['units_sold'], reverse=True)

        return {
            'stock_turnover_ratio': stock_turnover_ratio,
            'cost_of_goods_sold': round(cogs_total, 2),
            'inventory_holding_value': round(current_inventory_val, 2),
            'turnover_health': 'Healthy (Turnover > 3.0x)' if stock_turnover_ratio >= 3.0 else 'Moderate (2.0x - 3.0x)',
            'slow_moving_products': slow_movers[:8],
            'fast_moving_products': fast_movers[:8],
            'definitions': {
                'stock_turnover': 'Cost of Goods Sold (COGS) / Current Inventory Capital Value',
                'slow_moving': 'Products with < 40 units sold and >= 30 units idle in warehouse holding.',
                'fast_moving': 'Products with >= 80 units sold in current sales cycle.'
            }
        }
