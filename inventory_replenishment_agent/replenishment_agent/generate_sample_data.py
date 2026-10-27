"""
Synthetic Data Generator for Inventory Replenishment Advisory Agent.
Generates:
1. data/inventory.csv (30 rows with boundary cases: P101 low stock, P102 sufficient, P103 incoming gap, P900 no sales, P204 missing lead time)
2. data/sales.csv (60+ rows spanning rolling windows)
3. data/supplier_lead_times.xlsx (Valid Excel OpenXML file) and .csv companion
4. data/reorder_policy.pdf (Valid PDF with sections, version v2.4, effective date) and .txt companion
"""

import os
import csv
import io
import zipfile
import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def generate_inventory_csv():
    filepath = os.path.join(DATA_DIR, "inventory.csv")
    rows = [
        # product_id, location, sku_name, category, on_hand, reserved, incoming_confirmed, incoming_unconfirmed, unit_cost, target_stock_level, safety_stock
        # Key test cases
        ("P101", "LOC_EAST", "Industrial Grade Bearing A10", "Mechanical", 15, 5, 10, 20, 45.50, 150, 25),    # Low stock: on_hand 15 - 5 + 10 = 20 avail. ROP ~ (3.3*14)+25=71. Shortage=130.
        ("P102", "LOC_EAST", "Hydraulic Seal Ring 45mm", "Hydraulics", 120, 10, 0, 50, 12.00, 100, 15),       # Sufficient stock: 120 - 10 = 110 avail >= ROP (~27). Order 0.
        ("P103", "LOC_WEST", "Precision Linear Bushing", "Mechanical", 18, 8, 85, 150, 68.00, 120, 20),      # Incoming covers gap: on_hand 18 - 8 = 10; confirmed=85 -> avail=95. Target=120, ROP=64. Avail 95 > ROP 64!
        ("P900", "LOC_EAST", "Experimental Nano-Coating SKU", "Chemicals", 5, 0, 0, 0, 310.00, 50, 10),      # NO SALES HISTORY: Must flag INSUFFICIENT DATA
        ("P204", "LOC_CENTRAL", "High-Temp Ceramic Insulator", "Electrical", 22, 4, 15, 30, 85.00, 160, 30), # MISSING SUPPLIER LEAD TIME: Triggers Ask
        ("P305", "LOC_WEST", "Stainless Steel Hex Bolt M8x50", "Fasteners", 40, 10, 0, 0, 0.75, 500, 80),    # Pack size rounding & MOQ
        
        # Additional diverse retail / industrial inventory records (total 25+ rows)
        ("P104", "LOC_EAST", "Heavy-Duty Timing Belt T10", "Transmission", 35, 5, 20, 40, 32.50, 180, 30),
        ("P105", "LOC_WEST", "Viton O-Ring Assortment Pack", "Seals", 85, 15, 0, 0, 24.00, 150, 20),
        ("P106", "LOC_CENTRAL", "Cast Iron Flange Coupling 25mm", "Mechanical", 12, 2, 5, 15, 95.00, 80, 15),
        ("P107", "LOC_EAST", "Polyurethane Pneumatic Tubing 8mm", "Pneumatics", 210, 30, 50, 100, 1.80, 400, 50),
        ("P108", "LOC_WEST", "Brass Solenoid Valve 24V DC", "Valves", 14, 2, 10, 0, 75.00, 90, 15),
        ("P109", "LOC_CENTRAL", "Inductive Proximity Sensor M12", "Sensors", 45, 5, 0, 25, 42.00, 110, 20),
        ("P110", "LOC_EAST", "Digital Pressure Gauge 0-10 Bar", "Instrumentation", 8, 3, 0, 12, 130.00, 50, 10),
        ("P111", "LOC_WEST", "Copper Motor Bushing Sleeve", "Bearings", 60, 10, 40, 0, 15.50, 200, 30),
        ("P112", "LOC_CENTRAL", "Aluminum Din Rail 1m", "Hardware", 140, 20, 0, 0, 6.20, 250, 40),
        ("P113", "LOC_EAST", "Fiberglass Thermal Wrap 50mm", "Thermal", 18, 0, 10, 30, 28.00, 100, 15),
        ("P114", "LOC_WEST", "Spur Gear 20 Teeth Module 2", "Gears", 25, 5, 0, 0, 38.00, 120, 20),
        ("P115", "LOC_CENTRAL", "Optical Rotary Encoder 1024PPR", "Sensors", 6, 1, 0, 10, 165.00, 40, 8),
        ("P116", "LOC_EAST", "Graphite Packing Cord 6mm", "Gaskets", 90, 15, 30, 0, 19.00, 220, 35),
        ("P117", "LOC_WEST", "Zinc Plated Spring Washer M10", "Fasteners", 1200, 200, 500, 1000, 0.12, 3000, 400),
        ("P118", "LOC_CENTRAL", "Nylon Cable Drag Chain 15x30", "Accessories", 30, 4, 12, 0, 22.50, 140, 25),
        ("P119", "LOC_EAST", "Pillow Block Bearing UCP205", "Bearings", 16, 6, 0, 20, 52.00, 90, 15),
        ("P120", "LOC_WEST", "Silicone Thermal Paste 100g", "Chemicals", 55, 5, 20, 0, 18.00, 150, 25),
        ("P121", "LOC_CENTRAL", "Tungsten Carbide End Mill 6mm", "Tooling", 40, 10, 0, 0, 34.00, 130, 20),
        ("P122", "LOC_EAST", "Stainless Steel Shim Stock 0.1mm", "Raw Materials", 22, 2, 10, 0, 44.00, 110, 15),
        ("P123", "LOC_WEST", "Quick Release Air Coupler 1/4", "Pneumatics", 70, 15, 30, 50, 8.50, 250, 35),
        ("P124", "LOC_CENTRAL", "Helical Compression Spring 50mm", "Springs", 95, 20, 0, 0, 4.30, 300, 50),
        ("P125", "LOC_EAST", "Dual Channel Solid State Relay", "Electrical", 19, 3, 10, 15, 58.00, 100, 18),
    ]

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "product_id", "location", "sku_name", "category",
            "on_hand", "reserved", "incoming_confirmed", "incoming_unconfirmed",
            "unit_cost", "target_stock_level", "safety_stock"
        ])
        for row in rows:
            writer.writerow(row)
    print(f"Generated {filepath} ({len(rows)} records)")

