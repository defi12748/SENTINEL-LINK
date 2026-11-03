"""Verify a copied source tree with a fresh interpreter/environment.

Install requirements.lock.txt into a new venv, then use that venv's Python:
python deploy/verify_clean.py --smoke --out results/clean_install.json
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = Path(tempfile.mkdtemp(prefix="sentinel-clean-source-")) / "grss"
    target.mkdir()
    for folder in ("sentinel", "tests", "models", "docs", "deploy"):
        shutil.copytree(source / folder, target / folder,
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.log"))
    env = dict(os.environ, SENTINEL_DATA_ROOT=os.environ.get("SENTINEL_DATA_ROOT", str(source / "data")),
               PYTHONNOUSERSITE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    env.pop("PYTHONPATH", None)
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0],
              "platform": sys.platform, "fresh_source_copy": True,
              "isolated_python_environment": sys.prefix != sys.base_prefix,
              "dataset": "SHA-256-verified public recordings reused as test inputs", "checks": {}}
    successful = True
    def run(name, command):
        nonlocal successful
        process = subprocess.run([sys.executable, *command], cwd=target, env=env,
                                 capture_output=True, text=True, timeout=600)
        report["checks"][name] = {"exit_code": process.returncode, "stdout": process.stdout,
                                  "stderr": process.stderr}
        print(name, process.returncode, process.stdout[-1500:], process.stderr[-1000:], flush=True)
        successful = successful and process.returncode == 0
    run("doctor", ["-m", "sentinel", "doctor", "--verify-data", "--require-nasa"])
    run("tests", ["-m", "pytest", "tests", "-q", "-p", "no:asyncio"])
    if args.smoke and successful:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with (target / "api.log").open("w") as log:
            api = subprocess.Popen([sys.executable, "-m", "uvicorn", "sentinel.api.server:app", "--port", str(port)],
                                   cwd=target, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(60):
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3).close()
                        break
                    except OSError:
                        if api.poll() is not None:
                            raise RuntimeError("Clean API stopped during startup")
                        time.sleep(.5)
                run("api_smoke", ["deploy/smoke.py", "--api", f"http://127.0.0.1:{port}",
                                  "--out", "results/smoke.json"])
            finally:
                api.terminate()
                try:
                    api.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    api.kill()
            report["checks"]["api_log"] = (target / "api.log").read_text()[-4000:]
    report["ok"] = successful
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Verification report:", out)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
