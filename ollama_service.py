import json
import requests
from flask import current_app
from models import (
    db, Product, Category, Supplier, Sale, SaleItem,
    DemandForecast, Alert, ReorderRecommendation, PurchaseOrder
)
from services.inventory_service import InventoryService
from services.supplier_service import SupplierService

class OllamaService:

    @staticmethod
    def extract_intent_and_context(query):
        """
        Analyzes the query keywords to fetch relevant database records and summary context.
        """
        q = query.lower()
        context_data = {}
        structured_data = []

        # 1. Health & Overview
        health = InventoryService.get_inventory_health()
        context_data['inventory_health'] = health

        # 2. Low stock / Reorders
        if any(w in q for w in ['low', 'reorder', 'run out', 'stock-out', 'critical', 'shortage', 'stock out']):
            low_products = Product.query.filter(Product.current_stock <= Product.reorder_point).all()
            reorders = ReorderRecommendation.query.filter_by(status='Pending').all()
            stockouts = InventoryService.get_stockout_predictions()

            context_data['low_stock_products'] = [
                {'name': p.name, 'stock': p.current_stock, 'safety_stock': p.safety_stock, 'reorder_point': p.reorder_point}
                for p in low_products[:8]
            ]
            context_data['reorder_recommendations'] = [
                {'name': r.product.name if r.product else '', 'qty': r.reorder_quantity, 'priority': r.priority, 'reason': r.reason}
                for r in reorders[:5]
            ]
            context_data['stockout_predictions'] = [
                {'name': s['name'], 'days_remaining': s['estimated_days_remaining'], 'risk': s['stockout_risk']}
                for s in stockouts[:5]
            ]
            structured_data = [p.to_dict() for p in low_products[:5]]

        # 3. Fast / Slow Moving
        elif any(w in q for w in ['fast', 'velocity', 'top selling', 'best selling', 'slow', 'dead stock', 'overstock']):
            fast = InventoryService.get_fast_moving_products(5)
            slow = InventoryService.get_slow_moving_products(5)
            overstock = InventoryService.get_overstock_detection()

            context_data['fast_moving'] = [{'name': f['name'], 'units_30d': f['units_sold_30d'], 'daily_avg': f['avg_daily_sales']} for f in fast]
            context_data['slow_moving'] = [{'name': s['name'], 'current_stock': s['current_stock'], 'action': s['suggested_action']} for s in slow]
            context_data['overstock'] = [{'name': o['name'], 'excess_units': o['excess_units'], 'excess_value': o['excess_stock_value']} for o in overstock[:4]]
            structured_data = fast if 'fast' in q else slow

        # 4. Suppliers & Procurement
        elif any(w in q for w in ['supplier', 'lead time', 'vendor', 'procure', 'purchase order', 'cost']):
            suppliers = Supplier.query.all()
            context_data['suppliers'] = [
                {'name': s.company, 'rating': s.rating, 'reliability': s.reliability_score, 'lead_time_days': s.lead_time_days}
                for s in suppliers
            ]
            open_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['Ordered', 'In Transit'])).count()
            context_data['open_purchase_orders'] = open_pos

        # 5. Demand Forecast
        elif any(w in q for w in ['forecast', 'demand', 'future', 'predict', 'trend']):
            forecasts = DemandForecast.query.order_by(DemandForecast.predicted_demand.desc()).limit(6).all()
            context_data['demand_forecasts'] = [
                {'name': f.product.name if f.product else '', 'predicted': f.predicted_demand, 'status': f.demand_status, 'change_pct': f.demand_change_pct}
                for f in forecasts
            ]
            structured_data = [f.to_dict() for f in forecasts]

        # 6. Critical Alerts
        elif any(w in q for w in ['alert', 'warning', 'issue', 'problem', 'critical']):
            alerts = Alert.query.filter_by(is_read=False).order_by(Alert.created_at.desc()).limit(6).all()
            context_data['unread_alerts'] = [
                {'title': a.title, 'severity': a.severity, 'action': a.recommended_action}
                for a in alerts
            ]
            structured_data = [a.to_dict() for a in alerts]

        # Default summary context
        else:
            top_products = Product.query.order_by(Product.current_stock.asc()).limit(5).all()
            context_data['sample_products'] = [{'name': p.name, 'stock': p.current_stock, 'status': p.status} for p in top_products]

        return context_data, structured_data

    @classmethod
    def generate_chat_response(cls, message):
        """
        Coordinates with Ollama API using PostgreSQL data context.
        Falls back seamlessly to smart retail rule engine if Ollama is not accessible.
        """
        base_url = current_app.config.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        model = current_app.config.get('OLLAMA_MODEL', 'llama3.2')

        context_data, structured_data = cls.extract_intent_and_context(message)

        system_prompt = f"""
You are the Inventra AI Retail Assistant, an expert AI demand forecasting, inventory optimization, and procurement intelligence advisor.
Always provide crisp, helpful, data-backed insights using the real store data provided below.
When referencing products, cite exact quantities, stock levels, suppliers, and actionable advice.

CURRENT STORE INVENTORY & OPERATIONAL CONTEXT:
{json.dumps(context_data, indent=2)}

Format your response cleanly with bullet points, key metrics, and recommended actions.
"""

        # Try calling Ollama
        try:
            res = requests.post(
                f"{base_url}/api/generate",
                json={
                    'model': model,
                    'prompt': f"{system_prompt}\n\nUser Question: {message}\n\nInventra AI Assistant Response:",
                    'stream': False
                },
                timeout=6
            )
            if res.status_code == 200:
                data = res.json()
                reply = data.get('response', '').strip()
                if reply:
                    return {
                        'reply': reply,
                        'data': structured_data,
                        'generated_by': f'ollama-{model}',
                        'context_summary': context_data
                    }
        except Exception:
            # Ollama not running or timed out; execute intelligent local fallback
            pass

        # Intelligent Fallback Engine using exact DB context
        fallback_reply = cls._generate_intelligent_fallback(message, context_data)
        return {
            'reply': fallback_reply,
            'data': structured_data,
            'generated_by': 'inventra-ai-engine (data-aware)',
            'context_summary': context_data
        }

    @staticmethod
    def _generate_intelligent_fallback(query, context):
        q = query.lower()
        health = context.get('inventory_health', {})
        score = health.get('score', 86)
        status = health.get('status', 'Healthy')

        if any(w in q for w in ['low', 'reorder', 'run out', 'stock-out', 'shortage']):
            low = context.get('low_stock_products', [])
            recs = context.get('reorder_recommendations', [])
            if low:
                lines = [f"**Inventra Inventory Analysis:** There are currently **{len(low)}** products requiring immediate attention:"]
                for p in low[:4]:
                    lines.append(f"• **{p['name']}**: Only **{p['stock']}** units in stock (Safety threshold: {p['safety_stock']}, Reorder Point: {p['reorder_point']}).")
                if recs:
                    lines.append("\n**Top AI Reorder Recommendations:**")
                    for r in recs[:3]:
                        lines.append(f"• **{r['name']}**: Recommend ordering **{r['qty']} units** [{r['priority']} Priority]. Reason: {r['reason']}")
                lines.append("\n👉 *Recommendation:* Open the **Reorder Recommendations** tab or **Procurement Hub** to generate Purchase Orders with 1-click.")
                return "\n".join(lines)
            else:
                return f"All inventory levels are currently above reorder thresholds! Overall inventory health score is **{score}/100** ({status})."

        elif any(w in q for w in ['fast', 'velocity', 'top selling', 'best selling']):
            fast = context.get('fast_moving', [])
            if fast:
                lines = ["**Fast-Moving Product Velocity Report (Last 30 Days):**"]
                for f in fast:
                    lines.append(f"• **{f['name']}**: **{f['units_30d']}** units sold (~{f['daily_avg']} units/day).")
                lines.append("\n💡 *AI Insight:* Maintain high safety stock buffers for these SKU leaders to avoid lost sales during demand peaks.")
                return "\n".join(lines)

        elif any(w in q for w in ['slow', 'dead stock', 'overstock']):
            slow = context.get('slow_moving', [])
            overstock = context.get('overstock', [])
            lines = ["**Inventory Aging & Overstock Diagnostics:**"]
            if slow:
                lines.append("**Slow-Moving Items:**")
                for s in slow[:3]:
                    lines.append(f"• **{s['name']}** ({s['current_stock']} on hand) — Action: *{s['action']}*")
            if overstock:
                lines.append("\n**Overstock Risks:**")
                for o in overstock[:3]:
                    lines.append(f"• **{o['name']}**: **{o['excess_units']} excess units** tying up **₹{o['excess_value']}** in working capital.")
            return "\n".join(lines)

        elif any(w in q for w in ['supplier', 'lead time', 'vendor', 'procure']):
            sups = context.get('suppliers', [])
            if sups:
                lines = ["**Supplier Intelligence & Performance:**"]
                for s in sups:
                    lines.append(f"• **{s['name']}**: Rating: **{s['rating']}★** | Reliability: **{s['reliability']}%** | Lead Time: **{s['lead_time_days']} days**")
                best = min(sups, key=lambda x: x['lead_time_days']) if sups else None
                if best:
                    lines.append(f"\n🚀 **Fastest Supplier:** **{best['name']}** with an average turnaround of only **{best['lead_time_days']} days**.")
                return "\n".join(lines)

        elif any(w in q for w in ['forecast', 'demand', 'future', 'predict']):
            fc = context.get('demand_forecasts', [])
            if fc:
                lines = ["**AI Machine Learning Demand Forecast (Next 30 Days):**"]
                for f in fc[:4]:
                    trend_icon = "📈" if f['status'] == 'High Demand' else "📉"
                    lines.append(f"• {trend_icon} **{f['name']}**: Projected weekly demand **{f['predicted']} units** ({f['change_pct']:+.1f}% shift — *{f['status']}*).")
                lines.append("\nForecasts are calculated with Random Forest Regressor & Gradient Boosting models.")
                return "\n".join(lines)

        elif any(w in q for w in ['alert', 'warning', 'critical']):
            alerts = context.get('unread_alerts', [])
            if alerts:
                lines = [f"**Today's Critical Alerts ({len(alerts)} Unread):**"]
                for a in alerts:
                    lines.append(f"• [{a['severity'].upper()}] **{a['title']}**: {a['action']}")
                return "\n".join(lines)
            return "No critical system alerts right now. All inventory flows and purchase orders are running smoothly."

        # Default general overview
        return (
            f"Hello! I am your **Inventra AI Retail Assistant**.\n\n"
            f"• **Current Inventory Health Score:** **{score}/100** ({status})\n"
            f"• **Stock-Outs:** {health.get('stock_outs', 0)} items\n"
            f"• **Critical / Low Stock:** {health.get('critical_items', 0) + health.get('low_stock_items', 0)} items\n"
            f"• **Overstock:** {health.get('overstock_items', 0)} items\n\n"
            f"You can ask me questions like:\n"
            f"- *'Which products are running low?'*\n"
            f"- *'What products should I reorder today?'*\n"
            f"- *'Which products are fast moving?'*\n"
            f"- *'Show upcoming demand forecasts'*\n"
            f"- *'Which supplier has the shortest lead time?'*"
        )
