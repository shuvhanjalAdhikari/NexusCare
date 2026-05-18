# NexusCare Design System
## Complete Visual & Interaction Specification — 100% Coverage
**Version 2.0 | 53 Sections | Hospital Management SaaS Platform**

---

# 1. Color System

Every color in NexusCare is intentional and token-based. No hard-coded hex values are permitted anywhere in the codebase. All colors are applied via CSS custom properties so dark mode can be added with zero component rewrites.

## 1.1 Primary Blue Scale — Brand, Actions, Links

| Token | Hex | Usage |
|---|---|---|
| color-primary-50 | `#EFF6FF` | Hover backgrounds, tinted page surfaces |
| color-primary-100 | `#DBEAFE` | Active backgrounds, info callout fills |
| color-primary-200 | `#BFDBFE` | Borders on primary-tinted surfaces |
| color-primary-300 | `#93C5FD` | Disabled primary element color |
| color-primary-400 | `#60A5FA` | Secondary icons, decorative accents |
| color-primary-500 | `#3B82F6` | Button hover state (from primary-600) |
| color-primary-600 | `#2563EB` | **DEFAULT** — primary buttons, links, focus rings |
| color-primary-700 | `#1D4ED8` | Active/pressed primary button, sidebar active bg |
| color-primary-800 | `#1E40AF` | Dark emphasis text on light surfaces |
| color-primary-900 | `#1E3A8A` | Page-level headings, dark backgrounds |
| color-primary-950 | `#172554` | Deepest brand dark, hero sections |

## 1.2 Teal Accent Scale — AI Features, Charts, Special Indicators

| Token | Hex | Usage |
|---|---|---|
| color-accent-50 | `#F0FDFA` | AI feature section background |
| color-accent-100 | `#CCFBF1` | AI callout surface, chart fill areas |
| color-accent-200 | `#99F6E4` | Chart fill, accent borders |
| color-accent-300 | `#5EEAD4` | Secondary chart lines |
| color-accent-400 | `#2DD4BF` | Active chart data points |
| color-accent-500 | `#14B8A6` | **DEFAULT** — AI badges, chart primary color |
| color-accent-600 | `#0D9488` | AI hover states, chart emphasis |
| color-accent-700 | `#0F766E` | AI active/pressed states |
| color-accent-800 | `#115E59` | AI dark emphasis text |
| color-accent-900 | `#134E4A` | AI deepest shade — use sparingly |

## 1.3 Neutral Gray Scale — Structure, Typography, Borders

| Token | Hex | Usage |
|---|---|---|
| color-neutral-50 | `#F8FAFC` | Page/app background |
| color-neutral-100 | `#F1F5F9` | Table row alternate, input backgrounds |
| color-neutral-200 | `#E2E8F0` | Default borders, dividers |
| color-neutral-300 | `#CBD5E1` | Disabled borders, muted icons |
| color-neutral-400 | `#94A3B8` | Placeholder text, decorative icons |
| color-neutral-500 | `#64748B` | Text secondary, meta labels |
| color-neutral-600 | `#475569` | Body text secondary |
| color-neutral-700 | `#334155` | Body text primary |
| color-neutral-800 | `#1E293B` | Headings, high-emphasis text |
| color-neutral-900 | `#0F172A` | Sidebar background, deepest text |
| color-neutral-950 | `#020617` | True black — use only for print |

## 1.4 Semantic Scales

### 1.4.1 Success — Green

| Token | Hex | Usage |
|---|---|---|
| color-success-50 | `#F0FDF4` | Success toast background |
| color-success-100 | `#DCFCE7` | Success tag background |
| color-success-200 | `#BBF7D0` | Success border |
| color-success-500 | `#22C55E` | Success icon fill |
| color-success-600 | `#16A34A` | **DEFAULT** — success badges, completed status |
| color-success-700 | `#15803D` | Success hover |
| color-success-900 | `#14532D` | Success text on light bg |

### 1.4.2 Warning — Amber

| Token | Hex | Usage |
|---|---|---|
| color-warning-50 | `#FFFBEB` | Warning toast background |
| color-warning-100 | `#FEF3C7` | Warning tag background |
| color-warning-200 | `#FDE68A` | Warning border |
| color-warning-500 | `#F59E0B` | Warning icon fill |
| color-warning-600 | `#D97706` | **DEFAULT** — warning badges, pending status |
| color-warning-700 | `#B45309` | Warning hover |
| color-warning-900 | `#78350F` | Warning text on light bg |

### 1.4.3 Error — Red

| Token | Hex | Usage |
|---|---|---|
| color-error-50 | `#FEF2F2` | Error toast background |
| color-error-100 | `#FEE2E2` | Error tag background |
| color-error-200 | `#FECACA` | Error border |
| color-error-500 | `#EF4444` | Error icon fill |
| color-error-600 | `#DC2626` | **DEFAULT** — error badges, danger buttons |
| color-error-700 | `#B91C1C` | Danger hover |
| color-error-900 | `#7F1D1D` | Error text on light bg |

### 1.4.4 Info — Blue

| Token | Hex | Usage |
|---|---|---|
| color-info-50 | `#EFF6FF` | Info toast bg |
| color-info-100 | `#DBEAFE` | Info badge bg |
| color-info-600 | `#2563EB` | **DEFAULT** — info icons, borders |
| color-info-900 | `#1E3A8A` | Info text on light bg |

## 1.5 Surface & Background Tokens

| Token | Hex | Usage |
|---|---|---|
| color-bg-page | `#F8FAFC` | Main app/page background |
| color-bg-surface | `#FFFFFF` | Cards, panels, modals — primary white surface |
| color-bg-elevated | `#FFFFFF` | Dropdowns, tooltips — shadow distinguishes level |
| color-bg-sidebar | `#0F172A` | Fixed left sidebar (neutral-900) |
| color-bg-sidebar-hover | `#1E293B` | Sidebar nav item hover state |
| color-bg-sidebar-active | `#1D4ED8` | Sidebar active nav item (primary-700) |
| color-bg-overlay | `#00000080` | Modal backdrop — 50% opacity black |
| color-bg-input | `#FFFFFF` | Input field background |
| color-bg-input-disabled | `#F1F5F9` | Disabled input background |
| color-bg-table-alt | `#F8FAFC` | Alternating table row |
| color-bg-table-hover | `#EFF6FF` | Table row on hover |
| color-bg-table-selected | `#DBEAFE` | Table row when selected |
| color-bg-skeleton | `#E2E8F0` | Skeleton loader base |
| color-bg-skeleton-shine | `#F1F5F9` | Skeleton shimmer highlight |

## 1.6 Text Color Tokens

| Token | Hex | Usage |
|---|---|---|
| color-text-primary | `#1E293B` | Main body text, headings |
| color-text-secondary | `#64748B` | Labels, meta, secondary copy |
| color-text-disabled | `#94A3B8` | Disabled field values, muted text |
| color-text-inverse | `#FFFFFF` | Text on dark backgrounds |
| color-text-link | `#2563EB` | Inline hyperlinks |
| color-text-link-hover | `#1D4ED8` | Inline link on hover |
| color-text-link-visited | `#7C3AED` | Visited link color |
| color-text-error | `#DC2626` | Error messages, field-level errors |
| color-text-success | `#16A34A` | Success confirmation text |
| color-text-warning | `#D97706` | Warning message text |
| color-text-placeholder | `#94A3B8` | Placeholder text in inputs |

## 1.7 Border Color Tokens

| Token | Hex | Usage |
|---|---|---|
| color-border-default | `#E2E8F0` | Default input, card, table borders |
| color-border-strong | `#CBD5E1` | Stronger borders, section dividers |
| color-border-focus | `#2563EB` | Focus ring border on inputs and buttons |
| color-border-error | `#DC2626` | Error state border on inputs |
| color-border-success | `#16A34A` | Success state border on inputs |
| color-border-disabled | `#E2E8F0` | Disabled element border |

## 1.8 Color Usage Rules — Non-Negotiable

| Rule | Detail |
|---|---|
| Primary scale for primary actions only | Never use accent/semantic colors for primary buttons. Primary-600 default, primary-700 hover, primary-800 active. |
| Accent scale reserved for AI + charts | Teal is exclusively for AI features, data visualizations, and special indicators. Never for buttons or alerts. |
| Semantic colors for feedback only | Success/Warning/Error/Info are never decorative. Only appear for real system states. |
| Never use color as the only signal | All status colors must be paired with an icon OR text label. Color alone is inaccessible. |
| Enforce contrast minimums | Text on white: neutral-700 or darker. Text on primary-600: white only. Small text: minimum 4.5:1 WCAG AA. |
| Sidebar always neutral-900 | Never deviate. Active item uses primary-700 background. Inactive items use neutral-400 text. |
| Apply all colors via CSS variables | Never write hex values in component files. Always reference the token variable. |

---

# 2. Typography System

Font family: **Inter** (Google Fonts). Fallback: `-apple-system, BlinkMacSystemFont, Arial, sans-serif`. All sizes defined in rem and px. Line heights are tuned for information-dense medical interfaces.

## 2.1 Font Size Scale

| Token | px | rem | Line Height | Primary Usage |
|---|---|---|---|---|
| text-xs | 11px | 0.6875rem | 1.5 | Badge text, table meta, timestamps, legal copy |
| text-sm | 13px | 0.8125rem | 1.5 | Table cell content, helper/hint text |
| text-base | 14px | 0.875rem | 1.6 | Default body text, form labels, button text |
| text-md | 15px | 0.9375rem | 1.6 | Card body, input values, readable copy |
| text-lg | 16px | 1rem | 1.6 | Card titles, sub-section headings (H4) |
| text-xl | 18px | 1.125rem | 1.5 | Page section headings (H3) |
| text-2xl | 20px | 1.25rem | 1.4 | H2 section titles |
| text-3xl | 24px | 1.5rem | 1.3 | H1 page titles |
| text-4xl | 28px | 1.75rem | 1.25 | Dashboard stat numbers |
| text-5xl | 32px | 2rem | 1.2 | Hero stat numbers, large KPI values |
| text-display | 36px | 2.25rem | 1.1 | Super Admin platform-wide stats only |

## 2.2 Line Height Tokens

| Token | Value | Usage |
|---|---|---|
| leading-none | 1.0 | Display numbers, tight stat values |
| leading-tight | 1.25 | Large headings (H1, H2), stat cards |
| leading-snug | 1.375 | H3, card titles |
| leading-normal | 1.5 | Default body text, labels, lists |
| leading-relaxed | 1.625 | Long-form clinical notes, descriptive paragraphs |
| leading-loose | 2.0 | Spaced instructional text — use sparingly |

## 2.3 Font Weight Tokens

| Token | Weight | Usage |
|---|---|---|
| font-normal | 400 | Body text, table cell content, helper text |
| font-medium | 500 | Labels, nav items, badge text, form labels |
| font-semibold | 600 | Button text, card titles, active nav, H3, H4 |
| font-bold | 700 | H1, H2, stat numbers, high-emphasis callouts |
| font-extrabold | 800 | Cover/hero headings only — use sparingly |

## 2.4 Letter Spacing Tokens

| Token | Value | Usage |
|---|---|---|
| tracking-tighter | -0.02em | Large display numbers and stat values |
| tracking-tight | -0.01em | H1 titles |
| tracking-normal | 0em | Body text — default |
| tracking-wide | 0.02em | ALL CAPS labels, badge text, small meta |
| tracking-wider | 0.05em | Status chip text (uppercase short strings) |

## 2.5 Per-Element Typography Rules

| Element | Specification |
|---|---|
| H1 — Page title | text-3xl (24px), font-bold (700), neutral-800, leading-tight, one per page only |
| H2 — Section heading | text-2xl (20px), font-bold (700), neutral-800, leading-tight |
| H3 — Card/panel title | text-xl (18px), font-semibold (600), neutral-700, leading-snug |
| H4 — Sub-section label | text-lg (16px), font-semibold (600), neutral-700 |
| Body primary | text-md (15px), font-normal (400), neutral-700, leading-relaxed |
| Body secondary | text-base (14px), font-normal (400), neutral-500, leading-normal |
| Form label | text-base (14px), font-medium (500), neutral-700, always above input |
| Helper text | text-sm (13px), font-normal (400), neutral-500, below input |
| Error text | text-sm (13px), font-medium (500), error-600, below input in error state |
| Table header cell | text-sm (13px), font-semibold (600), neutral-600, uppercase, tracking-wide |
| Table data cell | text-base (14px), font-normal (400), neutral-700 |
| Badge / Tag | text-xs (11px), font-medium (500), uppercase, tracking-wider |
| Button text | text-base (14px), font-semibold (600), no uppercase, white-space: nowrap |
| Sidebar nav item | text-base (14px), font-medium (500), neutral-400 inactive / white active |
| Stat number | text-4xl or text-5xl, font-bold (700), tracking-tighter, neutral-800 |
| Stat label | text-sm (13px), font-medium (500), neutral-500, uppercase, tracking-wide |
| Tooltip | text-sm (13px), font-normal (400), white on neutral-900 bg |
| Placeholder text | text-base (14px), font-normal (400), neutral-400 |
| Code / monospace | Courier New, text-sm (13px), primary-900 on neutral-100 bg |
| Breadcrumb | text-sm (13px), font-medium (500), neutral-500 inactive / neutral-800 current |
| Tab label | text-base (14px), font-medium (500) inactive, font-semibold (600) active |

## 2.6 Inline Link Styles

| State | Specification |
|---|---|
| Default | color: primary-600 \| text-decoration: underline on hover only \| cursor: pointer |
| Hover | color: primary-700 \| text-decoration: underline \| transition: 150ms |
| Active | color: primary-800 |
| Visited | color: purple-600 — only for true navigational links |
| Focus | outline: 2px solid primary-600, outline-offset: 2px |
| Disabled | color: neutral-400 \| cursor: not-allowed \| no underline |

## 2.7 List Styles

| Type | Specification |
|---|---|
| Unordered list (ul) | Bullet: disc \| indent: 24px \| item gap: space-1 (4px) \| text-base neutral-700 |
| Ordered list (ol) | Marker: decimal \| indent: 24px \| item gap: space-1 (4px) \| text-base neutral-700 |
| Nested list (level 2) | Bullet: circle \| additional indent: 20px \| text-sm neutral-600 |
| Clinical notes list | text-md, leading-relaxed \| item gap: space-2 (8px) |

## 2.8 Truncation Rules

