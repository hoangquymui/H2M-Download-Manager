---
name: H2M Download Manager (HDM)
description: High-performance multi-connection download manager with zero-copy direct NTFS writing and browser streaming sniffer.
colors:
  primary: "#2563EB"
  primary-hover: "#3B82F6"
  primary-pressed: "#1D4ED8"
  accent-cyan: "#06B6D4"
  accent-purple: "#A855F7"
  success: "#10B981"
  success-bg: "#064E3B"
  warning: "#F59E0B"
  warning-bg: "#78350F"
  danger: "#EF4444"
  danger-bg: "#7F1D1D"
  neutral-bg: "#0B0F19"
  neutral-panel: "#111827"
  neutral-card: "#131C2E"
  neutral-elevated: "#1E293B"
  neutral-border: "#1E2B45"
  neutral-border-soft: "#162035"
  text-strong: "#FFFFFF"
  text-body: "#F1F5F9"
  text-muted: "#94A3B8"
  text-faint: "#64748B"
  text-disabled: "#475569"
typography:
  display:
    fontFamily: "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "18px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.2px"
  headline:
    fontFamily: "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.6px"
  title:
    fontFamily: "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.4px"
rounded:
  xs: "4px"
  sm: "6px"
  md: "7px"
  lg: "8px"
  xl: "11px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  xxl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.text-strong}"
    rounded: "{rounded.md}"
    padding: "7px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.text-strong}"
    rounded: "{rounded.md}"
    padding: "7px 16px"
  button-secondary:
    backgroundColor: "{colors.neutral-panel}"
    textColor: "{colors.text-body}"
    rounded: "{rounded.md}"
    padding: "7px 16px"
  input-field:
    backgroundColor: "{colors.neutral-card}"
    textColor: "{colors.text-body}"
    rounded: "{rounded.md}"
    padding: "7px 11px"
  card-container:
    backgroundColor: "{colors.neutral-card}"
    textColor: "{colors.text-body}"
    rounded: "{rounded.lg}"
    padding: "14px 14px"
---

# Design System: H2M Download Manager

## Overview

**Creative North Star: "The Precision Turbine"**

The visual world of H2M Download Manager (HDM) is engineered around the metaphor of a high-efficiency precision turbine: fast, silent, perfectly balanced, and purpose-built for sustained high-throughput data transfer. It rejects the bloated, banner-strewn, skeuomorphic legacy of Windows 2000s download managers (IDM, FlashGet) in favor of a clean, dark-slate instrument aesthetic where every pixel directly serves operational speed and readability.

The atmosphere is composed, technical, and restrained. Surfaces are deep slate tones (`#0B0F19` to `#131C2E`) with subtle ghost borders (`#1E2B45`). Visual priority belongs exclusively to live data: connection status, real-time segment distribution in the Dynamic Chunk Map, and transfer velocity. Accent highlights use Electric Cobalt Blue (`#2563EB`) and Speed Cyan (`#06B6D4`), ensuring users can scan active tasks at a glance without visual fatigue.

**Key Characteristics:**
- **Zero Distraction Slate**: Dark Slate background with high-contrast text conforming to WCAG AA/AAA.
- **Tonal Layering over Drop Shadows**: Surfaces are flat at rest; spatial hierarchy is achieved through controlled tone stepping.
- **Micro-Engineered Feedback**: Vector icons, dynamic progress bars, and high-visibility segment blocks.
- **Complete Symmetry across Themes**: Both Dark and Light modes share identical layout metrics, typography, and contrast rules.

## Colors

The palette balances deep midnight slate foundations with high-intensity signal accents that symbolize network activity and stream progress.

### Primary
- **Electric Cobalt Blue** (`#2563EB`): The primary brand and action color. Applied to primary call-to-actions ("Thêm URL", "Bắt đầu tải"), active tab states, and download progress gradients.
- **Cobalt Hover** (`#3B82F6`): Interactive hover state for primary buttons and selection indicators.
- **Cobalt Pressed** (`#1D4ED8`): Active/pressed state providing tactile mechanical feedback.

### Secondary
- **Speed Cyan** (`#06B6D4`): Applied to active download speed counters, chunk stream animations, and gradient transitions (`#2563EB` → `#06B6D4`).
- **Queued Purple** (`#A855F7`): Reserved for queued tasks, secondary badges, and auto-quality tags.

### Semantic
- **Emerald Done** (`#10B981`): Completed downloads, multi-thread range verification (`Range: Có`), and extension connection badge. Background: `#064E3B`, Border: `#059669`.
- **Amber Processing** (`#F59E0B`): Post-processing state (FFmpeg audio/video muxing), paused tasks, and disk warnings. Background: `#78350F`, Border: `#D97706`.
- **Ruby Error** (`#EF4444`): Connection timeouts, failed chunks, and irreversible deletions. Background: `#7F1D1D`, Border: `#DC2626`.

