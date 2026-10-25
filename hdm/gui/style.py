"""Modern stylesheet (QSS) and theme system for HDM.

Two complete color palettes (dark / light) are defined as flat token maps and a
single QSS template is rendered against them, so every widget automatically
follows the active theme. Dialogs that paint colors from Python simply call
:func:`get_palette` instead of hardcoding hex values.
"""

from __future__ import annotations

import os
import tempfile
from string import Template
from typing import Dict, Sequence, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication

from hdm.utils.system import get_app_data_folder

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

DARK_PALETTE: Dict[str, str] = {
    # Surfaces (Modern Slate Dark)
    "bg": "#0B0F19",
    "panel": "#111827",
    "panel_alt": "#0E1526",
    "elevated": "#1E293B",
    "card_bg": "#131C2E",
    "card_border": "#1E2B45",
    "border": "#1E293B",
    "border_soft": "#162035",
    "border_strong": "#334155",
    "divider": "#1E293B",
    # Text (WCAG AAA & AA compliant)
    "text": "#F1F5F9",
    "text_strong": "#FFFFFF",
    "text_muted": "#94A3B8",
    "text_faint": "#64748B",
    "text_disabled": "#475569",
    # Accent (Vibrant Electric Blue)
    "accent": "#2563EB",
    "accent_hover": "#3B82F6",
    "accent_pressed": "#1D4ED8",
    "accent_text": "#FFFFFF",
    "accent_soft": "#172554",
    "accent_border": "#1D4ED8",
    # Semantic colors
    "success": "#10B981",
    "success_bg": "#064E3B",
    "success_border": "#059669",
    "info": "#38BDF8",
    "cyan": "#06B6D4",
    "purple": "#A855F7",
    "warning": "#F59E0B",
    "warning_bg": "#78350F",
    "warning_border": "#D97706",
    "danger": "#EF4444",
    "danger_bg": "#7F1D1D",
    "danger_border": "#DC2626",
    "danger_hover": "#DC2626",
    "muted": "#94A3B8",
    # Interaction states
    "hover": "#1A243B",
    "selected": "#1E3A8A",
    "selected_text": "#FFFFFF",
    # Table
    "table_alt": "#0F1626",
    "header_bg": "#111827",
    "header_text": "#94A3B8",
    "header_divider": "#2E3D59",
    # Inputs / buttons
    "input_bg": "#131C2E",
    "input_border": "#273552",
    "input_focus_bg": "#172238",
    "input_readonly_bg": "#0E1526",
    "button_bg": "#172238",
    "button_border": "#273552",
    "button_hover": "#1E2B45",
    "button_pressed": "#111A2C",
    # Scrollbars
    "scroll_bg": "#0B0F19",
    "scroll_handle": "#273552",
    "scroll_handle_hover": "#3D4F75",
    # Window chrome
    "sidebar_bg": "#0E1526",
    "sidebar_hover": "#172238",
    "sidebar_sel_bg": "#172554",
    "sidebar_sel_text": "#60A5FA",
    "sidebar_sel_border": "#3B82F6",
    "toolbar_bg": "#111827",
    "menubar_bg": "#111827",
    "statusbar_bg": "#0E1526",
    # Progress & chunk map
    "progress_from": "#2563EB",
    "progress_to": "#06B6D4",
    "progress_text": "#FFFFFF",
    "progress_bg": "#131C2E",
    "progress_border": "#222F4D",
    "chunk_bg": "#162035",
    "chunk_divider": "#0B0F19",
    "chunk_text": "#FFFFFF",
    "chunk_done_from": "#10B981",
    "chunk_done_to": "#059669",
    "chunk_active_from": "#2563EB",
    "chunk_active_to": "#06B6D4",
    # Misc
    "brand_from": "#3B82F6",
    "brand_to": "#06B6D4",
    "chip_bg": "#172238",
    "chip_text": "#94A3B8",
    "empty_text": "#64748B",
    "group_title": "#38BDF8",
}

