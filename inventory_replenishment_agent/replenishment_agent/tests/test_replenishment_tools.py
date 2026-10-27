"""
Unit tests for core replenishment tools:
- get_stock_level()
- calculate_daily_sales()
- calculate_reorder_point()
- recommend_order_quantity()
- save_replenishment_plan() (Idempotency)
Compatible with pytest and standard unittest.
"""

import unittest
import os
import sys
import shutil
import tempfile
import json

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.tools import (
    get_stock_level,
    calculate_daily_sales,
    calculate_reorder_point,
    recommend_order_quantity,
    save_replenishment_plan,
)
from agent.state import ReplenishmentPlan, StockLevel, SalesStats, ReorderPointResult, OrderRecommendation

class TestReplenishmentTools(unittest.TestCase):
    def setUp(self):
        self.sample_inventory = [
            {
                "product_id": "P101",
                "location": "LOC_EAST",
                "sku_name": "Test SKU 101",
                "category": "Mechanical",
                "on_hand": 15,
                "reserved": 5,
                "incoming_confirmed": 10,
                "incoming_unconfirmed": 20,
                "unit_cost": 45.50,
                "target_stock_level": 150,
                "safety_stock": 25,
            },
            {
                "product_id": "P103",
                "location": "LOC_WEST",
                "sku_name": "Precision Bushing",
                "category": "Mechanical",
                "on_hand": 18,
                "reserved": 8,
                "incoming_confirmed": 85,
                "incoming_unconfirmed": 150,
                "unit_cost": 68.0,
                "target_stock_level": 120,
                "safety_stock": 20,
            }
        ]

        self.sample_sales = [
            {"product_id": "P101", "location": "LOC_EAST", "quantity_sold": 4, "sale_date": "2024-03-01"},
            {"product_id": "P101", "location": "LOC_EAST", "quantity_sold": 6, "sale_date": "2024-03-02"},
            {"product_id": "P101", "location": "LOC_EAST", "quantity_sold": 5, "sale_date": "2024-03-03"},
        ]

    def test_stock_level_available_position_excludes_unconfirmed(self):
        """
        Tests Requirement 6: Available inventory position = on_hand - reserved + confirmed incoming stock.
        Unconfirmed incoming stock MUST NOT be counted.
        """
        stock = get_stock_level(self.sample_inventory, "P101", "LOC_EAST")
        # 15 on_hand - 5 reserved + 10 confirmed = 20
        self.assertEqual(stock.available_position, 20)
        # Verify unconfirmed was recorded but NOT added to available position
        self.assertEqual(stock.incoming_unconfirmed, 20)
        self.assertEqual(stock.on_hand, 15)
        self.assertEqual(stock.reserved, 5)

        # Test P103 where incoming confirmed is large
        stock_p103 = get_stock_level(self.sample_inventory, "P103", "LOC_WEST")
        # 18 on_hand - 8 reserved + 85 confirmed = 95. Unconfirmed 150 is ignored.
        self.assertEqual(stock_p103.available_position, 95)
        self.assertEqual(stock_p103.incoming_unconfirmed, 150)

    def test_calculate_daily_sales_insufficient_data_p900(self):
        """
        Tests Requirement 5: If no sales history exists, flag insufficient data and never invent a quantity.
        """
        # P900 has zero records in sales
        sales_stats = calculate_daily_sales(self.sample_sales, "P900", "LOC_EAST", window_days=30)
        self.assertFalse(sales_stats.is_sufficient)
        self.assertEqual(sales_stats.status, "INSUFFICIENT_DATA")
        self.assertEqual(sales_stats.average_daily_sales, 0.0)
        self.assertEqual(sales_stats.total_sales, 0)
        self.assertIn("No sales history exists", sales_stats.message)

    def test_calculate_daily_sales_normal(self):
        """Tests rolling-window average daily sales computation."""
        # Total units = 4 + 6 + 5 = 15. Window = 30 days. Average = 15 / 30 = 0.5
        sales_stats = calculate_daily_sales(self.sample_sales, "P101", "LOC_EAST", window_days=30)
        self.assertTrue(sales_stats.is_sufficient)
        self.assertEqual(sales_stats.total_sales, 15)
        self.assertEqual(sales_stats.average_daily_sales, 0.5)

    def test_reorder_point_calculation(self):
        """
        Tests Requirement 7: Reorder point = average daily sales * lead_time_days + safety_stock
        using deterministic Python arithmetic.
        """
        ads = 4.0
        lead_time = 10.0
        safety_stock = 25
        # Expected ROP = (4.0 * 10.0) + 25 = 65.0
        result = calculate_reorder_point(ads, lead_time, safety_stock)
        self.assertEqual(result.reorder_point, 65.0)
        self.assertIn("ROP (65.00)", result.formula_used)

    def test_recommend_order_quantity_low_stock_with_moq_and_pack_size(self):
        """
        Tests Requirement 8: Target stock level, available position, MOQ, pack size ceiling.
        """
        # Target: 150, Available: 20 -> Shortage: 130
        # ROP: 60. Available (20) < ROP (60) -> Reorder required.
        # MOQ: 50, Pack size: 10. 130 is >= 50 and multiple of 10.
        rec = recommend_order_quantity(
            target_stock_level=150,
            available_position=20,
            reorder_point=60.0,
            unit_cost=10.0,
            supplier_moq=50,
            pack_size=10
        )
        self.assertTrue(rec.should_reorder)
        self.assertEqual(rec.recommended_order_quantity, 130)
        self.assertEqual(rec.gross_shortage, 130)

        # Test where shortage is below MOQ:
        # Target: 50, Available: 30 -> Shortage: 20. But MOQ: 50 -> must raise to 50.
        rec_moq = recommend_order_quantity(
            target_stock_level=50,
            available_position=30,
            reorder_point=40.0,
            unit_cost=5.0,
            supplier_moq=50,
            pack_size=1
        )
        self.assertTrue(rec_moq.should_reorder)
        self.assertEqual(rec_moq.recommended_order_quantity, 50)

        # Test pack size ceiling rounding:
        # Shortage 73 with pack size 25 -> math.ceil(73/25)*25 = 3 * 25 = 75
        rec_pack = recommend_order_quantity(
            target_stock_level=100,
            available_position=27,
            reorder_point=50.0,
            unit_cost=2.0,
            supplier_moq=20,
            pack_size=25
        )
        self.assertTrue(rec_pack.should_reorder)
        self.assertEqual(rec_pack.recommended_order_quantity, 75)

    def test_recommend_order_quantity_sufficient_stock(self):
        """
        When available_position >= reorder_point, recommended order quantity is 0.
        """
        rec = recommend_order_quantity(
            target_stock_level=100,
            available_position=80,
            reorder_point=50.0,
            unit_cost=15.0
        )
        self.assertFalse(rec.should_reorder)
        self.assertEqual(rec.recommended_order_quantity, 0)
        self.assertEqual(rec.estimated_cost, 0.0)

    def test_save_replenishment_plan_idempotency(self):
        """
        Tests Requirement 10: Retrying the same request returns existing plan ID instead of duplicate.
        """
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, "test_plans.json")

        try:
            stock = StockLevel("P101", "LOC_EAST", "Bearing", "Mechanical", 15, 5, 10, 20, 20, 45.5, 150, 25, "Breakdown")
            sales = SalesStats("P101", "LOC_EAST", 30, 90, 30, 3.0, True, "SUFFICIENT_DATA", "OK")
            rop = ReorderPointResult(3.0, 14.0, 25, 67.0, "Formula")
            rec = OrderRecommendation(True, 20, 67.0, 150, 130, 50, 10, 130, 5915.0, ["Assumption"], [])

            plan = ReplenishmentPlan(
                plan_id="PLAN-ORIGINAL-1",
                idempotency_key="IDEMP-P101-EAST-2024",
                created_at="2024-03-15T10:00:00Z",
                product_id="P101",
                location="LOC_EAST",
                stock_level=stock,
                sales_stats=sales,
                reorder_point_result=rop,
                recommendation=rec,
                status="APPROVED_REORDER",
                notes="Original plan"
            )

            # First save: must be new
            res_plan1, is_new1 = save_replenishment_plan(plan, storage_path=temp_file)
            self.assertTrue(is_new1)
            self.assertEqual(res_plan1.plan_id, "PLAN-ORIGINAL-1")

            # Duplicate save with different plan_id but same idempotency_key
            plan_dup = ReplenishmentPlan(
                plan_id="PLAN-DUPLICATE-99",
                idempotency_key="IDEMP-P101-EAST-2024",
                created_at="2024-03-15T10:05:00Z",
                product_id="P101",
                location="LOC_EAST",
                stock_level=stock,
                sales_stats=sales,
                reorder_point_result=rop,
                recommendation=rec,
                status="APPROVED_REORDER",
                notes="Duplicate attempt"
            )

            res_plan2, is_new2 = save_replenishment_plan(plan_dup, storage_path=temp_file)
            # Idempotency triggered: should not create a new plan
            self.assertFalse(is_new2)

            # Verify storage file only contains exactly 1 entry
            with open(temp_file, "r") as f:
                saved = json.load(f)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["idempotency_key"], "IDEMP-P101-EAST-2024")
        finally:
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    unittest.main()
