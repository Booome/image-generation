"""Drive the mask_editor E2E: server -> headless Chromium -> mask verification.

Usage:
    python tests/run_e2e.py [--image <path>] [--keep-mask <path>]

Requires (one-off):
    cd tests && npm install && npx playwright install chromium
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[3]
DEFAULT_IMAGE = REPO / "资产" / "场景" / "scn-000002.jpg"

# Every child process gets a deadline: a hanging test must FAIL, not stall.
UNIT_TIMEOUT_S = 180
BROWSER_TIMEOUT_S = 300


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(DEFAULT_IMAGE))
    ap.add_argument("--keep-mask", default=None, help="write the mask here instead of a temp file")
    ap.add_argument("--unit-only", action="store_true", help="skip the browser half")
    args = ap.parse_args()

    print("=== unit tests (offline) ===")
    for name in ("test_generate.py", "test_sizes.py", "test_assets.py", "test_contracts.py",
                 "test_semantics.py", "test_assets_library.py", "test_hygiene.py"):
        try:
            rc = subprocess.run([sys.executable, str(TESTS / name)],
                                timeout=UNIT_TIMEOUT_S).returncode
        except subprocess.TimeoutExpired:
            sys.exit("%s TIMED OUT after %ds - treat as failure and investigate"
                     % (name, UNIT_TIMEOUT_S))
        if rc != 0:
            sys.exit("%s failed (%d)" % (name, rc))
    browser_script = TESTS / "test_request.py"
    if browser_script.exists():
        rc = subprocess.run([sys.executable, str(browser_script)]).returncode
        if rc != 0:
            sys.exit("test_request.py failed (%d)" % rc)
    if args.unit_only:
        sys.exit(0)

    image = Path(args.image)
    if not image.exists():
        sys.exit(f"test image not found: {image}")
    mask = Path(args.keep_mask) if args.keep_mask else Path(tempfile.mkdtemp()) / "e2e_mask.png"
    # Delete any stale mask first: otherwise a run where the server silently
    # fails to write would still "pass" against the previous run's file.
    if mask.exists():
        mask.unlink()

    port = free_port()
    print("server on %d  image=%s  mask=%s" % (port, image.name, mask))

    server = subprocess.Popen([sys.executable, str(TESTS / "e2e_server.py"), str(image), str(mask), str(port)])
    try:
        if not wait_port(port):
            sys.exit("server did not start")
        env = dict(os.environ, E2E_PORT=str(port), E2E_MASK=str(mask))
        browser = subprocess.run(["node", str(TESTS / "e2e.js")], env=env, cwd=str(TESTS),
                         timeout=BROWSER_TIMEOUT_S)
        if browser.returncode != 0:
            sys.exit("browser test failed (%d)" % browser.returncode)
        verify = subprocess.run([sys.executable, str(TESTS / "verify_mask.py"), str(mask), str(image)],
                      timeout=UNIT_TIMEOUT_S)
        sys.exit(verify.returncode)
    finally:
        if server.poll() is None:
            server.terminate()


if __name__ == "__main__":
    main()
