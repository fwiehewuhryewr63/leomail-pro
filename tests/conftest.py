"""
Leomail v3 — Test Configuration
Adds backend to sys.path so imports work.
"""
import sys
from pathlib import Path

# Add project root to path so `backend.xxx` imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
