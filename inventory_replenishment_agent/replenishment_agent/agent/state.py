"""
State Definitions and Structured Output Models.
All models use Python dataclasses with type hints, structured outputs, and serialization helpers.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
import datetime
import hashlib
import json

@dataclass
class StockLevel:
    product_id: str
    location: str
    sku_name: str
    category: str
    on_hand: int
    reserved: int
    incoming_confirmed: int
    incoming_unconfirmed: int
    available_position: int
    unit_cost: float
    target_stock_level: int
    safety_stock: int
    calculation_breakdown: str

@dataclass
class SalesStats:
    product_id: str
    location: str
    window_days: int
    total_sales: int
    data_points_count: int
    average_daily_sales: float
    is_sufficient: bool
    status: str
    message: str

@dataclass
class ReorderPointResult:
    average_daily_sales: float
    lead_time_days: float
    safety_stock: int
    reorder_point: float
    formula_used: str

@dataclass
class PolicyChunk:
    chunk_id: str
    document_name: str
    section: str
    policy_version: str
    effective_date: str
    source_references: str
    content: str
    relevance_score: float = 0.0

@dataclass
class OrderRecommendation:
    should_reorder: bool
    available_position: int
    reorder_point: float
    target_stock_level: int
    gross_shortage: int
    supplier_moq: int
    pack_size: int
    recommended_order_quantity: int
    estimated_cost: float
    assumptions: List[str]
    policy_citations: List[Dict[str, str]]

@dataclass
class ReplenishmentPlan:
    plan_id: str
    idempotency_key: str
    created_at: str
    product_id: str
    location: str
    stock_level: StockLevel
    sales_stats: SalesStats
    reorder_point_result: Optional[ReorderPointResult]
    recommendation: OrderRecommendation
    status: str
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class StageTrace:
    stage_name: str
    timestamp: str
    status: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentState:
    thread_id: str
    product_id: str
    location: str
    target_stock_level: Optional[int] = None
    lookback_days: int = 30
    manual_lead_time: Optional[float] = None
    
    # Workflow tracking
    current_stage: str = "Request"
    stage_traces: List[StageTrace] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    ask_prompt: Optional[str] = None
    
    # Retrieval and Grading
    query_rewrites_count: int = 0
    max_query_rewrites: int = 2
    retrieved_chunks: List[PolicyChunk] = field(default_factory=list)
    graded_chunks: List[PolicyChunk] = field(default_factory=list)
    
    # Intermediate tool outputs
    stock_level: Optional[StockLevel] = None
    sales_stats: Optional[SalesStats] = None
    reorder_point_result: Optional[ReorderPointResult] = None
    recommendation: Optional[OrderRecommendation] = None
    plan: Optional[ReplenishmentPlan] = None
    
    # Error or termination
    is_terminal: bool = False
    termination_reason: Optional[str] = None

    def log_stage(self, stage: str, status: str, summary: str, details: Optional[Dict[str, Any]] = None, set_current_stage: bool = True):
        trace = StageTrace(
            stage_name=stage,
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
            status=status,
            summary=summary,
            details=details or {}
        )
        self.stage_traces.append(trace)
        if set_current_stage:
            self.current_stage = stage

    def compute_idempotency_key(self) -> str:
        as_of_date = datetime.date.today().isoformat()
        tgt = str(self.target_stock_level or "DEFAULT")
        raw = f"{self.product_id}|{self.location}|{tgt}|{as_of_date}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
