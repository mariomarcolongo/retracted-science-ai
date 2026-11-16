"""Run the complete offline regression suite (paper sections 3.5–3.6).

Usage: python3 -I tests/run_all.py
Tests create only synthetic inputs under /tmp; model runners use --dry, public
reference checking uses caches/mocks, and no credentials are loaded.
"""
from pathlib import Path
import sys
import unittest
import warnings
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=ResourceWarning)
suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