LIGHT_PALETTE: Dict[str, str] = {
    # Surfaces
    "bg": "#f4f6fb",
    "panel": "#ffffff",
    "panel_alt": "#f8fafd",
    "elevated": "#ffffff",
    "card_bg": "#ffffff",
    "card_border": "#e6ecf5",
    "border": "#e2e8f0",
    "border_soft": "#eef2f8",
    "border_strong": "#cfd8e6",
    "divider": "#e6ecf5",
    # Text
    "text": "#1e293b",
    "text_strong": "#0f172a",
    "text_muted": "#64748b",
    "text_faint": "#94a3b8",
    "text_disabled": "#b6c0cd",
    # Accent
    "accent": "#2563eb",
    "accent_hover": "#3b82f6",
    "accent_pressed": "#1d4ed8",
    "accent_text": "#ffffff",
    "accent_soft": "#e8f1ff",
    "accent_border": "#bcd7ff",
    # Semantic colors
    "success": "#047857",
    "success_bg": "#e7f8f0",
    "success_border": "#6ee7b7",
    "info": "#2563eb",
    "cyan": "#0284c7",
    "purple": "#7c3aed",
    "warning": "#b45309",
    "warning_bg": "#fff7e6",
    "warning_border": "#fcd34d",
    "danger": "#dc2626",
    "danger_bg": "#fdecec",
    "danger_border": "#fca5a5",
    "danger_hover": "#b91c1c",
    "muted": "#64748b",
    # Interaction states
    "hover": "#f1f5fb",
    "selected": "#e6efff",
    "selected_text": "#0f172a",
    # Table
    "table_alt": "#fafcff",
    "header_bg": "#f1f5fb",
    "header_text": "#64748b",
    "header_divider": "#B8C5D6",
    # Inputs / buttons
    "input_bg": "#ffffff",
    "input_border": "#d8e0ec",
    "input_focus_bg": "#ffffff",
    "input_readonly_bg": "#f3f6fb",
    "button_bg": "#ffffff",
    "button_border": "#d8e0ec",
    "button_hover": "#eef4ff",
    "button_pressed": "#e3ecfb",
    # Scrollbars
    "scroll_bg": "#f1f4fa",
    "scroll_handle": "#cbd5e1",
    "scroll_handle_hover": "#94a3b8",
    # Window chrome
    "sidebar_bg": "#ffffff",
    "sidebar_hover": "#f1f5fb",
    "sidebar_sel_bg": "#e8f1ff",
    "sidebar_sel_text": "#1d4ed8",
    "sidebar_sel_border": "#2563eb",
    "toolbar_bg": "#ffffff",
    "menubar_bg": "#ffffff",
    "statusbar_bg": "#f8fafd",
    # Progress & chunk map
    "progress_from": "#7cb2fb",
    "progress_to": "#4f8ef7",
    "progress_text": "#0f172a",
    "progress_bg": "#eef2f8",
    "progress_border": "#dbe4f0",
    "chunk_bg": "#e2e8f0",
    "chunk_divider": "#ffffff",
    "chunk_text": "#0f172a",
    "chunk_done_from": "#34d399",
    "chunk_done_to": "#10b981",
    "chunk_active_from": "#60a5fa",
    "chunk_active_to": "#3b82f6",
    # Misc
    "brand_from": "#2563eb",
    "brand_to": "#0ea5e9",
    "chip_bg": "#eef4ff",
    "chip_text": "#1d4ed8",
    "empty_text": "#94a3b8",
    "group_title": "#1d4ed8",
}

PALETTES: Dict[str, Dict[str, str]] = {
    "dark": DARK_PALETTE,
    "light": LIGHT_PALETTE,
}

DEFAULT_THEME = "dark"
THEME_PROPERTY = "hdmTheme"


