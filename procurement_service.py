import random
from datetime import datetime, timedelta
from models import (
    db, Product, Supplier, SupplierProduct, PurchaseRequisition,
    PurchaseRequisitionItem, PurchaseOrder, PurchaseOrderItem,
    Delivery, InventoryItem, InventoryMovement, DemandForecast,
    ProcurementRecommendation, AuditLog
)
from services.supplier_service import SupplierService

class ProcurementService:

    @staticmethod
    def generate_procurement_recommendations():
        """
        Calculates procurement needs across all products, selects the best supplier,
        and saves records in ProcurementRecommendation table.
        """
        products = Product.query.all()
        ProcurementRecommendation.query.filter_by(status='Open').delete()
        recommendations = []

        for p in products:
            # Check stock condition
            if p.current_stock <= p.reorder_point:
                # Compare suppliers to get top candidate
                comp = SupplierService.compare_suppliers_for_product(p.id)
                top_cand = comp['candidates'][0] if (comp and comp['candidates']) else None

                forecast = DemandForecast.query.filter_by(product_id=p.id)\
                    .order_by(DemandForecast.forecast_date.asc()).first()
                pred_demand = forecast.predicted_demand if forecast else 30.0

                deficit = int((pred_demand * 3) + p.safety_stock - p.current_stock)
                rec_qty = max(20, deficit)
                if top_cand and rec_qty < top_cand['min_order_qty']:
                    rec_qty = top_cand['min_order_qty']

                unit_cost = top_cand['unit_price'] if top_cand else p.cost_price
                est_cost = rec_qty * unit_cost
                lead_days = top_cand['lead_time_days'] if top_cand else p.lead_time_days

                priority = 'Critical' if p.current_stock <= (p.safety_stock / 2) else ('High' if p.current_stock <= p.reorder_point else 'Medium')

                rec = ProcurementRecommendation(
                    product_id=p.id,
                    recommended_supplier_id=top_cand['supplier_id'] if top_cand else None,
                    current_stock=p.current_stock,
                    predicted_demand=pred_demand,
                    safety_stock=p.safety_stock,
                    recommended_quantity=rec_qty,
                    unit_cost=unit_cost,
                    estimated_cost=est_cost,
                    priority=priority,
                    lead_time_days=lead_days,
                    reason=comp.get('recommendation_reason', 'Low inventory trigger'),
                    status='Open'
                )
                db.session.add(rec)
                recommendations.append(rec)

        db.session.commit()
        return [r.to_dict() for r in recommendations]

    @staticmethod
    def get_procurement_dashboard_data():
        """
        Calculates all procurement KPI metrics and card collections.
        """
        recs = ProcurementRecommendation.query.filter_by(status='Open').all()
        pending_reqs = PurchaseRequisition.query.filter_by(status='Pending').count()
        approved_reqs = PurchaseRequisition.query.filter_by(status='Approved').count()
        open_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['Draft', 'Pending Approval', 'Approved', 'Ordered'])).count()
        in_transit_pos = PurchaseOrder.query.filter_by(status='In Transit').count()
        completed_pos = PurchaseOrder.query.filter_by(status='Received').count()

        total_value = db.session.query(db.func.sum(PurchaseOrder.total_amount))\
            .filter(PurchaseOrder.status.in_(['Ordered', 'In Transit', 'Received'])).scalar() or 0.0

        urgent_count = sum(1 for r in recs if r.priority in ['Critical', 'High'])

        return {
            'recommended_purchases_count': len(recs),
            'pending_requisitions_count': pending_reqs,
            'approved_requisitions_count': approved_reqs,
            'open_pos_count': open_pos,
            'in_transit_pos_count': in_transit_pos,
            'completed_pos_count': completed_pos,
            'total_procurement_value': round(float(total_value), 2),
            'urgent_procurement_count': urgent_count,
            'recommendations': [r.to_dict() for r in recs]
        }

    @staticmethod
    def create_purchase_order(data, user_id=None):
        """
        Creates a new purchase order with line items and sets up scheduled delivery.
        """
        supplier_id = data.get('supplier_id')
        items_data = data.get('items', [])
        notes = data.get('notes', '')
        status = data.get('status', 'Ordered')

        supplier = Supplier.query.get(supplier_id)
        if not supplier:
            raise ValueError('Invalid supplier ID')

        po_num = f"PO-{datetime.utcnow().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        order_date = datetime.utcnow()
        expected_delivery = order_date + timedelta(days=supplier.lead_time_days or 4)

        total_amount = 0.0
        po = PurchaseOrder(
            po_number=po_num,
            supplier_id=supplier.id,
            order_date=order_date,
            expected_delivery=expected_delivery,
            status=status,
            total_amount=0.0,
            notes=notes
        )
        db.session.add(po)
        db.session.flush()

        for item in items_data:
            prod = Product.query.get(item['product_id'])
            if not prod:
                continue
            qty = int(item['quantity'])
            price = float(item.get('unit_price', prod.cost_price))
            line_tot = qty * price
            total_amount += line_tot

            po_item = PurchaseOrderItem(
                po_id=po.id,
                product_id=prod.id,
                quantity=qty,
                unit_price=price,
                total_price=line_tot
            )
            db.session.add(po_item)

        po.total_amount = total_amount

        # Create tracking delivery record
        delivery = Delivery(
            po_id=po.id,
            delivery_date=expected_delivery,
            status='In Transit' if status == 'In Transit' else 'Scheduled',
            tracking_number=f"TRK-{random.randint(10000000, 99999999)}",
            carrier='Express Freight Logistics'
        )
        db.session.add(delivery)

        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='PO_CREATED',
            entity='PurchaseOrder',
            entity_id=str(po.id),
            details=f"Created PO {po.po_number} with {len(items_data)} items for supplier {supplier.company} totalling ₹{round(total_amount, 2)}"
        )
        db.session.add(log)
        db.session.commit()
        return po.to_dict()

    @staticmethod
    def update_po_status(po_id, new_status, user_id=None, notes=None):
        """
        Updates PO status and, if transitioning to 'Received', AUTOMATICALLY UPDATES INVENTORY!
        """
        po = PurchaseOrder.query.get(po_id)
        if not po:
            return None

        old_status = po.status
        po.status = new_status
        if notes:
            po.notes = f"{po.notes or ''}\n{notes}".strip()

        # If marked as Received, update inventory
        if new_status == 'Received' and old_status != 'Received':
            now = datetime.utcnow()
            for item in po.items:
                product = item.product
                prev_qty = product.current_stock
                new_qty = prev_qty + item.quantity
                
                # Update product current stock
                product.current_stock = new_qty
                product.status = product.compute_status()

                # Update warehouse inventory
                inv_item = InventoryItem.query.filter_by(product_id=product.id).first()
                if inv_item:
                    inv_item.quantity_on_hand += item.quantity
                    inv_item.quantity_incoming = max(0, inv_item.quantity_incoming - item.quantity)
                    inv_item.last_restocked_at = now
                else:
                    inv_item = InventoryItem(
                        product_id=product.id,
                        warehouse_id=1,
                        quantity_on_hand=new_qty,
                        quantity_reserved=0,
                        quantity_incoming=0,
                        last_restocked_at=now
                    )
                    db.session.add(inv_item)

                # Record InventoryMovement
                movement = InventoryMovement(
                    product_id=product.id,
                    movement_type='PO_RECEIPT',
                    quantity=item.quantity,
                    previous_quantity=prev_qty,
                    new_quantity=new_qty,
                    reference_id=po.po_number,
                    reference_type='PurchaseOrder',
                    note=f"Received PO shipment {po.po_number} from {po.supplier.company}"
                )
                db.session.add(movement)

            # Update Delivery record
            if po.delivery:
                po.delivery.actual_delivery_date = now
                po.delivery.status = 'Delivered'
                po.delivery.received_qty = sum(item.quantity for item in po.items)

            # Create Audit Log
            log = AuditLog(
                user_id=user_id,
                action='PO_RECEIVED_INVENTORY_RESTOCKED',
                entity='PurchaseOrder',
                entity_id=str(po.id),
                details=f"PO {po.po_number} marked as Received. Inventory updated across {len(po.items)} products."
            )
            db.session.add(log)

        elif new_status == 'In Transit' and po.delivery:
            po.delivery.status = 'In Transit'

        db.session.commit()
        return po.to_dict()

    @staticmethod
    def get_procurement_cost_analytics():
        """
        Returns monthly spend, supplier breakdown, and category breakdown.
        """
        pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['Ordered', 'In Transit', 'Received'])).all()
        
        # Monthly spending
        monthly_spend = {}
        supplier_spend = {}
        category_spend = {}

        for po in pos:
            month_key = po.order_date.strftime('%b %Y') if po.order_date else 'Current'
            monthly_spend[month_key] = monthly_spend.get(month_key, 0.0) + po.total_amount

            sup_name = po.supplier.company if po.supplier else 'Unknown'
            supplier_spend[sup_name] = supplier_spend.get(sup_name, 0.0) + po.total_amount

            for item in po.items:
                cat_name = item.product.category.name if (item.product and item.product.category) else 'General'
                category_spend[cat_name] = category_spend.get(cat_name, 0.0) + item.total_price

        return {
            'monthly_spending': [{'month': k, 'amount': round(v, 2)} for k, v in monthly_spend.items()],
            'supplier_spending': [{'supplier': k, 'amount': round(v, 2)} for k, v in supplier_spend.items()],
            'category_spending': [{'category': k, 'amount': round(v, 2)} for k, v in category_spend.items()]
        }
