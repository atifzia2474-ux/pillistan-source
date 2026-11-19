from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QFrame, QDateEdit, QFileDialog, QMenu
)
from PySide6.QtCore import Qt, QDate

from database import SessionLocal
from sqlalchemy import func
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from finance_actions import FinanceActionsMixin

from models import (
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
    Account,
    AuditLog,
)


class FinanceManager(FinanceActionsMixin, QWidget):

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.current_user = user or {}
        self.has_finance_view = "finance.view" in self.current_user.get("permissions", [])

        self.setStyleSheet("""
            QWidget {
                background-color: #f4f7f5;
                color: #24352c;
                font-size: 13px;
            }
            QTabWidget::pane {
                background: white;
                border: 1px solid #dce5df;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #e7eee9;
                padding: 10px 18px;
                margin-right: 3px;
            }
            QTabBar::tab:selected {
                background: #164b37;
                color: white;
            }
            QTableWidget {
                background: white;
                border: 1px solid #dce5df;
                gridline-color: #edf1ee;
                selection-background-color: #dcebe1;
                selection-color: #164b37;
            }
            QHeaderView::section {
                background: #eaf0ec;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QPushButton {
                background: #164b37;
                color: white;
                padding: 8px 16px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background: #28664d;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(25, 20, 25, 20)
        root.setSpacing(14)

        header = QHBoxLayout()

        title = QLabel("Finance Workspace")
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #164b37;"
        )
        header.addWidget(title)
        header.addStretch()

        refresh = QPushButton("Refresh Data")
        refresh.clicked.connect(self.refresh_all)
        header.addWidget(refresh)

        root.addLayout(header)

        notice = QLabel(
            "Financial workspace | Draft journals, posting, reversals and period/account controls are permission-restricted."
        )
        notice.setStyleSheet(
            "background: #e7eee9; color: #385b48; "
            "padding: 10px; border-radius: 5px;"
        )
        root.addWidget(notice)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.overview_tab = QWidget()
        self.journals_tab = QWidget()
        self.periods_tab = QWidget()
        self.accounts_tab = QWidget()
        self.audit_tab = QWidget()
        self.trial_balance_tab = QWidget()

        self.tabs.addTab(self.overview_tab, "Overview")
        self.tabs.addTab(self.journals_tab, "Journal Entries")
        self.tabs.addTab(self.periods_tab, "Accounting Periods")
        self.tabs.addTab(self.accounts_tab, "Chart of Accounts")
        self.tabs.addTab(self.audit_tab, "Audit History")
        self.tabs.addTab(self.trial_balance_tab, "Trial Balance")

        self._build_overview()
        self._build_journals()
        self._build_periods()
        self._build_accounts()
        self._build_audit()
        self._build_trial_balance()

        if self.has_finance_view:
            self.refresh_all()
        else:
            self.tabs.hide()
            root.addWidget(QLabel("Access denied: your account does not have finance.view permission."))

    def _build_overview(self):
        layout = QVBoxLayout(self.overview_tab)

        self.overview_cards = QHBoxLayout()
        layout.addLayout(self.overview_cards)

        self.debit_value = self._metric_card(
            self.overview_cards, "Posted Debits"
        )
        self.credit_value = self._metric_card(
            self.overview_cards, "Posted Credits"
        )
        self.journal_value = self._metric_card(
            self.overview_cards, "Posted Journals"
        )
        self.period_value = self._metric_card(
            self.overview_cards, "Current Period"
        )

        label = QLabel("Recent Accounting Activity")
        label.setStyleSheet(
            "font-size: 17px; font-weight: bold; margin-top: 12px;"
        )
        layout.addWidget(label)

        self.recent_table = self._make_table(
            ["Date", "Module", "Action", "Record", "Username"]
        )
        layout.addWidget(self.recent_table)

    def _metric_card(self, layout, title):
        card = QFrame()
        card.setStyleSheet(
            "background: white; border: 1px solid #e1e9e3; "
            "border-radius: 8px;"
        )

        card_layout = QVBoxLayout(card)

        heading = QLabel(title)
        heading.setStyleSheet("color: #718078; font-size: 12px;")

        value = QLabel("Loading...")
        value.setStyleSheet(
            "font-size: 21px; font-weight: bold; color: #164b37;"
        )

        card_layout.addWidget(heading)
        card_layout.addWidget(value)
        layout.addWidget(card)

        return value

    def _build_journals(self):
        layout = QVBoxLayout(self.journals_tab)

        info = QLabel(
            "Journal register — drafts, posted entries and reversals."
        )
        layout.addWidget(info)

        self.journal_table = self._make_table([
            "Entry Number", "Date", "Description",
            "Status", "Period", "Debit", "Credit",
            "Reversal Of"
        ])
        self._build_journal_actions(layout)
        layout.addWidget(self.journal_table)

    def _build_periods(self):
        layout = QVBoxLayout(self.periods_tab)

        info = QLabel(
            "Accounting periods and their current status."
        )
        layout.addWidget(info)

        self.period_table = self._make_table([
            "ID", "Period", "Start Date", "End Date", "Status"
        ])
        self._build_period_actions(layout)
        layout.addWidget(self.period_table)

    def _build_accounts(self):
        layout = QVBoxLayout(self.accounts_tab)

        info = QLabel(
            "Chart of Accounts — parent accounts and detailed accounts."
        )
        layout.addWidget(info)

        self.account_table = self._make_table([
            "Code", "Account Name", "Type",
            "Normal Balance", "Parent Account", "Active"
        ])
        self._build_account_actions(layout)
        layout.addWidget(self.account_table)

    def _build_audit(self):
        layout = QVBoxLayout(self.audit_tab)

        info = QLabel(
            "Accounting audit history. Records are displayed in "
            "reverse chronological order."
        )
        layout.addWidget(info)

        self.audit_table = self._make_table([
            "Date", "Module", "Action", "Record Type",
            "Record ID", "Username", "Reason"
        ])
        layout.addWidget(self.audit_table)


    def _build_trial_balance(self):
        layout = QVBoxLayout(self.trial_balance_tab)

        info = QLabel(
            "Read-only Trial Balance. Only posted journal entries are included. "
            "Reversals are included automatically."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        filters = QHBoxLayout()

        filters.addWidget(QLabel("From:"))
        self.trial_start_date = QDateEdit()
        self.trial_start_date.setCalendarPopup(True)
        self.trial_start_date.setDisplayFormat("yyyy-MM-dd")
        self.trial_start_date.setDate(QDate.currentDate().addMonths(-1))
        filters.addWidget(self.trial_start_date)

        filters.addWidget(QLabel("To:"))
        self.trial_end_date = QDateEdit()
        self.trial_end_date.setCalendarPopup(True)
        self.trial_end_date.setDisplayFormat("yyyy-MM-dd")
        self.trial_end_date.setDate(QDate.currentDate())
        filters.addWidget(self.trial_end_date)

        apply_button = QPushButton("Apply Dates")
        apply_button.clicked.connect(self._load_trial_balance)
        filters.addWidget(apply_button)

        report_button = QPushButton("Report")
        report_button.setStyleSheet(
            "QPushButton { background-color: #164b37; color: white; "
            "font-weight: bold; padding: 7px 16px; border-radius: 5px; }"
            "QPushButton:hover { background-color: #21664b; }"
        )
        report_menu = QMenu(report_button)
        report_menu.setStyleSheet(
            "QMenu { background: white; color: #24352c; "
            "border: 1px solid #dce5df; padding: 5px; }"
            "QMenu::item { padding: 7px 24px; }"
            "QMenu::item:selected { background: #e7eee9; color: #164b37; }"
        )
        report_menu.addAction("PDF Report").triggered.connect(
            self._export_trial_balance_pdf
        )
        report_menu.addAction("Excel Report").triggered.connect(
            self._export_trial_balance_excel
        )
        report_menu.addAction("Word Report").triggered.connect(
            self._export_trial_balance_word
        )
        report_menu.addAction("CSV Report").triggered.connect(
            self._export_trial_balance_csv
        )
        report_button.setMenu(report_menu)
        filters.addWidget(report_button)

        filters.addStretch()
        layout.addLayout(filters)

        self.trial_balance_status = QLabel("Loading...")
        self.trial_balance_status.setStyleSheet(
            "font-weight: bold; padding: 8px; background: white;"
            "border: 1px solid #dce5df; border-radius: 5px;"
        )
        layout.addWidget(self.trial_balance_status)

        self.trial_balance_title = QLabel("TRIAL BALANCE WORK SHEET")
        self.trial_balance_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trial_balance_title.setStyleSheet(
            "font-size: 18px; font-weight: bold; padding: 12px;"
            "background: #164b37; color: white; border-radius: 5px;"
        )
        layout.addWidget(self.trial_balance_title)

        self.trial_balance_period_label = QLabel("Period: MM/DD/YYYY")
        self.trial_balance_period_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trial_balance_period_label.setStyleSheet(
            "font-weight: bold; padding: 6px;"
        )
        layout.addWidget(self.trial_balance_period_label)

        self.trial_balance_table = QTableWidget()
        self.trial_balance_table.setColumnCount(8)
        self.trial_balance_table.setHorizontalHeaderLabels([
            "Account Code", "Account Name",
            "Opening Debit", "Opening Credit",
            "Period Debit", "Period Credit",
            "Closing Debit", "Closing Credit"
        ])
        self.trial_balance_table.horizontalHeader().setVisible(False)
        self.trial_balance_table.verticalHeader().setVisible(False)
        self.trial_balance_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.trial_balance_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.trial_balance_table.setAlternatingRowColors(True)
        self.trial_balance_table.setColumnWidth(0, 105)
        self.trial_balance_table.setColumnWidth(1, 190)
        for column in range(2, 8):
            self.trial_balance_table.setColumnWidth(column, 135)
        layout.addWidget(self.trial_balance_table)

        self._trial_balance_defaulted = False
        self.trial_balance_rows = []
        self.trial_balance_totals = {}

    def _load_trial_balance(self):
        db = SessionLocal()

        try:
            today = date.today()

            if not self._trial_balance_defaulted:
                current_period = db.query(AccountingPeriod).filter(
                    AccountingPeriod.start_date <= today,
                    AccountingPeriod.end_date >= today
                ).first()

                if current_period:
                    self.trial_start_date.setDate(QDate(
                        current_period.start_date.year,
                        current_period.start_date.month,
                        current_period.start_date.day
                    ))

                self.trial_end_date.setDate(QDate(
                    today.year, today.month, today.day
                ))
                self._trial_balance_defaulted = True

            start_date = date.fromisoformat(
                self.trial_start_date.date().toString("yyyy-MM-dd")
            )
            end_date = date.fromisoformat(
                self.trial_end_date.date().toString("yyyy-MM-dd")
            )

            if start_date > end_date:
                raise ValueError("The start date cannot be after the end date.")

            zero = Decimal("0.00")

            # Posted activity before the report period.
            opening_results = db.query(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0)
            ).join(
                JournalEntry,
                JournalEntry.id == JournalEntryLine.journal_entry_id
            ).filter(
                JournalEntry.status == "posted",
                JournalEntry.entry_date < start_date
            ).group_by(
                JournalEntryLine.account_id
            ).all()

            opening_map = {
                account_id: (
                    Decimal(str(debit or 0)),
                    Decimal(str(credit or 0))
                )
                for account_id, debit, credit in opening_results
            }

            # Posted activity inside the selected date range.
            activity_results = db.query(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0)
            ).join(
                JournalEntry,
                JournalEntry.id == JournalEntryLine.journal_entry_id
            ).filter(
                JournalEntry.status == "posted",
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date
            ).group_by(
                JournalEntryLine.account_id
            ).all()

            activity_map = {
                account_id: (
                    Decimal(str(debit or 0)),
                    Decimal(str(credit or 0))
                )
                for account_id, debit, credit in activity_results
            }

            accounts = db.query(Account).order_by(Account.code).all()

            # Exclude parent/category accounts to prevent double counting.
            parent_ids = {
                account.parent_id
                for account in accounts
                if account.parent_id is not None
            }

            detail_accounts = [
                account for account in accounts
                if account.id not in parent_ids
            ]

            rows = []
            total_opening_debit = zero
            total_opening_credit = zero
            total_period_debit = zero
            total_period_credit = zero
            total_closing_debit = zero
            total_closing_credit = zero

            for account in detail_accounts:
                opening_debit, opening_credit = opening_map.get(
                    account.id, (zero, zero)
                )
                period_debit, period_credit = activity_map.get(
                    account.id, (zero, zero)
                )

                opening_net = opening_debit - opening_credit
                closing_net = (
                    opening_net + period_debit - period_credit
                )

                opening_dr = max(opening_net, zero)
                opening_cr = max(-opening_net, zero)
                closing_dr = max(closing_net, zero)
                closing_cr = max(-closing_net, zero)

                rows.append((
                    account.code,
                    account.name,
                    opening_dr,
                    opening_cr,
                    period_debit,
                    period_credit,
                    closing_dr,
                    closing_cr
                ))

                total_opening_debit += opening_dr
                total_opening_credit += opening_cr
                total_period_debit += period_debit
                total_period_credit += period_credit
                total_closing_debit += closing_dr
                total_closing_credit += closing_cr

            self.trial_balance_rows = rows
            self.trial_balance_totals = {
                "opening_debit": total_opening_debit,
                "opening_credit": total_opening_credit,
                "period_debit": total_period_debit,
                "period_credit": total_period_credit,
                "closing_debit": total_closing_debit,
                "closing_credit": total_closing_credit,
                "difference": total_closing_debit - total_closing_credit
            }

            display_rows = []

            for row in rows:
                display_rows.append((
                    row[0], row[1],
                    self._amount(row[2]),
                    self._amount(row[3]),
                    self._amount(row[4]),
                    self._amount(row[5]),
                    self._amount(row[6]),
                    self._amount(row[7])
                ))

            display_rows.append((
                "", "TOTAL",
                self._amount(total_opening_debit),
                self._amount(total_opening_credit),
                self._amount(total_period_debit),
                self._amount(total_period_credit),
                self._amount(total_closing_debit),
                self._amount(total_closing_credit)
            ))

            self.trial_balance_period_label.setText(
                "Period: "
                + self.trial_start_date.date().toString("MM/dd/yyyy")
                + " to "
                + self.trial_end_date.date().toString("MM/dd/yyyy")
            )
            self._set_trial_balance_table(display_rows)

            difference = total_closing_debit - total_closing_credit

            if abs(difference) < Decimal("0.01"):
                self.trial_balance_status.setText(
                    f"BALANCED | {start_date} to {end_date} | "
                    f"Closing debits: {self._amount(total_closing_debit)} | "
                    f"Closing credits: {self._amount(total_closing_credit)}"
                )
                self.trial_balance_status.setStyleSheet(
                    "font-weight: bold; padding: 8px; color: #164b37;"
                    "background: #e7eee9; border-radius: 5px;"
                )
            else:
                self.trial_balance_status.setText(
                    f"OUT OF BALANCE | Difference: {self._amount(abs(difference))}"
                )
                self.trial_balance_status.setStyleSheet(
                    "font-weight: bold; padding: 8px; color: #9b2525;"
                    "background: #fbeaea; border-radius: 5px;"
                )

        except Exception as exc:
            QMessageBox.critical(
                self, "Trial Balance Error",
                f"Could not calculate Trial Balance:\n\n{exc}"
            )
        finally:
            db.close()

    def _trial_balance_report_filename(self, extension):
        """Build a descriptive report filename from the selected date range."""
        start = self.trial_start_date.date().toString("dMMMyy")
        end = self.trial_end_date.date().toString("dMMMyy")
        return f"Trial_Balance_{start}_to_{end}.{extension}"

    def _export_trial_balance_excel(self):
        if not self.trial_balance_rows:
            QMessageBox.information(
                self, "Trial Balance", "There are no account rows available for this report."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trial Balance Report", self._trial_balance_report_filename("xlsx"),
            "Excel Workbook (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            from openpyxl.styles import (
                Font, Alignment, PatternFill, Border, Side
            )
            from openpyxl.worksheet.page import PageMargins

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Trial Balance"

            sheet.merge_cells("A1:H1")
            sheet["A1"] = "TRIAL BALANCE WORK SHEET"
            sheet["A1"].font = Font(bold=True, size=16, color="FFFFFF")
            sheet["A1"].fill = PatternFill("solid", fgColor="164B37")
            sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
            sheet.row_dimensions[1].height = 30

            sheet["A2"] = "Period:"
            sheet["B2"] = self.trial_start_date.date().toString("MM/dd/yyyy")
            sheet["C2"] = "To"
            sheet["D2"] = self.trial_end_date.date().toString("MM/dd/yyyy")

            sheet.merge_cells("A4:A7")
            sheet.merge_cells("B4:B7")
            sheet.merge_cells("C4:H4")
            sheet.merge_cells("C5:H5")
            sheet.merge_cells("C6:D6")
            sheet.merge_cells("E6:F6")
            sheet.merge_cells("G6:H6")

            sheet["A4"] = "Account Code"
            sheet["B4"] = "Account Name"
            sheet["C4"] = "General Ledger"
            sheet["C5"] = "Account Balance"
            sheet["C6"] = "Opening Balance"
            sheet["E6"] = "Period Activity"
            sheet["G6"] = "Closing Balance"

            subheaders = [
                "Debit", "Credit", "Debit", "Credit", "Debit", "Credit"
            ]
            for column, label in enumerate(subheaders, start=3):
                sheet.cell(row=7, column=column, value=label)

            header_fill = PatternFill("solid", fgColor="DCE8E0")
            dark_fill = PatternFill("solid", fgColor="164B37")
            thin = Side(style="thin", color="AABBAF")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)

            for row_num in range(4, 8):
                for col_num in range(1, 9):
                    cell = sheet.cell(row=row_num, column=col_num)
                    cell.font = Font(
                        bold=True,
                        color="FFFFFF" if row_num == 4 else "164B37"
                    )
                    cell.fill = dark_fill if row_num == 4 else header_fill
                    cell.alignment = Alignment(
                        horizontal="center", vertical="center", wrap_text=True
                    )
                    cell.border = border

            data_start = 8
            for row in self.trial_balance_rows:
                sheet.append([
                    row[0], row[1],
                    float(row[2]), float(row[3]),
                    float(row[4]), float(row[5]),
                    float(row[6]), float(row[7])
                ])

            totals = self.trial_balance_totals
            sheet.append([
                "", "TOTAL",
                float(totals["opening_debit"]),
                float(totals["opening_credit"]),
                float(totals["period_debit"]),
                float(totals["period_credit"]),
                float(totals["closing_debit"]),
                float(totals["closing_credit"])
            ])

            total_row = sheet.max_row
            for row_num in range(data_start, total_row + 1):
                for col_num in range(1, 9):
                    cell = sheet.cell(row=row_num, column=col_num)
                    cell.border = border
                    if col_num >= 3:
                        cell.number_format = '"PKR" #,##0.00'
                        cell.alignment = Alignment(horizontal="right")
                    else:
                        cell.alignment = Alignment(vertical="center")

            for cell in sheet[total_row]:
                cell.font = Font(bold=True)
                cell.fill = header_fill

            sheet.column_dimensions["A"].width = 16
            sheet.column_dimensions["B"].width = 28
            for letter in "CDEFGH":
                sheet.column_dimensions[letter].width = 19

            sheet.freeze_panes = "C8"
            sheet.sheet_view.showGridLines = False
            sheet.page_setup.orientation = "landscape"
            sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
            sheet.page_setup.fitToWidth = 1
            sheet.page_setup.fitToHeight = 0
            sheet.sheet_properties.pageSetUpPr.fitToPage = True
            sheet.page_margins = PageMargins(
                left=0.25, right=0.25, top=0.5, bottom=0.5
            )
            sheet.print_title_rows = "1:7"
            sheet.print_area = f"A1:H{total_row}"

            workbook.save(path)
            QMessageBox.information(
                self, "Report Saved", f"Your Trial Balance report has been saved successfully as an Excel file.\n\nSaved to:\n{path}"
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Report Save Error", f"Excel report could not be saved:\n\n{exc}"
            )

    def _export_trial_balance_pdf(self):
        if not self.trial_balance_rows:
            QMessageBox.information(
                self, "Trial Balance", "There are no account rows available for this report."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trial Balance Report", self._trial_balance_report_filename("pdf"),
            "PDF Document (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        try:
            document = SimpleDocTemplate(
                path, pagesize=landscape(A4),
                rightMargin=22, leftMargin=22,
                topMargin=24, bottomMargin=24
            )

            styles = getSampleStyleSheet()
            story = [
                Paragraph("TRIAL BALANCE WORK SHEET", styles["Title"]),
                Paragraph(
                    f"Period: {self.trial_start_date.date().toString('MM/dd/yyyy')} "
                    f"to {self.trial_end_date.date().toString('MM/dd/yyyy')}",
                    styles["Normal"]
                ),
                Spacer(1, 12)
            ]

            data = [
                ["Account Code", "Account Name", "General Ledger", "", "", "", "", ""],
                ["", "", "Account Balance", "", "", "", "", ""],
                ["", "", "Opening Balance", "", "Period Activity", "", "Closing Balance", ""],
                ["", "", "Debit", "Credit", "Debit", "Credit", "Debit", "Credit"]
            ]

            for row in self.trial_balance_rows:
                data.append([
                    str(row[0]), str(row[1]),
                    f"PKR {row[2]:,.2f}", f"PKR {row[3]:,.2f}",
                    f"PKR {row[4]:,.2f}", f"PKR {row[5]:,.2f}",
                    f"PKR {row[6]:,.2f}", f"PKR {row[7]:,.2f}"
                ])

            totals = self.trial_balance_totals
            data.append([
                "", "TOTAL",
                f"PKR {totals['opening_debit']:,.2f}",
                f"PKR {totals['opening_credit']:,.2f}",
                f"PKR {totals['period_debit']:,.2f}",
                f"PKR {totals['period_credit']:,.2f}",
                f"PKR {totals['closing_debit']:,.2f}",
                f"PKR {totals['closing_credit']:,.2f}"
            ])

            table = Table(
                data,
                colWidths=[62, 135, 91, 91, 91, 91, 91, 91],
                repeatRows=4
            )
            table.setStyle(TableStyle([
                ("SPAN", (0, 0), (0, 3)),
                ("SPAN", (1, 0), (1, 3)),
                ("SPAN", (2, 0), (7, 0)),
                ("SPAN", (2, 1), (7, 1)),
                ("SPAN", (2, 2), (3, 2)),
                ("SPAN", (4, 2), (5, 2)),
                ("SPAN", (6, 2), (7, 2)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#164b37")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 3), colors.HexColor("#dce8e0")),
                ("TEXTCOLOR", (0, 1), (-1, 3), colors.HexColor("#164b37")),
                ("FONTNAME", (0, 0), (-1, 3), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, 3), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aabbb0")),
                ("ALIGN", (2, 4), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 4), (1, -1), "LEFT"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e7eee9")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6)
            ]))

            story.append(table)
            document.build(story)

            QMessageBox.information(
                self, "Report Saved", f"Your Trial Balance report has been saved successfully as a PDF file.\n\nSaved to:\n{path}"
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Report Save Error", f"PDF report could not be saved:\n\n{exc}"
            )


    def _export_trial_balance_word(self):
        if not self.trial_balance_rows:
            QMessageBox.information(
                self, "Trial Balance", "There are no account rows available for this report."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trial Balance Report", self._trial_balance_report_filename("docx"),
            "Word Document (*.docx)"
        )
        if not path:
            return
        if not path.lower().endswith(".docx"):
            path += ".docx"

        try:
            from docx import Document
            from docx.shared import Inches, Pt, RGBColor
            from docx.enum.section import WD_ORIENT
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.enum.table import WD_TABLE_ALIGNMENT
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn

            document = Document()
            section = document.sections[0]
            section.orientation = WD_ORIENT.LANDSCAPE
            section.page_width = Inches(11)
            section.page_height = Inches(8.5)
            section.left_margin = Inches(0.35)
            section.right_margin = Inches(0.35)

            title = document.add_heading("TRIAL BALANCE WORK SHEET", 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in title.runs:
                run.font.color.rgb = RGBColor(22, 75, 55)
                run.font.size = Pt(16)

            period = document.add_paragraph(
                f"Period: {self.trial_start_date.date().toString('MM/dd/yyyy')} "
                f"to {self.trial_end_date.date().toString('MM/dd/yyyy')}"
            )
            period.alignment = WD_ALIGN_PARAGRAPH.CENTER

            table = document.add_table(rows=4, cols=8)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER

            table.cell(0, 0).merge(table.cell(3, 0))
            table.cell(0, 1).merge(table.cell(3, 1))
            table.cell(0, 2).merge(table.cell(0, 7))
            table.cell(1, 2).merge(table.cell(1, 7))
            table.cell(2, 2).merge(table.cell(2, 3))
            table.cell(2, 4).merge(table.cell(2, 5))
            table.cell(2, 6).merge(table.cell(2, 7))

            labels = {
                (0, 0): "Account Code", (0, 1): "Account Name",
                (0, 2): "General Ledger", (1, 2): "Account Balance",
                (2, 2): "Opening Balance", (2, 4): "Period Activity",
                (2, 6): "Closing Balance",
                (3, 2): "Debit", (3, 3): "Credit",
                (3, 4): "Debit", (3, 5): "Credit",
                (3, 6): "Debit", (3, 7): "Credit",
            }

            def shade(cell, fill):
                properties = cell._tc.get_or_add_tcPr()
                element = OxmlElement("w:shd")
                element.set(qn("w:fill"), fill)
                properties.append(element)

            for (r, c), value in labels.items():
                table.cell(r, c).text = value

            for r in range(4):
                for cell in table.rows[r].cells:
                    shade(cell, "164B37" if r == 0 else "DCE8E0")
                    for paragraph in cell.paragraphs:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        for run in paragraph.runs:
                            run.bold = True
                            run.font.size = Pt(8)
                            if r == 0:
                                run.font.color.rgb = RGBColor(255, 255, 255)

            for row in self.trial_balance_rows:
                cells = table.add_row().cells
                values = [str(row[0]), str(row[1])] + [
                    f"PKR {float(v):,.2f}" for v in row[2:8]
                ]
                for i, value in enumerate(values):
                    cells[i].text = value
                    for paragraph in cells[i].paragraphs:
                        paragraph.alignment = (
                            WD_ALIGN_PARAGRAPH.RIGHT if i >= 2
                            else WD_ALIGN_PARAGRAPH.LEFT
                        )
                        for run in paragraph.runs:
                            run.font.size = Pt(7)

            totals = self.trial_balance_totals
            total_values = [
                "", "TOTAL",
                f"PKR {float(totals['opening_debit']):,.2f}",
                f"PKR {float(totals['opening_credit']):,.2f}",
                f"PKR {float(totals['period_debit']):,.2f}",
                f"PKR {float(totals['period_credit']):,.2f}",
                f"PKR {float(totals['closing_debit']):,.2f}",
                f"PKR {float(totals['closing_credit']):,.2f}",
            ]
            cells = table.add_row().cells
            for i, value in enumerate(total_values):
                cells[i].text = value
                shade(cells[i], "E7EEE9")
                for paragraph in cells[i].paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
                        run.font.size = Pt(7)

            document.save(path)
            QMessageBox.information(
                self, "Report Saved", f"Your Trial Balance report has been saved successfully as a Word file.\n\nSaved to:\n{path}"
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Report Save Error", f"Word report could not be saved:\n\n{exc}"
            )

    def _export_trial_balance_csv(self):
        if not self.trial_balance_rows:
            QMessageBox.information(
                self, "Trial Balance", "There are no account rows available for this report."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trial Balance Report", self._trial_balance_report_filename("csv"),
            "CSV File (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["TRIAL BALANCE WORK SHEET"])
                writer.writerow([
                    "Period",
                    self.trial_start_date.date().toString("MM/dd/yyyy"),
                    "To",
                    self.trial_end_date.date().toString("MM/dd/yyyy"),
                ])
                writer.writerow([])
                writer.writerow([
                    "Account Code", "Account Name",
                    "Opening Debit (PKR)", "Opening Credit (PKR)",
                    "Period Debit (PKR)", "Period Credit (PKR)",
                    "Closing Debit (PKR)", "Closing Credit (PKR)",
                ])
                for row in self.trial_balance_rows:
                    writer.writerow([
                        row[0], row[1], *[float(v) for v in row[2:8]]
                    ])

                totals = self.trial_balance_totals
                writer.writerow([
                    "", "TOTAL",
                    float(totals["opening_debit"]),
                    float(totals["opening_credit"]),
                    float(totals["period_debit"]),
                    float(totals["period_credit"]),
                    float(totals["closing_debit"]),
                    float(totals["closing_credit"]),
                ])

            QMessageBox.information(
                self, "Report Saved", f"Your Trial Balance report has been saved successfully as a CSV file.\n\nSaved to:\n{path}"
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Report Save Error", f"CSV report could not be saved:\n\n{exc}"
            )

    def _set_trial_balance_table(self, rows):
        table = self.trial_balance_table
        table.clearSpans()
        table.clearContents()
        table.setRowCount(len(rows) + 4)

        headers = [
            ["Account Code", "Account Name", "General Ledger", "", "", "", "", ""],
            ["", "", "Account Balance", "", "", "", "", ""],
            ["", "", "Opening Balance", "", "Period Activity", "", "Closing Balance", ""],
            ["", "", "Debit", "Credit", "Debit", "Credit", "Debit", "Credit"]
        ]

        QColor = __import__(
            "PySide6.QtGui", fromlist=["QColor"]
        ).QColor
        QFont = __import__(
            "PySide6.QtGui", fromlist=["QFont"]
        ).QFont

        for row_index, header_row in enumerate(headers):
            for col_index, value in enumerate(header_row):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(
                    QColor("#164b37" if row_index == 0 else "#dce8e0")
                )
                item.setForeground(
                    QColor("white" if row_index == 0 else "#164b37")
                )
                item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                table.setItem(row_index, col_index, item)

        table.setSpan(0, 0, 4, 1)
        table.setSpan(0, 1, 4, 1)
        table.setSpan(0, 2, 1, 6)
        table.setSpan(1, 2, 1, 6)
        table.setSpan(2, 2, 1, 2)
        table.setSpan(2, 4, 1, 2)
        table.setSpan(2, 6, 1, 2)

        total_index = len(rows) + 3
        for row_index, values in enumerate(rows, start=4):
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(
                    "" if value is None else str(value)
                )
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if col_index >= 2:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)

                if row_index == total_index:
                    item.setBackground(QColor("#e7eee9"))
                    item.setFont(QFont("Arial", 9, QFont.Weight.Bold))

                table.setItem(row_index, col_index, item)

        table.setRowHeight(0, 30)
        table.setRowHeight(1, 27)
        table.setRowHeight(2, 27)
        table.setRowHeight(3, 25)
        table.resizeRowsToContents()

    def _make_table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _set_table(self, table, rows):
        table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                item = QTableWidgetItem(
                    "" if value is None else str(value)
                )
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )
                table.setItem(row_index, col_index, item)

        table.resizeRowsToContents()

    def _amount(self, value):
        amount = Decimal(str(value or 0))
        return f"PKR {amount:,.2f}"

    def refresh_all(self):
        if not getattr(self, "has_finance_view", True):
            return
        try:
            self._load_overview()
            self._load_journals()
            self._load_periods()
            self._load_accounts()
            self._load_audit()
            self._load_trial_balance()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Finance Data Error",
                f"Finance data could not be loaded:\n\n{exc}"
            )

    def _load_overview(self):
        db = SessionLocal()

        try:
            totals = db.query(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
                func.count(func.distinct(JournalEntry.id)),
            ).join(
                JournalEntry,
                JournalEntry.id == JournalEntryLine.journal_entry_id
            ).filter(
                JournalEntry.status == "posted"
            ).one()

            self.debit_value.setText(
                self._amount(totals[0])
            )
            self.credit_value.setText(
                self._amount(totals[1])
            )
            self.journal_value.setText(str(totals[2]))

            current = db.query(AccountingPeriod).filter(
                AccountingPeriod.start_date <= date.today(),
                AccountingPeriod.end_date >= date.today()
            ).first()

            if current:
                self.period_value.setText(current.name)
            else:
                self.period_value.setText("Not assigned")

            recent = db.query(AuditLog).filter(
                AuditLog.module.in_([
                    "accounting", "accounting_periods"
                ])
            ).order_by(
                AuditLog.created_at.desc(),
                AuditLog.id.desc()
            ).limit(15).all()

            rows = [
                (
                    item.created_at,
                    item.module,
                    item.action,
                    item.record_id,
                    item.username,
                )
                for item in recent
            ]

            self._set_table(self.recent_table, rows)

        finally:
            db.close()

    def _load_journals(self):
        db = SessionLocal()

        try:
            entries = db.query(JournalEntry).order_by(
                JournalEntry.entry_date.desc(),
                JournalEntry.id.desc()
            ).all()

            rows = []

            for entry in entries:
                totals = db.query(
                    func.coalesce(func.sum(JournalEntryLine.debit), 0),
                    func.coalesce(func.sum(JournalEntryLine.credit), 0),
                ).filter(
                    JournalEntryLine.journal_entry_id == entry.id
                ).one()

                period = db.query(AccountingPeriod).filter_by(
                    id=entry.accounting_period_id
                ).first() if entry.accounting_period_id else None

                rows.append((
                    entry.entry_number,
                    entry.entry_date,
                    entry.description,
                    entry.status,
                    period.name if period else "",
                    self._amount(totals[0]),
                    self._amount(totals[1]),
                    entry.reversal_of_id,
                ))

            self._set_table(self.journal_table, rows)

        finally:
            db.close()

    def _load_periods(self):
        db = SessionLocal()

        try:
            periods = db.query(AccountingPeriod).order_by(
                AccountingPeriod.start_date
            ).all()

            rows = [
                (
                    p.id, p.name, p.start_date,
                    p.end_date, p.status
                )
                for p in periods
            ]

            self._set_table(self.period_table, rows)

        finally:
            db.close()

    def _load_accounts(self):
        db = SessionLocal()

        try:
            accounts = db.query(Account).order_by(
                Account.code
            ).all()

            account_map = {
                account.id: account for account in accounts
            }

            rows = []

            for account in accounts:
                parent = account_map.get(account.parent_id)

                rows.append((
                    account.code,
                    account.name,
                    account.account_type,
                    account.normal_balance,
                    parent.code if parent else "",
                    "Yes" if account.is_active else "No",
                ))

            self._set_table(self.account_table, rows)

        finally:
            db.close()

    def _load_audit(self):
        db = SessionLocal()

        try:
            records = db.query(AuditLog).filter(
                AuditLog.module.in_([
                    "accounting", "accounting_periods"
                ])
            ).order_by(
                AuditLog.created_at.desc(),
                AuditLog.id.desc()
            ).limit(1000).all()

            rows = [
                (
                    record.created_at,
                    record.module,
                    record.action,
                    record.record_type,
                    record.record_id,
                    record.username,
                    record.reason,
                )
                for record in records
            ]

            self._set_table(self.audit_table, rows)

        finally:
            db.close()
