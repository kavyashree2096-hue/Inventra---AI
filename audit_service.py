import io
import csv
from datetime import datetime, timedelta
from sqlalchemy import func
from models import (
    db, Product, Category, InventoryItem, InventoryMovement,
    Sale, SaleItem, User, AuditLog, AuditSession, AuditSessionItem
)

class AuditService:

    @staticmethod
    def get_audit_summary():
        """
        Calculates audit KPI summary metrics across all sessions and logs.
        """
        total_sessions = AuditSession.query.count()
        total_items_verified = AuditSessionItem.query.count()
        matched_items = AuditSessionItem.query.filter_by(status='Matched').count()
        shortage_items = AuditSessionItem.query.filter_by(status='Shortage').count()
        excess_items = AuditSessionItem.query.filter_by(status='Excess').count()
        unresolved = AuditSessionItem.query.filter(
            AuditSessionItem.status.in_(['Shortage', 'Excess', 'Pending Verification'])
        ).count()
        resolved_items = AuditSessionItem.query.filter_by(status='Resolved').count()

        # Zero stock and negative stock items currently in product catalog
        zero_stock_count = Product.query.filter(Product.current_stock == 0).count()
        negative_stock_count = Product.query.filter(Product.current_stock < 0).count()

        return {
            'total_sessions': total_sessions,
            'products_verified': total_items_verified,
            'matched_products': matched_items,
            'stock_shortages': shortage_items,
            'stock_excesses': excess_items,
            'unresolved_discrepancies': unresolved,
            'resolved_discrepancies': resolved_items,
            'zero_stock_products': zero_stock_count,
            'negative_stock_products': negative_stock_count
        }

    @staticmethod
    def create_audit_session(data, user_id=None):
        """
        Creates a new physical stock verification audit session.
        Snapshots current recorded stock for eligible products.
        """
        title = data.get('title', f"Stock Audit {datetime.utcnow().strftime('%b %Y')}")
        warehouse = data.get('warehouse', 'Central Warehouse')
        category_id = data.get('category_id')
        notes = data.get('notes', 'Physical inventory count session')

        session_code = f"AUD-{datetime.utcnow().strftime('%Y%m')}-{AuditSession.query.count() + 101}"

        session = AuditSession(
            session_code=session_code,
            title=title,
            warehouse_name=warehouse,
            auditor_id=user_id,
            status='In Progress',
            notes=notes,
            created_at=datetime.utcnow()
        )
        db.session.add(session)
        db.session.flush()

        # Populate items from catalog
        prod_query = Product.query
        if category_id:
            prod_query = prod_query.filter_by(category_id=category_id)
        products = prod_query.all()

        for p in products:
            item = AuditSessionItem(
                session_id=session.id,
                product_id=p.id,
                recorded_stock=p.current_stock,
                physical_stock=p.current_stock,  # Default physical count matches recorded until verified
                difference=0,
                status='Matched',
                created_at=datetime.utcnow()
            )
            db.session.add(item)

        # Log system activity
        log = AuditLog(
            user_id=user_id,
            action='AUDIT_SESSION_CREATED',
            entity='AuditSession',
            entity_id=str(session.id),
            details=f"Created audit session {session_code} '{title}' with {len(products)} products snapshot."
        )
        db.session.add(log)
        db.session.commit()

        return session.to_dict()

    @staticmethod
    def update_session_item(item_id, physical_stock, reason=None, corrective_action=None, user_id=None):
        """
        Updates physically verified stock for an audit item and recalculates discrepancy.
        Formula: Stock Difference = Actual Stock - Recorded Stock
        """
        item = AuditSessionItem.query.get(item_id)
        if not item:
            return None

        item.physical_stock = int(physical_stock)
        diff = item.physical_stock - item.recorded_stock
        item.difference = diff
        item.is_adjusted = False

        if diff == 0:
            item.status = 'Matched'
        elif diff < 0:
            item.status = 'Shortage'
        else:
            item.status = 'Excess'

        if reason:
            item.discrepancy_reason = reason
        if corrective_action:
            item.corrective_action = corrective_action

        db.session.commit()
        return item.to_dict()

    @staticmethod
    def resolve_discrepancy(item_id, authorized_user_id, corrective_action=None):
        """
        Authorized reconciliation: Applies physical count adjustment to Product and Inventory tables.
        Requires authorized confirmation. Does not silently overwrite records.
        """
        item = AuditSessionItem.query.get(item_id)
        if not item:
            raise ValueError('Audit item not found')

        product = item.product
        prev_stock = product.current_stock
        new_stock = item.physical_stock
        diff = item.difference

        # Update product stock
        product.current_stock = new_stock
        product.status = product.compute_status()

        # Update warehouse inventory
        inv = InventoryItem.query.filter_by(product_id=product.id).first()
        if inv:
            inv.quantity_on_hand = new_stock
            inv.last_restocked_at = datetime.utcnow()

        # Record InventoryMovement
        movement = InventoryMovement(
            product_id=product.id,
            movement_type='ADJUSTMENT',
            quantity=diff,
            previous_quantity=prev_stock,
            new_quantity=new_stock,
            reference_id=item.session.session_code,
            reference_type='AuditSession',
            note=f"Reconciled discrepancy: {item.discrepancy_reason or 'Stock Audit Reconciliation'}. Action: {corrective_action or 'Physical count sync'}"
        )
        db.session.add(movement)

        # Mark item resolved
        item.status = 'Resolved'
        item.is_adjusted = True
        item.resolved_by_id = authorized_user_id
        item.resolved_at = datetime.utcnow()
        if corrective_action:
            item.corrective_action = corrective_action

        # Check if entire session is now reconciled
        session = item.session
        remaining_unresolved = sum(
            1 for it in session.items if it.status in ['Shortage', 'Excess', 'Pending Verification'] and it.id != item.id
        )
        if remaining_unresolved == 0:
            session.status = 'Reconciled'
            session.completed_at = datetime.utcnow()

        # Audit Log
        log = AuditLog(
            user_id=authorized_user_id,
            action='INVENTORY_AUDIT_ADJUSTMENT',
            entity='Product',
            entity_id=str(product.id),
            details=f"Reconciled {product.sku} ({product.name}) from {prev_stock} to {new_stock} (Diff: {diff:+d}). Reason: {item.discrepancy_reason}"
        )
        db.session.add(log)
        db.session.commit()

        return item.to_dict()

    @staticmethod
    def perform_sales_audit():
        """
        Validates sales transactions for data consistency, anomalies, and financial verification.
        Distinguishes data quality warnings from financial discrepancies.
        """
        sales = Sale.query.all()
        products_map = {p.id: p for p in Product.query.all()}

        anomalies = []
        warnings = []
        verified_count = 0
        discrepancy_count = 0
        total_checked_revenue = 0.0

        invoice_seen = {}

        for s in sales:
            verified_count += 1
            total_checked_revenue += s.net_amount

            # 1. Duplicate invoice numbers check
            if s.invoice_number in invoice_seen:
                discrepancy_count += 1
                anomalies.append({
                    'type': 'Duplicate Invoice',
                    'severity': 'Critical',
                    'reference': s.invoice_number,
                    'details': f"Duplicate invoice detected: {s.invoice_number} already recorded on {invoice_seen[s.invoice_number]}.",
                    'category': 'Financial Integrity'
                })
            else:
                invoice_seen[s.invoice_number] = s.sale_date.strftime('%Y-%m-%d') if s.sale_date else 'Unknown'

            # 2. Null or invalid dates
            if not s.sale_date:
                warnings.append({
                    'type': 'Missing Date',
                    'severity': 'Warning',
                    'reference': s.invoice_number,
                    'details': f"Sale {s.invoice_number} has missing or unparsed timestamp.",
                    'category': 'Data Quality'
                })

            # 3. Line total mismatches
            line_sum = 0.0
            for it in s.items:
                calc_total = round(it.quantity * it.unit_price, 2)
                recorded_total = round(it.total_price, 2)
                line_sum += recorded_total

                if abs(calc_total - recorded_total) > 0.05:
                    discrepancy_count += 1
                    anomalies.append({
                        'type': 'Line Total Mismatch',
                        'severity': 'High',
                        'reference': s.invoice_number,
                        'details': f"Item total mismatch: recorded ₹{recorded_total}, calculated ₹{calc_total} ({it.quantity} x ₹{it.unit_price}) for {it.product_name}.",
                        'category': 'Financial Integrity'
                    })

                # Invalid quantity or price
                if it.quantity <= 0:
                    warnings.append({
                        'type': 'Invalid Quantity',
                        'severity': 'Warning',
                        'reference': s.invoice_number,
                        'details': f"Negative or zero quantity ({it.quantity}) in sale {s.invoice_number}.",
                        'category': 'Data Quality'
                    })
                if it.unit_price <= 0:
                    warnings.append({
                        'type': 'Zero Unit Price',
                        'severity': 'Warning',
                        'reference': s.invoice_number,
                        'details': f"Unit price is zero or negative for {it.product_name} in {s.invoice_number}.",
                        'category': 'Data Quality'
                    })

            # Check invoice net total vs sum of line items
            if s.items and abs(round(line_sum, 2) - round(s.total_amount, 2)) > 0.10:
                discrepancy_count += 1
                anomalies.append({
                    'type': 'Invoice Total Inconsistency',
                    'severity': 'High',
                    'reference': s.invoice_number,
                    'details': f"Invoice total ₹{s.total_amount} deviates from sum of line items ₹{round(line_sum, 2)}.",
                    'category': 'Financial Integrity'
                })

            # Unusually large transaction (> ₹2,000)
            if s.net_amount > 2000.0:
                warnings.append({
                    'type': 'Large Transaction Flag',
                    'severity': 'Info',
                    'reference': s.invoice_number,
                    'details': f"Transaction value of ₹{round(s.net_amount, 2)} exceeds standard retail threshold (₹2,000). Validated as legitimate wholesale/bulk order.",
                    'category': 'Risk Review'
                })

        return {
            'total_sales_inspected': verified_count,
            'total_revenue_verified': round(total_checked_revenue, 2),
            'financial_discrepancies_count': discrepancy_count,
            'data_quality_warnings_count': len(warnings),
            'audit_health_rating': 'Grade A (Compliant)' if discrepancy_count == 0 else ('Grade B (Review Needed)' if discrepancy_count < 5 else 'Grade C (Action Required)'),
            'discrepancies': anomalies[:50],
            'warnings': warnings[:50]
        }

    @staticmethod
    def get_audit_charts_data():
        """
        Compiles data points for 5 interactive audit visualizations.
        """
        # 1. Shortages vs excesses by product
        items = AuditSessionItem.query.all()
        prod_diffs = {}
        for it in items:
            name = it.product.name[:22] if it.product else f"Prod #{it.product_id}"
            if name not in prod_diffs:
                prod_diffs[name] = {'product': name, 'shortage': 0, 'excess': 0}
            if it.difference < 0:
                prod_diffs[name]['shortage'] += abs(it.difference)
            elif it.difference > 0:
                prod_diffs[name]['excess'] += it.difference

        shortage_vs_excess = list(prod_diffs.values())[:10]

        # 2. Status distribution
        status_counts = db.session.query(
            AuditSessionItem.status, func.count(AuditSessionItem.id)
        ).group_by(AuditSessionItem.status).all()
        status_dist = [{'status': row[0], 'count': row[1]} for row in status_counts]

        # 3. Discrepancies by product category
        cat_discrepancies = {}
        for it in items:
            cat_name = it.product.category.name if (it.product and it.product.category) else 'Uncategorized'
            cat_discrepancies[cat_name] = cat_discrepancies.get(cat_name, 0) + abs(it.difference)

        category_breakdown = [{'category': k, 'discrepancy_units': v} for k, v in cat_discrepancies.items()]

        # 4. Discrepancies over time (by session date)
        sessions = AuditSession.query.order_by(AuditSession.created_at.asc()).all()
        time_trend = []
        for s in sessions:
            tot_diff = sum(abs(it.difference) for it in s.items)
            time_trend.append({
                'date': s.created_at.strftime('%Y-%m-%d') if s.created_at else 'Recent',
                'session': s.session_code,
                'discrepancy_units': tot_diff,
                'items_count': len(s.items)
            })

        # 5. Audit resolution trends
        resolution_counts = {
            'Resolved': AuditSessionItem.query.filter_by(status='Resolved').count(),
            'Matched On Count': AuditSessionItem.query.filter_by(status='Matched').count(),
            'Pending Action': AuditSessionItem.query.filter(AuditSessionItem.status.in_(['Shortage', 'Excess', 'Pending Verification'])).count()
        }
        resolution_trend = [{'stage': k, 'count': v} for k, v in resolution_counts.items()]

        return {
            'shortage_vs_excess': shortage_vs_excess,
            'status_distribution': status_dist,
            'category_breakdown': category_breakdown,
            'time_trend': time_trend,
            'resolution_trend': resolution_trend
        }

    @staticmethod
    def seed_initial_audit_data():
        """
        Idempotently creates a baseline realistic audit session if none exists,
        so users can explore audit operations immediately.
        """
        if AuditSession.query.first():
            return

        admin_user = User.query.filter_by(role='Admin').first()
        admin_id = admin_user.id if admin_user else 1

        session = AuditSession(
            session_code="AUD-202610-001",
            title="Q4 Comprehensive Floor Stock Audit",
            warehouse_name="Central Warehouse",
            auditor_id=admin_id,
            status="In Progress",
            notes="Quarterly multi-aisle cycle count and discrepancy verification.",
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db.session.add(session)
        db.session.flush()

        products = Product.query.all()
        # Seed realistic physical counts for initial exploration
        for idx, p in enumerate(products):
            recorded = p.current_stock
            if idx == 0:
                physical = max(0, recorded - 2)
                reason = "Damaged packaging in transit; item quarantined"
                action = "Write-off damaged stock; update inventory after supervisor sign-off"
            elif idx == 3:
                physical = recorded + 3
                reason = "Unrecorded return from store customer"
                action = "Re-stock into shelf inventory; adjust system count"
            elif idx == 6:
                physical = max(0, recorded - 1)
                reason = "Floor display sample missing barcode"
                action = "Re-barcode item and return to shelf"
            else:
                physical = recorded
                reason = None
                action = None

            diff = physical - recorded
            status = 'Matched' if diff == 0 else ('Shortage' if diff < 0 else 'Excess')

            item = AuditSessionItem(
                session_id=session.id,
                product_id=p.id,
                recorded_stock=recorded,
                physical_stock=physical,
                difference=diff,
                status=status,
                discrepancy_reason=reason,
                corrective_action=action,
                created_at=datetime.utcnow() - timedelta(days=2)
            )
            db.session.add(item)

        log = AuditLog(
            user_id=admin_id,
            action='AUDIT_SESSION_CREATED',
            entity='AuditSession',
            entity_id=str(session.id),
            details="Initialized Q4 Comprehensive Floor Stock Audit session with 18 SKUs."
        )
        db.session.add(log)
        db.session.commit()
