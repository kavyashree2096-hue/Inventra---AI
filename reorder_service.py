from datetime import datetime, timedelta
from models import (
    db, Product, DemandForecast, ReorderRecommendation,
    PurchaseOrder, PurchaseOrderItem, Alert
)

class ReorderService:

    @staticmethod
    def calculate_reorder_recommendations():
        """
        Executes the core business logic:
        Required Stock = Predicted Demand + Safety Stock + Lead-Time Demand
        Reorder Quantity = max(0, Required Stock - Available Stock - Incoming Stock)
        """
        products = Product.query.all()
        now = datetime.utcnow()

        # Delete existing pending recommendations
        ReorderRecommendation.query.filter_by(status='Pending').delete()
        recommendations = []

        for product in products:
            # 1. Fetch predicted demand (next 14-30 days)
            forecast = DemandForecast.query.filter_by(product_id=product.id)\
                .order_by(DemandForecast.forecast_date.asc()).first()
            
            weekly_pred = forecast.predicted_demand if forecast else 25.0
            daily_pred = max(1.0, weekly_pred / 7.0)

            # 2. Incoming stock from open purchase orders
            incoming_stock = db.session.query(db.func.sum(PurchaseOrderItem.quantity))\
                .join(PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.id)\
                .filter(
                    PurchaseOrderItem.product_id == product.id,
                    PurchaseOrder.status.in_(['Approved', 'Ordered', 'In Transit'])
                ).scalar() or 0

            # 3. Calculate lead time demand
            lead_time = product.lead_time_days or 4
            lead_time_demand = daily_pred * lead_time
            safety_stock = product.safety_stock or 15
            reorder_point = product.reorder_point or 25

            # 4. Required stock and reorder quantity
            # 30-day forecast horizon + safety + lead-time
            forecast_horizon_demand = daily_pred * 21.0
            required_stock = forecast_horizon_demand + safety_stock + lead_time_demand
            
            available_stock = product.current_stock
            net_deficit = required_stock - available_stock - incoming_stock
            reorder_qty = max(0, int(round(net_deficit)))

            # If current stock is below reorder point or deficit is positive
            if available_stock <= reorder_point or net_deficit > 0:
                # Priority logic
                if available_stock <= 0:
                    priority = 'Critical'
                    reason = f'Product is currently STOCK-OUT! Zero units available. Urgent restock needed.'
                elif available_stock <= (safety_stock / 2):
                    priority = 'Critical'
                    reason = f'Stock is below 50% safety threshold ({available_stock}/{safety_stock}). High probability of stock-out in {round(available_stock/daily_pred, 1)} days.'
                elif available_stock <= reorder_point:
                    priority = 'High'
                    reason = f'Stock ({available_stock}) reached reorder trigger point ({reorder_point}). Order {reorder_qty} units to maintain service level.'
                elif net_deficit > 10:
                    priority = 'Medium'
                    reason = f'Demand surge projected ({round(weekly_pred, 1)}/wk). Advance replenishment recommended.'
                else:
                    priority = 'Low'
                    reason = 'Routine buffer replenishment to reach optimal inventory ceiling.'

                rec = ReorderRecommendation(
                    product_id=product.id,
                    current_stock=available_stock,
                    predicted_demand=weekly_pred,
                    safety_stock=safety_stock,
                    reorder_point=reorder_point,
                    reorder_quantity=reorder_qty if reorder_qty > 0 else int(reorder_point * 1.5),
                    reorder_date=now + timedelta(days=1 if priority == 'Critical' else (3 if priority == 'High' else 7)),
                    priority=priority,
                    reason=reason,
                    status='Pending'
                )
                db.session.add(rec)
                recommendations.append(rec)

                # Create Alert for Critical and High priority items
                if priority in ['Critical', 'High']:
                    alert_exists = Alert.query.filter_by(product_id=product.id, is_read=False).first()
                    if not alert_exists:
                        alert = Alert(
                            title=f'{priority} Reorder Alert: {product.name}',
                            message=reason,
                            product_id=product.id,
                            alert_type='Reorder Required' if priority == 'High' else 'Critical Stock',
                            severity=priority,
                            recommended_action=f'Procure {rec.reorder_quantity} units immediately from preferred supplier.'
                        )
                        db.session.add(alert)

        db.session.commit()
        return [r.to_dict() for r in recommendations]

    @staticmethod
    def get_all_reorders():
        recs = ReorderRecommendation.query.order_by(
            db.case(
                (ReorderRecommendation.priority == 'Critical', 1),
                (ReorderRecommendation.priority == 'High', 2),
                (ReorderRecommendation.priority == 'Medium', 3),
                else_=4
            ),
            ReorderRecommendation.reorder_quantity.desc()
        ).all()
        return [r.to_dict() for r in recs]
