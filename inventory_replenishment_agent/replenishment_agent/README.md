# Inventory Replenishment Advisory Agent
**HCL Career Shaper Internship Project — Supply Chain Management & Autonomous Agent Engineering**

---

## 1. Project Overview

The **Inventory Replenishment Advisory Agent** is a production-grade, deterministic Python system engineered for enterprise inventory replenishment decisions. It joins multi-source supply chain datasets, enforces corporate replenishment policies, uses bounded retrieval to ground decisions with explicit policy section citations, and performs **100% deterministic mathematical calculations** in pure Python (strictly prohibiting LLMs from performing arithmetic).

### Key Architectural Tenets:
1. **Zero LLM Hallucination for Arithmetic**: Average Daily Sales (ADS), Available Inventory Position, Reorder Point (ROP), and final order quantities (including supplier MOQ and pack size rounding) are strictly computed in Python code.
2. **Deterministic Available Position**:
   $$\text{Available Position} = \text{On-Hand} - \text{Reserved} + \text{Confirmed Incoming}$$
   *Unconfirmed incoming stock is explicitly excluded* per Section 2 of the Corporate Policy.
3. **Data Sufficiency Guardrail**: If historical sales data is missing (e.g., SKU `P900`), the system strictly refuses to invent sales velocity, flags `INSUFFICIENT_DATA`, and halts automatic ordering pending human operational audit.
4. **Interactive "Ask" Stage**: If critical parameters (such as supplier lead time for `P204`) are null, the workflow suspends execution, enters the `Ask` stage, and requests verified input from the operator.
5. **Plan Idempotency**: Every generated plan is registered with an idempotency key (hash of `product_id|location|target_stock_level|as_of_date`) and unique Plan ID. Duplicate submissions return the existing plan ID without creating duplicate purchase orders.

---

## 2. The 7-Stage Agent Workflow

The agent operates as a stateful, conditional 7-stage state machine:

```
[1. Request]   --> Validates SKU, location, parameters; joins catalog records
      │
[2. Ask]       --> Detects missing fields (e.g. Lead Time for P204); prompts user
      │
[3. Retrieve]  --> Retrieves chunks from reorder_policy.pdf (preserving metadata & version)
      │
[4. Grade]     --> Evaluates policy chunk relevance; triggers bounded query rewrite (max 2)
      │
[5. Tools]     --> Executes deterministic Python tools (stock, sales, ROP, order qty)
      │
[6. Route]     --> Conditional branching:
                   ├─ Insufficient sales data -> HALTED_INSUFFICIENT_DATA
                   ├─ Available >= ROP        -> SUFFICIENT_STOCK (Order 0)
                   └─ Available < ROP         -> REORDER_REQUIRED (MOQ/Pack Size applied)
      │
[7. Recommend] --> Synthesizes plan, records policy citations, registers Idempotency Key
```

---

## 3. Directory Structure

```
replenishment_agent/
│
├── README.md                      # Comprehensive documentation & Windows run guide
├── requirements.txt               # Dependencies (pytest, openpyxl, pandas, pypdf)
├── main.py                        # CLI runner, batch evaluator, interactive mode
├── generate_sample_data.py        # Generates synthetic CSV, XLSX, and PDF files
│
├── data/
│   ├── inventory.csv              # 28 SKU records across LOC_EAST, LOC_WEST, LOC_CENTRAL
│   ├── sales.csv                  # 360+ daily transaction logs across lookback window
│   ├── supplier_lead_times.xlsx   # Valid OpenXML Excel spreadsheet (and .csv companion)
│   ├── supplier_lead_times.csv    # Companion CSV
│   ├── reorder_policy.pdf         # Standard PDF-1.4 policy document (v2.4)
│   ├── reorder_policy.txt         # Text source
│   └── saved_plans.json           # Idempotent persistence store for replenishment plans
│
├── agent/
│   ├── __init__.py                # Package exports
│   ├── state.py                   # Dataclasses (AgentState, ReplenishmentPlan, StockLevel, etc.)
│   ├── data_loader.py             # OpenXML XLSX/CSV/PDF readers and dataset join engine
│   ├── retriever.py               # Document retriever preserving section, version, effective date
│   ├── grader.py                  # Policy relevance grader & bounded query rewriter
│   ├── tools.py                   # The 5 core deterministic tools with structured outputs
│   └── workflow.py                # 7-stage state machine orchestrator
│
└── tests/
    ├── __init__.py
    ├── conftest.py                # Sets sys.path for pytest
    ├── test_replenishment_tools.py# Unit tests for calculations, exclusions, and idempotency
    └── test_agent_workflow.py     # E2E integration tests for all 6 core scenarios
```