| Rule | Specification |
|---|---|
| Single-line | overflow: hidden \| text-overflow: ellipsis \| white-space: nowrap \| max-width defined |
| Multi-line clamp | -webkit-line-clamp (2 or 3 lines max) \| overflow: hidden \| display: -webkit-box |
| Patient names | **NEVER truncate.** Always show full name. Widen column or wrap to second line. |
| Drug names | Never truncate in prescriptions. Truncation allowed only in previews with tooltip. |
| Tooltip on truncation | Any truncated text MUST show full content in a tooltip on hover. |

## 2.9 Paragraph Spacing Rules

| Context | Spacing |
|---|---|
| Between paragraphs | margin-bottom: space-4 (16px) body content \| space-3 (12px) compact contexts |
| After H1 | margin-bottom: space-6 (24px) |
| After H2 | margin-bottom: space-4 (16px) |
| After H3/H4 | margin-bottom: space-3 (12px) |
| Clinical notes | Paragraphs: space-3 gap \| Sections: space-6 gap |

---

# 3. Spacing System

All spacing values are multiples of 4px. Never use arbitrary values. Every margin, padding, and gap must reference a token from this scale. No exceptions.

## 3.1 Spacing Scale

| Token | px | rem | Primary Usage |
|---|---|---|---|
| space-0 | 0px | 0 | Explicitly remove spacing |
| space-px | 1px | 0.0625rem | Hairlines, borders only |
| space-0.5 | 2px | 0.125rem | Micro-adjustments, icon offsets |
| space-1 | 4px | 0.25rem | Badge padding horizontal, icon gaps, tight spacing |
| space-1.5 | 6px | 0.375rem | Small badge padding, chip padding |
| space-2 | 8px | 0.5rem | Input padding top/bottom, small gaps, list item spacing |
| space-2.5 | 10px | 0.625rem | Tag internal padding |
| space-3 | 12px | 0.75rem | Button padding vertical, default list item padding |
| space-4 | 16px | 1rem | Button padding horizontal, card padding (compact), form field gap |
| space-5 | 20px | 1.25rem | Sidebar item padding, table cell padding, medium gap |
| space-6 | 24px | 1.5rem | Card padding default, section gap, modal padding |
| space-7 | 28px | 1.75rem | Card padding large variant |
| space-8 | 32px | 2rem | Section margin, panel padding, grid gap |
| space-10 | 40px | 2.5rem | Page section gap, large panel spacing |
| space-12 | 48px | 3rem | Large section separation |
| space-16 | 64px | 4rem | Page top padding, hero spacing |
| space-20 | 80px | 5rem | Dashboard section separation |
| space-24 | 96px | 6rem | Maximum vertical separation — use sparingly |

## 3.2 Spacing Application Rules

| Context | Spacing Rule |
|---|---|
| Card internal padding | space-6 default \| space-4 compact/dense \| space-8 featured cards |
| Form: vertical gap between label+input groups | space-5 (20px) \| space-8 between logical sections |
| Button padding — SM | Horizontal: space-3 (12px) \| Vertical: space-2 (8px) |
| Button padding — MD | Horizontal: space-4 (16px) \| Vertical: space-2.5 (10px) |
| Button padding — LG | Horizontal: space-5 (20px) \| Vertical: space-3 (12px) |
| Table cell padding — default | Vertical: space-3 (12px) \| Horizontal: space-4 (16px) |
| Table cell padding — dense | Vertical: space-2 (8px) \| Horizontal: space-3 (12px) |
| Sidebar nav item | Horizontal: space-4 (16px) \| Vertical: space-3 (12px) |
| Modal padding | space-6 all sides \| space-6 gap between header/body/footer |
| Section gap on dashboard | space-8 between stat row and charts \| space-6 between charts and table |
| Icon + text inline gap | space-2 (8px) — non-negotiable, never less |
| Stack gap — tight | space-2 (8px) — for closely related items |
| Stack gap — default | space-3 (12px) — for standard vertical lists |
| Stack gap — loose | space-4 (16px) — for clearly separated items |
| Inline element gap | space-2 between inline badges, chips, tags in a row |
| Tooltip padding | Vertical: space-1.5 (6px) \| Horizontal: space-3 (12px) |
| Badge internal padding | Vertical: space-0.5–1 \| Horizontal: space-1.5–space-2 |
| Negative spacing | Avoid. Only use for overlapping avatar stacks: -space-2 (-8px) |

---

# 4. Border Radius System

| Token | Value | Usage & Component Mapping |
|---|---|---|
| radius-none | 0px | No rounding — table inner cells, flush-edge dividers, print |
| radius-sm | 4px | Badge, tag, tooltip, table row selection highlight, code snippet |
| radius-md | 6px | Input fields, small buttons (SM), dropdown items, context menu items |
| radius-default | 8px | **DEFAULT** — all standard buttons (MD/LG), cards inner elements, checkboxes |
| radius-lg | 12px | Cards, panels, modals, dropdowns panels, filter chip groups |
| radius-xl | 16px | Large modals, side drawers, sheet overlays |
| radius-2xl | 20px | Dashboard stat cards (featured), hero cards |
| radius-full | 9999px | Pill badges, avatar circles, toggle switch track, circular icon buttons |

---

# 5. Shadow & Elevation System

Shadows communicate elevation level. Use the lowest elevation that achieves visual separation. Never stack multiple shadows on one element.

| Token | CSS Value | Usage |
|---|---|---|
| shadow-none | `none` | Flat elements — table cells, sidebar items, dividers |
| shadow-xs | `0 1px 2px rgba(0,0,0,0.05)` | Inputs on hover, small raised elements |
| shadow-sm | `0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)` | Default cards, panels |
| shadow-md | `0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06)` | Elevated cards, stat cards, popovers |
| shadow-lg | `0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)` | Modals, dialog boxes |
| shadow-xl | `0 20px 25px rgba(0,0,0,0.1), 0 10px 10px rgba(0,0,0,0.04)` | Dropdown menus, floating panels |
| shadow-2xl | `0 25px 50px rgba(0,0,0,0.15)` | Full-screen drawers, bottom sheets |
| shadow-inner | `inset 0 2px 4px rgba(0,0,0,0.06)` | Depressed input focus, pressed button |
| shadow-focus-primary | `0 0 0 3px rgba(37,99,235,0.35)` | Primary button/input focus ring (blue) |
| shadow-focus-error | `0 0 0 3px rgba(220,38,38,0.35)` | Error input focus ring (red) |
| shadow-focus-success | `0 0 0 3px rgba(22,163,74,0.35)` | Success input focus ring (green) |

---

# 6. Border System

## 6.1 Border Width Tokens

| Token | Value | Usage |
|---|---|---|
| border-none | 0px | Explicitly remove border |
| border-1 | 1px | **DEFAULT** — inputs, cards, table cells, dividers |
| border-2 | 2px | Selected table rows, active tab underlines, strong dividers |
| border-4 | 4px | Left accent border on alert/callout cards |
| border-8 | 8px | Thick left accent for sidebar active indicator |

## 6.2 Border Style Rules

