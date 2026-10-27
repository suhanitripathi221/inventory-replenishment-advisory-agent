
import streamlit as st
import json
import subprocess
import sys
from pathlib import Path

st.set_page_config(
    page_title="Inventory Replenishment Advisory Agent",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Inventory Replenishment Advisory Agent")
st.caption("HCL Career Shaper Internship Project")
st.write(
    "Analyze inventory levels and generate deterministic "
    "replenishment recommendations using the Python agent."
)

project_dir = Path(__file__).resolve().parent
main_file = project_dir / "main.py"

st.subheader("Inventory Analysis")

product_id = st.text_input("Enter Product ID", value="P101")

if st.button("Run Inventory Analysis", type="primary"):
    if not product_id.strip():
        st.error("Please enter a product ID.")
    elif not main_file.exists():
        st.error("main.py was not found in this folder.")
    else:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(main_file),
                    "--product",
                    product_id.strip(),
                    "--json"
                ],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    st.success("Analysis completed!")
                    st.json(output)
                except json.JSONDecodeError:
                    st.success("Analysis completed!")
                    st.code(result.stdout or "No output returned.")

            else:
                st.error("The agent could not complete the analysis.")
                st.code(result.stderr or result.stdout)

        except subprocess.TimeoutExpired:
            st.error("Analysis timed out. Please try again.")
        except Exception as error:
            st.error(f"Error: {error}")

st.divider()
st.caption(
    "Python-based inventory decision support | "
    "HCL Career Shaper Internship"
)
