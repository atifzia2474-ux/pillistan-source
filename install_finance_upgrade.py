from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TARGET = Path.cwd().resolve()
FILES = ("finance_manager.py", "finance_actions.py", "desktop_main.py")

required = [ROOT / name for name in FILES]
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise SystemExit("Package is incomplete: " + ", ".join(missing))

for name in ("finance_manager.py", "desktop_main.py"):
    if not (TARGET / name).is_file():
        raise SystemExit(f"Run this installer from the Pillistan project folder; missing {name}")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = TARGET / "backups" / f"before_finance_upgrade_installer_{stamp}"
backup.mkdir(parents=True, exist_ok=True)

for name in ("finance_manager.py", "desktop_main.py"):
    shutil.copy2(TARGET / name, backup / name)

try:
    for name in FILES:
        shutil.copy2(ROOT / name, TARGET / name)
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", *FILES],
        cwd=TARGET, capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout or "Python compile check failed")
except Exception:
    for name in ("finance_manager.py", "desktop_main.py"):
        saved = backup / name
        if saved.exists():
            shutil.copy2(saved, TARGET / name)
    new_file = TARGET / "finance_actions.py"
    if new_file.exists():
        new_file.unlink()
    raise

print("Finance upgrade installed successfully.")
print(f"Backup: {backup}")
print("Installed: finance_manager.py, finance_actions.py, desktop_main.py")
print("Python syntax check: PASS")
print("No database migration was run. No database was opened or modified by this installer.")