| Component | Border Specification |
|---|---|
| Input — default | 1px solid color-border-default (#E2E8F0) |
| Input — focus | 1px solid color-border-focus (#2563EB) + shadow-focus-primary |
| Input — error | 1px solid color-border-error (#DC2626) + shadow-focus-error on focus |
| Input — disabled | 1px solid color-border-disabled (#E2E8F0) |
| Card — default | 1px solid neutral-200 (#E2E8F0) |
| Card — elevated | No border — shadow-md replaces border |
| Card — alert variant | Left border: 4px solid semantic-color |
| Table — header bottom | 2px solid neutral-200 |
| Table — row divider | 1px solid neutral-100 — very subtle |
| Modal — no outer border | Shadow-lg provides elevation boundary |
| Sidebar | Right border: 1px solid neutral-800 |
| Divider — horizontal | 1px solid neutral-200, full width, margin: space-6 vertical |
| Divider — vertical | 1px solid neutral-200, height: 100%, margin: space-3 horizontal |
| Divider — with label | Line both sides, label centered, text-xs neutral-500 uppercase |

---

# 7. Z-Index System

Z-index conflicts break hospital UIs. Every layer is explicitly named and non-negotiable.

| Token | Value | Usage |
|---|---|---|
| z-base | 0 | Default document flow elements |
| z-raised | 10 | Sticky table headers, raised cards |
| z-dropdown | 100 | Dropdown menus, select panels, date pickers, autocomplete |
| z-sticky | 200 | Sticky page headers, fixed sidebars |
| z-overlay | 300 | Modal backdrop overlay |
| z-modal | 400 | Modal dialogs, drawer panels |
| z-popover | 500 | Popovers and tooltips that appear over modals |
| z-toast | 600 | Toast notifications — always topmost UI layer |
| z-max | 9999 | Emergency alerts only — hospital-wide broadcast banners |

---

# 8. Icon System

Icon library: **Lucide React** (open source, consistent 1.5 stroke width). Never mix icon libraries. All icons are SVG and tree-shakeable.

## 8.1 Icon Size Scale

| Token | Size | Usage |
|---|---|---|
| icon-xs | 12px | Inline text icons, badge decorators |
| icon-sm | 14px | Table cell status icons, small button icons |
| icon-md | 16px | **DEFAULT** — nav icons, form icons, button icons, input affixes |
| icon-lg | 20px | Card header icons, page title icons |
| icon-xl | 24px | Empty state main icon, feature callout icons |
| icon-2xl | 32px | Large feature callout icons |
| icon-3xl | 48px | Empty state hero icons, error state hero icons |

## 8.2 Icon Color Pairing Rules

| Context | Color Rule |
|---|---|
| Icon in primary button | white — inherits button text color |
| Icon in secondary button | neutral-600 default, neutral-700 hover |
| Icon in ghost/link button | Matches button text color |
| Navigation icon — inactive | neutral-400 |
| Navigation icon — active | white |
| Status icon — success | success-600 |
| Status icon — warning | warning-600 |
| Status icon — error | error-600 |
| Status icon — info | primary-600 |
| Icon in body text | neutral-500 — never darker than body text |
| Icon in input field (left) | neutral-400 |
| Icon in input (right, action) | neutral-500 hover neutral-700 |
| AI feature icon (Sparkles) | accent-500 |
| Destructive action icon | error-600 |
| Disabled icon | neutral-300 — always lighter than disabled text |

## 8.3 Icon + Label Rules

- Navigation items: ALWAYS pair icon with text label. Icon-only nav is inaccessible.
- Buttons: icon + text for primary/secondary. Icon-only only for ghost/toolbar with aria-label.
- Table action column: icon-only buttons allowed with aria-label and tooltip.
- Status badges: icon left of text — same semantic color for both.
- Icon-only buttons minimum size: 32x32px (44x44px on mobile).

## 8.4 Required Icon Set by Module

| Module | Required Icons |
|---|---|
| Sidebar Navigation | LayoutDashboard, Users, Calendar, FileText, Pill, FlaskConical, CreditCard, BarChart2, Settings, Bell, ChevronRight, LogOut, Menu, X |
| Patient Module | User, UserPlus, Search, Filter, Download, Eye, Edit, Trash2, FileText, Heart, Activity, AlertTriangle, ClipboardList |
| Appointments | Calendar, Clock, Plus, Check, X, RefreshCw, ChevronLeft, ChevronRight, MapPin, UserCheck |
| Prescriptions | Pill, AlertCircle, CheckCircle, ClipboardList, Printer, Download, AlertTriangle |
| Lab Module | FlaskConical, Upload, AlertTriangle, CheckCircle, Eye, Download, Microscope, TestTube |
| Billing | CreditCard, Receipt, DollarSign, TrendingUp, TrendingDown, Download, Send, CheckCircle |
| Staff Module | Users, UserPlus, Shield, Clock, Calendar, Edit, Trash2, Key |
| Notifications | Bell, BellOff, Info, CheckCircle, AlertTriangle, XCircle, X, MailOpen |
| AI Features | Sparkles, Wand2, Brain, MessageSquare, Lightbulb, Zap |
| System / Status | Wifi, WifiOff, RefreshCw, Loader2, ChevronUp, ChevronDown, MoreHorizontal, MoreVertical, ExternalLink, Copy, Lock, Unlock |
| Empty States | InboxIcon, FolderOpen, SearchX, CalendarX, ClipboardX, FileX |
| Forms / Inputs | Eye, EyeOff, Search, X, ChevronDown, Upload, Paperclip, Calendar |

---

# 9. Motion & Animation System

## 9.1 Transition Duration Tokens

| Token | Value | Usage |
|---|---|---|
| transition-instant | 50ms | Checkbox check, radio select — immediate feedback |
| transition-fast | 100ms | Button hover color, icon color change |
| transition-default | 150ms | Input border, hover states, badge color transitions |
| transition-medium | 200ms | Dropdown open/close, tooltip appear, page fade |
| transition-slow | 300ms | Modal enter, sidebar collapse, drawer open |
| transition-xslow | 500ms | Skeleton-to-content, route transitions |

## 9.2 Easing Function Tokens

| Token | CSS Value | Usage |
|---|---|---|
| ease-linear | `linear` | Progress bars, loading indicators |
| ease-in | `cubic-bezier(0.4,0,1,1)` | Elements exiting the screen (close/dismiss) |
| ease-out | `cubic-bezier(0,0,0.2,1)` | Elements entering the screen (open/appear) |
| ease-in-out | `cubic-bezier(0.4,0,0.2,1)` | Elements that move but stay (collapse, expand, resize) |

## 9.3 Per-Component Animation Specs

| Component / State | Animation Specification |
|---|---|
| Modal open | scale 95%→100% + opacity 0→1 \| 300ms ease-out |
| Modal close | scale 100%→95% + opacity 1→0 \| 200ms ease-in |
| Drawer open (right) | translateX 100%→0 \| 300ms ease-out |
| Drawer close (right) | translateX 0→100% \| 200ms ease-in |
| Toast enter | translateX 100%→0 + opacity 0→1 \| 300ms ease-out |
| Toast exit | translateX 0→100% + opacity 1→0 \| 200ms ease-in |
| Dropdown open | translateY -8px→0 + opacity 0→1 \| 150ms ease-out |
| Dropdown close | translateY 0→-8px + opacity 1→0 \| 100ms ease-in |
| Tooltip appear | opacity 0→1 + scale 95%→100% \| 150ms ease-out \| delay: 400ms |
| Sidebar collapse | width 260px→68px \| 200ms ease-in-out \| labels fade 150ms |
| Accordion open | max-height 0→content + opacity 0→1 \| 200ms ease-out |
| Accordion close | max-height content→0 + opacity 1→0 \| 150ms ease-in |
| Button hover | background-color \| 100ms ease-out |
| Button loading | Loader2 rotation 360deg \| 700ms linear infinite |
| Button press | scale 1→0.98 \| 50ms \| release 0.98→1 \| 100ms ease-out |
| Tab switch | active underline slides horizontally \| 200ms ease-in-out |
| Page route change | opacity 0→1 fade \| 200ms ease-out on new page mount |
| Table row appear | opacity 0→1 + translateY 4px→0 \| staggered 30ms per row |
| Skeleton shimmer | neutral-200→neutral-100→neutral-200 sweep \| 1.5s linear infinite |
| Form error shake | translateX 0→-6px→6px→-3px→3px→0 \| 400ms |
| Toggle switch | thumb translateX + track bg \| 150ms ease-in-out |
| Progress bar fill | width transition \| 300ms ease-out |
| Checkbox check | SVG checkmark draw-on \| 100ms ease-out |

## 9.4 Reduced Motion Rules

> **⚠️ `prefers-reduced-motion`: Critical Requirement**
> All animations MUST be disabled or significantly reduced when the OS has Reduce Motion enabled. Wrap all CSS animations and transitions in `@media (prefers-reduced-motion: reduce)`. Use instant transitions only. No scale, translate, or opacity animations. Skeleton: replace shimmer with static neutral-200. Loader2 may still rotate at reduced speed (1.5s instead of 0.7s).

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

---

# 10. Button Component

## 10.1 Size Variants

| Size | Specification |
|---|---|
| SM | Height: 32px \| Padding: 8px 12px \| Font: text-sm (13px) font-semibold \| Icon: icon-sm (14px) \| radius-md (6px) |
| MD (Default) | Height: 38px \| Padding: 10px 16px \| Font: text-base (14px) font-semibold \| Icon: icon-md (16px) \| radius-default (8px) |
| LG | Height: 44px \| Padding: 12px 20px \| Font: text-md (15px) font-semibold \| Icon: icon-md (16px) \| radius-default (8px) |
| Icon-only SM | 32x32px \| No label \| aria-label required \| radius-default |
| Icon-only MD | 38x38px \| No label \| aria-label required \| radius-default |
| Icon-only LG | 44x44px \| No label \| aria-label required \| radius-default |

## 10.2 Style Variants

### Primary Button
| State | Specification |
|---|---|
| Default | bg: primary-600 \| text: white \| border: none \| shadow: shadow-xs |
| Hover | bg: primary-700 \| transition: 100ms |
| Active | bg: primary-800 \| scale: 0.98 |
| Focus | shadow: shadow-focus-primary \| outline: none |
| Disabled | bg: neutral-200 \| text: neutral-400 \| cursor: not-allowed \| opacity: 0.6 |
| Loading | bg: primary-700 \| Loader2 spin icon left \| pointer-events: none \| aria-busy=true |

### Secondary Button
| State | Specification |
|---|---|
| Default | bg: white \| border: 1px neutral-300 \| text: neutral-700 |
| Hover | bg: neutral-50 \| border: neutral-400 |
| Active | bg: neutral-100 \| scale: 0.98 |
| Focus | shadow: shadow-focus-primary \| border: primary-600 |
| Disabled | bg: neutral-50 \| text: neutral-400 \| border: neutral-200 \| cursor: not-allowed |
| Loading | Same as active + Loader2 spin \| pointer-events: none |

### Danger Button
| State | Specification |
|---|---|
| Default | bg: error-600 \| text: white \| border: none |
| Hover | bg: error-700 |
| Active | bg: error-800 \| scale: 0.98 |
| Focus | shadow: shadow-focus-error |
| Disabled | bg: neutral-200 \| text: neutral-400 \| cursor: not-allowed |

### Ghost Button
| State | Specification |
|---|---|
| Default | bg: transparent \| border: none \| text: neutral-600 |
| Hover | bg: neutral-100 \| text: neutral-800 |
| Active | bg: neutral-200 \| scale: 0.98 |
| Focus | shadow: shadow-focus-primary |
| Use for | Tertiary actions, icon-only toolbar buttons, cancel actions in tables |

### Link Button
| State | Specification |
|---|---|
| Default | bg: transparent \| border: none \| text: primary-600 \| padding: 0 |
| Hover | text: primary-700 \| underline |
| Focus | outline: 2px solid primary-600 \| outline-offset: 2px |
| Use for | Inline text-level actions only — never as a standalone CTA |

### Button Group
| Property | Specification |
|---|---|
| Layout | Horizontal flex row \| gap: 0 \| buttons share borders |
| Border handling | Remove border-right on all but last. Remove border-left on all but first. |
| Radius | First button: radius on left side only. Last: right only. Middle: none. |
| Selection | One active at a time. Active: primary-100 bg, primary-700 text, primary-600 border. |

## 10.3 Button Rules

- Loading state disables all interaction. Set `pointer-events: none`.
- Never place two Primary buttons side by side. One CTA per visual section.
- Button text never wraps — `white-space: nowrap` always.
- Minimum touch target on mobile: 44x44px even for SM buttons.
- Icon placement: left for constructive actions. Right for navigation (Next →).
- Destructive actions: always Danger variant. Never Primary for delete/cancel/void.

---

# 11. Input Field Component

## 11.1 Size Variants

| Size | Specification |
|---|---|
| SM | Height: 32px \| Padding: 4px 10px \| Font: text-sm (13px) \| radius-md (6px) |
| MD (Default) | Height: 38px \| Padding: 8px 12px \| Font: text-base (14px) \| radius-default (8px) |
| LG | Height: 44px \| Padding: 10px 14px \| Font: text-md (15px) \| radius-default (8px) |

## 11.2 All States

| State | Specification |
|---|---|
| Default | border: 1px neutral-300 \| bg: white \| text: neutral-700 \| placeholder: neutral-400 |
| Focus | border: 1px primary-600 \| shadow: shadow-focus-primary \| outline: none |
| Filled | border: 1px neutral-300 \| text: neutral-800 |
| Error | border: 1px error-600 \| error message below \| shadow-focus-error on focus |
| Success | border: 1px success-600 \| CheckCircle icon right \| after async validation only |
| Disabled | bg: neutral-100 \| border: neutral-200 \| text: neutral-400 \| cursor: not-allowed |
| Read-only | bg: neutral-50 \| border: neutral-200 \| text: neutral-600 \| no focus ring |
| Loading | Spinner icon replacing right icon \| pointer-events: none |

## 11.3 Input Affix Variants

| Type | Specification |
|---|---|
| Left icon | Icon at left inside padding \| padding-left: 36px \| icon-md, neutral-400 |
| Right icon | Icon at right inside padding \| padding-right: 36px |
| Left prefix text | Text (e.g. $ or +1) \| bg: neutral-100 \| border-right: 1px neutral-300 \| text: neutral-500 |
| Right suffix text | Text (e.g. kg or .com) \| bg: neutral-100 \| border-left: 1px neutral-300 |
| Search input | Search icon left (neutral-400) \| X clear icon right (when value present) |
| Password input | Eye/EyeOff toggle on right \| toggles between password/text type |
| Copy input | Copy icon on right \| brief "Copied!" tooltip on click |

## 11.4 Character Count

| State | Specification |
|---|---|
| Display | text-xs neutral-400 \| right-aligned below input \| format: `24 / 100` |
| Near limit | text-xs warning-600 when > 80% of max |
| At limit | text-xs error-600 \| input border switches to error-600 |
| Placement | Same line as helper text — error takes priority, count moves right |

## 11.5 Input Rules

- Label always above input — never inside (placeholder is not a label).
- Placeholder color must be neutral-400 — always lighter than filled text.
- Error message replaces helper text in error-600 with AlertCircle icon.
- All inputs require explicit `name` and `id` attributes for accessibility.
- Required fields: asterisk (*) in error-600 in label.

---

# 12. Textarea Component

| Property | Specification |
|---|---|
| Min height | 80px (approx 3 lines) |
| Default height | 120px short notes \| 200px clinical/SOAP fields |
| Max height | 400px before internal scroll begins |
| Resize behavior | `resize: vertical` only. Never horizontal. Never both. |
| Auto-grow | Expands as user types via scrollHeight approach. Max-height: 400px then scroll. |
| Padding | Vertical: space-2 (8px) \| Horizontal: space-3 (12px) — matches Input MD |
| Font | text-base (14px), neutral-700, leading-relaxed |
| Border/radius | Same as Input MD: 1px neutral-300, radius-default (8px) |
| All states | Default, focus, error, disabled, read-only — same as Input Field |
| Character count | Always show for clinical note fields \| bottom-right inside textarea border |
| Label | Always above textarea. Never use placeholder as the label. |

---

# 13. Select / Dropdown Component

### Select States

| State | Specification |
|---|---|
| Default | Visually identical to Input MD \| ChevronDown icon right \| bg: white |
| Open | border: primary-600 \| ChevronUp icon \| dropdown panel visible below |
| Option — default | text: neutral-700 \| padding: space-2 space-3 |
| Option — hover | bg: primary-50 \| text: primary-700 \| transition: 100ms |
| Option — selected | bg: primary-100 \| text: primary-700 \| Check icon right (primary-600) |
| Option — disabled | text: neutral-400 \| cursor: not-allowed \| no hover |
| Disabled select | Same as Input disabled state |
| Loading | Spinner icon replaces ChevronDown \| panel not openable |

### Dropdown Panel

| Property | Specification |
|---|---|
| Background | white |
| Border | 1px neutral-200 |
| Radius | radius-lg (12px) |
| Shadow | shadow-xl |
| Max height | 240px — overflow-y: auto |
| z-index | z-dropdown (100) |
| Position | Below trigger by default. Flips above if insufficient space. |
| Min width | Same as trigger. Can be wider, never narrower. |

### Multi-Select with Pills

| Property | Specification |
|---|---|
| Selected items | Appear as removable pills inside the input field |
| Pill style | bg: primary-100 \| text: primary-700 \| X icon right \| radius-full \| text-xs |
| Input grows | Field height increases as pills wrap to next line |
| Max pills visible | 3 pills then "+N more" indicator |
| Remove pill | Click X or focus pill and press Delete/Backspace |

### Searchable Select

| Property | Specification |
|---|---|
| Trigger | Input with Search icon left \| ChevronDown right |
| Typing | Filters options in real-time \| no match: "No results found" |
| Highlight | Matched substring bolded in option text |
| Clear | X icon appears in trigger when value selected |

### Option Groups

| Property | Specification |
|---|---|
| Group header | text-xs uppercase tracking-wide neutral-500 \| padding: space-1.5 space-3 \| not selectable |
| Group items | Same as regular options but indented by space-3 |
| Separator | 1px neutral-100 between groups |

- **Keyboard:** Arrow Down opens. Arrow Up/Down navigate. Enter selects. Escape closes.

---

# 14. Checkbox Component

### Checkbox Dimensions

| Size | Specification |
|---|---|
| SM checkbox | 16x16px \| border-radius: radius-sm (4px) \| 10px checkmark |
| MD checkbox (Default) | 20x20px \| border-radius: radius-sm (4px) \| 12px checkmark |

### Checkbox States

| State | Specification |
|---|---|
| Unchecked — default | bg: white \| border: 1.5px neutral-300 \| no fill |
| Unchecked — hover | border: 1.5px primary-400 \| bg: primary-50 |
| Unchecked — focus | border: 1.5px primary-600 \| shadow: shadow-focus-primary |
| Checked | bg: primary-600 \| border: primary-600 \| white checkmark SVG centered |
| Checked — hover | bg: primary-700 \| border: primary-700 |
| Indeterminate | bg: primary-600 \| border: primary-600 \| white horizontal dash centered |
| Disabled unchecked | bg: neutral-100 \| border: neutral-200 \| cursor: not-allowed |
| Disabled checked | bg: neutral-300 \| border: neutral-300 \| white checkmark |
| Error state | border: error-600 \| error message below group label |

### Checkbox Group Layout

| Property | Specification |
|---|---|
| Vertical group | Stack vertically \| gap: space-3 |
| Horizontal group | Flex row \| gap: space-6 \| wraps on overflow |
| Item layout | Checkbox (left) + label text (right) \| gap: space-2 |
| Group label | text-base font-medium neutral-700 \| margin-bottom: space-2 \| above group |
| Error text | text-sm error-600 \| AlertCircle icon \| below last checkbox |

---

# 15. Radio Button Component

### Radio Dimensions

| Size | Specification |
|---|---|
| SM radio | 16x16px outer \| 6px inner dot when selected \| radius-full |
| MD radio (Default) | 20x20px outer \| 8px inner dot when selected \| radius-full |

### Radio States

| State | Specification |
|---|---|
| Unselected — default | bg: white \| border: 1.5px neutral-300 |
| Unselected — hover | border: 1.5px primary-400 \| bg: primary-50 |
| Unselected — focus | shadow: shadow-focus-primary |
| Selected | bg: white \| border: 2px primary-600 \| inner dot: primary-600 centered circle |
| Selected — hover | border: primary-700 \| inner dot: primary-700 |
| Disabled unselected | bg: neutral-100 \| border: neutral-200 \| cursor: not-allowed |
| Disabled selected | border: neutral-300 \| inner dot: neutral-300 |

### Radio Group Layout

| Property | Specification |
|---|---|
| Vertical (default) | Stack radios vertically \| gap: space-3 |
| Horizontal | Flex row \| gap: space-6 \| wraps on overflow |
| Item layout | Radio (left) + label (right) \| gap: space-2 |
| Rules | Exactly one radio selectable at a time. Same name attribute. No deselection by clicking. |

---

# 16. Toggle / Switch Component

### Toggle Dimensions

| Size | Specification |
|---|---|
| SM | Track: 32x18px \| Thumb: 14x14px \| Thumb offset from edge: 2px |
| MD (Default) | Track: 44x24px \| Thumb: 18x18px \| Thumb offset: 3px |
| LG | Track: 56x30px \| Thumb: 24x24px \| Thumb offset: 3px |

### Toggle States

| State | Specification |
|---|---|
| Off — default | Track: neutral-300 \| Thumb: white \| shadow: shadow-xs on thumb |
| Off — hover | Track: neutral-400 |
| Off — focus | shadow: shadow-focus-primary around track |
| On — default | Track: primary-600 \| Thumb: white \| Thumb slides right |
| On — hover | Track: primary-700 |
| Disabled off | Track: neutral-200 \| Thumb: neutral-100 \| cursor: not-allowed |
| Disabled on | Track: primary-200 \| Thumb: white \| cursor: not-allowed |
| With label | Label right of toggle \| gap: space-2 \| text-base font-medium neutral-700 |
| With sub-label | Small description below toggle label \| text-sm neutral-500 |

### Toggle Animation

| Property | Specification |
|---|---|
| Thumb | translateX \| 150ms ease-in-out \| distance = track width - thumb width - 2×padding |
| Track color | background-color transition \| 150ms ease-in-out |

---

# 17. Date Picker Component

### Trigger

| Property | Specification |
|---|---|
| Input style | Same as Input MD \| Calendar icon left (neutral-400) \| value format: MM/DD/YYYY |
| Empty state | Placeholder: "Select date" in neutral-400 |
| Clear button | X icon right when date selected — clears selection |

### Calendar Panel

| Property | Specification |
|---|---|
| Width | 280px fixed |
| Background | white |
| Border | 1px neutral-200 |
| Radius | radius-lg (12px) |
| Shadow | shadow-xl |
| z-index | z-dropdown (100) |
| Padding | space-4 all sides |
| Position | Below trigger. Flips above if insufficient space below viewport. |

### Calendar Header

| Property | Specification |
|---|---|
| Layout | Month name + Year (centered, font-semibold) \| Left arrow (prev) \| Right arrow (next) |
| Month/Year click | Switches to month-picker or year-picker view |
| Arrow buttons | Ghost icon-only \| 32x32px \| ChevronLeft/ChevronRight |

### Day Grid

| State | Specification |
|---|---|
| Header row | Sun Mon Tue Wed Thu Fri Sat \| text-xs uppercase neutral-500 |
| Day cell | 36x36px \| text-base neutral-700 \| radius-default \| centered |
| Day — hover | bg: primary-50 \| text: primary-700 \| transition: 100ms |
| Day — selected | bg: primary-600 \| text: white |
| Day — today | text: primary-600 \| font-bold \| 3px primary-600 dot below number |
| Day — disabled | text: neutral-300 \| cursor: not-allowed \| no hover |
| Day — outside month | text: neutral-300 \| still clickable (navigates to that month) |
| Range start | bg: primary-600 \| radius left side only |
| Range end | bg: primary-600 \| radius right side only |
| Range middle | bg: primary-100 \| no radius |

### Date Range & Time

| Property | Specification |
|---|---|
| Date range | Two calendars side by side desktop \| stacked mobile \| first click = start, second = end |
| Hover preview | Range highlight in primary-50 while hovering after start selected |
| Preset ranges | Today \| Last 7 days \| Last 30 days \| This month \| Custom |
| Time picker | Hours/Minutes spinners or direct input \| AM/PM toggle \| below day grid |

- **Keyboard:** Arrow keys navigate days. Enter selects. Page Up/Down changes month. Escape closes.

---

# 18. File Upload Component

### Drag-and-Drop Zone

| State | Specification |
|---|---|
| Default | Full width \| min-height: 120px \| 2px dashed neutral-300 \| bg: neutral-50 \| Upload icon (icon-xl, neutral-400) centered |
| Hover (drag over) | border: 2px dashed primary-400 \| bg: primary-50 \| icon turns primary-400 |
| Active drag | border: 2px solid primary-600 \| "Drop files here" text |
| Disabled | bg: neutral-100 \| border: neutral-200 \| cursor: not-allowed \| all content neutral-300 |
| Error | border: 2px dashed error-400 \| bg: error-50 \| error message below zone |

### File List

| Property | Specification |
|---|---|
| File row | Paperclip icon (neutral-400) \| filename (truncated, neutral-700) \| file size (neutral-500) \| X remove button |
| Image preview | 40x40px thumbnail instead of icon |
| Upload progress | Progress bar below filename \| accent-500 fill \| text-xs neutral-500 percentage |
| Upload success | CheckCircle icon (success-600) replaces progress bar |
| Upload error | XCircle icon (error-600) \| error message text-sm \| Retry button |
| File restrictions | Accepted: PDF, JPG, PNG — Max size: 10MB \| text-xs neutral-500 below zone |

---

# 19. Slider / Range Component

| Property | Specification |
|---|---|
| Track | 4px height \| bg: neutral-200 \| radius-full |
| Filled track | primary-600 \| from left edge to thumb |
| Thumb | 18x18px circle \| bg: white \| border: 2px primary-600 \| shadow-sm \| radius-full |
| Thumb — hover | border: primary-700 \| shadow-md \| scale: 1.1 |
| Thumb — focus | shadow: shadow-focus-primary |
| Thumb — active | scale: 1.2 \| border: primary-800 |
| Disabled track | bg: neutral-200 all \| cursor: not-allowed |
| Disabled thumb | border: neutral-300 \| bg: neutral-100 |
| Tooltip on drag | Value above thumb \| neutral-900 bg, white text, radius-sm \| appears on mousedown |
| Min/Max labels | text-xs neutral-500 \| below track left/right edges |
| Range slider | Two thumbs \| filled track between them \| both draggable |

---

# 20. Card Component

### Default Card

| Property | Value |
|---|---|
| Background | white |
| Border | 1px neutral-200 |
| Radius | radius-lg (12px) |
| Shadow | shadow-sm |
| Padding | space-6 (24px) all sides |

### Stat Card (Dashboard KPI)

| Property | Specification |
|---|---|
| Background | white |
| Border | none \| top accent: 3px solid primary-600 (or semantic color) |
| Radius | radius-2xl (20px) |
| Shadow | shadow-md |
| Padding | space-6 |
| Internal layout | Icon (40x40 bg-primary-100, icon-lg primary-600) \| Stat number (text-4xl/5xl font-bold tracking-tighter) \| Stat label (text-sm uppercase neutral-500) \| Trend (TrendingUp/Down + % change) |
| Sparkline | Optional 60px height mini-chart at bottom — no axes, just trend shape |

### Alert Card

| Property | Specification |
|---|---|
| Background | Semantic-50 (success-50 / warning-50 / error-50 / info-50) |
| Border | Left: 4px solid semantic-600 \| other sides: 1px semantic-200 |
| Radius | radius-lg |
| Padding | space-4 |
| Content | Icon (semantic-600, icon-md) + Title (font-semibold neutral-800) + Body (neutral-700) |

### AI Card

| Property | Specification |
|---|---|
| Background | accent-50 (#F0FDFA) |
| Border | 1px accent-200 |
| Radius | radius-lg |
| Shadow | shadow-sm |
| Header | Sparkles icon (accent-500) + "AI Insight" title \| AI badge in accent-100/accent-700 |

### Compact Card

| Property | Specification |
|---|---|
| Background | white |
| Border | 1px neutral-200 |
| Radius | radius-lg |
| Shadow | shadow-sm |
| Padding | space-4 — for dense dashboards |

### Card With Image

| Property | Specification |
|---|---|
| Image area | Full width at top \| height: 160–200px \| object-fit: cover \| radius on top corners only |
| Body | Below image \| standard space-6 padding |
| Overlay | Optional gradient: transparent to rgba(0,0,0,0.4) for text on image |

### Clickable Card

| State | Specification |
|---|---|
| Cursor | pointer |
| Hover | shadow-md (up from shadow-sm) \| translateY: -2px \| transition: 150ms |
| Focus | shadow: shadow-focus-primary |
| Active | translateY: 0 \| shadow-sm |
| Requirement | Must have clear clickable affordance: arrow icon, "View" link, or hover state change |

## 20.1 Card Anatomy Rules

- **Card Header:** H3 title + optional right-side action button or badge.
- **Card Body:** primary content. No min or max height constraints.
- **Card Footer:** secondary actions/metadata. Separated by 1px neutral-200 border-top. Padding: space-4 space-6.
- Never nest cards inside cards. Use panels or dividers instead.

---

# 21. Modal / Dialog Component

## 21.1 Size Variants

| Size | Usage |
|---|---|
| SM (400px max-width) | Confirmations, alerts, simple single-field prompts |
| MD (560px max-width) — Default | Standard forms, record viewing — most common modals |
| LG (720px max-width) | Multi-section forms, prescription forms, complex editing |
| XL (900px max-width) | Lab report viewing, document preview, advanced editing |
| Full Sheet / Drawer | Right-side panel: 480px width — patient record slide-over |

## 21.2 Structure

| Section | Specification |
|---|---|
| Backdrop | bg: rgba(0,0,0,0.5) \| z-index: z-overlay (300) \| click = close (except destructive) |
| Container | bg: white \| radius-xl (16px) \| shadow-2xl \| z-index: z-modal (400) \| centered |
| Header | Padding: space-6 \| H2 title + optional subtitle \| X close button right (Ghost, 32x32px) \| border-bottom: 1px neutral-200 |
| Body | Padding: space-6 \| overflow-y: auto \| max-height: 70vh |
| Footer | Padding: space-4 space-6 \| border-top: 1px neutral-200 \| flex justify-end \| gap: space-3 \| Cancel left, primary action right |

### Confirmation Dialog

| Property | Specification |
|---|---|
| Size | Modal SM (400px) |
| Icon | AlertTriangle (warning-500) or semantic icon — icon-xl — centered above title |
| Title | Clear question: "Cancel this appointment?" \| text-xl font-bold neutral-800 |
| Body | Consequence: "This will notify the patient." \| text-base neutral-600 |
| Footer | Cancel (Secondary) \| Confirm (Primary or Danger based on action) |

### Destructive Confirmation with Text Input

| Property | Specification |
|---|---|
| Use when | Irreversible high-stakes: delete patient record, void invoice, discharge patient |
| Requirement | User must type a confirmation phrase before primary action button becomes enabled |
| Button | Danger variant — disabled until phrase matches exactly (case-sensitive) |

### Alert Dialog (Non-dismissible)

| Property | Specification |
|---|---|
| Behavior | Clicking backdrop does NOT close \| No X button \| Must click a button to dismiss |
| Use when | Critical alert, session expiry, mandatory acknowledgement |
| Footer | Acknowledge / OK button only — no Cancel |

## 21.3 Modal Rules

- Focus must be trapped inside modal while open. Tab key cycles within modal only.
- Escape closes all modals except Alert Dialogs and Destructive Confirmations.
- Scroll: body scrolls internally — header and footer always visible.
- Never open a modal inside a modal. Use a stepper/wizard pattern.
- Mobile: modals become full-screen (width: 100vw, height: 100vh, radius: 0).
- Animation: enter 300ms ease-out scale+fade. Exit 200ms ease-in.

---

# 22. Drawer / Side Panel Component

### Right Drawer

| Property | Specification |
|---|---|
| Width | 480px default \| 600px for complex records \| 100% on mobile |
| Position | Fixed right: 0 \| top: 0 \| height: 100vh |
| Background | white |
| Shadow | shadow-2xl |
| z-index | z-modal (400) |
| Backdrop | rgba(0,0,0,0.5) at z-overlay (300) |
| Animation | Enter: translateX 100%→0 \| 300ms ease-out \| Exit: translateX 0→100% \| 200ms ease-in |

### Drawer Structure

| Section | Specification |
|---|---|
| Header | Height: 64px \| padding: space-4 space-6 \| H3 title + X close right \| border-bottom: 1px neutral-200 \| sticky |
| Body | padding: space-6 \| overflow-y: auto \| flex: 1 |
| Footer | padding: space-4 space-6 \| border-top: 1px neutral-200 \| sticky at bottom |

### Bottom Sheet (Mobile Only)

| Property | Specification |
|---|---|
| Height | auto up to 85vh \| handle bar: 40px wide, 4px tall, neutral-300, radius-full, centered |
| Animation | Enter: translateY 100%→0 \| 300ms ease-out \| Exit: translateY 0→100% \| 200ms ease-in |
| Radius | radius-xl on top corners only (16px) |
| Swipe | Swipe down to dismiss — minimum 100px downward drag |

---

# 23. Table Component

## 23.1 Row Specification

| Row Type | Specification |
|---|---|
| Header row | bg: neutral-50 \| text: neutral-600 \| text-sm font-semibold uppercase tracking-wide \| height: 44px \| sticky on scroll |
| Data row — default | bg: white \| text: neutral-700 text-base \| height: 52px |
| Data row — alt | bg: neutral-50 (alternating rows) |
| Data row — dense | height: 40px \| text-sm — billing, lab orders |
| Row — hover | bg: primary-50 \| transition: 100ms |
| Row — selected | bg: primary-100 \| left border: 2px primary-600 |
| Footer/Total | bg: neutral-100 \| text: neutral-800 font-semibold \| border-top: 2px neutral-300 |

## 23.2 Sorting

| State | Specification |
|---|---|
| Default | ChevronsUpDown icon right of header (neutral-400) |
| Ascending | ChevronUp (primary-600) \| header text: primary-600 |
| Descending | ChevronDown (primary-600) \| header text: primary-600 |
| Behavior | Click: sort asc. Click again: desc. Third click: remove sort. |

## 23.3 Pagination — Full Spec

| Property | Specification |
|---|---|
| Position | Bottom of table \| padding-top: space-4 |
| Layout | Rows-per-page selector (left) \| Result count "Showing 1-25 of 143" (center) \| Page navigation (right) |
| Rows per page | Select: 10, 25, 50, 100 \| default: 25 |
| Page buttons | Previous \| 1 … 4 5 6 … 12 \| Next \| Height: 32px \| radius-default |
| Current page | bg: primary-600 \| text: white \| font-semibold |
| Other pages | bg: white \| border: 1px neutral-200 \| text: neutral-700 \| hover: bg neutral-50 |
| Ellipsis | Shown when >7 pages. Show first, last, current +/-1 always. |
| Prev/Next | Disabled (opacity-50, cursor-not-allowed) on first/last page |
| Mobile | Simplified: Previous [Page X of Y] Next — no individual page numbers |

## 23.4 Search, Filter & Bulk Select

### Search & Filter

| Property | Specification |
|---|---|
| Search bar | Input MD above table \| Search icon left \| 300px desktop, full-width mobile |
| Filter chips | Active filter: label + value + X \| bg: primary-100 \| text: primary-700 |
| Active count | "3 filters active" indicator with "Clear All" link |

### Bulk Select

| Property | Specification |
|---|---|
| Trigger | Checkbox in first column header \| checks/unchecks all visible rows |
| Bulk action bar | Appears above table replacing search bar when >0 rows selected |
| Bulk bar | bg: primary-600 \| text: white \| "X rows selected" \| action buttons \| X deselect all |

## 23.5 Column Width Guidelines

- Patient name: 200px minimum. Never truncate patient names.
- Date/time columns: 160px fixed.
- Status badge columns: 120px fixed.
- ID columns: 140px fixed.
- Action column: 100-140px, always last column, right-aligned.
- Amount/number columns: right-aligned text. Min 100px.

---

# 24. Tabs Component

### Tab Sizes

| Size | Specification |
|---|---|
| SM | Height: 32px \| padding: space-2 space-3 \| text-sm |
| MD (Default) | Height: 40px \| padding: space-2.5 space-4 \| text-base |
| LG | Height: 48px \| padding: space-3 space-5 \| text-md |

### Underline Variant (Default)

| State | Specification |
|---|---|
| Tab bar | border-bottom: 2px neutral-200 \| full width |
| Tab — inactive | text: neutral-500 \| font-medium \| no bg \| transparent underline |
| Tab — hover | text: neutral-700 \| border-bottom: 2px neutral-400 |
| Tab — active | text: primary-700 \| font-semibold \| border-bottom: 2px primary-600 |
| Tab — focus | outline: 2px solid primary-600 \| outline-offset: -2px |
| Tab — disabled | text: neutral-300 \| cursor: not-allowed |
| Active indicator | Animated: slides horizontally to active tab \| 200ms ease-in-out |

### Pill Variant

| State | Specification |
|---|---|
| Tab bar | bg: neutral-100 \| radius-default \| padding: space-1 \| inline-flex |
| Tab — inactive | bg: transparent \| text: neutral-600 |
| Tab — active | bg: white \| text: primary-700 \| font-semibold \| shadow-sm \| radius-md |
| Use for | Compact filter-style tabs, segmented controls inside cards |

### Tab Enhancements

| Feature | Specification |
|---|---|
| With badge | Count badge right of label \| text-xs \| radius-full \| min-width: 18px |
| With icon | Icon left of label \| icon-sm \| same color as label text |
| Overflow | Horizontal scroll mobile \| "More" dropdown desktop for overflow tabs |
| Vertical | Tab list left (200px) \| content right \| active: 2px left border primary-600 |

- **Keyboard:** Arrow Left/Right navigate tabs. Enter/Space activates. Home/End go to first/last.

---

# 25. Breadcrumb Component

| Property | Specification |
|---|---|
| Font | text-sm (13px) \| font-medium (500) |
| Separator | ChevronRight icon \| icon-xs (12px) \| neutral-400 \| margin: 0 space-1.5 |
| Inactive | text: neutral-500 \| hover: text neutral-700, underline |
| Current | text: neutral-800 \| font-semibold \| not clickable |
| Max items | 4 max. If more: first + ellipsis button + last 2. Click ellipsis to expand. |
| Mobile | Show only: Parent > Current (last 2 items) |
| Placement | Below topbar, above H1 \| margin-bottom: space-2 |
| ARIA | `nav` with `aria-label="Breadcrumb"` \| `ol` list \| current: `aria-current="page"` |

---

# 26. Badge / Tag Component

## 26.1 Color Variants

| Variant | Background | Text Color | Border |
|---|---|---|---|
| Success | success-100 (#DCFCE7) | success-700 (#15803D) | 1px success-200 |
| Warning | warning-100 (#FEF3C7) | warning-700 (#B45309) | 1px warning-200 |
| Error | error-100 (#FEE2E2) | error-700 (#B91C1C) | 1px error-200 |
| Info | info-100 (#DBEAFE) | info-700 (#1D4ED8) | 1px info-200 |
| Neutral | neutral-100 (#F1F5F9) | neutral-600 (#475569) | 1px neutral-200 |
| Primary | primary-100 (#DBEAFE) | primary-700 (#1D4ED8) | 1px primary-200 |
| AI | accent-100 (#CCFBF1) | accent-700 (#0F766E) | 1px accent-200 |
| Role | purple-100 (#EDE9FE) | purple-700 (#6D28D9) | 1px purple-200 |

## 26.2 Size Variants

| Size | Specification |
|---|---|
| SM | height: 18px \| padding: 1px 6px \| text-xs (11px) \| font-medium \| uppercase \| tracking-wider \| radius-sm |
| MD (Default) | height: 22px \| padding: 2px 8px \| text-xs (11px) \| font-medium \| uppercase \| radius-sm |
| LG | height: 26px \| padding: 4px 10px \| text-sm (13px) \| font-medium \| radius-md \| icon optional |

## 26.3 Special Badge Types

### Dot Badge

| Property | Specification |
|---|---|
| Shape | 8px circle \| radius-full |
| Position | Absolute top-right of parent \| translate(-25%, -25%) |
| Color | error-600 for alerts \| primary-600 general \| success-600 positive |

### Count Badge

| Property | Specification |
|---|---|
| Min width | 18px \| height: 18px \| radius-full |
| Content | Number \| text-xs font-bold \| centered \| "99+" for counts above 99 |
| Color | error-600 bg, white text (urgent) \| neutral-700 bg, white text (general) |

### Removable Tag

| Property | Specification |
|---|---|
| X button | icon-xs (10px) right \| padding-right: space-1.5 \| clickable area: 16x16px min |
| Hover on X | icon turns error-600 |
| Remove animation | Fade out + scale down \| 150ms ease-in |

---

# 27. Appointment Status Badges

Every appointment status must be instantly distinguishable. All use Badge MD size with icon.

| Status | Background | Text | Border | Icon |
|---|---|---|---|---|
| Scheduled | primary-100 | primary-700 | primary-200 | Calendar |
| Confirmed | accent-100 | accent-700 | accent-200 | CheckCircle |
| Checked In | warning-100 | warning-700 | warning-200 | Clock |
| In Progress | #EDE9FE | #6D28D9 | #DDD6FE | Activity |
| Completed | success-100 | success-700 | success-200 | CheckCircle |
| Cancelled | error-100 | error-700 | error-200 | XCircle |
| No Show | neutral-100 | neutral-600 | neutral-200 | UserX |
| Rescheduled | #FFF7ED | #C2410C | #FED7AA | RefreshCw |

---

# 28. Tooltip Component

### Tooltip Specification

| Property | Specification |
|---|---|
| Background | neutral-900 (#0F172A) |
| Text | white \| text-sm (13px) \| font-normal \| leading-normal |
| Padding | 6px 12px (space-1.5 space-3) |
| Radius | radius-sm (4px) |
| Shadow | shadow-lg |
| Max width | 240px \| wraps to multi-line if longer |
| z-index | z-popover (500) — appears above modals |
| Arrow | 6px triangle \| same bg as tooltip \| positioned at trigger edge center |

### Tooltip Positioning

| Position | Specification |
|---|---|
| Top (default) | Appears above trigger \| arrow at bottom center pointing down |
| Bottom | Appears below \| arrow at top center pointing up |
| Left | Appears left \| arrow at right center pointing right |
| Right | Appears right \| arrow at left center pointing left |
| Auto-flip | If preferred position clips viewport edge, flip to opposite side |
| Offset | 8px gap between tooltip edge and trigger element |

### Tooltip Behavior

| Property | Specification |
|---|---|
| Appear delay | 400ms after hover/focus — prevents flicker on fast mouse movements |
| Disappear | Immediately on mouseleave/blur |
| Animation | Fade in + scale 95%→100% \| 150ms ease-out |
| Trigger | hover AND focus (keyboard accessible) |
| Mobile | Appears on tap. Tap outside to dismiss. |
| Content rules | Max 1-2 short sentences. No interactive elements inside. No HTML formatting. |

---

# 29. Popover Component

| Property | Specification |
|---|---|
| Background | white |
| Border | 1px neutral-200 |
| Radius | radius-lg (12px) |
| Shadow | shadow-xl |
| Padding | space-4 |
| Min/Max width | 200px / 320px |
| z-index | z-popover (500) |
| Trigger | Click (not hover) — popovers contain interactive content |
| Close | Click outside \| Escape key \| X button inside (optional) |
| With form | Can contain inputs, buttons, select — max 3 form fields |
| Differs from tooltip | Tooltip: hover, read-only. Popover: click, interactive content. |

---

# 30. Toast / Notification Component

### Toast Variants

| Variant | Specification |
|---|---|
| Success | bg: success-600 \| text: white \| CheckCircle icon \| Auto-dismiss: 4 seconds |
| Error | bg: error-600 \| text: white \| XCircle icon \| Auto-dismiss: 6 seconds (critical) |
| Warning | bg: warning-600 \| text: white \| AlertTriangle icon \| Auto-dismiss: 5 seconds |
| Info | bg: primary-600 \| text: white \| Info icon \| Auto-dismiss: 4 seconds |
| Loading | bg: neutral-700 \| text: white \| Loader2 spin icon \| No auto-dismiss |

### Toast Layout & Behavior

| Property | Specification |
|---|---|
| Position | Fixed: top-right \| top: space-6 from top \| right: space-6 from right |
| Width | 320px desktop \| calc(100% - space-8) mobile |
| Stack | Max 4 toasts. Newest on top. Oldest auto-dismissed first. |
| Anatomy | Icon (20px, left) + Title (font-semibold) + Body optional (text-sm) + X close (right) |
| Animation | Slide in from right: translateX 100%→0 + opacity 0→1 \| 300ms ease-out |
| Dismiss | Slide out right: translateX 0→100% \| 200ms ease-in |
| Padding | space-4 all sides \| gap: space-3 between icon and text |
| z-index | z-toast (600) — always topmost |
| Hover pause | Auto-dismiss timer pauses when user hovers |

### Toast With Action Button

| Property | Specification |
|---|---|
| Use | When toast requires user response: "Appointment saved. View appointment." |
| Button | Ghost variant in white \| text-sm \| underline style \| right of message |
| Max | One action button per toast only |

---

# 31. Alert / Banner Component

### Inline Alert

| Variant | Specification |
|---|---|
| Success | bg: success-50 \| border: 1px success-200 \| left: 4px success-600 \| icon: CheckCircle success-600 |
| Warning | bg: warning-50 \| border: 1px warning-200 \| left: 4px warning-600 \| icon: AlertTriangle warning-600 |
| Error | bg: error-50 \| border: 1px error-200 \| left: 4px error-600 \| icon: XCircle error-600 |
| Info | bg: primary-50 \| border: 1px primary-200 \| left: 4px primary-600 \| icon: Info primary-600 |
| Padding | space-4 \| radius-lg |
| Layout | Icon (icon-md left) + content (title font-semibold + body text-base) + X close (right, optional) |

### Page-Level Banner (Full Width)

| Property | Specification |
|---|---|
| Position | Below topbar \| above page content \| full width |
| Height | 48px minimum \| auto if content wraps |
| Warning banner | bg: warning-100 \| text: warning-900 \| AlertTriangle left \| dismiss X right |
| Info banner | bg: primary-100 \| text: primary-900 \| Info left \| dismiss X right |
| Error banner | bg: error-100 \| text: error-900 \| XCircle left \| X right (non-dismissible for critical) |
| Persistent | System maintenance banners are not dismissible — no X button |
| With action | Optional button right: "Upgrade Now", "Learn More" |

---

# 32. Progress Bar Component

### Linear Progress Bar

| Property | Specification |
|---|---|
| Track | Full width \| bg: neutral-200 \| radius-full |
| Height — XS | 4px — subtle inline (file upload) |
| Height — SM (Default) | 8px — standard indicator |
| Height — MD | 12px — prominent (onboarding, large uploads) |
| Fill | primary-600 default \| success-600 complete \| error-600 failure \| radius-full |
| Animation | width transition \| 300ms ease-out on each update |
| Label | text-sm neutral-600 right of bar \| or inside bar if height >= 12px |

### Indeterminate Progress

| Property | Specification |
|---|---|
| Behavior | Gradient sweep: primary-400→primary-600→primary-400 left to right |
| Duration | 1.5s linear infinite |
| Use | When total duration is unknown: API loading, form submission |

### Step Progress

| Property | Specification |
|---|---|
| Layout | Horizontal bar divided into N equal segments \| filled: color \| unfilled: neutral-200 |
| Segment gap | 2px between segments \| radius-full on each segment |
| Labels | Optional step labels below \| text-xs neutral-500 |

---

# 33. Accordion / Collapsible Component

### Accordion Item Structure

| Property | Specification |
|---|---|
| Trigger row | Full width button \| height: 52px \| padding: space-3 space-4 \| text-base font-semibold neutral-800 \| ChevronDown right |
| Icon rotation | ChevronDown rotates to ChevronUp when open \| transition: 200ms ease-in-out |
| Content panel | padding: space-4 \| border-top: 1px neutral-100 \| text-base neutral-700 leading-relaxed |
| Border | 1px neutral-200 on full item \| radius-lg on first and last |
| Divider | 1px neutral-100 between items (not on last) |

### Accordion Behavior

| Property | Specification |
|---|---|
| Single-open | Only one panel open at a time. Opening new panel closes previous. |
| Multi-open | Multiple panels open simultaneously. Use for FAQs and long lists. |
| Animation | Height expands: max-height 0→content \| opacity 0→1 \| 200ms ease-out |
| Collapse | Height: content→0 \| opacity 1→0 \| 150ms ease-in |
| Nested | One level deep only. Same visual spec, padding-left: space-4 offset. Max 2 levels. |
| Keyboard | Enter/Space toggle. Arrow Up/Down navigate triggers. Home/End first/last. |

### Accordion States

| State | Specification |
|---|---|
| Trigger — default | bg: white \| text: neutral-800 |
| Trigger — hover | bg: neutral-50 \| text: neutral-900 |
| Trigger — open | bg: white \| text: primary-700 \| icon: primary-600 |
| Trigger — focus | outline: 2px solid primary-600 \| outline-offset: -2px |
| Trigger — disabled | text: neutral-400 \| cursor: not-allowed |

---

# 34. Avatar Component

### Avatar Sizes

| Size | Specification |
|---|---|
| XS | 24x24px \| text-xs (10px initials) \| icon-xs icons |
| SM | 32x32px \| text-sm (11px initials) \| icon-sm icons |
| MD (Default) | 40x40px \| text-base (14px initials) \| icon-md icons |
| LG | 48x48px \| text-md (15px initials) \| icon-lg icons |
| XL | 64x64px \| text-xl (16px initials) \| icon-xl icons |

### Avatar Types

| Type | Specification |
|---|---|
| Image avatar | Photo \| object-fit: cover \| radius-full \| border: 2px white on dark backgrounds |
| Initials fallback | First + last initials \| bg color from name hash \| text: white \| font-semibold |
| Initials color palette | Rotate from: primary-600, teal-600, purple-600, warning-600, error-600 |
| Icon fallback | User icon (neutral-400) on neutral-100 bg \| radius-full \| when name unknown |
| Border | 2px white (on colored bg) \| 2px neutral-200 (on white bg) |

### Status Indicator Dot

| Property | Specification |
|---|---|
| Size | 10px circle \| border: 2px white |
| Position | Absolute bottom-right \| translate(25%, 25%) |
| Online | success-500 |
| Away | warning-500 |
| Busy | error-500 |
| Offline | neutral-400 |

### Avatar Group (Stack)

| Property | Specification |
|---|---|
| Layout | Horizontal overlap \| each avatar offset: -8px (-space-2) |
| Max visible | 4 avatars then +N overflow indicator |
| Overflow | Same size circle \| bg: neutral-200 \| text: neutral-600 \| text-xs |
| Border | 2px white border on each avatar to separate overlapping circles |

---

# 35. Chip / Filter Chip Component

### Chip Specification

| State | Specification |
|---|---|
| Height | 28px \| padding: space-1.5 space-3 \| radius-full \| text-sm font-medium |
| Default | bg: neutral-100 \| border: 1px neutral-200 \| text: neutral-700 |
| Hover | bg: neutral-200 \| border: neutral-300 |
| Selected | bg: primary-100 \| border: primary-200 \| text: primary-700 \| Check icon left (icon-xs) |
| Focus | outline: 2px solid primary-600 \| outline-offset: 2px |
| Disabled | bg: neutral-50 \| border: neutral-200 \| text: neutral-400 \| cursor: not-allowed |

### Removable Chip

| Property | Specification |
|---|---|
| Style | bg: primary-100 \| border: 1px primary-200 \| text: primary-700 \| X icon right |
| X button | icon-xs (10px) \| primary-500 default \| hover: error-600 \| clickable area 16x16px |
| Remove | Click X or press Delete/Backspace when chip is focused |

### Chip Group

| Property | Specification |
|---|---|
| Layout | flex-wrap \| gap: space-2 |
| Overflow | Wraps to new lines — no horizontal scroll on chip groups |
| All-clear | "Clear all" link at end when >2 chips active |

---

# 36. Sidebar Navigation Component

### Sidebar Dimensions

| Property | Specification |
|---|---|
| Expanded width | 260px \| Fixed left: 0, top: 0 \| height: 100vh \| z-index: z-sticky (200) |
| Collapsed width | 68px \| Icon-only mode \| tooltip on hover shows full label |
| Background | neutral-900 (#0F172A) |
| Right border | 1px neutral-800 |
| Collapse toggle | Button at bottom \| ChevronLeft/Right icon \| 200ms width transition |

### Nav Item States

| State | Specification |
|---|---|
| Default (inactive) | text: neutral-400 \| icon: neutral-400 \| bg: transparent \| font-medium \| height: 44px \| padding: space-3 space-4 |
| Hover | text: white \| icon: white \| bg: neutral-800 \| radius-default \| transition: 150ms |
| Active | text: white \| icon: white \| bg: primary-700 \| radius-default \| font-semibold |
| Active indicator | 3px left border in primary-400 on inside-left edge |
| Focus | outline: 2px solid primary-400 \| outline-offset: -2px |
| Group header | text: neutral-500 \| text-xs uppercase tracking-wider \| padding: space-6 space-4 space-2 \| not clickable |
| Notification badge | Error-500 count badge on Bell icon |

### Sidebar Structure (Top to Bottom)

| Section | Specification |
|---|---|
| Logo area | height: 64px \| logo (max-height: 32px) or NexusCare wordmark \| border-bottom: 1px neutral-800 |
| Hospital name | text-sm font-medium neutral-300 \| below logo \| only when tenant logo present |
| Nav — Main | Dashboard \| Patients \| Appointments \| Prescriptions \| Lab |
| Nav — Clinical | (group header) Staff Management \| Billing \| Analytics |
| Nav — System | (group header) Notifications (with badge) \| Settings |
| User profile | Fixed at bottom \| border-top: 1px neutral-800 \| Avatar (SM) + Name + Role badge |
| Collapse button | Just above user profile \| icon-only ghost \| full width |

### Sub-Navigation

| Property | Specification |
|---|---|
| Trigger | Nav item with ChevronRight right \| rotates down when open |
| Sub-items | padding-left: space-10 \| text-sm \| same hover/active states |
| Animation | Height expand \| 200ms ease-out |
| Max levels | One level deep — no nested sub-sub-menus |

---

# 37. Topbar Component

### Topbar Structure

| Property | Specification |
|---|---|
| Height | 64px fixed \| position: sticky top: 0 \| z-index: z-sticky (200) |
| Background | white \| border-bottom: 1px neutral-200 \| shadow-xs |
| Left zone | H1 page title (text-2xl font-bold neutral-800) + optional breadcrumb above it |
| Center | Optional global search bar (480px max-width) on screens >= 1280px |
| Right zone | Search icon (mobile) \| Notification bell \| Avatar + name + role + ChevronDown |

### Notification Bell & Drawer

| Property | Specification |
|---|---|
| Bell icon | icon-lg (20px) \| neutral-600 \| hover: neutral-900 |
| Count badge | error-600 \| count or "9+" \| SM badge \| top-right of bell |
| Click | Opens notification drawer from right \| width: 380px \| z-modal (400) |
| Drawer header | "Notifications" title \| "Mark all read" link (right) \| X close |
| Notification item | Avatar (XS) + content + timestamp \| unread: bg primary-50, 2px primary-600 left border \| read: white |
| Empty state | BellOff icon-xl \| "No notifications" \| neutral-500 |

### User Menu Dropdown

| Property | Specification |
|---|---|
| Trigger | Avatar (SM, 32px) + display name + ChevronDown |
| Panel | min-width: 200px \| shadow-xl \| radius-lg \| bg: white \| border: 1px neutral-200 |
| Header | Avatar (MD) + full name + email + role badge \| padding: space-4 \| border-bottom |
| Menu items | Profile Settings \| Switch Role (if applicable) \| divider \| Logout (error-600, LogOut icon) |
| Item hover | bg: neutral-50 |

### Mobile Topbar

| Zone | Specification |
|---|---|
| Left zone | Menu hamburger icon — opens sidebar as overlay drawer |
| Center | NexusCare logo or hospital name (max 20 chars) |
| Right | Bell icon with badge \| Avatar only (no name) |

---

# 38. Context Menu Component

| Property | Specification |
|---|---|
| Trigger | Right-click OR MoreHorizontal/MoreVertical icon button (Ghost icon-only) |
| Panel | bg: white \| border: 1px neutral-200 \| radius-lg \| shadow-xl \| min-width: 160px \| max-width: 240px |
| z-index | z-dropdown (100) |
| Position | At cursor (right-click) or below trigger. Auto-flips near viewport edges. |
| Item height | 36px \| padding: space-2 space-3 \| text-base neutral-700 \| icon-sm left optional |
| Item hover | bg: neutral-50 \| text: neutral-900 |
| Divider | 1px neutral-100 between groups |
| Disabled | text: neutral-400 \| cursor: not-allowed \| no hover |
| Destructive | text: error-600 \| error-colored icon \| hover bg: error-50 |
| Close | Click outside \| Escape \| item selection |
| Keyboard | Arrow Up/Down navigate \| Enter/Space activate \| Escape close |

---

# 39. Stepper / Wizard Component

### Horizontal Stepper

| State | Specification |
|---|---|
| Step circle | 32x32px \| radius-full \| step number or check icon centered |
| Pending | bg: white \| border: 2px neutral-300 \| text: neutral-500 \| font-semibold |
| Active | bg: primary-600 \| text: white \| shadow-sm |
| Completed | bg: success-600 \| CheckCircle white icon (no number) |
| Error | bg: error-600 \| X white icon |
| Connector line | 2px \| bg: neutral-200 pending / success-600 completed \| flex: 1 between circles |
| Step label | text-sm font-medium \| neutral-500 pending / primary-700 active / success-700 completed |

### Vertical Stepper

| Property | Specification |
|---|---|
| Layout | Step circles on left \| content on right \| 2px vertical connector left-aligned with circles |
| Content area | Title (text-base font-semibold) + description + form fields |
| Spacing | space-6 between steps |

### Stepper Navigation

| Property | Specification |
|---|---|
| Footer buttons | Back (Secondary) \| Next (Primary) \| Submit (Primary, last step only) |
| Next behavior | Validates current step before advancing. Error state shown if invalid. |
| Step clicking | Can click completed steps. Cannot skip to future steps. |
| Mobile | Shows "Step X of Y" text + progress bar below topbar only |

---

# 40. Form Layout Patterns

## 40.1 Single Column Form

| Property | Specification |
|---|---|
| Max width | 480px \| centered in modal or page |
| Field gap | space-5 (20px) between label+input groups |
| Submit | Full-width Primary LG button \| margin-top: space-6 |
| Use | Login, Register, Forgot Password, simple settings |

## 40.2 Two-Column Form

| Property | Specification |
|---|---|
| Max width | 720px |
| Grid | grid-cols-2 \| gap-x: space-6 \| gap-y: space-5 |
| Full-width fields | Notes, address, description, instructions — col-span-2 |
| Section divider | 1px neutral-200 rule + H4 title between logical groups |
| Use | Patient registration, staff profile, appointment booking |

## 40.3 Multi-Step Form

| Property | Specification |
|---|---|
| Step indicator | Horizontal Stepper at top (see Section 39) |
| Navigation | Back/Next. Next validates current step first. |
| Save state | Form state persisted in memory across steps. Never lose data on Back. |
| Cancel | Always available. Shows: "Discard changes and leave?" confirmation. |

## 40.4 Inline Edit Form

| Property | Specification |
|---|---|
| Trigger | Click display value → transforms to input in-place |
| Controls | Checkmark (save) \| X (cancel) appear inline right of input |
| Cancel | Also triggered by Escape key |
| Save | Also triggered by Enter (single-line) or Ctrl+Enter (textarea) |

## 40.5 Form Error Summary

| Property | Specification |
|---|---|
| Position | Top of form \| inline Error Alert component |
| Trigger | Appears on form submit when validation fails |
| Content | List of all field errors with anchor links to each field |
| Focus | Scrolls to error summary \| first error field receives focus |

---

# 41. Healthcare-Specific Components

## 41.1 Patient ID Badge

| Property | Specification |
|---|---|
| Format | `HOS-YYYY-NNNNNN` \| Courier New monospace \| text-sm \| neutral-700 |
| Container | bg: neutral-100 \| radius-sm \| padding: 2px 8px \| inline-flex \| Copy icon right |
| Copy | Copies to clipboard \| "Copied!" tooltip for 1.5 seconds |

## 41.2 Vitals Display Card

| Property | Specification |
|---|---|
| Grid layout | 3 columns desktop \| 2 tablet \| 1 mobile \| gap: space-4 |
| Each vital | Icon (icon-md) + Label (text-xs uppercase neutral-500) + Value (text-2xl font-bold neutral-800) + Unit (text-sm neutral-500) |
| Normal | Value: neutral-800 |
| High/Low | Value: error-600 \| AlertTriangle icon-xs error-600 \| bg: error-50 subtle |
| Borderline | Value: warning-600 \| AlertCircle icon-xs warning-600 \| bg: warning-50 subtle |
| Timestamp | text-xs neutral-400 \| "Recorded by Dr. X at 10:32 AM" \| below grid |

## 41.3 Medical Timeline

| Property | Specification |
|---|---|
| Layout | Vertical list \| left connector line: 2px neutral-200 \| each entry has date dot |
| Date dot | 12px circle \| Visit: primary-600 \| Lab: accent-500 \| Prescription: warning-500 \| Emergency: error-500 |
| Entry card | Date+time (text-xs neutral-500) \| title (text-base font-semibold) \| summary (text-sm neutral-600) |
| Expand | Click entry expands to show full SOAP note / result details |
| Gap | space-4 between timeline entries |

## 41.4 Prescription Item Row

| Property | Specification |
|---|---|
| Layout | Pill icon (accent-500) \| Drug name (font-semibold) \| Dose + frequency (text-sm neutral-600) \| Duration badge \| Status badge |
| Interaction | AlertTriangle (warning-500) if drug interaction \| hover for interaction detail tooltip |
| Divider | 1px neutral-100 between rows |

## 41.5 Drug Interaction Warning

| Severity | Specification |
|---|---|
| Major | bg: error-50 \| border: 1px error-200 \| AlertTriangle error-600 \| text: error-900 \| blocks submission \| requires doctor override acknowledgement |
| Moderate | bg: warning-50 \| border: 1px warning-200 \| AlertCircle warning-600 \| warning shown, does not block |
| Minor | bg: neutral-50 \| border: 1px neutral-200 \| Info neutral-500 \| informational only |

## 41.6 Appointment Queue Card

| Property | Specification |
|---|---|
| Status strip | Left 4px border = status color |
| Queue number | text-3xl font-bold primary-600 \| left side |
| Patient info | Name (font-semibold) + Patient ID (text-sm neutral-500) + Age |
| Actions | Start Consultation (Primary SM) \| Check In (Secondary SM) \| Cancel (Ghost SM) |

## 41.7 Lab Result Row

| State | Specification |
|---|---|
| Layout | Test name (font-semibold) \| Result value + unit \| Reference range \| Status badge |
| Normal | Result: neutral-800 \| Status: Success badge "Normal" |
| High | Result: error-600 bold \| arrow up icon \| Status: Error badge "High" |
| Low | Result: error-600 bold \| arrow down icon \| Status: Error badge "Low" |
| Critical | Full row: bg error-50 \| AlertTriangle error-600 \| requires acknowledgement |
| Reference | text-sm neutral-400 \| format: "Normal: 70-100 mg/dL" |

## 41.8 Allergy Tag

| Severity | Specification |
|---|---|
| Severe | bg: error-100 \| border: 1px error-200 \| text: error-700 \| radius-full \| AlertTriangle icon-xs error-600 left |
| Moderate | Warning variant — same structure with warning colors |
| Mild | Neutral variant |
| Placement | Prominently displayed in patient header — never hidden |
| NKA | Neutral badge: "NKA" — text-sm neutral-600 |

## 41.9 Diagnosis Badge

| Type | Specification |
|---|---|
| Primary | bg: primary-100 \| text: primary-800 \| border: primary-200 \| ICD code in Courier New prefix |
| Secondary | bg: neutral-100 \| text: neutral-700 \| border: neutral-200 |
| ICD code | Courier New font \| text-xs \| neutral-500 \| displayed before diagnosis name |

## 41.10 Emergency Alert Banner

| Property | Specification |
|---|---|
| Position | Full-width \| top: 0 \| fixed \| z-index: z-max (9999) |
| Style | bg: error-600 \| text: white \| font-semibold \| AlertTriangle icon left \| animated pulse |
| Dismiss | NOT dismissible by regular users. Only Hospital Admin can dismiss. |
| Use | Code Blue alerts, hospital-wide emergencies, critical system outages only |

---

# 42. Data Visualization Components

## 42.1 Chart Color Palette

| Series | Token | Hex | Usage |
|---|---|---|---|
| Series 1 (Primary) | accent-500 | `#14B8A6` | First/main data series |
| Series 2 | primary-500 | `#3B82F6` | Second data series |
| Series 3 | purple-500 | `#8B5CF6` | Third data series |
| Series 4 | warning-500 | `#F59E0B` | Fourth data series |
| Series 5 | error-500 | `#EF4444` | Fifth data series |
| Series 6+ | neutral-400 | `#94A3B8` | De-emphasized additional series |

## 42.2 Chart Types

### Line Chart

| Property | Specification |
|---|---|
| Use | Revenue over time, appointment trends, patient growth |
| Line | 2px stroke \| accent-500 primary \| dots on data points: 6px circle, white center |
| Hover | Tooltip shows exact value + date \| 1px neutral-200 dashed vertical reference line |
| Grid | Horizontal only \| 1px neutral-100 \| very subtle |

### Bar Chart

| Property | Specification |
|---|---|
| Use | Revenue by department, appointments by doctor |
| Bar radius | radius-sm (4px) on top corners only |
| Hover | bg opacity 80% \| tooltip |
| Labels | Value labels above bars \| text-xs neutral-600 |

### Donut / Pie Chart

| Property | Specification |
|---|---|
| Use | Appointment type breakdown, diagnosis distribution |
| Max slices | 5 segments. Others grouped into "Other" (neutral-400) slice. |
| Hole | 60% hole for donut. Center shows total or key metric. |
| Hover | Slice lifts 4px out \| tooltip: label + value + % |
| Legend | Below chart \| horizontal \| 8px colored dot + label \| text-sm neutral-600 |

### KPI Stat Card

| Property | Specification |
|---|---|
| Metric | text-4xl/5xl font-bold tracking-tighter neutral-800 |
| Label | text-sm uppercase tracking-wide neutral-500 |
| Trend | TrendingUp (success-600) or TrendingDown (error-600) + % change text-sm |
| Period | text-xs neutral-400 "vs last month" below trend |

### Sparkline

| Property | Specification |
|---|---|
| Dimensions | 60px height \| full card width minus padding |
| Style | No axes, no labels \| 2px stroke \| accent-500 \| subtle area fill at 10% opacity |
| Use | Inside stat cards only as supporting context |

## 42.3 Chart Visual Rules

| Rule | Specification |
|---|---|
| Background | Always on white card surface — never floating on page bg |
| Grid lines | Horizontal only \| neutral-100 \| subtle, never distracting |
| Axis labels | text-xs neutral-500 \| no bold \| enough labels without clutter |
| Tooltip | bg: neutral-900 \| text: white \| radius-md \| shadow-lg \| exact value + label + date |
| Legend | Below chart \| horizontal \| 8px colored dot + label \| text-sm neutral-600 |
| No data | Empty state message centered in chart area \| never show empty axes |
| Loading | Skeleton shimmer rectangle same dimensions as loaded chart |
| Responsive | Reflows to container width. Remove axis labels on small containers. |

---

# 43. Layout System

## 43.1 Breakpoints

| Token | Min Width | Usage |
|---|---|---|
| screen-sm | 640px | Large phones landscape |
| screen-md | 768px | Tablets — iPad portrait (clinical tablets) |
| screen-lg | 1024px | iPad landscape, small laptops |
| screen-xl | 1280px | Standard desktop — primary design target |
| screen-2xl | 1536px | Large monitors — Analytics/Admin |

## 43.2 App Shell Structure

| Property | Specification |
|---|---|
| Sidebar | Fixed left \| 260px expanded \| 68px collapsed \| 100vh \| z-sticky (200) |
| Main area | margin-left: 260px (expanded) \| transitions with sidebar |
| Topbar | Sticky top: 0 \| 64px \| within main area \| z-sticky (200) |
| Content zone | padding: space-6 desktop \| space-4 tablet \| space-3 mobile \| below topbar |
| Scroll | Main area scrolls vertically. Sidebar does not scroll. Topbar sticks. |

## 43.3 Content Max-Widths

| Page Type | Max Width |
|---|---|
| Dashboard | none — full content width |
| List pages | none — tables use all available space |
| Form pages | 720px centered for full-page forms |
| Single column forms | 480px centered |
| Detail pages | none — 2/3 + 1/3 grid handles width |
| Article/text content | 760px max-width for long-form text |

## 43.4 Page Layout Patterns

### Dashboard Page
- Row 1: KPI stat cards — 4 columns xl, 2 md, 1 sm — gap: space-6
- Row 2: Charts — 2 columns (2/3 + 1/3) xl, 1 column md — gap: space-6
- Row 3: Tables or queues — full width

### List Page (Patients, Appointments, Staff)
- Topbar: Page title left + primary action button right
- Filter/search bar: full width below topbar \| margin-bottom: space-4
- Table: full width, fills remaining viewport height

### Detail / Record Page
- Left column (2/3 width): vitals, visit history, notes
- Right column (1/3 width): summary card, quick actions, upcoming appointments
- On tablet: stacks vertically, summary card first

## 43.5 Grid System

| Context | Grid Specification |
|---|---|
| Dashboard KPI row | grid-cols-4 xl / grid-cols-2 md / grid-cols-1 sm \| gap-6 |
| Dashboard chart row | grid-cols-3 xl (chart=2, sidebar=1) / grid-cols-1 md |
| Patient record | grid-cols-3 xl (main=2, aside=1) / grid-cols-1 md |
| Form fields | grid-cols-2 lg / grid-cols-1 sm \| gap-x-6 gap-y-5 |
| Staff grid | grid-cols-4 xl / grid-cols-2 md / grid-cols-1 sm |
| Vitals grid | grid-cols-3 lg / grid-cols-2 md / grid-cols-1 sm |

## 43.6 Scroll Behavior

- Main content: default scroll. Custom scrollbar only if unavoidable: 6px, neutral-300 thumb.
- Modal body: internal scroll only. Never scroll background page behind modal.
- Table on mobile: horizontal scroll. Gradient fade on right edge when content overflows.

---

# 44. State Patterns — Loading, Empty, Error

## 44.1 Loading States

> **⚠️ Rule: No full-page spinners.**
> Every data-fetching view shows skeleton UI, not a spinner. Spinners are exclusively for button loading states and inline indicators. Full-page spinners block the entire UI and are forbidden.

### Skeleton UI Rules

| Property | Specification |
|---|---|
| Shape match | Skeleton shape must match loaded content — skeleton cards same dimensions as real cards |
| Color | Base: neutral-200 \| shimmer: neutral-100 wave |
| Animation | Gradient sweep left→right \| 1.5s linear infinite \| respect prefers-reduced-motion |
| CSS | `background: linear-gradient(90deg, #E2E8F0 25%, #F1F5F9 50%, #E2E8F0 75%)` \| `background-size: 200%` \| `animation: shimmer 1.5s linear infinite` |

### Skeleton Patterns by Module

| Module | Skeleton Pattern |
|---|---|
| Dashboard | 4 stat card skeletons + 2 chart placeholder boxes + 5 table row skeletons |
| Patient list | Search bar skeleton + 10 table row skeletons |
| Patient record | Header skeleton + 2-column layout with card skeletons in each |
| Appointment calendar | Calendar grid day skeletons + appointment slot line skeletons |
| Prescription form | Drug input skeleton + multiple item row skeletons |
| Lab results | Test name + result + reference range skeletons |
| Analytics charts | Rectangle placeholder same height as chart container |

## 44.2 Empty States

Every module with a data list MUST have a defined empty state. They are a primary user experience moment.

| Module | Empty Message | Action |
|---|---|---|
| Patients | No patients registered yet | Add First Patient (Primary button) |
| Appointments | No appointments scheduled | Book Appointment (Primary button) |
| Prescriptions | No prescriptions for this patient | Create Prescription (doctor role only) |
| Lab Orders | No lab tests ordered | Order Lab Test (doctor role only) |
| Billing | No invoices generated | None — informational |
| Staff | No staff members added | Invite Staff (Primary button) |
| Notifications | You are all caught up! | None — positive empty state |
| Search results | No results for [query] | Clear filters (link button) |
| Analytics | No data for this time period | Select different date range |
| Drug inventory | No drugs in inventory | Add Drug (Primary button) |
| Timeline | No medical history recorded | Add Visit Note (doctor role) |

### Empty State Anatomy

| Property | Specification |
|---|---|
| Icon | icon-3xl (48px) \| neutral-300 \| module-relevant icon |
| Title | text-xl font-semibold neutral-700 \| names what is empty |
| Body | text-base neutral-500 \| optional \| 1-2 lines of context |
| Action | Primary MD button \| only when direct creation action is available |
| Layout | Centered \| padding-top: 20% of container \| padding: space-16 |

## 44.3 Error States

### Network / API Error

| Property | Specification |
|---|---|
| Display | Full container replaced — not overlaid on stale data |
| Icon | WifiOff or AlertTriangle \| icon-3xl \| error-300 |
| Title | "Something went wrong" \| text-xl font-semibold neutral-700 |
| Body | Human-readable message. Error code in text-xs for support. |
| Action | "Try Again" button (Secondary) \| retries the failed request |
| Retry | Show skeleton on retry. After 3 failures: "Contact support" link. |

### Form Validation Errors

| Property | Specification |
|---|---|
| Field-level | Error message immediately below field \| error-600 + AlertCircle \| text-sm |
| Form-level | Error Alert at top listing all errors — on backend validation error |
| Specificity | Never generic messages for form errors. Be field-specific. |
| Focus | First error field receives focus automatically on submit failure |

### Error Pages

| Error | Specification |
|---|---|
| 404 Not Found | Full page \| illustration \| "Page not found" H1 \| "Go to Dashboard" Primary button |
| 403 Forbidden | Full page \| Lock icon \| "You do not have permission" \| "Go Back" button |
| 401 Unauthorized | Redirect immediately to login — no error page shown |
| Session expired | Toast: "Session expired. Please log in again." \| Redirect to login |

---

# 45. Interaction State Completeness Checklist

Every interactive element MUST have ALL applicable states defined and implemented. No exceptions.

| State | Required For |
|---|---|
| Default | All interactive elements — the baseline visual |
| Hover | Buttons, links, nav items, table rows (clickable), cards (clickable), dropdown items |
| Focus | ALL interactive elements — visible focus ring required. Never remove outline. |
| Active/Pressed | Buttons (scale 0.98), nav items, accordion triggers, tab items |
| Loading | Buttons triggering async actions, data-fetching containers, table refresh |
| Disabled | Buttons, inputs, selects, checkboxes, radios, toggles — when action unavailable |
| Error | Inputs, forms, async toast notifications |
| Success | Form submit toast, async confirmation, inline input validation |
| Empty | Tables, lists, dashboards — every data container has an empty state |
| Selected | Table rows (checkbox), nav items (active), filter chips, radio, checkbox |
| Read-only | Input fields displaying non-editable content |
| Skeleton | All data-fetching containers while data loads |

---

# 46. Accessibility Guidelines

## 46.1 Contrast Ratios (WCAG AA)

| Color Combination | Ratio | Status |
|---|---|---|
| neutral-800 on white | 14.7:1 | ✅ Exceeds AAA |
| neutral-700 on white | 10.7:1 | ✅ Exceeds AAA |
| primary-600 on white | 4.6:1 | ✅ Passes AA |
| white on primary-600 | 4.6:1 | ✅ Passes AA |
| white on primary-700 | 6.6:1 | ✅ Exceeds AA |
| white on neutral-900 | 18.1:1 | ✅ Exceeds AAA |
| success-600 on white | 4.5:1 | ✅ Passes AA — verify at small sizes |
| error-600 on white | 4.7:1 | ✅ Passes AA |
| neutral-500 on white | 4.0:1 | ⚠️ Use only for text-sm+ (18px+) — fails at smaller |
| neutral-400 on white | 2.6:1 | ❌ FAILS AA — decorative only, never for text |

## 46.2 Focus Visible Spec (WCAG 2.2)

| Element | Specification |
|---|---|
| Primary elements | `outline: none` \| `box-shadow: 0 0 0 3px rgba(37,99,235,0.35)` (shadow-focus-primary) |
| Error elements | `box-shadow: 0 0 0 3px rgba(220,38,38,0.35)` (shadow-focus-error) |
| On dark surfaces | `outline: 2px solid white` \| `outline-offset: 2px` (e.g. sidebar items) |
| Never remove | Never set `outline: none` without providing an equivalent custom focus indicator |
| Minimum size | Focus indicator: minimum 3px width, 3:1 contrast with adjacent colors (WCAG 2.2 3.3) |

## 46.3 Keyboard Navigation

| Component | Keyboard Behavior |
|---|---|
| Modal | Trap focus. Tab cycles within. Escape closes (not alert dialogs). |
| Dropdown/Select | Arrow Down opens. Arrow Up/Down navigate. Enter selects. Escape closes. |
| Table | Tab moves rows (if selectable). Space toggles checkbox. Enter opens record. |
| Sidebar nav | Tab navigates. Enter/Space activates. Arrow keys for sub-menus. |
| Date picker | Arrow keys navigate days. Enter selects. Page Up/Down change month. |
| Tabs | Arrow Left/Right navigate. Enter/Space activates. Home/End first/last. |
| Accordion | Enter/Space toggle. Arrow Up/Down navigate. Home/End first/last. |
| Context menu | Arrow Up/Down navigate. Enter activates. Escape closes. |
| Slider | Arrow Left/Right adjust value. Home/End go to min/max. |
| Form | Tab order follows visual left-to-right, top-to-bottom. Enter submits last field. |

## 46.4 Required ARIA Attributes

- Icon-only buttons: `aria-label="[Action description]"` — always, no exceptions.
- Form inputs: visible label + `id` + `htmlFor` matching label. No exceptions.
- Status badges: `aria-label="Status: [value]"` for screen reader context.
- Modal: `role="dialog"` \| `aria-modal="true"` \| `aria-labelledby="[header id]"`.
- Table: `role="table"` \| `<th>` with `scope="col"` \| caption or `aria-label` on table.
- Loading: `aria-busy="true"` on loading container \| `aria-live="polite"` on content region.
- Error messages: linked to input via `aria-describedby="[error-id]"`.
- Tabs: `role="tablist"` \| `role="tab"` \| `role="tabpanel"` \| `aria-selected` \| `aria-controls`.
- Accordion: `<button>` with `aria-expanded` \| `aria-controls` pointing to panel.
- Navigation: `<nav>` element with `aria-label="Main navigation"` (sidebar).
- Page: single `<h1>`. Skip-to-content link at very top of every page.

---

# 47. Responsive Design Rules

## 47.1 Per-Component Responsive Behavior

| Component | Desktop (xl, 1280px+) | Tablet / Mobile (< 1024px) |
|---|---|---|
| Sidebar | Fixed 260px — always visible | Hidden — opens as overlay drawer on hamburger tap |
| Topbar | Full: title + search + notifications | Hamburger + page title + bell icon only |
| KPI stat cards | 4 columns | 2 columns tablet \| 1 column mobile |
| Charts | Side by side (2/3 + 1/3) | Stacked full width |
| Data tables | Full width, all columns visible | Horizontal scroll — priority columns only |
| Modals | Centered with max-width | Full screen: 100vw, 100vh, radius-none |
| Drawers | 480px fixed width from right | Full width bottom sheet |
| Form grids | 2 columns | 1 column always |
| Patient record | 2/3 + 1/3 column layout | Stacked — summary card first |
| Primary buttons | Auto width | Full width inside forms and modal footers |
| Breadcrumbs | Full path visible | Parent > Current only |
| Tabs | All tabs in row | Horizontal scroll or More dropdown |

## 47.2 Touch Target Rules

- Minimum touch target: 44x44px for ALL interactive elements on touch devices.
- Expand hit area via padding — not element size — when visual must stay small.
- Minimum spacing between adjacent touch targets: 8px to prevent mis-taps.
- Table row actions on mobile: open action sheet (bottom sheet) instead of inline icons.

---

# 48. Print Stylesheet Rules

Clinical staff print lab reports, prescriptions, and patient summaries. Print styles must produce clean, professional output.

### Elements Hidden on Print

| Element | Rule |
|---|---|
| Sidebar | `display: none` |
| Topbar | `display: none` |
| All buttons | `display: none` |
| Toast/notifications | `display: none` |
| Filter bars | `display: none` |
| Pagination controls | `display: none` |
| Dropdown menus | `display: none` |
| Page-level banners | `display: none` |

### Print Typography

| Property | Specification |
|---|---|
| Font | Body: 11pt \| H1: 18pt \| H2: 14pt \| H3: 12pt |
| Font family | Arial — no web fonts in print |
| Line height | 1.4 — tighter than screen for paper efficiency |
| Color | All text: black \| Remove all bg colors \| Remove shadows |
| Links | Show URL: `a[href]::after { content: " (" attr(href) ")" }` |

### Page Break Rules

| Rule | Specification |
|---|---|
| Never break inside | Vitals card, prescription row, lab result row, patient header |
| Always break before | New patient section in multi-patient print, H1 page title |
| Widows/orphans | `widow: 2` \| `orphan: 2` |

### Lab Report Print Spec

| Property | Specification |
|---|---|
| Header | Hospital logo + name + report title + patient name + DOB + report date |
| Results table | Full width \| all borders visible \| black text \| High/Low as text (H)/(L) — not color |
| Signature line | "Reviewed by: __________ Date: __________" at bottom |
| Footer | Page X of Y \| printed date \| report ID |

### Prescription Print Spec

| Property | Specification |
|---|---|
| Header | Hospital letterhead \| doctor name + license number + date |
| Drug list | Numbered \| drug name + dose + frequency + duration \| each on separate line |
| Instructions | Patient instructions \| 12pt \| bordered box |
| Signature | Signature line at bottom \| stamp area |

---

# 49. RBAC-Aware UI Rules

The UI adapts based on the authenticated user role. This is a security requirement, not a feature.

## 49.1 Element Visibility Rules

| UI Element | Visibility Rule |
|---|---|
| Add Patient button | Receptionist and Hospital Admin only (patients:create) |
| Edit patient record | Doctor and Hospital Admin only |
| Write prescription | Doctor only (prescriptions:create) |
| Dispense medication | Pharmacist only (prescriptions:dispense) |
| Upload lab result | Lab Technician only (lab:upload_results) |
| Review lab result | Doctor only (lab:review_results) |
| Billing tab | Receptionist, Accountant, Hospital Admin only |
| Staff Management nav | Hospital Admin only |
| Analytics nav | Hospital Admin + Doctor (limited view) only |
| Delete buttons | Hospital Admin only — never visible to other roles |
| Super Admin section | Super Admin only — entirely absent for all other roles |

## 49.2 Navigation Visibility by Role

| Nav Item | Super Admin | Hosp Admin | Doctor | Nurse | Receptionist | Pharmacist | Patient |
|---|---|---|---|---|---|---|---|
| Dashboard | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Patients | No | Yes | Yes | Yes | Yes | Read | Own |
| Appointments | No | Yes | Yes | Read | Yes | No | Own |
| Prescriptions | No | No | Yes | Read | No | Yes | Own |
| Lab | No | No | Yes | Read | No | No | Own |
| Billing | Yes | Yes | No | No | Read | No | Own |
| Staff Mgmt | Yes | Yes | No | No | No | No | No |
| Analytics | Platform | Yes | Limited | No | No | No | No |
| Settings | Yes | Yes | No | No | No | No | No |
| Platform Mgmt | Yes | No | No | No | No | No | No |

## 49.3 RBAC Implementation Rules

- Never show a button or link that will return a 403. Check permissions before rendering.
- Sidebar nav items filter based on role — items are absent, never greyed out.
- Direct URL access to forbidden page: redirect to dashboard with error toast.
- Frontend checks for UX only. Backend enforces all permissions. Frontend is never the sole security layer.

---

# 50. Multi-Tenant UI Rules

### Per-Tenant Branding

| Property | Specification |
|---|---|
| Logo | Hospital logo in sidebar top (max-height: 32px, max-width: 180px) — replaces NexusCare wordmark |
| Name | Hospital name below logo \| text-sm font-medium neutral-300 |
| Favicon | NexusCare default favicon in MVP. Hospital-specific favicons are enterprise roadmap. |
| Colors | NOT customizable per tenant in MVP. NexusCare system colors apply universally. |

### Tenant Context Indicator

| Property | Specification |
|---|---|
| Super Admin viewing tenant | Prominent banner: "Viewing: [Hospital Name]" \| bg: warning-100 \| text: neutral-700 \| "Exit View" button right |
| API isolation | Every API call carries `hospitalId`. UI must never show data from another hospital. |
| Super Admin dashboard | Platform-level metrics only — no patient/appointment data |

---

# 51. Dark Mode Readiness

Dark mode is not built in MVP. The token architecture must support it. All colors are applied via CSS custom properties — zero component rewrites required to add dark mode.

> **Token Architecture Requirement**
> Use CSS custom properties for all colors: `--color-bg-page`, `--color-bg-surface`, `--color-text-primary` etc. Light mode defines variables in `:root`. Dark mode overrides them in `[data-theme=dark]`. Components reference variables only — never raw hex.

| Light Mode Variable | Dark Mode Override Value |
|---|---|
| `--color-bg-page: #F8FAFC` | → `#0F172A` (neutral-900) |
| `--color-bg-surface: #FFFFFF` | → `#1E293B` (neutral-800) |
| `--color-bg-elevated: #FFFFFF` | → `#334155` (neutral-700) |
| `--color-text-primary: #1E293B` | → `#F1F5F9` (neutral-100) |
| `--color-text-secondary: #64748B` | → `#94A3B8` (neutral-400) |
| `--color-border-default: #E2E8F0` | → `#334155` (neutral-700) |
| `--color-bg-sidebar: #0F172A` | → `#020617` (neutral-950) |
| `--color-bg-input: #FFFFFF` | → `#1E293B` (neutral-800) |

---

# 52. Tailwind CSS Token Mapping

All design tokens map directly to Tailwind config. Custom values extend the default theme — never replace it.

```js
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#EFF6FF', 100: '#DBEAFE', 200: '#BFDBFE', 300: '#93C5FD',
          400: '#60A5FA', 500: '#3B82F6', 600: '#2563EB', 700: '#1D4ED8',
          800: '#1E40AF', 900: '#1E3A8A', 950: '#172554'
        },
        accent: {
          50: '#F0FDFA', 100: '#CCFBF1', 200: '#99F6E4', 300: '#5EEAD4',
          400: '#2DD4BF', 500: '#14B8A6', 600: '#0D9488', 700: '#0F766E',
          800: '#115E59', 900: '#134E4A'
        },
        neutral: {
          50: '#F8FAFC', 100: '#F1F5F9', 200: '#E2E8F0', 300: '#CBD5E1',
          400: '#94A3B8', 500: '#64748B', 600: '#475569', 700: '#334155',
          800: '#1E293B', 900: '#0F172A', 950: '#020617'
        },
        success: {
          50: '#F0FDF4', 100: '#DCFCE7', 200: '#BBF7D0',
          500: '#22C55E', 600: '#16A34A', 700: '#15803D', 900: '#14532D'
        },
        warning: {
          50: '#FFFBEB', 100: '#FEF3C7', 200: '#FDE68A',
          500: '#F59E0B', 600: '#D97706', 700: '#B45309', 900: '#78350F'
        },
        error: {
          50: '#FEF2F2', 100: '#FEE2E2', 200: '#FECACA',
          500: '#EF4444', 600: '#DC2626', 700: '#B91C1C', 900: '#7F1D1D'
        },
        info: {
          50: '#EFF6FF', 100: '#DBEAFE', 600: '#2563EB', 900: '#1E3A8A'
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'Courier New', 'monospace'],
      },
      fontSize: {
        'xs': '11px', 'sm': '13px', 'base': '14px', 'md': '15px',
        'lg': '16px', 'xl': '18px', '2xl': '20px', '3xl': '24px',
        '4xl': '28px', '5xl': '32px', 'display': '36px',
      },
      lineHeight: {
        'none': '1.0', 'tight': '1.25', 'snug': '1.375',
        'normal': '1.5', 'relaxed': '1.625', 'loose': '2.0',
      },
      spacing: {
        'px': '1px', '0.5': '2px', '1': '4px', '1.5': '6px',
        '2': '8px', '2.5': '10px', '3': '12px', '4': '16px',
        '5': '20px', '6': '24px', '7': '28px', '8': '32px',
        '10': '40px', '12': '48px', '16': '64px', '20': '80px', '24': '96px',
      },
      borderRadius: {
        'none': '0', 'sm': '4px', 'md': '6px', 'DEFAULT': '8px',
        'lg': '12px', 'xl': '16px', '2xl': '20px', 'full': '9999px',
      },
      boxShadow: {
        'xs':    '0 1px 2px rgba(0,0,0,0.05)',
        'sm':    '0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)',
        'md':    '0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06)',
        'lg':    '0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)',
        'xl':    '0 20px 25px rgba(0,0,0,0.1), 0 10px 10px rgba(0,0,0,0.04)',
        '2xl':   '0 25px 50px rgba(0,0,0,0.15)',
        'inner': 'inset 0 2px 4px rgba(0,0,0,0.06)',
        'focus-primary': '0 0 0 3px rgba(37,99,235,0.35)',
        'focus-error':   '0 0 0 3px rgba(220,38,38,0.35)',
        'focus-success': '0 0 0 3px rgba(22,163,74,0.35)',
      },
      zIndex: {
        'dropdown': '100', 'sticky': '200', 'overlay': '300',
        'modal': '400', 'popover': '500', 'toast': '600', 'max': '9999',
      },
      transitionDuration: {
        'instant': '50ms', 'fast': '100ms', 'default': '150ms',
        'medium': '200ms', 'slow': '300ms', 'xslow': '500ms',
      },
      transitionTimingFunction: {
        'ease-in':     'cubic-bezier(0.4, 0, 1, 1)',
        'ease-out':    'cubic-bezier(0, 0, 0.2, 1)',
        'ease-in-out': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
};
```

---

# 53. Design Principles

## 53.1 Core Principles (Ranked by Priority)

| Priority | Principle | What It Means for NexusCare |
|---|---|---|
| 1 | **Clarity** | Medical staff are under time pressure. Every screen must communicate its purpose within 3 seconds. Remove everything that does not serve the immediate task. |
| 2 | **Consistency** | The same interaction works the same way everywhere. A doctor using prescriptions should not re-learn patterns from appointments. Every token, component, and pattern exists exactly once. |
| 3 | **Density** | Hospital UIs need more information per screen than consumer apps. Use compact spacing. Avoid decorative whitespace. Clinical tables show 25+ rows by default. |
| 4 | **Speed** | Every interaction must feel instant. Use optimistic UI for writes. Use skeleton loaders — never block UI waiting for data. Perceived performance is as important as actual performance. |
| 5 | **Trust** | Healthcare is high-stakes. Errors are costly. The correct action must be obvious. Destructive actions must be hard to trigger accidentally. Communicate clearly when something goes wrong. |
| 6 | **Accessibility** | Clinical staff work in difficult environments — bright windows, gloved hands, poor lighting, high cognitive load. Design for real conditions, not ideal ones. |

## 53.2 What Is Forbidden — Non-Negotiable Rules

| Never Do This | Why |
|---|---|
| Color as the only status signal | Color-blind users and clinical lighting make color-only signals unreliable and inaccessible. |
| Full-page spinners | They block the entire UI. Use skeleton loaders for page-level loading. |
| Autosubmitting forms | Never submit automatically. Always require explicit user action. |
| Removing the focus ring | Breaks keyboard navigation. Use the design system focus ring — no `outline: none` without replacement. |
| Raw technical error messages | "500 Internal Server Error" or stack traces are never acceptable. Always show human-readable, actionable messages. |
| One-click destructive actions | Deleting records, voiding invoices — all require confirmation modals. |
| Unbounded tables | Pagination required everywhere. Max 100 rows per page. |
| Custom one-off components | Every pattern goes into this system first. No undocumented components in the product. |
| Hard-coded values in CSS | All values reference design tokens. No magic numbers like `margin: 13px`. |
| Truncating patient names | Patient names must always be fully visible — widen column, wrap text, or show tooltip. |
| Mixing icon libraries | Lucide React only. Never import from another icon library. |
| Skipping ARIA on icons | Every icon-only button must have an `aria-label`. No exceptions. |

---

*NexusCare Design System — Version 2.0*
*53 Sections | 100% Coverage | Complete Visual & Interaction Specification*

*This document is the single source of truth for all visual and interaction decisions in NexusCare. Every component built must reference this specification. Deviations require a design system update — not a one-off workaround.*
