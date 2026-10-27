import sys
import os

# Add parent directory to sys.path so 'agent' is importable by pytest and unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
