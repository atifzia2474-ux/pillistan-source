import re
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

THEMES = {
    "Emerald Green": {
        "background": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface_alt": "#F0F7F3",
        "primary": "#087A50",
        "primary_hover": "#066640",
        "accent": "#159B68",
        "text": "#17211C",
        "muted": "#52645A",
        "border": "#D5E3DA",
        "grid": "#E5EDE8",
        "selection": "#D4F0E0",
        "notice_bg": "#E5F4EB",
        "notice_text": "#145A39",
    },
    "Ruby Red": {
        "background": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface_alt": "#FFF1F1",
        "primary": "#B42335",
        "primary_hover": "#921B2A",
        "accent": "#D33B4D",
        "text": "#211719",
        "muted": "#685357",
        "border": "#EAD5D8",
        "grid": "#F0E3E5",
        "selection": "#F9DDE1",
        "notice_bg": "#FCEAEC",
        "notice_text": "#8B1E2D",
    },
}

DEFAULT_THEME = "Emerald Green"

# Maps the older colours used by individual modules to theme colours.
LEGACY_COLORS = {
    # Existing green and light styles
    "#164b37": "primary",
    "#28664d": "primary_hover",
    "#21664b": "primary_hover",
    "#f4f7f5": "background",
    "#24352c": "text",
    "#dce5df": "border",
    "#e7eee9": "surface_alt",
    "#edf1ee": "grid",
    "#dcebe1": "selection",
    "#eaf0ec": "surface_alt",
    "#718078": "muted",
    "#385b48": "notice_text",
    "#d5e9dc": "notice_text",
    "#e1e9e3": "border",
    "#d5ded8": "border",
    "#e5ebe7": "grid",
    "#dce8e0": "selection",
    "#aabbb0": "border",

    # Older navy inventory and purchase styles
    "#101b2a": "background",
    "#101827": "background",
    "#182536": "surface",
    "#223449": "surface_alt",
    "#172235": "surface",
    "#172538": "surface",
    "#1c2b3d": "surface",
    "#1e293b": "surface",
    "#20344a": "surface_alt",
    "#263449": "surface_alt",
    "#334155": "border",
    "#344256": "border",
    "#34465c": "border",
    "#475569": "border",
    "#293b50": "grid",
    "#e8f0f7": "text",
    "#e5e7eb": "text",
    "#d1d5db": "muted",
    "#9aafc3": "muted",
    "#94a3b8": "muted",
    "#b9d4e8": "text",

    # Older teal/green styles
    "#087f5b": "primary",
    "#047857": "primary",
    "#065f46": "primary",
    "#099268": "primary_hover",
    "#059669": "accent",
    "#10b981": "accent",
    "#34d399": "accent",

    # Other light styles
    "#fbeaea": "notice_bg",
}

def settings():
    return QSettings("ZAO Enterprises", "Pillistan")

def current_theme():
    selected = settings().value("appearance/color_theme", DEFAULT_THEME)
    return selected if selected in THEMES else DEFAULT_THEME

def save_theme(name):
    if name not in THEMES:
        raise ValueError(f"Unknown Pillistan theme: {name}")
    settings().setValue("appearance/color_theme", name)
    settings().sync()

