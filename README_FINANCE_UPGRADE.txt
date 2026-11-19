PILLISTAN FINANCE UPGRADE

Included files:
- finance_manager.py: upgraded Finance workspace, preserving existing reports and exports
- finance_actions.py: permission-aware journal, accounting period, and chart-of-accounts actions
- desktop_main.py: passes the authenticated user into Finance at construction time
- install_finance_upgrade.py: backup-first installer with syntax validation and rollback

INSTALLATION
1. Extract this ZIP into a temporary folder.
2. Open the existing PowerShell window in D:\Pillistan (the project root).
3. Run: python "<extracted-folder>\install_finance_upgrade.py"
   The installer copies the package files into the current project directory.
4. It creates a timestamped backup before replacing finance_manager.py and desktop_main.py.
5. It runs Python syntax validation and restores the two backed-up files if installation fails.

FUNCTIONALITY ADDED
- Manual journal draft creation with multiple lines and balanced-journal validation through accounting_service.
- Posting selected draft entries through the existing posting service.
- Reversing a posted journal through the existing reversal service, with mandatory reason.
- Creating, closing, and reopening accounting periods through the existing audited period service.
- Creating detailed child accounts and activating/deactivating eligible custom accounts with audit records.
- Uses authenticated username and finance.view / finance.manage permissions.

SAFETY
- No schema migration is included or required for these changes.
- The installer does not connect to or modify any database.
- Journal posting still requires an open accounting period and valid balanced lines.
- Opening balances are deliberately not enabled in this batch. The database has OpeningBalance models, but the supplied source set contains no complete opening-balance service/workflow. This should be implemented separately with its own posting and audit rules rather than approximated with an ordinary journal.
- Run the first application test against the isolated development database, not production.
