#!/usr/bin/env python3
"""
Inventory Replenishment Advisory Agent - CLI Runner
HCL Career Shaper Internship Project.
Executes the 7-stage replenishment advisory workflow locally via CLI or batch mode.
"""

import sys
import os
import argparse
import json
import unittest

# Ensure replenishment_agent is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.workflow import ReplenishmentWorkflow
from agent.tools import list_saved_plans
from agent.data_loader import DataLoader

def print_banner():
    print("=" * 75)
    print("   INVENTORY REPLENISHMENT ADVISORY AGENT")
    print("   HCL Career Shaper Internship Project | Autonomous SCM Advisory")
    print("   7-Stage Workflow: Request -> Ask -> Retrieve -> Grade -> Tools -> Route -> Recommend")
    print("=" * 75)

def run_single(args):
    workflow = ReplenishmentWorkflow()
    state = workflow.get_or_create_state(
        product_id=args.product,
        location=args.location,
        target_stock_level=args.target,
        lookback_days=args.lookback,
        manual_lead_time=args.lead_time
    )

    state = workflow.run(state)

    # If paused at Ask stage and interactive mode is enabled
    if state.current_stage == "Ask" and args.interactive and state.manual_lead_time is None:
        print("\n" + "!" * 60)
        print(f"INTERACTIVE OPERATOR PROMPT (Stage: Ask)")
        print(f"{state.ask_prompt}")
        print("!" * 60)
        try:
            val = input("\nEnter Supplier Lead Time in days: ").strip()
            state.manual_lead_time = float(val)
            print(f"Recorded input: {state.manual_lead_time} days. Resuming workflow...")
            state = workflow.run(state)
        except Exception as e:
            print(f"Invalid input: {e}. Exiting.")
            return

    if args.json:
        # Output clean JSON
        output = {
            "thread_id": state.thread_id,
            "product_id": state.product_id,
            "location": state.location,
            "current_stage": state.current_stage,
            "is_terminal": state.is_terminal,
            "termination_reason": state.termination_reason,
            "ask_prompt": state.ask_prompt,
            "missing_fields": state.missing_fields,
            "stage_traces": [
                {
                    "stage": t.stage_name,
                    "status": t.status,
                    "summary": t.summary,
                    "details": t.details,
                    "timestamp": t.timestamp
                }
                for t in state.stage_traces
            ],
            "plan": state.plan.to_dict() if state.plan else None
        }
        print(json.dumps(output, indent=2))
        return

    # Formatted terminal display
    print(f"\n[EVALUATION REPORT for SKU {state.product_id} @ {state.location}]")
    print("-" * 75)
    print(f"Workflow Status : {'COMPLETED' if state.is_terminal else 'PAUSED (' + state.current_stage + ')'}")
    if state.termination_reason:
        print(f"Notice          : {state.termination_reason}")

    print("\n--- WORKFLOW EXECUTION TRACE ---")
    for t in state.stage_traces:
        badge = f"[{t.stage_name.upper():<9}] [{t.status:<14}]"
        print(f"{badge} {t.summary}")

    if state.plan:
        plan = state.plan
        rec = plan.recommendation
        stock = plan.stock_level
        sales = plan.sales_stats
        rop = plan.reorder_point_result

        print("\n" + "=" * 75)
        print(f"REPLENISHMENT PLAN: {plan.plan_id}")
        print(f"Idempotency Key  : {plan.idempotency_key}")
        print(f"Plan Status      : {plan.status}")
        print(f"SKU Name         : {stock.sku_name} ({stock.category})")
        print("-" * 75)
        print("INVENTORY POSITION:")
        print(f"  • On-Hand Stock         : {stock.on_hand} units")
        print(f"  • Reserved Stock        : {stock.reserved} units")
        print(f"  • Confirmed Incoming    : {stock.incoming_confirmed} units")
        print(f"  • Unconfirmed Incoming  : {stock.incoming_unconfirmed} units (EXCLUDED from position)")
        print(f"  • AVAILABLE POSITION    : {stock.available_position} units")
        print("-" * 75)
        print("DEMAND VELOCITY & REORDER POINT:")
        if sales.is_sufficient:
            print(f"  • Average Daily Sales   : {sales.average_daily_sales:.2f} units/day ({sales.window_days}-day window)")
            print(f"  • Supplier Lead Time    : {rop.lead_time_days} days")
            print(f"  • Safety Stock Buffer   : {rop.safety_stock} units")
            print(f"  • REORDER POINT (ROP)   : {rop.reorder_point:.2f} units")
        else:
            print(f"  • SALES HISTORY         : INSUFFICIENT DATA (0 units sold recorded)")
            print(f"  • Policy Directive      : Zero sales invented. Automatic ordering halted.")

        print("-" * 75)
        print("RECOMMENDATION SUMMARY:")
        print(f"  • Reorder Recommended?  : {'YES' if rec.should_reorder else 'NO'}")
        print(f"  • Recommended Quantity  : {rec.recommended_order_quantity} units")
        print(f"  • Estimated Reorder Cost: ${rec.estimated_cost:,.2f} (@ ${stock.unit_cost:.2f}/unit)")
        print(f"  • Supplier Constraints  : MOQ={rec.supplier_moq}, Pack Size={rec.pack_size}")
        
        print("\nASSUMPTIONS & LOGIC:")
        for asm in rec.assumptions:
            print(f"  ✓ {asm}")

        print("\nPOLICY CITATIONS (reorder_policy.pdf):")
        for cit in rec.policy_citations:
            print(f"  § [{cit.get('policy_version', 'v2.4')}] {cit.get('section')}: {cit.get('reference')}")
            print(f"    \"{cit.get('excerpt')}\"")
        print("=" * 75)

