from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

project = Path.cwd()
if project.resolve() != Path(r"D:\Pillistan").resolve():
    raise SystemExit("Please run this installer from D:\\Pillistan.")

source_dir = Path(__file__).resolve().parent
for filename in ("returns_module.py", "migrate_returns_schema.py"):
    source = source_dir / filename
    if not source.exists():
        raise SystemExit(f"Package is missing {filename}.")
    shutil.copy2(source, project / filename)

main_path = project / "desktop_main.py"
main_text = main_path.read_text(encoding="utf-8")
backup_dir = project / "backups" / ("before_returns_desktop_link_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
backup_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(main_path, backup_dir / "desktop_main.py")

if "from returns_module import ReturnsManager" not in main_text:
    import_marker = "from courier_manager import CourierManager"
    if import_marker not in main_text:
        raise SystemExit("Could not locate CourierManager import. No desktop_main.py changes made.")
    main_text = main_text.replace(import_marker, import_marker + "\nfrom returns_module import ReturnsManager", 1)

# Replace the Returns placeholder block while preserving dictionary indentation.
pattern = r'"Returns"\s*:\s*lambda\s*:\s*self\._create_placeholder_page\(\s*"Returns"\s*,\s*"Returns management will be implemented in a later development step\."\s*\)\s*,'
replacement = '"Returns": lambda: ReturnsManager(SessionLocal),'
updated, count = re.subn(pattern, replacement, main_text, count=1)
if count == 0 and '"Returns": lambda: ReturnsManager(SessionLocal)' not in main_text:
    raise SystemExit("Could not safely locate the Returns placeholder. Source files copied, but desktop_main.py was not changed.")
main_path.write_text(updated, encoding="utf-8")
print("Returns module and migration script installed.")
print("desktop_main.py connected to ReturnsManager.")
print("Desktop backup:", backup_dir)
print("The production database has not been opened or migrated by this installer.")
