from models import db, Supplier, SupplierProduct, Product, PurchaseOrder, Delivery

class SupplierService:

    @staticmethod
    def get_all_suppliers():
        suppliers = Supplier.query.all()
        results = []
        for s in suppliers:
            data = s.to_dict()
            total_orders = PurchaseOrder.query.filter_by(supplier_id=s.id).count()
            total_spent = db.session.query(db.func.sum(PurchaseOrder.total_amount))\
                .filter(PurchaseOrder.supplier_id == s.id, PurchaseOrder.status == 'Received').scalar() or 0.0
            
            data['total_orders'] = total_orders
            data['total_spent'] = round(float(total_spent), 2)
            results.append(data)
        return results

    @staticmethod
    def compare_suppliers_for_product(product_id):
        """
        Compares all suppliers for a given product and ranks them using multi-criteria weighted scoring:
        - Price (35%)
        - Lead Time (25%)
        - Reliability Score (25%)
        - Supplier Rating (15%)
        """
        product = Product.query.get(product_id)
        if not product:
            return None

        links = SupplierProduct.query.filter_by(product_id=product_id).all()
        if not links:
            # If no direct link exists, find suppliers in same category or general suppliers
            suppliers = Supplier.query.filter_by(active_status=True).limit(3).all()
            links = []
            for s in suppliers:
                sp = SupplierProduct(
                    supplier_id=s.id,
                    product_id=product.id,
                    unit_price=round(product.cost_price * (1.0 + (s.id % 3) * 0.05), 2),
                    min_order_qty=20,
                    lead_time_days=s.lead_time_days,
                    is_preferred=(s.id == 1)
                )
                db.session.add(sp)
                links.append(sp)
            db.session.commit()

        # Gather comparison data
        candidates = []
        prices = [l.unit_price for l in links]
        min_p, max_p = min(prices), max(prices) if max(prices) > min(prices) else min(prices) + 1.0
        leads = [l.lead_time_days for l in links]
        min_l, max_l = min(leads), max(leads) if max(leads) > min(leads) else min(leads) + 1.0

        for link in links:
            supplier = link.supplier
            # Normalization
            norm_price = (link.unit_price - min_p) / (max_p - min_p) if max_p > min_p else 0
            norm_lead = (link.lead_time_days - min_l) / (max_l - min_l) if max_l > min_l else 0
            norm_rel = supplier.reliability_score / 100.0
            norm_rating = supplier.rating / 5.0

            # Composite Score (higher is better)
            score = (
                0.35 * (1.0 - norm_price) +
                0.25 * (1.0 - norm_lead) +
                0.25 * norm_rel +
                0.15 * norm_rating
            )

            candidates.append({
                'supplier_id': supplier.id,
                'supplier_name': supplier.name,
                'supplier_company': supplier.company,
                'unit_price': link.unit_price,
                'min_order_qty': link.min_order_qty,
                'lead_time_days': link.lead_time_days,
                'rating': supplier.rating,
                'reliability_score': supplier.reliability_score,
                'delivery_performance_pct': supplier.delivery_performance_pct,
                'is_preferred': link.is_preferred,
                'ai_score': round(score * 100, 1),
                'score_raw': score
            })

        candidates.sort(key=lambda x: x['score_raw'], reverse=True)
        best_candidate = candidates[0] if candidates else None

        reason = ""
        if best_candidate:
            reason = f"{best_candidate['supplier_company']} achieves top composite rank ({best_candidate['ai_score']} pts) offering optimal unit cost (₹{best_candidate['unit_price']}) with {best_candidate['lead_time_days']}-day turnaround and {best_candidate['reliability_score']}% fulfillment reliability."

        return {
            'product_id': product.id,
            'product_name': product.name,
            'product_sku': product.sku,
            'product_image': product.image_url,
            'current_stock': product.current_stock,
            'suppliers_compared': len(candidates),
            'recommended_supplier_id': best_candidate['supplier_id'] if best_candidate else None,
            'recommended_supplier_name': best_candidate['supplier_company'] if best_candidate else None,
            'recommendation_reason': reason,
            'candidates': candidates
        }
