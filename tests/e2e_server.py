"""Run mask_editor's HTTP server headlessly for the E2E test (no browser auto-open).

Usage: python e2e_server.py <image> <mask-out> <port>

mask_editor is loaded by path so the test runs from a plain checkout.
"""
import importlib.util
import sys
import webbrowser
from pathlib import Path

# Patch before mask_editor.main() runs, so the test never pops a real window.
webbrowser.open = lambda *a, **k: None

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mask_editor.py"
spec = importlib.util.spec_from_file_location("mask_editor", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

image, mask, port = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = ["mask_editor.py", "--image", image, "--out", mask, "--port", port]
mod.main()