def generate_sales_csv():
    filepath = os.path.join(DATA_DIR, "sales.csv")
    base_date = datetime.date(2024, 3, 15)
    
    rows = []
    # Generate daily sales for test products across last 30 days
    # Note: P900 intentionally omitted (no sales history)
    sales_profiles = {
        ("P101", "LOC_EAST"): [3, 4, 2, 5, 3, 4, 2, 3, 4, 3, 5, 2, 4, 3, 3, 4, 5, 2, 3, 4, 2, 4, 3, 5, 3, 2, 4, 3, 4, 3], # sum=100, mean=3.33
        ("P102", "LOC_EAST"): [1, 2, 1, 2, 0, 1, 2, 1, 2, 1, 0, 2, 1, 1, 2, 1, 2, 1, 0, 2, 1, 1, 2, 1, 2, 1, 1, 2, 1, 1], # mean ~ 1.2
        ("P103", "LOC_WEST"): [2, 3, 2, 2, 3, 1, 2, 3, 2, 2, 3, 2, 1, 2, 3, 2, 3, 2, 2, 1, 3, 2, 2, 3, 2, 1, 2, 3, 2, 2], # mean ~ 2.1
        ("P204", "LOC_CENTRAL"): [4, 5, 3, 6, 4, 5, 4, 3, 5, 4, 6, 5, 3, 4, 5, 4, 6, 3, 5, 4, 5, 3, 6, 4, 5, 4, 3, 5, 4, 5], # mean ~ 4.4
        ("P305", "LOC_WEST"): [12, 15, 14, 18, 10, 16, 14, 15, 12, 18, 15, 14, 16, 12, 15, 14, 18, 10, 16, 14, 15, 12, 18, 15, 14, 16, 12, 15, 14, 16], # mean ~ 14.6
        ("P104", "LOC_EAST"): [5, 6, 4, 5, 7, 5, 6, 4, 5, 6, 4, 5, 6, 7, 5, 4, 6, 5, 6, 5, 4, 6, 5, 7, 4, 5, 6, 5, 6, 5],
        ("P105", "LOC_WEST"): [3, 4, 3, 5, 4, 3, 4, 3, 5, 4, 3, 4, 3, 4, 5, 3, 4, 3, 4, 5, 3, 4, 3, 4, 5, 3, 4, 3, 4, 4],
        ("P106", "LOC_CENTRAL"): [1, 2, 1, 1, 2, 1, 0, 1, 2, 1, 1, 2, 1, 0, 1, 2, 1, 1, 2, 1, 0, 1, 2, 1, 1, 2, 1, 0, 1, 2],
        ("P107", "LOC_EAST"): [8, 10, 9, 12, 7, 11, 10, 8, 12, 9, 10, 11, 8, 12, 7, 10, 9, 11, 8, 12, 9, 10, 8, 11, 9, 10, 12, 8, 10, 9],
        ("P108", "LOC_WEST"): [2, 3, 2, 3, 1, 2, 3, 2, 3, 2, 1, 3, 2, 2, 3, 1, 2, 3, 2, 3, 2, 1, 3, 2, 2, 3, 1, 2, 3, 2],
        ("P109", "LOC_CENTRAL"): [3, 4, 3, 2, 4, 3, 5, 3, 4, 2, 3, 4, 3, 5, 2, 4, 3, 3, 4, 2, 5, 3, 4, 2, 3, 4, 3, 5, 2, 4],
        ("P110", "LOC_EAST"): [1, 1, 2, 1, 0, 1, 1, 2, 1, 0, 1, 2, 1, 1, 0, 2, 1, 1, 1, 0, 2, 1, 1, 2, 0, 1, 1, 2, 1, 1],
    }

    # Add transactions
    for (pid, loc), series in sales_profiles.items():
        for day_offset, qty in enumerate(series):
            txn_date = base_date - datetime.timedelta(days=29 - day_offset)
            order_id = f"SO-{pid}-{loc[-2:]}-{1000 + day_offset}"
            rows.append((txn_date.strftime("%Y-%m-%d"), pid, loc, qty, order_id))

    # Add a boundary entry: duplicate order ID check / same day multiple sales
    rows.append(("2024-03-14", "P101", "LOC_EAST", 2, "SO-P101-ST-9999"))

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sale_date", "product_id", "location", "quantity_sold", "order_id"])
        for r in rows:
            writer.writerow(r)
    print(f"Generated {filepath} ({len(rows)} sales records)")