def application_stylesheet(name):
    c = THEMES[name]
    return f"""
        QWidget {{
            background-color: {c['background']};
            color: {c['text']};
            font-family: Segoe UI;
            font-size: 13px;
        }}
        QLabel {{
            color: {c['text']};
        }}
        QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox,
        QTextEdit, QPlainTextEdit {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 5px;
            padding: 6px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['surface']};
            color: {c['text']};
            selection-background-color: {c['selection']};
            selection-color: {c['text']};
        }}
        QTableWidget, QTableView, QTreeWidget, QListWidget {{
            background-color: {c['surface']};
            color: {c['text']};
            alternate-background-color: {c['surface_alt']};
            gridline-color: {c['grid']};
            selection-background-color: {c['selection']};
            selection-color: {c['text']};
            border: 1px solid {c['border']};
        }}
        QHeaderView::section {{
            background-color: {c['surface_alt']};
            color: {c['text']};
            padding: 8px;
            border: none;
            font-weight: bold;
        }}
        QTabWidget::pane {{
            background-color: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 6px;
        }}
        QTabBar::tab {{
            background-color: {c['surface_alt']};
            color: {c['text']};
            padding: 10px 18px;
            margin-right: 3px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background-color: {c['primary']};
            color: white;
        }}
        QPushButton {{
            background-color: {c['primary']};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {c['primary_hover']};
        }}
        QMenu {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
        }}
        QMenu::item:selected {{
            background-color: {c['selection']};
            color: {c['text']};
        }}
        QToolTip {{
            background-color: {c['surface_alt']};
            color: {c['text']};
            border: 1px solid {c['border']};
        }}
    """

def _recolor_stylesheet(stylesheet, colors):
    """Recolour old module styles while preserving white text on accent buttons."""
    if not stylesheet:
        return stylesheet

    replacements = {
        old: colors[key]
        for old, key in LEGACY_COLORS.items()
    }

    def replace_block(match):
        selector = match.group(1)
        declarations = match.group(2)

        for old, new in replacements.items():
            declarations = re.sub(
                re.escape(old),
                new,
                declarations,
                flags=re.IGNORECASE
            )

        # White text on old dark input/table surfaces would become invisible
        # after those surfaces turn white. Keep white on buttons and headers.
        keep_white = any(token in selector for token in (
            "QPushButton", "QHeaderView::section", "QTabBar::tab:selected"
        ))

        if selector.strip() and not keep_white:
            declarations = re.sub(
                r"(?i)(?<![-\w])(color\s*:\s*)white(\s*;)",
                lambda m: m.group(1) + colors["text"] + m.group(2),
                declarations
            )
            declarations = re.sub(
                r"(?i)(?<![-\w])(color\s*:\s*)#ffffff(\s*;)",
                lambda m: m.group(1) + colors["text"] + m.group(2),
                declarations
            )

        return selector + "{" + declarations + "}"

    # Process normal QSS selector blocks.
    result = re.sub(r"([^{}]+)\{([^{}]*)\}", replace_block, stylesheet)

    # Also recolour simple inline declarations without selector blocks.
    if "{" not in stylesheet:
        for old, new in replacements.items():
            result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE)

    return result

def apply_theme(app, root=None, name=None):
    selected = name or current_theme()
    if selected not in THEMES:
        selected = DEFAULT_THEME

    colors = THEMES[selected]
    app.setStyleSheet(application_stylesheet(selected))

    # Include all open windows and the supplied root.
    windows = list(app.topLevelWidgets())
    if root is not None and root not in windows:
        windows.append(root)

    visited = set()
    for window in windows:
        widgets = [window] + window.findChildren(QWidget)

        for widget in widgets:
            identity = id(widget)
            if identity in visited:
                continue
            visited.add(identity)

            current = widget.styleSheet()
            original = widget.property("_pillistan_original_stylesheet")
            last_applied = widget.property("_pillistan_applied_stylesheet")

            # Keep the true original stylesheet. If a module changes its own
            # stylesheet later, capture that new version before recolouring.
            if original is None or (
                last_applied is not None and current != last_applied
            ):
                original = current
                widget.setProperty(
                    "_pillistan_original_stylesheet", original
                )

            updated = _recolor_stylesheet(original or "", colors)

            if current != updated:
                widget.setStyleSheet(updated)

            widget.setProperty(
                "_pillistan_applied_stylesheet", updated
            )

        window.update()

    app.setProperty("pillistan_theme", selected)
    app.setProperty("pillistan_theme_colors", colors)
    app.processEvents()
    return selected
