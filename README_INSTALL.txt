PILLISTAN IMPROVEMENTS PATCH
===========================

Included improvements
---------------------
1. Optional per-product low-stock thresholds in Product Management.
   - Leave the product-specific option unchecked to use the global threshold.
   - Inventory checks total available quantity across all active batches.
   - Products with no stock are also included in low-stock warnings.
2. Scheduled, verified SQLite backups.
   - Enabled by default, initially every 1 hour.
   - Settings options: 1, 2, 4, 6, 12, or 24 hours.
   - Uses SQLite's online backup API while Pillistan is running.
   - Checks backup integrity and required Pillistan tables.
   - Default retention: 168 backups (one week at hourly intervals).
   - Backup folder and retention are configurable.
3. Additional manual backup prompt when closing Pillistan.
   - Backup Now / Close Without Backup / Cancel.
   - Transactions are still saved by their normal database commits.
   - No backup is made after every transaction.
4. Administrator profile and password controls.
   - Edit your own username and full name.
   - Change password after verifying current password and confirming new password.
   - Last active Administrator cannot be deactivated.
5. Restore compatibility.
   - Restoring an older database backup automatically adds the nullable
     low_stock_threshold column if it is missing, after creating a verified
     safety backup.

Files in this patch
-------------------
models.py
product_manager.py
inventory_manager.py
settings_centre.py
desktop_main.py
backup_service.py                  (new)
migrate_pillistan_improvements.py  (new)

INSTALLATION - FOLLOW IN ORDER
------------------------------
IMPORTANT: Close Pillistan before replacing source files or running migration.

1. Make a source-code backup from PowerShell:

   Set-Location D:\Pillistan
   $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
   $backupDir = ".\source_backup_$stamp"
   New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
   Copy-Item models.py, product_manager.py, inventory_manager.py, settings_centre.py, desktop_main.py $backupDir

2. Extract this ZIP directly into D:\Pillistan and allow the five existing
   source files to be overwritten. The two new .py files must also be placed
   in D:\Pillistan.

3. Run the syntax check:

   python -m py_compile models.py product_manager.py inventory_manager.py settings_centre.py desktop_main.py backup_service.py migrate_pillistan_improvements.py

4. Run the one-time database migration while Pillistan is CLOSED:

   python migrate_pillistan_improvements.py

   The migration creates and verifies a pre-migration database backup in
   %USERPROFILE%\PillistanBackups before changing the products table.
   Existing products are preserved. If the column already exists, it reports
   that no migration is needed.

5. Start Pillistan:

   python desktop_main.py

6. In Settings Centre > Backup & Restore:
   - Confirm or choose the backup folder.
   - Confirm automatic backups are enabled.
   - Choose the interval.
   - Set retention if desired.
   - Click Save Settings.

7. In Product Management, edit a product and optionally enable its own
   low-stock threshold. If disabled, the global Inventory threshold is used.

Important safeguards
--------------------
- The patch does not modify auth_manager.py or database.py.
- It does not modify purchase/accounting modules or accounting triggers.
- The live database is not migrated until you run step 4.
- Do not run the migration while Pillistan is open.
- The scheduled backup runs on the selected interval, not after each transaction.
- A manual end-of-day backup is offered whenever you close the main application.
- If the backup fails at closing, Pillistan remains open so you can retry or
  choose Close Without Backup on the next prompt.
- SQLite online backup is designed to operate while the database is in use.
  It avoids a raw copy of the live database, though a very large database can
  still cause brief disk/CPU activity.

Testing performed before packaging
-----------------------------------
- Python syntax compilation passed for all modified and new modules.
- Isolated SQLite test: threshold-column migration preserved existing products.
- Isolated SQLite test: online backup completed and passed integrity_check.
- Isolated SQLite test: retention kept the configured newest backups.

The PySide6 GUI cannot be launched in this build environment, so please perform
the first application launch and visual check on your Windows machine after
the steps above. No production database was changed while preparing this patch.