def run_batch():
    print_banner()
    loader = DataLoader()
    items = loader.load_inventory()
    workflow = ReplenishmentWorkflow()
    
    print(f"\nRunning batch evaluation across {len(items)} catalog SKUs...\n")
    print(f"{'SKU':<8} {'Location':<14} {'Avail':<7} {'ROP':<7} {'Reorder?':<10} {'Order Qty':<10} {'Status':<22}")
    print("-" * 85)

    for item in items:
        pid = item["product_id"]
        loc = item["location"]
        state = workflow.get_or_create_state(product_id=pid, location=loc)
        state = workflow.run(state)
        
        if state.plan:
            rec = state.plan.recommendation
            rop_str = f"{state.plan.reorder_point_result.reorder_point:.1f}" if state.plan.reorder_point_result else "N/A"
            reorder_str = "YES" if rec.should_reorder else "NO"
            print(f"{pid:<8} {loc:<14} {rec.available_position:<7} {rop_str:<7} {reorder_str:<10} {rec.recommended_order_quantity:<10} {state.plan.status:<22}")
        elif state.current_stage == "Ask":
            print(f"{pid:<8} {loc:<14} {'--':<7} {'--':<7} {'PAUSED':<10} {'--':<10} {'AWAITING_LEAD_TIME':<22}")
        else:
            print(f"{pid:<8} {loc:<14} {'--':<7} {'--':<7} {'ERROR':<10} {'--':<10} {str(state.termination_reason)[:22]:<22}")

def run_all_tests():
    print_banner()
    print("\nRunning automated test suite for Inventory Replenishment Advisory Agent...\n")
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

def main():
    parser = argparse.ArgumentParser(description="Inventory Replenishment Advisory Agent CLI")
    parser.add_argument("--product", "-p", default="P101", help="Product SKU (e.g. P101, P102, P103, P900, P204)")
    parser.add_argument("--location", "-l", default="LOC_EAST", help="Warehouse location (e.g. LOC_EAST, LOC_WEST, LOC_CENTRAL)")
    parser.add_argument("--target", "-t", type=int, default=None, help="Target stock level override")
    parser.add_argument("--lookback", type=int, default=30, help="Lookback window in days for sales velocity")
    parser.add_argument("--lead-time", type=float, default=None, help="Manual lead time override in days")
    parser.add_argument("--interactive", "-i", action="store_true", help="Prompt for missing inputs (e.g. lead time)")
    parser.add_argument("--batch", "-b", action="store_true", help="Run batch evaluation over all SKUs")
    parser.add_argument("--run-tests", action="store_true", help="Execute complete automated test suite")
    parser.add_argument("--json", action="store_true", help="Output result as pure JSON")

    args = parser.parse_args()

    if args.run_tests:
        run_all_tests()
    elif args.batch:
        run_batch()
    else:
        if not args.json:
            print_banner()
        run_single(args)

if __name__ == "__main__":
    main()