# ---------------------------------------------------------------------------
# QSS template (rendered through string.Template -> $token)
# ---------------------------------------------------------------------------

_QSS_TEMPLATE = """
/* ===================== Global reset & typography ===================== */
QWidget {
    background-color: $bg;
    color: $text;
    font-family: "Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
    selection-background-color: $selected;
    selection-color: $selected_text;
}
QMainWindow, QDialog { background-color: $bg; }
QLabel { background: transparent; }
QToolTip {
    background-color: $elevated;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 9px;
    font-size: 12px;
}

/* ===================== Menu bar ===================== */
QMenuBar {
    background-color: $menubar_bg;
    color: $text_muted;
    border-bottom: 1px solid $divider;
    padding: 4px 10px;
    font-size: 12px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 12px;
    border-radius: 6px;
}
QMenuBar::item:selected {
    background-color: $sidebar_sel_bg;
    color: $accent;
}
QMenuBar::item:pressed { background-color: $accent_soft; }

/* ===================== Dropdown menus ===================== */
QMenu {
    background-color: $elevated;
    color: $text;
    border: 1px solid $border_strong;
    padding: 6px;
    border-radius: 9px;
}
QMenu::item {
    padding: 7px 30px 7px 12px;
    border-radius: 6px;
    font-size: 13px;
}
QMenu::item:selected {
    background-color: $accent;
    color: $accent_text;
}
QMenu::item:disabled { color: $text_faint; }
QMenu::separator {
    height: 1px;
    background-color: $border;
    margin: 5px 6px;
}

/* ===================== Toolbar ===================== */
QToolBar, QToolBar#main_toolbar {
    background-color: $toolbar_bg;
    border: none;
    border-bottom: 1px solid $divider;
    spacing: 6px;
    padding: 5px 12px;
}
QToolBar::separator, QToolBar#main_toolbar::separator {
    width: 1px;
    background-color: $border;
    margin: 4px 6px;
}

QToolButton {
    background-color: $button_bg;
    color: $text;
    border: 1px solid $button_border;
    border-radius: 7px;
    padding: 5px 12px;
    font-weight: 600;
    font-size: 12px;
}
QToolButton:hover {
    background-color: $button_hover;
    border-color: $accent;
    color: $accent;
}
QToolButton:pressed {
    background-color: $button_pressed;
    color: $accent;
}
QToolButton:disabled {
    background-color: $bg;
    color: $text_disabled;
    border-color: $border_soft;
}

/* Primary "Add URL" button */
QToolButton#btn_primary_add {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_pressed);
    color: $accent_text;
    border: 1px solid $accent;
    border-radius: 7px;
    padding: 5px 16px;
    font-weight: 700;
}
QToolButton#btn_primary_add:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent_hover, stop:1 $accent);
    border-color: $accent_hover;
    color: $accent_text;
}
QToolButton#btn_primary_add:pressed {
    background-color: $accent_pressed;
    color: $accent_text;
}

/* Theme switch button (sun / moon) */
QToolButton#theme_toggle {
    background-color: $button_bg;
    color: $text;
    border: 1px solid $button_border;
    border-radius: 7px;
    padding: 0;
    font-size: 15px;
    font-weight: 600;
}
QToolButton#theme_toggle:hover {
    background-color: $accent_soft;
    border-color: $accent_border;
    color: $accent;
}

/* Search field in the toolbar */
QLineEdit#search_input {
    background-color: $input_bg;
    color: $text;
    border: 1px solid $input_border;
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 12px;
}
QLineEdit#search_input:focus {
    border-color: $accent;
    background-color: $input_focus_bg;
}

/* Toolbar expanding spacer (transparent, fixes mismatched color block) */
QWidget#toolbar_spacer {
    background: transparent;
    background-color: transparent;
    border: none;
}

/* ===================== Sidebar ===================== */
QWidget#sidebar_container {
    background-color: $sidebar_bg;
    border-right: 1px solid $divider;
}
QWidget#brand_bar {
    background-color: $sidebar_bg;
    border-bottom: 1px solid $divider;
}
QLabel#brand_title {
    background: transparent;
    color: $text_strong;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 0.6px;
}
QLabel#brand_sub {
    background: transparent;
    color: $text_faint;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.8px;
}
QLabel#sidebar_footer {
    background: transparent;
    color: $text_faint;
    font-size: 10px;
    padding: 10px 14px;
}

QListWidget#sidebar {
    background-color: $sidebar_bg;
    border: none;
    padding: 6px 8px;
    outline: none;
}
QListWidget#sidebar::item {
    padding: 8px 12px;
    border-radius: 7px;
    margin: 1px 2px;
    color: $text_muted;
    font-size: 13px;
    border-left: 3px solid transparent;
}
QListWidget#sidebar::item:hover {
    background-color: $sidebar_hover;
    color: $text;
}
QListWidget#sidebar::item:selected {
    background-color: $sidebar_sel_bg;
    color: $sidebar_sel_text;
    font-weight: 600;
    border-left: 3px solid $sidebar_sel_border;
}
QListWidget#sidebar::item:disabled {
    background: transparent;
    color: $text_faint;
    padding: 12px 12px 4px 12px;
    margin: 0;
    border-left: 3px solid transparent;
    letter-spacing: 0.8px;
}


/* ===================== Content area & page header ===================== */
QWidget#content_area { background-color: $bg; }
QLabel#page_title {
    color: $text_strong;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.2px;
}
QLabel#page_subtitle {
    color: $text_muted;
    font-size: 12px;
}
QLabel#page_badge {
    background-color: $accent_soft;
    color: $accent;
    border: 1px solid $accent_border;
    border-radius: 11px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#empty_state {
    color: $empty_text;
    font-size: 13px;
    background: transparent;
}

/* ===================== Table ===================== */
QFrame#table_card {
    background-color: $card_bg;
    border: 1px solid $card_border;
    border-radius: 8px;
}
QTableWidget#download_table {
    background-color: $card_bg;
    alternate-background-color: $table_alt;
    border: none;
    gridline-color: $border_soft;
    color: $text;
    font-size: 13px;
}
QTableWidget#download_table::item {
    padding: 6px 10px;
    border-bottom: 1px solid $border_soft;
}
QTableWidget#download_table::item:hover { background-color: $hover; }
QTableWidget#download_table::item:selected {
    background-color: $selected;
    color: $selected_text;
}
QHeaderView {
    background-color: $header_bg;
    border: none;
    border-bottom: 1px solid $border;
}
QHeaderView::section {
    background-color: $header_bg;
    color: $header_text;
    padding: 9px 12px;
    border-top: none;
    border-left: none;
    border-right: 1px solid $header_divider;
    border-bottom: 1px solid $border;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.4px;
}
QHeaderView::section:hover {
    color: $accent;
    background-color: $hover;
}
QHeaderView::section:last {
    border-right: none;
}
QTableCornerButton::section {
    background-color: $header_bg;
    border: none;
}


/* ===================== Progress bar ===================== */
QProgressBar {
    background-color: $progress_bg;
    border: 1px solid $progress_border;
    border-radius: 6px;
    text-align: center;
    color: $progress_text;
    font-weight: 700;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $progress_from, stop:1 $progress_to);
    border-radius: 5px;
}

/* ===================== Push buttons ===================== */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_pressed);
    color: $accent_text;
    border: 1px solid $accent;
    border-radius: 7px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent_hover, stop:1 $accent);
}
QPushButton:pressed { background-color: $accent_pressed; }
QPushButton:disabled {
    background: $button_bg;
    color: $text_disabled;
    border-color: $button_border;
}
QPushButton#btn_secondary {
    background: $button_bg;
    color: $text;
    border: 1px solid $button_border;
    border-radius: 7px;
    padding: 7px 16px;
}
QPushButton#btn_secondary:hover {
    background: $button_hover;
    border-color: $accent;
    color: $accent;
}
QPushButton#btn_secondary:pressed { background: $button_pressed; }
QPushButton#btn_danger {
    background: $danger;
    border-color: $danger;
    color: $accent_text;
    border-radius: 7px;
    padding: 7px 16px;
}
QPushButton#btn_danger:hover { background: $danger_hover; border-color: $danger_hover; }

/* ===================== Form inputs ===================== */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: $input_bg;
    color: $text;
    border: 1px solid $input_border;
    border-radius: 7px;
    padding: 7px 11px;
    font-size: 13px;
    selection-background-color: $accent;
    selection-color: $accent_text;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid $accent;
    background-color: $input_focus_bg;
}
QLineEdit:read-only {
    background-color: $input_readonly_bg;
    color: $text_muted;
    border-color: $border;
}
QLineEdit#url_input {
    background-color: $input_readonly_bg;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 9px;
    font-size: 11px;
}
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 20px;
    border: none;
    background: transparent;
}
QSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 7px;
}
QSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 7px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: $button_hover; }
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed { background-color: $button_pressed; }
QSpinBox::up-arrow { image: $spin_up_icon; width: 9px; height: 6px; }
QSpinBox::down-arrow { image: $spin_down_icon; width: 9px; height: 6px; }

QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid $input_border;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}
QComboBox::drop-down:hover { background-color: $button_hover; }
QComboBox::down-arrow { image: $chevron_down_icon; width: 11px; height: 8px; }
QComboBox QAbstractItemView {
    background-color: $elevated;
    color: $text;
    border: 1px solid $border_strong;
    selection-background-color: $accent;
    selection-color: $accent_text;
    padding: 4px;
    outline: none;
}

/* ===================== Checkbox & Radio ===================== */
QCheckBox, QRadioButton {
    spacing: 8px;
    color: $text;
    background: transparent;
    background-color: transparent;
}
QGroupBox QCheckBox, QGroupBox QRadioButton {
    background: transparent;
    background-color: transparent;
}
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid $input_border;
    background-color: $input_bg;
}
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked {
    background-color: $accent;
    border-color: $accent;
    image: $check_icon;
}

/* ===================== Scrollbars ===================== */
QScrollBar:vertical {
    background: $scroll_bg;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: $scroll_handle;
    min-height: 26px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background: $scroll_handle_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QScrollBar:horizontal {
    background: $scroll_bg;
    height: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: $scroll_handle;
    min-width: 26px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover { background: $scroll_handle_hover; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ===================== Splitter ===================== */
QSplitter::handle { background-color: $divider; width: 1px; }
QSplitter::handle:hover { background-color: $accent; }

/* ===================== Status bar ===================== */
QStatusBar {
    background-color: $statusbar_bg;
    border-top: 1px solid $divider;
    color: $text_muted;
    font-size: 12px;
    padding: 2px 4px;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { padding: 2px 8px; }
QLabel#status_server { color: $success; font-weight: 600; }
QLabel#status_speed { color: $cyan; font-weight: 700; font-size: 12px; }
QLabel#status_tasks { color: $text_muted; font-weight: 500; }

/* ===================== Dialogs, cards & sections ===================== */
QGroupBox {
    border: 1px solid $card_border;
    border-radius: 8px;
    margin-top: 8px;
    padding-top: 36px;
    padding-left: 14px;
    padding-right: 14px;
    padding-bottom: 14px;
    font-weight: 700;
    color: $group_title;
    background-color: $card_bg;
}
QGroupBox::title {
    subcontrol-origin: content;
    subcontrol-position: top left;
    left: 2px;
    top: -26px;
    font-weight: 700;
    font-size: 13px;
    color: $group_title;
    background: transparent;
    background-color: transparent;
}
QFrame#info_card, QFrame#form_card {
    background-color: $card_bg;
    border: 1px solid $card_border;
    border-radius: 8px;
}
QLabel#section_label {
    color: $accent;
    font-weight: 700;
    font-size: 12px;
}
QLabel#dialog_value { color: $text_strong; font-weight: 600; }
QLabel#dialog_value_accent { color: $accent; font-weight: 700; font-size: 13px; }
QLabel#dialog_value_info { color: $cyan; font-weight: 700; }
QLabel#legend_done { color: $success; font-weight: 700; font-size: 11px; }
QLabel#legend_active { color: $info; font-weight: 700; font-size: 11px; }
QLabel#legend_pending { color: $empty_text; font-weight: 700; font-size: 11px; }
QLabel#legend_hint { color: $text_muted; font-size: 11px; font-style: italic; }
QLabel#settings_hint {
    color: $text_faint;
    font-size: 11px;
    padding-top: 2px;
}
QMessageBox { background-color: $bg; }
QMessageBox QLabel { color: $text; }
QSizeGrip { background: transparent; }
"""


# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------


def normalize_theme(theme: str | None) -> str:
    """Return a valid theme key ("dark" or "light")."""
    key = (theme or DEFAULT_THEME).strip().lower()
    return key if key in PALETTES else DEFAULT_THEME


def current_theme() -> str:
    """Theme currently applied to the running QApplication (defaults to dark)."""
    app = QApplication.instance()
    if app is None:
        return DEFAULT_THEME
    return normalize_theme(app.property(THEME_PROPERTY))


def get_palette(theme: str | None = None) -> Dict[str, str]:
    """Return the color token map for *theme* (or the active theme)."""
    return PALETTES[normalize_theme(theme or current_theme())]


# ---------------------------------------------------------------------------
# QSS glyphs (checkbox tick, combo & spin-box chevrons)
#
# Qt stylesheets can only embed images through file paths, so the few glyphs QSS
# cannot express natively (a check mark and small chevrons) are rasterised once
# into the HDM data folder and injected into the template as ``$check_icon``
# tokens. When no writable folder is available the tokens degrade to ``none`` so
# the widgets still render (just without the glyph).
# ---------------------------------------------------------------------------

GlyphPoints = Sequence[Tuple[float, float]]

_GLYPH_SPECS: Dict[str, Dict[str, object]] = {
    "check": {
        "size": (17, 17),
        "points": ((4.2, 8.9), (7.3, 12.0), (13.4, 4.9)),
        "stroke": 2.4,
    },
    "chevron_down": {
        "size": (11, 8),
        "points": ((1.8, 2.6), (5.5, 6.2), (9.2, 2.6)),
        "stroke": 1.8,
    },
    "chevron_up": {
        "size": (11, 8),
        "points": ((1.8, 6.2), (5.5, 2.6), (9.2, 6.2)),
        "stroke": 1.8,
    },
    "spin_down": {
        "size": (9, 6),
        "points": ((1.6, 1.8), (4.5, 4.6), (7.4, 1.8)),
        "stroke": 1.5,
    },
    "spin_up": {
        "size": (9, 6),
        "points": ((1.6, 4.6), (4.5, 1.8), (7.4, 4.6)),
        "stroke": 1.5,
    },
}

