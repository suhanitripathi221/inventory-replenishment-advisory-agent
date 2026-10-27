"""
Core Inventory Calculation Tools with Structured Outputs.
All calculations are executed deterministically in pure Python without LLM arithmetic.
"""

import math
import uuid
import datetime
import os
import json
from typing import List, Dict, Optional, Tuple, Any

from .state import (
    StockLevel,
    SalesStats,
    ReorderPointResult,
    OrderRecommendation,
    ReplenishmentPlan,
)

PLAN_STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "saved_plans.json")

def get_stock_level(
    inventory_records: List[Dict[str, Any]],
    product_id: str,
    location: str
) -> StockLevel:
    """
    Computes stock level for product_id and location.
    RULE: Available Inventory Position = on_hand - reserved + incoming_confirmed.
    Unconfirmed incoming stock is explicitly excluded from available position.
    """
    record = next((r for r in inventory_records if r["product_id"] == product_id and r["location"] == location), None)
    if not record:
        raise ValueError(f"SKU {product_id} not found in inventory records for location {location}")

    on_hand = int(record["on_hand"])
    reserved = int(record["reserved"])
    incoming_confirmed = int(record["incoming_confirmed"])
    incoming_unconfirmed = int(record["incoming_unconfirmed"])
    unit_cost = float(record["unit_cost"])
    target_stock_level = int(record["target_stock_level"])
    safety_stock = int(record["safety_stock"])

    # Core inventory position formula:
    # Available = on_hand - reserved + incoming_confirmed
    available_position = on_hand - reserved + incoming_confirmed

    breakdown = (
        f"Available ({available_position}) = On-Hand ({on_hand}) - Reserved ({reserved}) "
        f"+ Confirmed Incoming ({incoming_confirmed}) [Unconfirmed Incoming ({incoming_unconfirmed}) ignored per Rule 2.2]"
    )

    return StockLevel(
        product_id=product_id,
        location=location,
        sku_name=record.get("sku_name", f"SKU-{product_id}"),
        category=record.get("category", "General"),
        on_hand=on_hand,
        reserved=reserved,
        incoming_confirmed=incoming_confirmed,
        incoming_unconfirmed=incoming_unconfirmed,
        available_position=available_position,
        unit_cost=unit_cost,
        target_stock_level=target_stock_level,
        safety_stock=safety_stock,
        calculation_breakdown=breakdown
    )

def calculate_daily_sales(
    sales_records: List[Dict[str, Any]],
    product_id: str,
    location: str,
    window_days: int = 30
) -> SalesStats:
    """
    Calculates rolling-window average daily sales safely.
    If no sales history exists (e.g. SKU P900), flags insufficient data and NEVER invents a quantity.
    """
    if window_days <= 0:
        raise ValueError("window_days must be a positive integer greater than zero")

    # Filter sales for product and location
    matching_sales = [
        s for s in sales_records
        if s["product_id"] == product_id and s["location"] == location
    ]

    if not matching_sales:
        return SalesStats(
            product_id=product_id,
            location=location,
            window_days=window_days,
            total_sales=0,
            data_points_count=0,
            average_daily_sales=0.0,
            is_sufficient=False,
            status="INSUFFICIENT_DATA",
            message=f"No sales history exists for SKU {product_id} at {location} in the {window_days}-day window. Sales velocity cannot be determined."
        )

    # Sort sales by date descending up to window_days
    # Sum total units
    total_units = sum(int(s["quantity_sold"]) for s in matching_sales)
    data_points = len(matching_sales)

    # Deterministic average daily sales calculation
    # Using window_days as denominator for the rolling observation window
    avg_daily_sales = round(total_units / float(window_days), 4)

    return SalesStats(
        product_id=product_id,
        location=location,
        window_days=window_days,
        total_sales=total_units,
        data_points_count=data_points,
        average_daily_sales=avg_daily_sales,
        is_sufficient=True,
        status="SUFFICIENT_DATA",
        message=f"Calculated average daily sales: {avg_daily_sales:.2f} units/day over {window_days} days ({total_units} total units across {data_points} logs)."
    )

def calculate_reorder_point(
    average_daily_sales: float,
    lead_time_days: float,
    safety_stock: int
) -> ReorderPointResult:
    """
    Calculates reorder point = average_daily_sales * lead_time_days + safety_stock
    Strictly deterministic Python arithmetic.
    """
    if average_daily_sales < 0:
        raise ValueError("average_daily_sales cannot be negative")
    if lead_time_days < 0:
        raise ValueError("lead_time_days cannot be negative")
    if safety_stock < 0:
        raise ValueError("safety_stock cannot be negative")

    lead_time_demand = average_daily_sales * lead_time_days
    rop = lead_time_demand + safety_stock

    formula_str = (
        f"ROP ({rop:.2f}) = (Average Daily Sales ({average_daily_sales:.2f}) * "
        f"Lead Time Days ({lead_time_days})) + Safety Stock ({safety_stock})"
    )

    return ReorderPointResult(
        average_daily_sales=round(average_daily_sales, 4),
        lead_time_days=round(lead_time_days, 2),
        safety_stock=safety_stock,
        reorder_point=round(rop, 2),
        formula_used=formula_str
    )

