from datetime import date
from decimal import Decimal
import json

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QMessageBox, QInputDialog
)

from database import SessionLocal
from models import Account, AccountingPeriod, JournalEntry, JournalEntryLine, AuditLog
from accounting_service import create_draft_entry, post_journal_entry, reverse_journal_entry
from accounting_period_service import (
    create_accounting_period, close_accounting_period, reopen_accounting_period
)


class FinanceActionsMixin:
    """Permission-aware Finance actions. Uses the existing accounting services."""

    def _finance_username(self):
        return (self.current_user or {}).get("username", "")

    def _can_manage_finance(self):
        return "finance.manage" in (self.current_user or {}).get("permissions", [])

    def _build_journal_actions(self, layout):
        bar = QHBoxLayout()
        self.new_journal_button = QPushButton("New Journal Draft")
        self.post_journal_button = QPushButton("Post Selected Draft")
        self.reverse_journal_button = QPushButton("Reverse Selected Posted Entry")
        for button, callback in (
            (self.new_journal_button, self._new_journal),
            (self.post_journal_button, self._post_selected_journal),
            (self.reverse_journal_button, self._reverse_selected_journal),
        ):
            button.clicked.connect(callback)
            button.setVisible(self._can_manage_finance())
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)

    def _build_period_actions(self, layout):
        bar = QHBoxLayout()
        actions = [
            ("Create Period", self._create_period),
            ("Close Selected Period", self._close_selected_period),
            ("Reopen Selected Period", self._reopen_selected_period),
        ]
        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(callback)
            button.setVisible(self._can_manage_finance())
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)

    def _build_account_actions(self, layout):
        bar = QHBoxLayout()
        for label, callback in (
            ("Add Detailed Account", self._add_account),
            ("Activate / Deactivate Selected", self._toggle_account),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            button.setVisible(self._can_manage_finance())
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)

    def _selected_id(self, table, column=0):
        row = table.currentRow()
        if row < 0 or table.item(row, column) is None:
            raise ValueError("Select a record first.")
        return int(table.item(row, column).text())

    def _new_journal(self):
        if not self._can_manage_finance():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Journal Draft")
        dialog.resize(850, 520)
        root = QVBoxLayout(dialog)
        form = QFormLayout()
        entry_date = QDateEdit(QDate.currentDate())
        entry_date.setCalendarPopup(True)
        entry_date.setDisplayFormat("yyyy-MM-dd")
        description = QLineEdit()
        description.setPlaceholderText("Reason / description for this journal")
        form.addRow("Entry date:", entry_date)
        form.addRow("Description:", description)
        root.addLayout(form)
        table = QTableWidget(4, 4)
        table.setHorizontalHeaderLabels(["Account", "Line description", "Debit (PKR)", "Credit (PKR)"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        db = SessionLocal()
        try:
            accounts = db.query(Account).filter_by(is_active=True).order_by(Account.code).all()
            detail_accounts = [a for a in accounts if not db.query(Account.id).filter_by(parent_id=a.id).first()]
            account_options = [(f"{a.code} - {a.name}", a.code) for a in detail_accounts]
        finally:
            db.close()
        for r in range(table.rowCount()):
            combo = QComboBox()
            combo.addItem("Select account", "")
            for label, code in account_options:
                combo.addItem(label, code)
            table.setCellWidget(r, 0, combo)
            table.setItem(r, 1, QTableWidgetItem(""))
            for c in (2, 3):
                spin = QDoubleSpinBox()
                spin.setMaximum(99999999999.99)
                spin.setDecimals(2)
                spin.setPrefix("PKR ")
                table.setCellWidget(r, c, spin)
        root.addWidget(table)
        controls = QHBoxLayout()
        add_line = QPushButton("Add Line")
        add_line.clicked.connect(lambda: self._append_journal_line(table, account_options))
        controls.addWidget(add_line)
        controls.addStretch()
        save = QPushButton("Save as Draft")
        cancel = QPushButton("Cancel")
        controls.addWidget(save)
        controls.addWidget(cancel)
        root.addLayout(controls)
        cancel.clicked.connect(dialog.reject)
        def save_draft():
            try:
                if not description.text().strip():
                    raise ValueError("Enter a journal description.")
                lines = []
                for r in range(table.rowCount()):
                    combo = table.cellWidget(r, 0)
                    code = combo.currentData()
                    debit = Decimal(str(table.cellWidget(r, 2).value())).quantize(Decimal("0.01"))
                    credit = Decimal(str(table.cellWidget(r, 3).value())).quantize(Decimal("0.01"))
                    if not code and debit == 0 and credit == 0:
                        continue
                    if not code:
                        raise ValueError(f"Select an account on line {r + 1}.")
                    note = table.item(r, 1).text() if table.item(r, 1) else ""
                    lines.append({"account_code": code, "debit": debit, "credit": credit, "description": note})
                journal_id = create_draft_entry(
                    entry_date=date.fromisoformat(entry_date.date().toString("yyyy-MM-dd")),
                    description=description.text().strip(), lines=lines,
                    username=self._finance_username(), source_module="finance_manual"
                )
                QMessageBox.information(dialog, "Draft Saved", f"Journal draft #{journal_id} saved. It has not affected posted balances.")
                dialog.accept()
                self.refresh_all()
            except Exception as exc:
                QMessageBox.warning(dialog, "Cannot Save Journal", str(exc))
        save.clicked.connect(save_draft)
        dialog.exec()

    def _append_journal_line(self, table, account_options):
        row = table.rowCount()
        table.insertRow(row)
        combo = QComboBox()
        combo.addItem("Select account", "")
        for label, code in account_options:
            combo.addItem(label, code)
        table.setCellWidget(row, 0, combo)
        table.setItem(row, 1, QTableWidgetItem(""))
        for c in (2, 3):
            spin = QDoubleSpinBox()
            spin.setMaximum(99999999999.99)
            spin.setDecimals(2)
            spin.setPrefix("PKR ")
            table.setCellWidget(row, c, spin)

    def _selected_journal_id(self):
        row = self.journal_table.currentRow()
        if row < 0 or self.journal_table.item(row, 0) is None:
            raise ValueError("Select a journal entry first.")
        entry_number = self.journal_table.item(row, 0).text()
        db = SessionLocal()
        try:
            entry = db.query(JournalEntry).filter_by(entry_number=entry_number).first()
            if entry is None:
                raise ValueError("The selected journal entry no longer exists.")
            return entry.id
        finally:
            db.close()

    def _post_selected_journal(self):
        if not self._can_manage_finance():
            return
        try:
            entry_id = self._selected_journal_id()
            db = SessionLocal()
            try:
                entry = db.get(JournalEntry, entry_id)
                if entry is None or entry.status != "draft":
                    raise ValueError("Select a draft journal entry.")
                if QMessageBox.question(self, "Confirm Posting", f"Post {entry.entry_number}? Posted entries affect financial reports and cannot be edited.") != QMessageBox.StandardButton.Yes:
                    return
            finally:
                db.close()
            post_journal_entry(entry_id, username=self._finance_username())
            QMessageBox.information(self, "Posted", "Journal entry posted successfully.")
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot Post Journal", str(exc))

    def _reverse_selected_journal(self):
        if not self._can_manage_finance():
            return
        try:
            entry_id = self._selected_journal_id()
            db = SessionLocal()
            try:
                entry = db.get(JournalEntry, entry_id)
                if entry is None or entry.status != "posted":
                    raise ValueError("Select a posted journal entry.")
                if entry.reversal_of_id:
                    raise ValueError("A reversal entry cannot itself be reversed from this screen.")
                entry_number = entry.entry_number
            finally:
                db.close()
            reason, ok = QInputDialog.getText(self, "Reverse Journal", f"Reason for reversing {entry_number}:")
            if not ok or not reason.strip():
                return
            if QMessageBox.question(self, "Confirm Reversal", "This creates and posts a separate reversing entry. Continue?") != QMessageBox.StandardButton.Yes:
                return
            reversal_id = reverse_journal_entry(entry_id, date.today(), reason.strip(), self._finance_username())
            QMessageBox.information(self, "Reversed", f"Reversal posted. New journal ID: {reversal_id}")
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot Reverse Journal", str(exc))

    def _create_period(self):
        if not self._can_manage_finance():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Accounting Period")
        form = QFormLayout(dialog)
        name = QLineEdit()
        start = QDateEdit(QDate.currentDate().addMonths(-1)); start.setCalendarPopup(True); start.setDisplayFormat("yyyy-MM-dd")
        end = QDateEdit(QDate.currentDate()); end.setCalendarPopup(True); end.setDisplayFormat("yyyy-MM-dd")
        reason = QLineEdit(); reason.setPlaceholderText("Why is this accounting period being created?")
        form.addRow("Period name:", name); form.addRow("Start date:", start); form.addRow("End date:", end); form.addRow("Reason:", reason)
        buttons = QHBoxLayout(); save = QPushButton("Create"); cancel = QPushButton("Cancel"); buttons.addWidget(save); buttons.addWidget(cancel); form.addRow(buttons)
        cancel.clicked.connect(dialog.reject)
        def create():
            try:
                create_accounting_period(name.text(), date.fromisoformat(start.date().toString("yyyy-MM-dd")), date.fromisoformat(end.date().toString("yyyy-MM-dd")), self._finance_username(), reason.text())
                dialog.accept(); self.refresh_all()
            except Exception as exc: QMessageBox.warning(dialog, "Cannot Create Period", str(exc))
        save.clicked.connect(create); dialog.exec()

    def _period_action(self, action):
        if not self._can_manage_finance():
            return
        try:
            period_id = self._selected_id(self.period_table)
            reason, ok = QInputDialog.getText(self, action, "Enter the reason (required):")
            if not ok or not reason.strip(): return
            if action == "Close": close_accounting_period(period_id, self._finance_username(), reason)
            else: reopen_accounting_period(period_id, self._finance_username(), reason)
            QMessageBox.information(self, "Accounting Period", f"Accounting period {action.lower()} operation completed successfully.")
            self.refresh_all()
        except Exception as exc: QMessageBox.warning(self, "Accounting Period", str(exc))

    def _close_selected_period(self): self._period_action("Close")
    def _reopen_selected_period(self): self._period_action("Reopen")

    def _add_account(self):
        if not self._can_manage_finance(): return
        db = SessionLocal()
        try:
            parents = db.query(Account).order_by(Account.code).all()
            choices = [(f"{a.code} - {a.name}", a.id, a.account_type) for a in parents]
        finally: db.close()
        if not choices:
            QMessageBox.warning(self, "Chart of Accounts", "Create or seed parent accounts first."); return
        dialog = QDialog(self); dialog.setWindowTitle("Add Detailed Account")
        form = QFormLayout(dialog)
        code = QLineEdit(); name = QLineEdit(); description = QLineEdit()
        parent = QComboBox()
        for label, aid, typ in choices: parent.addItem(label, (aid, typ))
        form.addRow("Account code:", code); form.addRow("Account name:", name); form.addRow("Parent account:", parent); form.addRow("Description:", description)
        buttons = QHBoxLayout(); save = QPushButton("Save Account"); cancel = QPushButton("Cancel"); buttons.addWidget(save); buttons.addWidget(cancel); form.addRow(buttons); cancel.clicked.connect(dialog.reject)
        def save_account():
            db2 = SessionLocal()
            try:
                selected = parent.currentData(); parent_id, account_type = selected
                parent_obj = db2.get(Account, parent_id)
                if parent_obj is None: raise ValueError("Selected parent account no longer exists.")
                if db2.query(Account.id).filter_by(parent_id=parent_id).first():
                    raise ValueError("Choose a detailed parent account, not a category that already has children.")
                account_code = code.text().strip(); account_name = name.text().strip()
                if not account_code or len(account_code) > 30: raise ValueError("Account code must contain 1 to 30 characters.")
                if not account_name or len(account_name) > 200: raise ValueError("Account name must contain 1 to 200 characters.")
                if db2.query(Account.id).filter_by(code=account_code).first(): raise ValueError("This account code already exists.")
                normal = "debit" if account_type in ("asset", "expense") else "credit"
                account = Account(code=account_code, name=account_name, account_type=account_type, normal_balance=normal, parent_id=parent_id, description=description.text().strip() or None, is_active=True, is_system=False)
                db2.add(account); db2.flush()
                db2.add(AuditLog(module="accounting", action="account_created", record_type="Account", record_id=account.id, username=self._finance_username(), new_values=json.dumps({"code": account_code, "name": account_name, "parent_id": parent_id})))
                db2.commit(); dialog.accept(); self.refresh_all()
            except Exception as exc:
                db2.rollback(); QMessageBox.warning(dialog, "Cannot Save Account", str(exc))
            finally: db2.close()
        save.clicked.connect(save_account); dialog.exec()

    def _toggle_account(self):
        if not self._can_manage_finance():
            return
        try:
            row = self.account_table.currentRow()
            if row < 0: raise ValueError("Select an account first.")
            code = self.account_table.item(row, 0).text()
            db = SessionLocal()
            try:
                account = db.query(Account).filter_by(code=code).first()
                if account is None: raise ValueError("Account not found.")
                if account.is_system: raise ValueError("System chart-of-accounts entries are protected from activation changes here.")
                if db.query(Account.id).filter_by(parent_id=account.id).first(): raise ValueError("A parent account with child accounts cannot be deactivated.")
                if account.is_active:
                    used = db.query(JournalEntryLine.id).filter_by(account_id=account.id).first()
                    if used: raise ValueError("This account has journal history and cannot be deactivated.")
                old = account.is_active; account.is_active = not old
                db.add(AuditLog(module="accounting", action="account_activated" if not old else "account_deactivated", record_type="Account", record_id=account.id, username=self._finance_username(), old_values=json.dumps({"is_active": old}), new_values=json.dumps({"is_active": account.is_active})))
                db.commit()
            except Exception: db.rollback(); raise
            finally: db.close()
            self.refresh_all()
        except Exception as exc: QMessageBox.warning(self, "Chart of Accounts", str(exc))
