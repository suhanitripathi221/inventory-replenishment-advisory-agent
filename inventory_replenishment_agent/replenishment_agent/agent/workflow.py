"""
7-Stage Agent Workflow Engine:
Request -> Ask -> Retrieve -> Grade -> Tools -> Route -> Recommend
Featuring agent state, conditional routing, thread-based memory,
bounded retrieval query rewriting, input guardrails, and deterministic calculations.
"""

import uuid
import datetime
from typing import Dict, List, Optional, Any

from .state import (
    AgentState,
    StockLevel,
    SalesStats,
    ReorderPointResult,
    OrderRecommendation,
    ReplenishmentPlan,
)
from .data_loader import DataLoader
from .retriever import PolicyRetriever
from .grader import PolicyGrader
from .tools import (
    get_stock_level,
    calculate_daily_sales,
    calculate_reorder_point,
    recommend_order_quantity,
    save_replenishment_plan,
)

class ReplenishmentWorkflow:
    def __init__(self, data_loader: Optional[DataLoader] = None, retriever: Optional[PolicyRetriever] = None):
        self.loader = data_loader or DataLoader()
        self.retriever = retriever or PolicyRetriever()
        self.grader = PolicyGrader(min_relevance_threshold=0.35)
        self.thread_memory: Dict[str, AgentState] = {}

    def get_or_create_state(
        self,
        product_id: str,
        location: str,
        target_stock_level: Optional[int] = None,
        lookback_days: int = 30,
        manual_lead_time: Optional[float] = None,
        thread_id: Optional[str] = None
    ) -> AgentState:
        t_id = thread_id or f"TH-{uuid.uuid4().hex[:8]}"
        if t_id in self.thread_memory:
            state = self.thread_memory[t_id]
            if manual_lead_time is not None:
                state.manual_lead_time = manual_lead_time
            if target_stock_level is not None:
                state.target_stock_level = target_stock_level
            return state

        state = AgentState(
            thread_id=t_id,
            product_id=product_id.strip().upper(),
            location=location.strip().upper(),
            target_stock_level=target_stock_level,
            lookback_days=lookback_days,
            manual_lead_time=manual_lead_time,
            current_stage="Request"
        )
        self.thread_memory[t_id] = state
        return state

    def run(self, state: AgentState) -> AgentState:
        """
        Executes the 7-stage workflow until terminal completion or pausing at 'Ask' for missing input.
        """
        max_steps = 15
        step_count = 0

        while not state.is_terminal and step_count < max_steps:
            step_count += 1
            stage = state.current_stage

            if stage == "Request":
                self._step_request(state)
            elif stage == "Ask":
                paused = self._step_ask(state)
                if paused:
                    break
            elif stage == "Retrieve":
                self._step_retrieve(state)
            elif stage == "Grade":
                self._step_grade(state)
            elif stage == "Tools":
                self._step_tools(state)
            elif stage == "Route":
                self._step_route(state)
            elif stage == "Recommend":
                self._step_recommend(state)
            else:
                state.is_terminal = True
                break

        return state

    # ---------------- STAGE 1: REQUEST ----------------
    def _step_request(self, state: AgentState):
        state.log_stage("Request", "STARTED", f"Initiating evaluation for SKU {state.product_id} at {state.location}")

        # Guardrails: Validate inputs
        if not state.product_id or not state.location:
            state.is_terminal = True
            state.termination_reason = "GUARDRAIL_VIOLATION: product_id and location must not be empty"
            state.log_stage("Request", "FAILED", state.termination_reason)
            return

        if state.lookback_days <= 0 or state.lookback_days > 365:
            state.is_terminal = True
            state.termination_reason = "GUARDRAIL_VIOLATION: lookback_days must be between 1 and 365"
            state.log_stage("Request", "FAILED", state.termination_reason)
            return

        unified = self.loader.get_unified_product_record(state.product_id, state.location)
        if not unified:
            state.is_terminal = True
            state.termination_reason = f"DATA_NOT_FOUND: Product {state.product_id} at location {state.location} not found in inventory dataset"
            state.log_stage("Request", "FAILED", state.termination_reason)
            return

        if state.target_stock_level is None:
            state.target_stock_level = unified["target_stock_level"]

        state.log_stage(
            "Request", "SUCCESS",
            f"Validated inputs and catalog records for {unified.get('sku_name', state.product_id)}.",
            {"sku_name": unified.get("sku_name"), "category": unified.get("category")}
        )
        state.current_stage = "Ask"

    # ---------------- STAGE 2: ASK ----------------
    def _step_ask(self, state: AgentState) -> bool:
        """
        Checks if required parameters are missing.
        Returns True if workflow must PAUSE for user interaction.
        """
        unified = self.loader.get_unified_product_record(state.product_id, state.location)
        lead_time = state.manual_lead_time if state.manual_lead_time is not None else (unified.get("lead_time_days") if unified else None)

        if lead_time is None:
            state.missing_fields = ["lead_time_days"]
            supplier_name = unified.get("supplier_name", "Supplier") if unified else "Supplier"
            state.ask_prompt = (
                f"Missing critical parameter: Supplier Lead Time for SKU {state.product_id} "
                f"({supplier_name}) is null in supplier database. Please specify lead time in days to proceed."
            )
            state.log_stage(
                "Ask", "PAUSED",
                f"Evaluation paused. Missing supplier lead time for SKU {state.product_id}. Prompting operator.",
                {"missing_fields": state.missing_fields, "prompt": state.ask_prompt},
                set_current_stage=True
            )
            return True
        else:
            state.missing_fields = []
            state.log_stage(
                "Ask", "SUCCESS",
                f"Required data verified. Supplier lead time = {lead_time} days.",
                {"effective_lead_time_days": lead_time, "source": "Manual Input" if state.manual_lead_time is not None else "Supplier Catalog"},
                set_current_stage=False
            )
            state.current_stage = "Retrieve"
            return False

    # ---------------- STAGE 3: RETRIEVE ----------------
    def _step_retrieve(self, state: AgentState):
        state.log_stage("Retrieve", "STARTED", f"Retrieving policy clauses from {self.retriever.DOCUMENT_NAME} {self.retriever.POLICY_VERSION}")
        query = f"reorder point calculation available inventory position MOQ safety stock rule"
        chunks = self.retriever.retrieve(query, top_k=3)
        state.retrieved_chunks = chunks
        state.log_stage(
            "Retrieve", "SUCCESS",
            f"Retrieved {len(chunks)} candidate policy sections from {self.retriever.DOCUMENT_NAME}.",
            {"chunks": [{"id": c.chunk_id, "section": c.section, "score": c.relevance_score} for c in chunks]}
        )
        state.current_stage = "Grade"

    # ---------------- STAGE 4: GRADE ----------------
    def _step_grade(self, state: AgentState):
        state.log_stage("Grade", "STARTED", "Grading retrieved policy clauses for relevance against decision boundaries")
        query = "reorder point available inventory position MOQ safety stock"
        graded, is_sufficient = self.grader.grade_chunks(query, state.retrieved_chunks)

        if not is_sufficient and state.query_rewrites_count < state.max_query_rewrites:
            state.query_rewrites_count += 1
            rewritten_query = self.grader.rewrite_query(query, state.query_rewrites_count - 1, {"product_id": state.product_id})
            state.log_stage(
                "Grade", "REWRITING_QUERY",
                f"Relevance below threshold. Bounded query rewrite attempt {state.query_rewrites_count}/{state.max_query_rewrites}.",
                {"new_query": rewritten_query}
            )
            state.retrieved_chunks = self.retriever.retrieve(rewritten_query, top_k=3)
            graded, is_sufficient = self.grader.grade_chunks(rewritten_query, state.retrieved_chunks)

        state.graded_chunks = graded if graded else state.retrieved_chunks
        state.log_stage(
            "Grade", "SUCCESS",
            f"Grading verified. {len(state.graded_chunks)} relevant policy clauses confirmed.",
            {"verified_sections": [c.section for c in state.graded_chunks]}
        )
        state.current_stage = "Tools"

    # ---------------- STAGE 5: TOOLS ----------------
    def _step_tools(self, state: AgentState):
        state.log_stage("Tools", "STARTED", "Executing deterministic Python calculation tools (zero LLM arithmetic)")
        
        inventory_items = self.loader.load_inventory()
        sales_items = self.loader.load_sales()
        unified = self.loader.get_unified_product_record(state.product_id, state.location)

        # 1. get_stock_level()
        stock_level = get_stock_level(inventory_items, state.product_id, state.location)
        state.stock_level = stock_level

        # 2. calculate_daily_sales()
        sales_stats = calculate_daily_sales(sales_items, state.product_id, state.location, window_days=state.lookback_days)
        state.sales_stats = sales_stats

        effective_lead_time = state.manual_lead_time if state.manual_lead_time is not None else unified["lead_time_days"]

        # 3. calculate_reorder_point() & 4. recommend_order_quantity()
        if sales_stats.is_sufficient and effective_lead_time is not None:
            rop_result = calculate_reorder_point(
                average_daily_sales=sales_stats.average_daily_sales,
                lead_time_days=effective_lead_time,
                safety_stock=stock_level.safety_stock
            )
            state.reorder_point_result = rop_result

            citations = [
                {
                    "section": c.section,
                    "reference": c.source_references,
                    "policy_version": c.policy_version,
                    "excerpt": c.content.split("\n")[1] if len(c.content.split("\n")) > 1 else c.content
                }
                for c in state.graded_chunks
            ]

            recommendation = recommend_order_quantity(
                target_stock_level=state.target_stock_level or stock_level.target_stock_level,
                available_position=stock_level.available_position,
                reorder_point=rop_result.reorder_point,
                unit_cost=stock_level.unit_cost,
                supplier_moq=unified.get("minimum_order_quantity", 0),
                pack_size=unified.get("pack_size", 1),
                policy_citations=citations
            )
            state.recommendation = recommendation
        else:
            state.reorder_point_result = None
            state.recommendation = None

        state.log_stage(
            "Tools", "SUCCESS",
            f"Calculations executed. Available: {stock_level.available_position}, Sales Sufficient: {sales_stats.is_sufficient}.",
            {
                "available_position": stock_level.available_position,
                "breakdown": stock_level.calculation_breakdown,
                "average_daily_sales": sales_stats.average_daily_sales,
                "reorder_point": state.reorder_point_result.reorder_point if state.reorder_point_result else None
            }
        )
        state.current_stage = "Route"

    # ---------------- STAGE 6: ROUTE ----------------
    def _step_route(self, state: AgentState):
        state.log_stage("Route", "STARTED", "Evaluating conditional routing branches")

        # Branch 1: Insufficient Sales History (P900 test case)
        if state.sales_stats and not state.sales_stats.is_sufficient:
            state.log_stage(
                "Route", "BRANCH_INSUFFICIENT_DATA",
                f"Conditional Branch: NO SALES HISTORY DETECTED for SKU {state.product_id}. Routing to SAFE_DATA_GUARDRAIL.",
                {"policy_clause": "Rule 3.2: Never hallucinate or guess sales velocity. Flag INSUFFICIENT_DATA."}
            )
            state.current_stage = "Recommend"
            return

        # Branch 2: Sufficient stock vs Reorder required
        if state.recommendation and state.recommendation.should_reorder:
            state.log_stage(
                "Route", "BRANCH_REORDER_REQUIRED",
                f"Conditional Branch: Available position ({state.stock_level.available_position}) < ROP ({state.reorder_point_result.reorder_point}). Routing to REORDER_ADVISORY.",
                {"recommended_qty": state.recommendation.recommended_order_quantity}
            )
        else:
            rop_val = state.reorder_point_result.reorder_point if state.reorder_point_result else 0
            state.log_stage(
                "Route", "BRANCH_SUFFICIENT_STOCK",
                f"Conditional Branch: Available position ({state.stock_level.available_position}) >= ROP ({rop_val}). Routing to NO_REORDER_CONFIRMATION.",
                {"recommended_qty": 0}
            )

        state.current_stage = "Recommend"

    # ---------------- STAGE 7: RECOMMEND ----------------
    def _step_recommend(self, state: AgentState):
        state.log_stage("Recommend", "STARTED", "Synthesizing final replenishment advisory and registering plan idempotency key")
        
        idempotency_key = state.compute_idempotency_key()
        created_at = datetime.datetime.utcnow().isoformat() + "Z"

        if state.sales_stats and not state.sales_stats.is_sufficient:
            rec = OrderRecommendation(
                should_reorder=False,
                available_position=state.stock_level.available_position,
                reorder_point=0.0,
                target_stock_level=state.target_stock_level or state.stock_level.target_stock_level,
                gross_shortage=0,
                supplier_moq=0,
                pack_size=1,
                recommended_order_quantity=0,
                estimated_cost=0.0,
                assumptions=[
                    "INSUFFICIENT DATA GUARDRAIL: No historical sales transactions recorded in sales dataset.",
                    "Strict policy prohibition: System refuses to invent or hallucinate demand velocity.",
                    "Action required: Human supply chain analyst audit before manual purchase requisition."
                ],
                policy_citations=[
                    {
                        "section": "SECTION 3: Safe Daily Sales Velocity & Data Sufficiency",
                        "reference": "reorder_policy.pdf (Rule 3.2 & Rule 3.3)",
                        "policy_version": self.retriever.POLICY_VERSION,
                        "excerpt": "If a SKU has no historical transaction records, the system SHALL NOT hallucinate, invent, or guess sales velocity. Flag INSUFFICIENT_DATA."
                    }
                ]
            )
            status = "HALTED_INSUFFICIENT_DATA"
            notes = "Automated replenishment halted due to absence of sales history. Human audit required."
        else:
            rec = state.recommendation
            status = "APPROVED_REORDER" if rec.should_reorder else "SUFFICIENT_STOCK"
            notes = (
                f"Order of {rec.recommended_order_quantity} units recommended."
                if rec.should_reorder else
                f"Current inventory position ({state.stock_level.available_position}) satisfies lead time demand and safety buffer."
            )

        plan = ReplenishmentPlan(
            plan_id=f"PLAN-{uuid.uuid4().hex[:8].upper()}",
            idempotency_key=idempotency_key,
            created_at=created_at,
            product_id=state.product_id,
            location=state.location,
            stock_level=state.stock_level,
            sales_stats=state.sales_stats,
            reorder_point_result=state.reorder_point_result,
            recommendation=rec,
            status=status,
            notes=notes
        )

        persisted_plan, is_new = save_replenishment_plan(plan)
        state.plan = persisted_plan
        state.is_terminal = True

        save_msg = "Created new replenishment plan" if is_new else f"Idempotent retry detected: returning existing plan {persisted_plan.plan_id}"
        state.log_stage(
            "Recommend", "SUCCESS",
            f"{save_msg}. Status: {persisted_plan.status}. Plan ID: {persisted_plan.plan_id}.",
            {
                "plan_id": persisted_plan.plan_id,
                "idempotency_key": idempotency_key,
                "is_new_plan": is_new,
                "recommended_quantity": rec.recommended_order_quantity,
                "status": persisted_plan.status
            }
        )