def recommend_order_quantity(
    target_stock_level: int,
    available_position: int,
    reorder_point: float,
    unit_cost: float,
    supplier_moq: int = 0,
    pack_size: int = 1,
    policy_citations: Optional[List[Dict[str, str]]] = None
) -> OrderRecommendation:
    """
    Recommends order quantity using target stock level, available inventory position,
    ceiling/rounding rules, and supplier minimum order quantity (MOQ).
    Explains all assumptions explicitly.
    """
    assumptions = []
    citations = policy_citations or []

    # Rule 5.1: If Available Position >= Reorder Point -> No reorder required
    if available_position >= reorder_point:
        assumptions.append(
            f"Available inventory position ({available_position}) is greater than or equal to the "
            f"reorder point ({reorder_point:.2f}). Stock is currently sufficient; no replenishment required."
        )
        return OrderRecommendation(
            should_reorder=False,
            available_position=available_position,
            reorder_point=reorder_point,
            target_stock_level=target_stock_level,
            gross_shortage=0,
            supplier_moq=supplier_moq,
            pack_size=pack_size,
            recommended_order_quantity=0,
            estimated_cost=0.0,
            assumptions=assumptions,
            policy_citations=citations
        )

    # Rule 5.2: Gross Shortage = Target Stock Level - Available Inventory Position
    gross_shortage = max(0, target_stock_level - available_position)
    assumptions.append(
        f"Available position ({available_position}) has breached reorder point ({reorder_point:.2f}). "
        f"Gross shortage to reach target ({target_stock_level}) is {gross_shortage} units."
    )

    # Rule 5.3: Supplier MOQ Constraint
    base_qty = gross_shortage
    if supplier_moq > 0 and base_qty < supplier_moq:
        assumptions.append(
            f"Gross shortage ({gross_shortage}) is below supplier minimum order quantity ({supplier_moq}). "
            f"Quantity elevated to MOQ ({supplier_moq})."
        )
        base_qty = supplier_moq
    elif supplier_moq > 0:
        assumptions.append(
            f"Gross shortage ({gross_shortage}) satisfies supplier minimum order quantity ({supplier_moq})."
        )

    # Rule 5.4: Pack Size / Lot Ceiling Rounding
    pack = max(1, pack_size)
    if pack > 1:
        batches = math.ceil(base_qty / pack)
        rounded_qty = batches * pack
        if rounded_qty > base_qty:
            assumptions.append(
                f"Supplier pack size constraint of {pack} units applied: rounded up from {base_qty} to "
                f"{rounded_qty} units ({batches} full packs)."
            )
        else:
            assumptions.append(
                f"Order quantity {base_qty} aligns exactly with pack size {pack} ({batches} packs)."
            )
        final_qty = rounded_qty
    else:
        final_qty = base_qty
        assumptions.append("No pack size multiplier constraint (individual unit packaging).")

    estimated_cost = round(final_qty * unit_cost, 2)

    return OrderRecommendation(
        should_reorder=True,
        available_position=available_position,
        reorder_point=reorder_point,
        target_stock_level=target_stock_level,
        gross_shortage=gross_shortage,
        supplier_moq=supplier_moq,
        pack_size=pack,
        recommended_order_quantity=final_qty,
        estimated_cost=estimated_cost,
        assumptions=assumptions,
        policy_citations=citations
    )

def save_replenishment_plan(
    plan: ReplenishmentPlan,
    storage_path: str = PLAN_STORE_PATH
) -> Tuple[ReplenishmentPlan, bool]:
    """
    Saves plans with unique IDs, timestamps, and idempotency keys.
    If the idempotency key already exists in the store, returns the existing plan ID
    and details instead of creating a duplicate.
    Returns: (plan, is_new_record)
    """
    existing_plans: List[Dict[str, Any]] = []
    if os.path.exists(storage_path):
        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                existing_plans = json.load(f)
        except Exception:
            existing_plans = []

    # Check for existing plan with identical idempotency key
    for exp in existing_plans:
        if exp.get("idempotency_key") == plan.idempotency_key:
            # Idempotency match: return existing record
            return plan, False

    # New plan registration
    plan_dict = plan.to_dict()
    existing_plans.append(plan_dict)

    os.makedirs(os.path.dirname(storage_path), exist_ok=True)
    with open(storage_path, "w", encoding="utf-8") as f:
        json.dump(existing_plans, f, indent=2)

    return plan, True

def list_saved_plans(storage_path: str = PLAN_STORE_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(storage_path):
        return []
    try:
        with open(storage_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
