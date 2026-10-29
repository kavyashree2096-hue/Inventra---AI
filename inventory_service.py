import numpy as np
from datetime import datetime, timedelta
from models import db, Product, Sale, SaleItem, InventoryMovement, DemandForecast

class InventoryService:

    @staticmethod
    def get_inventory_health():
        """
        Calculates the Inventory Health Score (0-100) based on:
        - Stock-outs (-20 per stock-out, max 40 penalty)
        - Critical low stock (-10 each, max 30 penalty)
        - Overstock (-5 each, max 20 penalty)
        - Slow-moving excess inventory (-5 each, max 20 penalty)
        """
        products = Product.query.all()
        if not products:
            return {'score': 100, 'status': 'Healthy', 'breakdown': {}}

        total_prods = len(products)
        stock_outs = sum(1 for p in products if p.current_stock <= 0)
        critical_items = sum(1 for p in products if 0 < p.current_stock <= (p.safety_stock / 2))
        low_stock_items = sum(1 for p in products if (p.safety_stock / 2) < p.current_stock <= p.reorder_point)
        overstock_items = sum(1 for p in products if p.current_stock >= p.max_stock)
        
        # Base score 100
        score = 100.0
        score -= min(40.0, stock_outs * 15.0)
        score -= min(25.0, critical_items * 8.0)
        score -= min(15.0, low_stock_items * 3.0)
        score -= min(15.0, overstock_items * 4.0)

        score = max(10.0, min(100.0, round(score, 1)))

        if score >= 85:
            status = 'Healthy'
        elif score >= 70:
            status = 'Monitor'
        elif score >= 50:
            status = 'Needs Attention'
        else:
            status = 'Critical'

        return {
            'score': score,
            'status': status,
            'total_products': total_prods,
            'stock_outs': stock_outs,
            'critical_items': critical_items,
            'low_stock_items': low_stock_items,
            'overstock_items': overstock_items,
            'healthy_items': max(0, total_prods - stock_outs - critical_items - low_stock_items - overstock_items)
        }

    @staticmethod
    def get_fast_moving_products(limit=10):
        """
        Identifies fast-moving products using sales velocity over the last 30 days.
        """
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        sales_data = db.session.query(
            SaleItem.product_id,
            db.func.sum(SaleItem.quantity).label('units_sold'),
            db.func.sum(SaleItem.total_price).label('revenue')
        ).join(Sale, SaleItem.sale_id == Sale.id)\
         .filter(Sale.sale_date >= thirty_days_ago)\
         .group_by(SaleItem.product_id)\
         .order_by(db.desc('units_sold')).all()

        results = []
        for row in sales_data:
            product = Product.query.get(row.product_id)
            if not product:
                continue

            units_sold = int(row.units_sold or 0)
            avg_daily_sales = round(units_sold / 30.0, 2)
            days_of_inventory = round(product.current_stock / max(0.1, avg_daily_sales), 1)

            # Recommended reorder quantity based on 30-day velocity + safety stock
            rec_reorder = max(0, int((avg_daily_sales * 30) + product.safety_stock - product.current_stock))

            results.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category_name': product.category.name if product.category else 'General',
                'image_url': product.image_url,
                'selling_price': product.selling_price,
                'current_stock': product.current_stock,
                'units_sold_30d': units_sold,
                'avg_daily_sales': avg_daily_sales,
                'days_of_inventory_remaining': days_of_inventory,
                'revenue_30d': round(float(row.revenue or 0), 2),
                'recommended_reorder_qty': rec_reorder,
                'urgency': 'Immediate' if days_of_inventory < product.lead_time_days else ('High' if days_of_inventory < 14 else 'Normal')
            })

            if len(results) >= limit:
                break

        return results

    @staticmethod
    def get_slow_moving_products(limit=10):
        """
        Identifies slow-moving products with low sales velocity or no sales in 30 days.
        """
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        products = Product.query.all()
        results = []

        for product in products:
            units_sold = db.session.query(db.func.sum(SaleItem.quantity))\
                .join(Sale, SaleItem.sale_id == Sale.id)\
                .filter(SaleItem.product_id == product.id, Sale.sale_date >= thirty_days_ago).scalar() or 0

            avg_daily_sales = round(units_sold / 30.0, 2)
            inventory_value = round(product.current_stock * product.cost_price, 2)

            # If less than 0.3 units sold per day or stock has been sitting
            if avg_daily_sales < 0.6 and product.current_stock > 10:
                # Find last sale date
                last_sale = db.session.query(db.func.max(Sale.sale_date))\
                    .join(SaleItem, SaleItem.sale_id == Sale.id)\
                    .filter(SaleItem.product_id == product.id).scalar()

                days_since_sale = (datetime.utcnow() - last_sale).days if last_sale else 45

                if days_since_sale > 25:
                    action = 'Initiate 20% promotional bundle' if inventory_value > 500 else 'Discount 10% & freeze procurement'
                else:
                    action = 'Monitor sales trajectory'

                results.append({
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'category_name': product.category.name if product.category else 'General',
                    'image_url': product.image_url,
                    'current_stock': product.current_stock,
                    'units_sold_30d': units_sold,
                    'avg_daily_sales': avg_daily_sales,
                    'days_since_last_sale': days_since_sale,
                    'inventory_value': inventory_value,
                    'suggested_action': action
                })

        # Sort by highest inventory value tied up
        results.sort(key=lambda x: x['inventory_value'], reverse=True)
        return results[:limit]

    @staticmethod
    def get_stockout_predictions():
        """
        Detects products at risk of becoming unavailable based on
        current stock, predicted demand, safety stock, and supplier lead time.
        """
        products = Product.query.all()
        risks = []

        for product in products:
            # Get latest weekly predicted demand
            latest_forecast = DemandForecast.query.filter_by(product_id=product.id)\
                .order_by(DemandForecast.forecast_date.asc()).first()
            
            weekly_demand = latest_forecast.predicted_demand if latest_forecast else 20.0
            daily_usage = max(0.5, weekly_demand / 7.0)
            
            days_remaining = round(product.current_stock / daily_usage, 1)

            # Lead time buffer
            lead_time = product.lead_time_days or 4

            if days_remaining <= lead_time:
                risk_level = 'Critical Risk'
                rec_action = f'Product will stock out in {days_remaining} days! Lead time is {lead_time} days. Immediate PO required.'
            elif days_remaining <= (lead_time + 4):
                risk_level = 'High Risk'
                rec_action = f'Estimated {days_remaining} days remaining. Trigger purchase requisition this week.'
            elif days_remaining <= 14 and product.current_stock <= product.reorder_point:
                risk_level = 'Moderate Risk'
                rec_action = 'Approaching reorder point. Schedule replenishment with regular batch.'
            else:
                continue

            risks.append({
                'product_id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category_name': product.category.name if product.category else 'General',
                'image_url': product.image_url,
                'current_stock': product.current_stock,
                'predicted_daily_usage': round(daily_usage, 1),
                'supplier_lead_time_days': lead_time,
                'estimated_days_remaining': days_remaining,
                'stockout_risk': risk_level,
                'recommended_action': rec_action
            })

        risks.sort(key=lambda x: x['estimated_days_remaining'])
        return risks

    @staticmethod
    def get_overstock_detection():
        """
        Detects products with excess inventory tying up working capital.
        """
        products = Product.query.filter(Product.current_stock > Product.max_stock).all()
        overstock = []

        for product in products:
            excess_units = product.current_stock - product.max_stock
            excess_value = round(excess_units * product.cost_price, 2)
            
            overstock.append({
                'product_id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category_name': product.category.name if product.category else 'General',
                'image_url': product.image_url,
                'current_stock': product.current_stock,
                'max_recommended_stock': product.max_stock,
                'excess_units': excess_units,
                'excess_stock_value': excess_value,
                'suggested_action': 'Halt procurement, redistribute to regional stores, or run seasonal clearance promotion.'
            })

        overstock.sort(key=lambda x: x['excess_stock_value'], reverse=True)
        return overstock