def generate_supplier_data():
    csv_filepath = os.path.join(DATA_DIR, "supplier_lead_times.csv")
    xlsx_filepath = os.path.join(DATA_DIR, "supplier_lead_times.xlsx")

    suppliers = [
        # product_id, supplier_id, supplier_name, lead_time_days, minimum_order_quantity, pack_size, reliability_score
        ("P101", "SUP-901", "Apex Precision Bearings Ltd", 14, 50, 10, 0.96),
        ("P102", "SUP-902", "Vulkan Hydraulic Seals Inc", 10, 25, 5, 0.98),
        ("P103", "SUP-903", "Koyo Linear Motion Systems", 21, 40, 10, 0.94),
        ("P900", "SUP-999", "AeroTech Specialty Chem Corp", 30, 10, 1, 0.85),
        ("P204", "SUP-904", "CeramTech Global Industries", "", 20, 5, 0.90), # MISSING LEAD TIME!
        ("P305", "SUP-905", "FastenerWorld Manufacturing", 7, 100, 50, 0.99), # MOQ=100, pack_size=50
        ("P104", "SUP-906", "Gates Industrial Power Belts", 12, 30, 5, 0.95),
        ("P105", "SUP-907", "Parker Seal & Elastomers", 10, 40, 10, 0.97),
        ("P106", "SUP-908", "Nordic Flange Works AB", 18, 15, 1, 0.92),
        ("P107", "SUP-909", "Festo Pneumatics Supply", 8, 100, 25, 0.98),
        ("P108", "SUP-910", "SMC Fluid Automation", 15, 20, 2, 0.96),
        ("P109", "SUP-911", "Omron Sensing Components", 14, 25, 5, 0.97),
        ("P110", "SUP-912", "Wika Instrumentation Ltd", 20, 10, 2, 0.93),
        ("P111", "SUP-913", "Federal Bronze Co", 14, 50, 10, 0.95),
        ("P112", "SUP-914", "Unistrut Aluminum Systems", 7, 50, 10, 0.99),
        ("P113", "SUP-915", "ThermaTherm Insulation Co", 16, 20, 5, 0.91),
        ("P114", "SUP-916", "Martin Sprocket & Gear", 18, 25, 5, 0.94),
        ("P115", "SUP-917", "Heidenhain Encoder Works", 25, 10, 1, 0.97),
        ("P116", "SUP-918", "Garlock Sealing Technologies", 12, 30, 5, 0.95),
        ("P117", "SUP-919", "FastenerWorld Manufacturing", 5, 500, 100, 0.98),
        ("P118", "SUP-920", "Igus Energy Chains LLC", 14, 20, 4, 0.96),
        ("P119", "SUP-921", "SKF Reliability Systems", 15, 20, 4, 0.97),
        ("P120", "SUP-922", "Dow Chemical Lubricants", 10, 30, 6, 0.94),
        ("P121", "SUP-923", "Sandvik Coromant Cutting Tools", 9, 20, 5, 0.99),
        ("P122", "SUP-924", "Precision Shim & Coil Co", 14, 25, 5, 0.93),
        ("P123", "SUP-925", "Milton Pneumatic Fittings", 7, 50, 10, 0.96),
        ("P124", "SUP-926", "Associated Spring Raymond", 11, 60, 12, 0.95),
        ("P125", "SUP-927", "Crydom Solid State Relays", 16, 20, 4, 0.97),
    ]

    # Write CSV companion
    with open(csv_filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["product_id", "supplier_id", "supplier_name", "lead_time_days", "minimum_order_quantity", "pack_size", "reliability_score"])
        for s in suppliers:
            writer.writerow(s)
    print(f"Generated {csv_filepath} ({len(suppliers)} suppliers)")

    # Build a real standard XLSX file without requiring third-party libraries (pure OpenXML zip packaging)
    build_minimal_xlsx(xlsx_filepath, [
        ["product_id", "supplier_id", "supplier_name", "lead_time_days", "minimum_order_quantity", "pack_size", "reliability_score"]
    ] + [list(s) for s in suppliers])
    print(f"Generated {xlsx_filepath}")