### Neutral
- **Midnight Slate Void** (`#0B0F19`): Window background and deepest foundation layer.
- **Deep Slate Panel** (`#111827`): Sidebar background, toolbar header, and menubar surface.
- **Layered Slate Card** (`#131C2E`): Table card container, input background, and form surfaces.
- **Elevated Slate** (`#1E293B`): Context menus, tooltip cards, and modal dialog surfaces.
- **Ghost Border** (`#1E2B45`): 1px structural boundary between cards, headers, and form inputs.
- **Text Strong** (`#FFFFFF`): Section headings, active table items, and button text.
- **Text Body** (`#F1F5F9`): Standard table cell content and form input values.
- **Text Muted** (`#94A3B8`): Column headers, ETA indicators, and inactive sidebar labels.
- **Text Faint** (`#64748B`): Empty state indicators, subtitles, and secondary hints.

### Named Rules
**The One Voice Rule.** The primary Cobalt accent (`#2563EB`) is strictly reserved for primary actions, active chunk streams, and selected sidebar items. It never covers more than 10% of any viewport.
**The Ghost Border Rule.** All internal surface divisions rely on a crisp 1px border (`#1E2B45` in dark mode, `#E2E8F0` in light mode) rather than heavy shadows or high-contrast drop dividers.

## Typography

**Display Font:** `Segoe UI` (with fallback to `Inter`, `-apple-system`, `sans-serif`)
**Body Font:** `Segoe UI` (with fallback to `Inter`, `-apple-system`, `sans-serif`)
**Label/Numeric Font:** `Segoe UI` (with tabular numerals where supported)

**Character:** Clean, highly legible system typography tuned for high-density Windows UI, prioritizing fast numerical scanning and clear label hierarchy.

### Hierarchy
- **Display** (800 / Bold, 18px, line-height 1.2, letter-spacing 0.2px): Main page title ("Tất cả lượt tải", "Tệp nén").
- **Headline** (700 / Bold, 15px, line-height 1.3, letter-spacing 0.6px): Brand title ("H2M"), modal dialog titles.
- **Title** (600 / Semi-Bold, 13px, line-height 1.4): Table text, sidebar items, button labels.
- **Body** (400 / Regular, 13px, line-height 1.5): Standard form inputs, file paths, dialog descriptions.
- **Label** (700 / Bold, 11px, line-height 1.2, letter-spacing 0.4px): Table column headers, progress percentages, badges.

### Named Rules
**The Numeric Clarity Rule.** Download speeds (`MB/s`, `KB/s`), ETAs, file sizes, and chunk byte ranges are displayed with bold weight and color-coded status, ensuring instant comprehension during active transfers.

## Layout

The desktop interface uses an asymmetric Master-Detail structure optimized for 1240×760 resolution with a minimum bounding constraint of 1000×600:

- **Sidebar (Master Navigation)**: Fixed 236px width, containing brand lockup (32px icon + title), status filters ("Đang tải", "Đã hoàn thành"), category filters, and version footer.
- **Toolbar**: 42px height, holding action buttons ("Thêm URL", "Tiếp tục", "Tạm dừng", "Xóa", "Xoá nhiều", "Thư mục", "Cài đặt"), separated by a transparent expanding spacer that pushes the search box and dark/light toggle to the right edge.
- **Content Area**: Flexible card container with 18px horizontal and 14px vertical padding. Holds the dynamic page header, active task count pill, and the primary downloads table.
- **Table Grid**: 9-column interactive table with standardized section widths:
  - Checkbox (42px) | Tên tệp (260px) | Danh mục (112px) | Dung lượng (100px) | Tiến độ (190px) | Tốc độ (104px) | Còn lại (108px) | Trạng thái (106px) | Ngày thêm (126px).
- **Batch Action Bar**: Slides down above the table when batch delete mode is activated, housing "Chọn tất cả", item count label, and confirm buttons.

## Elevation & Depth

HDM employs a **pure tonal layering model** at rest. Surfaces do not use heavy diffuse shadows to simulate physical elevation; instead, depth is conveyed through calibrated lightness steps from the background to the interactive foreground:

- **Level 0 (Canvas Base)**: `#0B0F19` — the deepest window background.
- **Level 1 (Structural Panels)**: `#111827` — sidebar, toolbar, and menubar.
- **Level 2 (Containers & Cards)**: `#131C2E` — downloads table card, modal content cards.
- **Level 3 (Interactive Controls)**: `#172238` — buttons, inputs, dropdown menus.
- **Level 4 (Floating Overlays)**: `#1E293B` with `box-shadow: 0 12px 36px rgba(0, 0, 0, 0.65)` — context menus, extension quality dropdown, and IDM-style confirmation modals.

