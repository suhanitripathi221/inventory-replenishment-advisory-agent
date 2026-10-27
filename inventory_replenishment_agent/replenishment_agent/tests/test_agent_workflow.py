"""
End-to-End Workflow & Integration Tests:
- Low stock scenario (P101)
- Sufficient stock scenario (P102)
- Incoming stock covering the gap (P103)
- No sales history guardrail (P900)
- Missing lead time operator Ask prompt (P204)
- Policy retriever section chunking & metadata preservation
Compatible with pytest and standard unittest.
"""

import unittest
import os
import sys

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.workflow import ReplenishmentWorkflow
from agent.retriever import PolicyRetriever
from agent.data_loader import DataLoader

class TestAgentWorkflow(unittest.TestCase):
    def setUp(self):
        self.workflow = ReplenishmentWorkflow()
        self.retriever = PolicyRetriever()

    def test_scenario_low_stock_p101(self):
        """
        Scenario 1: Low Stock SKU P101.
        On-hand: 15, Reserved: 5, Confirmed: 10 -> Available: 20.
        ROP is approx 71 units. Available < ROP -> Triggers Reorder!
        Target is 150 -> Order quantity recommended.
        """
        state = self.workflow.get_or_create_state("P101", "LOC_EAST")
        state = self.workflow.run(state)

        self.assertTrue(state.is_terminal)
        self.assertEqual(state.current_stage, "Recommend")
        self.assertIsNotNone(state.plan)
        self.assertEqual(state.plan.status, "APPROVED_REORDER")
        self.assertTrue(state.plan.recommendation.should_reorder)
        self.assertGreater(state.plan.recommendation.recommended_order_quantity, 0)
        self.assertEqual(state.stock_level.available_position, 20)

        # Check policy citation inclusion
        citations = state.plan.recommendation.policy_citations
        self.assertGreater(len(citations), 0)
        self.assertIn("v2.4", [c.get("policy_version") for c in citations])

    def test_scenario_sufficient_stock_p102(self):
        """
        Scenario 2: Sufficient Stock SKU P102.
        On-hand: 120, Reserved: 10 -> Available: 110.
        Available (110) > ROP (~27) -> Order Quantity MUST be 0.
        """
        state = self.workflow.get_or_create_state("P102", "LOC_EAST")
        state = self.workflow.run(state)

        self.assertTrue(state.is_terminal)
        self.assertIsNotNone(state.plan)
        self.assertEqual(state.plan.status, "SUFFICIENT_STOCK")
        self.assertFalse(state.plan.recommendation.should_reorder)
        self.assertEqual(state.plan.recommendation.recommended_order_quantity, 0)

    def test_scenario_incoming_stock_covers_gap_p103(self):
        """
        Scenario 3: Incoming confirmed stock covers the gap (SKU P103).
        On-hand: 18, Reserved: 8, Incoming Confirmed: 85 -> Available: 95.
        Unconfirmed incoming is 150 (ignored).
        ROP is approx 64.1.
        Because confirmed incoming (85) brings available to 95 >= ROP (64.1),
        NO reorder is required!
        """
        state = self.workflow.get_or_create_state("P103", "LOC_WEST")
        state = self.workflow.run(state)

        self.assertTrue(state.is_terminal)
        self.assertEqual(state.stock_level.available_position, 95)
        self.assertEqual(state.stock_level.incoming_unconfirmed, 150)
        self.assertFalse(state.plan.recommendation.should_reorder)
        self.assertEqual(state.plan.recommendation.recommended_order_quantity, 0)

    def test_scenario_no_sales_history_p900(self):
        """
        Scenario 4: No sales history guardrail (SKU P900).
        MUST flag insufficient data.
        MUST NOT invent or hallucinate sales velocity or order quantity.
        Recommended order quantity MUST be 0 with HALTED_INSUFFICIENT_DATA status.
        """
        state = self.workflow.get_or_create_state("P900", "LOC_EAST")
        state = self.workflow.run(state)

        self.assertTrue(state.is_terminal)
        self.assertFalse(state.sales_stats.is_sufficient)
        self.assertEqual(state.sales_stats.status, "INSUFFICIENT_DATA")
        self.assertEqual(state.sales_stats.average_daily_sales, 0.0)
        self.assertEqual(state.plan.status, "HALTED_INSUFFICIENT_DATA")
        self.assertEqual(state.plan.recommendation.recommended_order_quantity, 0)
        self.assertIn("INSUFFICIENT DATA GUARDRAIL", state.plan.recommendation.assumptions[0])

    def test_scenario_missing_lead_time_ask_stage_p204(self):
        """
        Scenario 5: Missing lead time triggers Ask stage (SKU P204).
        Supplier database has null lead_time_days.
        Workflow MUST pause at stage 'Ask', prompt user, and NOT proceed until lead time is provided.
        When lead time is provided, workflow resumes to completion.
        """
        state = self.workflow.get_or_create_state("P204", "LOC_CENTRAL")
        state = self.workflow.run(state)

        # First run without manual lead time: should pause at Ask
        self.assertFalse(state.is_terminal)
        self.assertEqual(state.current_stage, "Ask")
        self.assertIn("lead_time_days", state.missing_fields)
        self.assertIsNotNone(state.ask_prompt)
        self.assertIn("Missing critical parameter: Supplier Lead Time", state.ask_prompt)

        # Now simulate operator supplying the missing value (e.g. 15 days)
        state.manual_lead_time = 15.0
        state = self.workflow.run(state)

        # Now workflow finishes
        self.assertTrue(state.is_terminal)
        self.assertEqual(state.current_stage, "Recommend")
        self.assertIsNotNone(state.plan)
        self.assertEqual(state.plan.reorder_point_result.lead_time_days, 15.0)

    def test_policy_retriever_metadata_preservation(self):
        """
        Scenario 6: Policy Retriever chunking & metadata preservation.
        Must preserve:
        - document_name
        - section
        - policy_version (v2.4)
        - effective_date (2024-03-01)
        - source_references
        """
        chunks = self.retriever.get_all_chunks()
        self.assertGreaterEqual(len(chunks), 5)
        
        for c in chunks:
            self.assertEqual(c.document_name, "Corporate Inventory Replenishment & Reorder Policy")
            self.assertEqual(c.policy_version, "v2.4")
            self.assertEqual(c.effective_date, "2024-03-01")
            self.assertTrue(c.section.startswith("SECTION") or c.section.startswith("Full"))
            self.assertIn("reorder_policy.pdf", c.source_references)
            self.assertGreater(len(c.content), 20)

        # Test query retrieval
        retrieved = self.retriever.retrieve("Available inventory position unconfirmed", top_k=1)
        self.assertEqual(len(retrieved), 1)
        self.assertIn("SECTION 2", retrieved[0].section)

if __name__ == "__main__":
    unittest.main()