def build_minimal_xlsx(filepath, rows):
    """Creates a 100% valid Excel .xlsx file using standard library zipfile and OpenXML."""
    sheet_rows_xml = []
    for r_idx, row in enumerate(rows, start=1):
        c_xml = []
        for c_idx, val in enumerate(row, start=1):
            col_letter = chr(64 + c_idx) if c_idx <= 26 else f"A{chr(64 + c_idx - 26)}"
            cell_ref = f"{col_letter}{r_idx}"
            s_val = str(val)
            if s_val == "":
                continue
            is_num = False
            try:
                float(s_val)
                is_num = True
            except ValueError:
                is_num = False
            
            if is_num and not (c_idx == 1 and s_val.startswith("P")):
                c_xml.append(f'<c r="{cell_ref}"><v>{s_val}</v></c>')
            else:
                escaped = s_val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
                c_xml.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows_xml.append(f'<row r="{r_idx}">{"".join(c_xml)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + "".join(sheet_rows_xml) + '</sheetData>'
        '</worksheet>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )

    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        '<sheet name="SupplierLeadTimes" sheetId="1" r:id="rId1"/>'
        '</sheets>'
        '</workbook>'
    )

    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    with open(filepath, "wb") as f:
        f.write(buf.getvalue())

def generate_policy_document():
    pdf_filepath = os.path.join(DATA_DIR, "reorder_policy.pdf")
    txt_filepath = os.path.join(DATA_DIR, "reorder_policy.txt")

    policy_content = """# Corporate Inventory Replenishment & Reorder Policy
Document Name: Corporate Inventory Replenishment & Reorder Policy
Policy Version: v2.4
Effective Date: 2024-03-01
Author: HCL Supply Chain Excellence Group
Status: Approved & Mandatory

============================================================
SECTION 1: Scope, Purpose & Governance
============================================================
This policy governs all inventory management, stock level audits, and automated replenishment proposals across all regional fulfillment centers and regional warehouses (LOC_EAST, LOC_WEST, LOC_CENTRAL). The objective is to eliminate stockouts while minimizing holding costs and avoiding inventory deadweight. All algorithmic replenishment agents must adhere strictly to these operational boundaries.

============================================================
SECTION 2: Calculation of Available Inventory Position
============================================================
Available inventory position determines the actual stock available to satisfy demand and pipeline replenishment.
Rule 2.1: Available inventory position MUST strictly be computed using the deterministic equation:
    Available Inventory Position = On-Hand Stock - Reserved Stock + Confirmed Incoming Stock
Rule 2.2: Unconfirmed purchase orders or unverified incoming shipments SHALL NOT be counted towards available inventory under any circumstance. Only purchase orders marked with confirmed transit status qualify as Confirmed Incoming Stock.
Rule 2.3: Reserved stock represents inventory allocated to confirmed customer sales orders awaiting shipment and must always be deducted.

============================================================
SECTION 3: Safe Daily Sales Velocity & Data Sufficiency
============================================================
Rule 3.1: Average Daily Sales (ADS) velocity must be derived from historical sales transactions across a rolling lookback window (default: 30 days).
Rule 3.2: INSUFFICIENT DATA GUARDRAIL: If a SKU has no historical transaction records in the specified lookback window, or has fewer than the minimum required observations, the system SHALL NOT hallucinate, invent, or guess sales velocity.
Rule 3.3: In the case of insufficient data (such as product P900), the system must immediately flag status as "INSUFFICIENT_DATA", set recommended order quantity to 0 (or alert state), and halt automatic ordering pending human operational audit.

============================================================
SECTION 4: Reorder Point (ROP) Determination
============================================================
Rule 4.1: The Reorder Point triggers a replenishment action when Available Inventory Position falls strictly below this threshold.
Rule 4.2: The Reorder Point MUST be deterministically computed as:
    Reorder Point (ROP) = (Average Daily Sales * Supplier Lead Time Days) + Safety Stock
Rule 4.3: Arithmetic operations must be executed deterministically in Python code. An LLM or language model shall never be permitted to perform numerical arithmetic.
Rule 4.4: Safety Stock is defined as the buffer stock required to protect against demand volatility and lead-time delays, as designated in master SKU parameters.

============================================================
SECTION 5: Order Quantity Optimization & Lot Sizing
============================================================
Rule 5.1: If Available Inventory Position is greater than or equal to the Reorder Point, no order should be generated (Recommended Quantity = 0).
Rule 5.2: When Available Inventory Position falls strictly below the Reorder Point, the baseline shortage is:
    Gross Shortage = Target Stock Level - Available Inventory Position
Rule 5.3: Minimum Order Quantity (MOQ) Constraint: The recommended order quantity must never be less than the Supplier Minimum Order Quantity (MOQ). If Gross Shortage < MOQ, the order quantity must be raised to MOQ.
Rule 5.4: Pack Size / Lot Ceiling Rule: Order quantities must be rounded up to the nearest integer multiple of the Supplier Pack Size using ceiling division:
    Final Recommended Quantity = ceil(max(Gross Shortage, MOQ) / Pack Size) * Pack Size
Rule 5.5: Every replenishment recommendation must articulate its assumptions, detailing the target stock level, available inventory position, and lot sizing calculations.

============================================================
SECTION 6: Missing Data Handling, Interactive Prompts & Idempotency
============================================================
Rule 6.1: When essential data parameters—specifically Supplier Lead Time—are missing or null (e.g., product P204), the agent must not fabricate values. The agent must pause execution, transition to the "Ask" stage, and prompt the human operator for the verified lead time in days.
Rule 6.2: Once the operator supplies the missing value, the agent resumes execution through the state machine.
Rule 6.3: Idempotency Key Registration: To eliminate duplicate order submissions during network retries or identical re-evaluations, every generated replenishment plan must be registered with a unique Plan ID, timestamp, and a cryptographic/hash idempotency key based on (product_id, location, target_stock_level, as_of_date).
Rule 6.4: If a duplicate plan request is processed, the system must recognize the existing idempotency key and return the original Plan ID and plan record without creating a duplicate.
"""

    with open(txt_filepath, "w", encoding="utf-8") as f:
        f.write(policy_content)
    print(f"Generated {txt_filepath}")

    build_valid_pdf(pdf_filepath, policy_content)
    print(f"Generated {pdf_filepath}")