### Named Rules
**The Flat-At-Rest Rule.** Surfaces are completely flat at rest. Drop shadows appear only as ambient halos on floating menus, browser extension buttons, and modal dialogs.

## Shapes

- **Base Radius (`7px`)**: Applied consistently to primary buttons, secondary buttons, tool buttons, text inputs, combo boxes, and spin boxes.
- **Card Radius (`8px`)**: Applied to the main table container card, settings group boxes, and batch action bars.
- **Menu Radius (`9px`–`12px`)**: Applied to context menus, dropdown quality menus, and floating tooltips.
- **Pill Radius (`11px`–`full`)**: Applied to status count badges ("● 1 đang tải"), extension connection pills, and quality chips.
- **Circular (`50%`)**: Applied exclusively to the 28px browser extension download icon button and dismiss badge.

## Components

### Primary Button ("Thêm URL", "Bắt đầu tải")
- **Shape**: Rounded rectangle (7px radius).
- **Background**: Horizontal gradient `qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #1D4ED8)`.
- **Text**: Bold white (`#FFFFFF`), 13px, 7px vertical and 16px horizontal padding.
- **States**: Hover shifts gradient to `#3B82F6` → `#2563EB`; Pressed collapses to `#1D4ED8`.

### Secondary Button ("Tiếp tục", "Tạm dừng", "Hủy bỏ")
- **Shape**: Rounded rectangle (7px radius).
- **Background**: `#172238` with 1px border (`#273552`).
- **Text**: Semi-bold `#F1F5F9`, 13px.
- **States**: Hover changes border to `#2563EB` and text to `#2563EB`.

### Downloads Table & Progress Bar
- **Row Height**: 46px fixed row section with subtle alternating background (`#131C2E` / `#0F1626`).
- **Progress Bar**: 18px height, 6px radius, background `#131C2E`, border `#222F4D`. Progress fill uses a vibrant two-stop gradient (`#2563EB` → `#06B6D4`).
- **Format**: Numerical progress format `45.2%` centered in white text.

### Dynamic Chunk Map Widget (Signature Component)
- **Concept**: Visualizes the exact byte-range distribution across all 1 to 32 parallel worker threads.
- **Height**: 28px high-density progress band with 1px dark separators (`#0B0F19`) between segments.
- **Colors**: Completed chunks render in Emerald (`#10B981` → `#059669`); active downloading chunks render in Cobalt-to-Cyan (`#2563EB` → `#06B6D4`); pending segments render in muted slate (`#162035`).

### Form Inputs & Spin Boxes
- **Style**: Dark slate background (`#131C2E`), 1px border (`#273552`), 7px radius, padding `7px 11px`.
- **Focus**: Border turns to `#2563EB` with background brightening to `#172238`.
- **Spin Controls**: Integrated up/down arrow buttons with hover states.

### Browser Extension Floating Button & Quality Menu
- **Floating Button**: 28px circular button with backdrop blur (10px), dark slate background `rgba(15, 23, 42, 0.94)`, 1px border `rgba(255, 255, 255, 0.22)`, and glowing Cobalt download icon (`#38BDF8`).
- **Dismiss Badge**: 13px circular button positioned at `top: -4px; right: -4px` with red hover state.
- **Quality Menu**: 260px width floating card positioned strictly outside the video player container, displaying MP4 resolution options (1080p, 720p, 480p, 360p, Auto) and MP3 audio bitrates (320k, 192k, 128k).

## Do's and Don'ts

### Do:
- **Do** maintain identical layouts and component dimensions when switching between Dark and Light mode.
- **Do** keep the browser extension download button strictly outside the video viewing container on every web surface.
- **Do** format all transfer speeds and data sizes with standardized units (`KB/s`, `MB/s`, `GB`) and bold typography.
- **Do** use the 7px border radius for all actionable buttons, inputs, and selection tabs.
- **Do** use the two-stop gradient (`#2563EB` to `#06B6D4`) for active download bars and chunk segments.

### Don't:
- **Don't** use skeuomorphic 3D bevels, glossy glass gradients, or Windows XP-era icon styling.
- **Don't** insert promotional banners, notification ads, or extraneous visual widgets into dialogs.
- **Don't** use heavy drop shadows on static desktop cards or table headers; rely on tonal slate layering.
- **Don't** position the extension download button inside the video player frame where it could obstruct subtitles or media controls.
- **Don't** hardcode hex colors in Python GUI widgets; always query `get_palette()` from `style.py`.