# template token -> (glyph name, palette token providing the stroke color)
_GLYPH_TOKENS: Tuple[Tuple[str, str, str], ...] = (
    ("check_icon", "check", "accent_text"),
    ("chevron_down_icon", "chevron_down", "text_muted"),
    ("chevron_up_icon", "chevron_up", "text_muted"),
    ("spin_down_icon", "spin_down", "text_muted"),
    ("spin_up_icon", "spin_up", "text_muted"),
)

_NO_GLYPHS: Dict[str, str] = {token: "none" for token, _, _ in _GLYPH_TOKENS}


def _glyph_folder() -> str | None:
    """Return a writable folder that can host the rasterised glyphs."""
    candidates = []
    try:
        candidates.append(os.path.join(get_app_data_folder(), "glyphs"))
    except OSError:
        pass
    candidates.append(os.path.join(tempfile.gettempdir(), "hdm-glyphs"))
    for folder in candidates:
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            continue
        return folder
    return None


def _glyph(name: str, color: str) -> str | None:
    """Rasterise the *name* glyph in *color* once and return its file path."""
    spec = _GLYPH_SPECS[name]
    folder = _glyph_folder()
    if folder is None:
        return None

    width, height = spec["size"]  # type: ignore[misc]
    points: GlyphPoints = spec["points"]  # type: ignore[assignment]
    stroke: float = spec["stroke"]  # type: ignore[assignment]
    path = os.path.join(folder, f"{name}_{color.lstrip('#')}.png")
    if not os.path.exists(path):
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor(color), stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline([QPointF(x, y) for x, y in points])
        finally:
            painter.end()
        if not image.save(path, "PNG"):
            return None
    return path.replace(os.sep, "/")