def build_valid_pdf(filepath, text_content):
    """Creates a standard PDF-1.4 compliant file using built-in Python bytes generation."""
    lines = text_content.strip().split("\n")
    pages = []
    current_page_lines = []
    for line in lines:
        current_page_lines.append(line)
        if len(current_page_lines) >= 42:
            pages.append(current_page_lines)
            current_page_lines = []
    if current_page_lines:
        pages.append(current_page_lines)

    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    
    num_pages = len(pages)
    page_obj_ids = [3 + i * 2 for i in range(num_pages)]
    content_obj_ids = [4 + i * 2 for i in range(num_pages)]
    
    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    pages_obj = f"<< /Type /Pages /Kids [{kids_str}] /Count {num_pages} >>".encode("ascii")
    objects.append(pages_obj)

    for i in range(num_pages):
        p_obj = (
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            f"/MediaBox [0 0 612 792] /Contents {content_obj_ids[i]} 0 R >>"
        ).encode("ascii")
        objects.append(p_obj)

        stream_cmds = ["BT", "/F1 9 Tf", "50 740 Td", "14 TL"]
        first = True
        for line in pages[i]:
            escaped = (
                line.replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .encode("latin-1", errors="replace")
                .decode("latin-1")
            )
            if first:
                stream_cmds.append(f"({escaped}) Tj")
                first = False
            else:
                stream_cmds.append(f"T* ({escaped}) Tj")
        stream_cmds.append("ET")
        stream_data = "\n".join(stream_cmds).encode("latin-1")
        
        c_obj = (
            f"<< /Length {len(stream_data)} >>\nstream\n".encode("ascii")
            + stream_data
            + b"\nendstream"
        )
        objects.append(c_obj)

    with open(filepath, "wb") as f:
        f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, obj in enumerate(objects, start=1):
            offsets.append(f.tell())
            f.write(f"{i} 0 obj\n".encode("ascii"))
            f.write(obj)
            f.write(b"\nendobj\n")
        
        xref_offset = f.tell()
        f.write(b"xref\n")
        f.write(f"0 {len(objects) + 1}\n".encode("ascii"))
        f.write(b"0000000000 65535 f \n")
        for off in offsets:
            f.write(f"{off:010d} 00000 n \n".encode("ascii"))
        f.write(b"trailer\n")
        f.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii"))
        f.write(b"startxref\n")
        f.write(f"{xref_offset}\n".encode("ascii"))
        f.write(b"%%EOF\n")

if __name__ == "__main__":
    ensure_dirs()
    generate_inventory_csv()
    generate_sales_csv()
    generate_supplier_data()
    generate_policy_document()
    print("All sample datasets successfully generated!")