---

## 4. Setup & Running in VS Code on Windows (PowerShell)

Follow these exact commands in Windows PowerShell:

### Step 1: Open Terminal in Project Directory
```powershell
cd replenishment_agent
```

### Step 2: Create and Activate Python Virtual Environment
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment in PowerShell
.\venv\Scripts\Activate.ps1
```
*(Note: If PowerShell reports script execution policy restrictions, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### Step 3: Install Project Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Generate or Refresh Sample Datasets
```powershell
python generate_sample_data.py
```

### Step 5: Run Automated Pytest Test Suite
```powershell
# Run with pytest (verbose mode)
pytest -v

# Or run with Python's built-in unittest
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 5. CLI Execution Modes

### A. Evaluate Low Stock Item (Triggers Reorder & MOQ)
```powershell
python main.py --product P101 --location LOC_EAST
```
- Available Position = $15 - 5 + 10 = 20$.
- Reorder Point $\approx 73.1$ units.
- Output: `APPROVED_REORDER` with recommended order of 130 units.

### B. Evaluate Sufficient Stock Item (No Order Needed)
```powershell
python main.py --product P102 --location LOC_EAST
```
- Available Position = $120 - 10 = 110$.
- Available ($110$) $\ge$ ROP ($27.7$).
- Output: `SUFFICIENT_STOCK` with 0 units ordered.

### C. Evaluate Incoming Stock Covering Gap
```powershell
python main.py --product P103 --location LOC_WEST
```
- Available Position = $18 - 8 + 85 = 95$.
- Unconfirmed incoming (150) is excluded per Rule 2.2.
- Available ($95$) $\ge$ ROP ($65.5$).
- Output: `SUFFICIENT_STOCK` with 0 units ordered.

### D. Evaluate No Sales History Guardrail (P900)
```powershell
python main.py --product P900 --location LOC_EAST
```
- Sales dataset has 0 historical logs.
- Output: `HALTED_INSUFFICIENT_DATA`. Zero sales invented. Recommended quantity = 0.

### E. Interactive Ask Mode for Missing Lead Time (P204)
```powershell
# Run with interactive flag:
python main.py --product P204 --location LOC_CENTRAL --interactive
```
The agent pauses at the `Ask` stage, prints:
`Missing critical parameter: Supplier Lead Time for SKU P204... Please specify lead time in days to proceed.`
Type `15` and press Enter to resume execution to completion!

### F. Run Batch Evaluation on Entire Catalog
```powershell
python main.py --batch
```

### G. JSON Mode (For REST API / Integrations)
```powershell
python main.py --product P101 --json
```

---

## 6. Mathematical Formulas & Policy Rules Reference

| Metric | Mathematical Formula | Policy Authority |
|---|---|---|
| **Available Inventory Position** | $\text{On-Hand} - \text{Reserved} + \text{Confirmed Incoming}$ *(Unconfirmed ignored)* | Policy v2.4, Section 2, Rule 2.1 |
| **Average Daily Sales (ADS)** | $\sum \text{Quantity Sold} \div \text{Lookback Window (days)}$ | Policy v2.4, Section 3, Rule 3.1 |
| **Reorder Point (ROP)** | $(\text{Average Daily Sales} \times \text{Lead Time Days}) + \text{Safety Stock}$ | Policy v2.4, Section 4, Rule 4.2 |
| **Gross Shortage** | $\max(0, \text{Target Stock Level} - \text{Available Position})$ | Policy v2.4, Section 5, Rule 5.2 |
| **Pack Size & MOQ Rounding** | $\lceil \max(\text{Gross Shortage}, \text{MOQ}) / \text{Pack Size} \rceil \times \text{Pack Size}$ | Policy v2.4, Section 5, Rule 5.4 |
| **Plan Idempotency** | $\text{SHA-256}(\text{SKU} \parallel \text{Location} \parallel \text{Target} \parallel \text{Date})[0:16]$ | Policy v2.4, Section 6, Rule 6.3 |

---

## 7. Author & Submission Details
- **Project**: Inventory Replenishment Advisory Agent
- **Program**: HCL Career Shaper Internship
- **Technology Stack**: Python 3.10+, Pytest, Dataclasses, OpenXML, PDF-1.4
- **Deterministic Engine**: 100% pure Python calculations without LLM dependency.