def _glyph_tokens(colors: Dict[str, str]) -> Dict[str, str]:
    """Return the QSS tokens pointing at the glyphs rasterised for *colors*."""
    tokens = dict(_NO_GLYPHS)
    try:
        for token, name, color_token in _GLYPH_TOKENS:
            path = _glyph(name, colors[color_token])
            tokens[token] = f'url("{path}")' if path else "none"
    except Exception:  # pragma: no cover - glyph rendering is purely cosmetic
        return dict(_NO_GLYPHS)
    return tokens


def build_stylesheet(theme: str = DEFAULT_THEME) -> str:
    """Render the QSS template with the tokens of *theme*."""
    tokens = dict(PALETTES[normalize_theme(theme)])
    tokens.update(_glyph_tokens(tokens))
    return Template(_QSS_TEMPLATE).substitute(tokens)


def build_palette(theme: str = DEFAULT_THEME) -> QPalette:
    """Build a QPalette matching *theme* so native widgets stay consistent."""
    colors = PALETTES[normalize_theme(theme)]
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(colors["bg"]))
    pal.setColor(QPalette.WindowText, QColor(colors["text"]))
    pal.setColor(QPalette.Base, QColor(colors["input_bg"]))
    pal.setColor(QPalette.AlternateBase, QColor(colors["table_alt"]))
    pal.setColor(QPalette.Text, QColor(colors["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(colors["text_faint"]))
    pal.setColor(QPalette.Button, QColor(colors["button_bg"]))
    pal.setColor(QPalette.ButtonText, QColor(colors["text"]))
    pal.setColor(QPalette.BrightText, QColor(colors["danger"]))
    pal.setColor(QPalette.Highlight, QColor(colors["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(colors["accent_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(colors["elevated"]))
    pal.setColor(QPalette.ToolTipText, QColor(colors["text"]))
    pal.setColor(QPalette.Mid, QColor(colors["border"]))
    pal.setColor(QPalette.Midlight, QColor(colors["border_soft"]))
    pal.setColor(QPalette.Dark, QColor(colors["border_strong"]))
    pal.setColor(QPalette.Light, QColor(colors["panel"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["text_disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(colors["text_disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["text_disabled"]))
    return pal


def apply_theme(app: QApplication | None, theme: str) -> str:
    """Apply *theme* (no-op when there is no QApplication). Returns the theme key."""
    key = normalize_theme(theme)
    if app is not None:
        app.setProperty(THEME_PROPERTY, key)
        app.setPalette(build_palette(key))
        app.setStyleSheet(build_stylesheet(key))
    return key


# Static exports kept for backwards compatibility
DARK_THEME = build_stylesheet("dark")
LIGHT_THEME = build_stylesheet("light")


