"""Install the exact NASA source revisions used by the prototype.

Run after installing GNU Radio and the C build prerequisites listed in README.md.
Existing custom checkouts are preserved; use SENTINEL_ONAIR_PATH/CRYPTOLIB_SRC for them.
"""

import os
import platform
import subprocess
from pathlib import Path

ONAIR_COMMIT = "aa5559c0f234eba263041b6007573f16870194e5"


def main():
    target = Path.home() / ".sentinel" / "OnAIR"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(target)], check=True)
        subprocess.run(["git", "-C", str(target), "remote", "add", "origin", "https://github.com/nasa-itc/OnAIR.git"], check=True)
        subprocess.run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", ONAIR_COMMIT], check=True)
        subprocess.run(["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    if head != ONAIR_COMMIT:
        raise SystemExit("Existing OnAIR checkout preserved. Set SENTINEL_ONAIR_PATH to your selected revision.")
    script = Path(__file__).resolve().parents[1] / "sentinel/trust/cryptolib_bridge/build.sh"
    script.write_bytes(script.read_bytes().replace(b"\r\n", b"\n"))
    if platform.system() == "Windows":
        distro = os.environ.get("SENTINEL_WSL_DISTRO")
        prefix = ["wsl", "-d", distro, "--"] if distro else ["wsl", "--"]
        linux_path = f"/mnt/{script.drive[0].lower()}{script.as_posix()[len(script.drive):]}"
        command = prefix + ["bash", linux_path]
    else:
        command = ["bash", str(script)]
    subprocess.run(command, check=True, timeout=600)
    print("NASA modules ready. Run python -m sentinel doctor --require-nasa")


if __name__ == "__main__":
    main()
