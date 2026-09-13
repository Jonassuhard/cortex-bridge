#!/usr/bin/env python3
"""Run the installed standard-library context preparation helper."""
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
runpy.run_module("orchestration.artifacts", run_name="__main__")
