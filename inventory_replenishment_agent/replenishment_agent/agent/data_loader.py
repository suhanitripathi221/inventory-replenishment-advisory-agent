"""
Data Loader and Join Engine.
Reads inventory.csv, sales.csv, supplier_lead_times.xlsx (via standard library OpenXML zip parser or fallback), and reorder_policy.
Joins inventory, sales, and supplier data using product_id and location.
"""

import os
import csv
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

class DataLoader:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir

    def load_inventory(self) -> List[Dict[str, Any]]:
        path = os.path.join(self.data_dir, "inventory.csv")
        records = []
        if not os.path.exists(path):
            raise FileNotFoundError(f"inventory.csv not found at {path}")
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {
                    "product_id": row["product_id"].strip(),
                    "location": row["location"].strip(),
                    "sku_name": row["sku_name"].strip(),
                    "category": row["category"].strip(),
                    "on_hand": int(float(row["on_hand"])),
                    "reserved": int(float(row["reserved"])),
                    "incoming_confirmed": int(float(row["incoming_confirmed"])),
                    "incoming_unconfirmed": int(float(row["incoming_unconfirmed"])),
                    "unit_cost": float(row["unit_cost"]),
                    "target_stock_level": int(float(row["target_stock_level"])),
                    "safety_stock": int(float(row["safety_stock"])),
                }
                records.append(cleaned)
        return records

    def load_sales(self) -> List[Dict[str, Any]]:
        path = os.path.join(self.data_dir, "sales.csv")
        records = []
        if not os.path.exists(path):
            raise FileNotFoundError(f"sales.csv not found at {path}")
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {
                    "sale_date": row["sale_date"].strip(),
                    "product_id": row["product_id"].strip(),
                    "location": row["location"].strip(),
                    "quantity_sold": int(float(row["quantity_sold"])),
                    "order_id": row.get("order_id", "").strip(),
                }
                records.append(cleaned)
        return records

    def load_suppliers(self) -> List[Dict[str, Any]]:
        """
        Loads supplier lead times from supplier_lead_times.xlsx using standard library zipfile/XML parser.
        Falls back to supplier_lead_times.csv if xlsx is unreadable.
        """
        xlsx_path = os.path.join(self.data_dir, "supplier_lead_times.xlsx")
        csv_path = os.path.join(self.data_dir, "supplier_lead_times.csv")
        
        if os.path.exists(xlsx_path):
            try:
                return self._parse_xlsx(xlsx_path)
            except Exception as e:
                # Fallback to companion CSV
                pass
        
        if os.path.exists(csv_path):
            records = []
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    lt = row["lead_time_days"].strip()
                    records.append({
                        "product_id": row["product_id"].strip(),
                        "supplier_id": row["supplier_id"].strip(),
                        "supplier_name": row["supplier_name"].strip(),
                        "lead_time_days": float(lt) if lt != "" else None,
                        "minimum_order_quantity": int(float(row["minimum_order_quantity"])) if row.get("minimum_order_quantity") else 0,
                        "pack_size": int(float(row["pack_size"])) if row.get("pack_size") else 1,
                        "reliability_score": float(row["reliability_score"]) if row.get("reliability_score") else 1.0,
                    })
            return records
        
        raise FileNotFoundError(f"Neither {xlsx_path} nor {csv_path} was found.")

    def _parse_xlsx(self, filepath: str) -> List[Dict[str, Any]]:
        """Pure-Python OpenXML XLSX parser without external dependencies."""
        with zipfile.ZipFile(filepath, "r") as zf:
            sheet_xml = zf.read("xl/worksheets/sheet1.xml")
            root = ET.fromstring(sheet_xml)
            ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            
            rows_data = []
            for row in root.findall(".//ns:row", ns):
                row_dict_by_col = {}
                for cell in row.findall("ns:c", ns):
                    cell_ref = cell.attrib.get("r", "")
                    col_letters = "".join(filter(str.isalpha, cell_ref)).upper()
                    if not col_letters:
                        continue
                    col_idx = 0
                    for ch in col_letters:
                        col_idx = col_idx * 26 + (ord(ch) - ord("A") + 1)
                    col_idx -= 1

                    t_elem = cell.find(".//ns:t", ns)
                    v_elem = cell.find("ns:v", ns)
                    if t_elem is not None and t_elem.text:
                        val = t_elem.text
                    elif v_elem is not None and v_elem.text:
                        val = v_elem.text
                    else:
                        val = ""
                    row_dict_by_col[col_idx] = val

                if row_dict_by_col:
                    max_col = max(row_dict_by_col.keys())
                    row_vals = [row_dict_by_col.get(c, "") for c in range(max_col + 1)]
                    rows_data.append(row_vals)

        if not rows_data or len(rows_data) < 2:
            raise ValueError("XLSX has insufficient rows")
        
        headers = [h.strip() for h in rows_data[0]]
        records = []
        for r in rows_data[1:]:
            row_dict = {}
            for i, h in enumerate(headers):
                val = r[i] if i < len(r) else ""
                row_dict[h] = val
            
            lt_str = str(row_dict.get("lead_time_days", "")).strip()
            lt_val = float(lt_str) if lt_str != "" else None
            
            records.append({
                "product_id": str(row_dict.get("product_id", "")).strip(),
                "supplier_id": str(row_dict.get("supplier_id", "")).strip(),
                "supplier_name": str(row_dict.get("supplier_name", "")).strip(),
                "lead_time_days": lt_val,
                "minimum_order_quantity": int(float(row_dict.get("minimum_order_quantity", 0) or 0)),
                "pack_size": int(float(row_dict.get("pack_size", 1) or 1)),
                "reliability_score": float(row_dict.get("reliability_score", 1.0) or 1.0),
            })
        return records

    def get_unified_product_record(self, product_id: str, location: str) -> Optional[Dict[str, Any]]:
        """
        Joins inventory, supplier, and sales metadata for a specific product and location.
        """
        inventory_items = self.load_inventory()
        inv = next((i for i in inventory_items if i["product_id"] == product_id and i["location"] == location), None)
        if not inv:
            return None

        suppliers = self.load_suppliers()
        sup = next((s for s in suppliers if s["product_id"] == product_id), None)

        unified = dict(inv)
        if sup:
            unified["supplier_id"] = sup["supplier_id"]
            unified["supplier_name"] = sup["supplier_name"]
            unified["lead_time_days"] = sup["lead_time_days"]
            unified["minimum_order_quantity"] = sup["minimum_order_quantity"]
            unified["pack_size"] = sup["pack_size"]
            unified["reliability_score"] = sup["reliability_score"]
        else:
            unified["supplier_id"] = None
            unified["supplier_name"] = "Unknown"
            unified["lead_time_days"] = None
            unified["minimum_order_quantity"] = 0
            unified["pack_size"] = 1
            unified["reliability_score"] = 0.0

        return unified
