# Design System — Keelhaul

## Product Context
- **What this is:** ERA compliance calendar and task engine for small private exempt funds
- **Who it's for:** GP/Managing Member of a 1-3 person fund who is personally responsible for compliance
- **Space/industry:** Financial compliance / fund operations. No direct competitor for small ERAs.
- **Project type:** Internal web app / dashboard with potential to become a product

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian with nautical warmth
- **Decoration level:** Intentional — subtle texture on key surfaces (dashboard header, sidebar), clean elsewhere
- **Mood:** Serious enough to trust with regulatory deadlines, characterful enough to not feel like enterprise software. A well-maintained ship's bridge: every instrument earns its place, brass accents catch the light.

## Typography
- **Display/Hero:** Instrument Serif — elegant serif gives headings a "document of record" gravitas without feeling corporate. Differentiates from generic SaaS dashboards.
- **Body:** DM Sans — clean geometric sans, highly readable at small sizes, pairs well with Instrument Serif
- **UI/Labels:** DM Sans (same as body)
- **Data/Tables:** DM Sans with `font-variant-numeric: tabular-nums` — numbers align in columns
- **Code/Mono:** JetBrains Mono — for CRD numbers, filing references, jurisdiction codes (e.g., US-NY, CA-AB)
- **Loading:** Google Fonts CDN
  ```html
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,300..700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  ```
- **Scale:**
  - xs: 12px / 0.75rem
  - sm: 13px / 0.8125rem
  - base: 15px / 0.9375rem
  - lg: 18px / 1.125rem
  - xl: 24px / 1.5rem
  - 2xl: 30px / 1.875rem
  - 3xl: 48px / 3rem

## Color
- **Approach:** Restrained with one bold accent
- **Primary (Navy):**
  - 50: #f0f4f8, 100: #d9e2ec, 200: #bcccdc, 300: #9fb3c8, 400: #627d98
  - 500: #3e6085, 600: #2d4a6f, **700: #1e3a5f** (primary), 800: #15294a, 900: #0d1b2a
  - Usage: sidebar, headings, primary buttons, links
- **Accent (Amber/Brass):**
  - 50: #fffbeb, 100: #fef3c7, 200: #fde68a, 300: #fcd34d, 400: #fbbf24
  - **500: #d97706** (accent), 600: #b45309, 700: #92400e
  - Usage: overdue indicators, attention CTAs, warning states. Amber IS the warning color.
- **Neutrals (Warm Stone):**
  - 50: #fafaf9, 100: #f5f5f4, 200: #e7e5e4, 300: #d6d3d1, 400: #a8a29e
  - 500: #78716c, 600: #57534e, 700: #44403c, 800: #292524, 900: #1c1917
  - Usage: backgrounds, borders, secondary text. Warm grays, not blue-grays.
- **Semantic:**
  - Success: #16a34a (bg: #f0fdf4)
  - Warning: #d97706 (bg: #fffbeb) — same as accent
  - Error: #dc2626 (bg: #fef2f2)
  - Info: #2563eb (bg: #eff6ff)
- **Dark mode:** Invert surfaces (navy-900 bg, navy-800 cards), keep navy + amber identity, reduce saturation 10-20% on semantic colors

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — not cramped like a Bloomberg terminal, not spacious like a marketing page
- **Scale:** 2xs(2px) xs(4px) sm(8px) md(16px) lg(24px) xl(32px) 2xl(48px) 3xl(64px)

## Layout
- **Approach:** Grid-disciplined — strict columns, predictable alignment
- **Grid:** 1 col mobile, 2 col tablet, sidebar + content desktop
- **Max content width:** 1100px
- **Border radius:**
  - sm: 4px (badges, small elements)
  - md: 8px (buttons, inputs, alerts)
  - lg: 12px (cards, containers, tables)
  - full: 9999px (status badges, pills)

## Motion
- **Approach:** Minimal-functional — compliance software shouldn't dance
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro(50-100ms) short(150-250ms) medium(250-400ms)
- **Specific:** Badge color transitions on status change (200ms ease-out), toast slide-in (250ms), HTMX content swap (150ms fade)

## Component Patterns

### Status Badges
- Completed: green bg (#f0fdf4) + green text (#16a34a)
- In Progress: blue bg (#eff6ff) + blue text (#2563eb)
- Not Started: stone bg (#f5f5f4) + stone text (#57534e)
- Overdue: red bg (#fef2f2) + red text (#dc2626)
- Deferred: amber bg (#fffbeb) + amber text (#92400e)

### Delegation Badges
- Compliance Counsel: indigo bg (#eef2ff) + indigo text (#4338ca)
- Fund Admin: teal bg (#f0fdfa) + teal text (#0f766e)
- Internal: no badge, plain text

### Obligation Category Colors (calendar)
- FORM_ADV: navy
- BLUE_SKY: green
- FORM_D: amber
- FORM_PF: blue
- AML_CFT: purple
- STATE_NOTICE: teal
- INTERNATIONAL: indigo

### Alert Banners
- Left border (4px) + tinted background + icon + text
- Alberta PLACEHOLDER: amber alert with "Requires Legal Review" heading

### Cards
- Standard: `bg-white border border-stone-200 rounded-lg p-6` (light), `bg-navy-800 border-navy-700` (dark)
- Stat cards: smaller padding (p-4), centered text, large tabular number

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-22 | Initial design system created | Created by /design-consultation based on product context from eng + design reviews |
| 2026-03-22 | Instrument Serif for headings | Serif in a dashboard is unusual but gives "document of record" gravitas — distinguishes from generic SaaS |
| 2026-03-22 | Deep navy (#1e3a5f) over bright blue | Maritime identity, more opinionated than generic SaaS blue |
| 2026-03-22 | Warm stone neutrals over cool grays | Approachable rather than sterile — important for solo GP under compliance stress |
| 2026-03-22 | Amber as both accent and warning color | Nautical brass + urgency signal in one color. Dual purpose reduces palette complexity |
