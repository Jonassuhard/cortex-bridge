#!/usr/bin/env python3
"""Entrypoint for the installed, bundled stdlib native journal."""
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
runpy.run_module("orchestration.native_journal", run_name="__main__")
