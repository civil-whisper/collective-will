# Website Design System — Plausible-Inspired Analytics UI

## Design Reference

**Primary inspiration**: [Plausible Analytics](https://plausible.io/plausible.io) — single-page, clean analytics dashboard with big metric cards, time-series chart, and ranked breakdown lists.

**Design principles** (borrowed from Plausible):
- Everything important on one screen — no deep navigation required for the overview
- Big, readable numbers for key metrics at the top
- Clean time-series chart as the visual anchor
- Ranked lists below for breakdowns (clusters by domain, top policies, etc.)
- Minimal decoration — whitespace and typography do the work
- Light/dark mode support
- Mobile-first responsive layout

## Color Palette

Use a neutral base with a single accent color for interactivity and highlights.

| Token | Light Mode | Dark Mode | Usage |
|-------|-----------|-----------|-------|
| `background` | `#f9fafb` (gray-50) | `#0f172a` (slate-900) | Page background |
| `surface` | `#ffffff` | `#1e293b` (slate-800) | Cards, panels |
| `surface-alt` | `#f3f4f6` (gray-100) | `#334155` (slate-700) | Hover, secondary cards |
| `border` | `#e5e7eb` (gray-200) | `#334155` (slate-700) | Card borders, dividers |
| `text-primary` | `#111827` (gray-900) | `#f1f5f9` (slate-100) | Headings, big numbers |
| `text-secondary` | `#6b7280` (gray-500) | `#94a3b8` (slate-400) | Labels, descriptions |
| `accent` | `#4f46e5` (indigo-600) | `#818cf8` (indigo-400) | Links, active states, chart line |
| `accent-light` | `#eef2ff` (indigo-50) | `#312e81` (indigo-900) | Chart fill, hover backgrounds |
| `success` | `#16a34a` (green-600) | `#4ade80` (green-400) | Positive trends, valid chain |
| `danger` | `#dc2626` (red-600) | `#f87171` (red-400) | Negative trends, broken chain |

## Typography

| Element | Font | Weight | Size |
|---------|------|--------|------|
| Big metric number | System sans-serif | 700 (bold) | `text-3xl` (1.875rem) |
| Metric label | System sans-serif | 500 (medium) | `text-sm` (0.875rem) |
| Page heading | System sans-serif | 700 | `text-2xl` (1.5rem) |
| Section heading | System sans-serif | 600 (semibold) | `text-lg` (1.125rem) |
| Body text | System sans-serif | 400 (normal) | `text-sm` (0.875rem) |
| Code / hashes | Monospace | 400 | `text-xs` (0.75rem) |

System font stack: `Inter, system-ui, -apple-system, sans-serif` (with Vazirmatn for Farsi).

## Layout Patterns

### Analytics Overview Page (Plausible-style)

```
┌─────────────────────────────────────────────────────────┐
│  NavBar  [Logo]  [Analytics] [Community Votes] [Audit] [🌐] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Active Voters]  [Total Clusters]  [Submissions]  [Cycle] │
│     1,247           23               892            #4   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  ▇▇▇ Time-series chart (participation / votes) ▇▇▇ │   │
│  │  ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─ Top Clusters ───────────┐  ┌─ By Domain ──────────┐ │
│  │ 1. Economic reform  45%  │  │ Economy       38%    │ │
│  │ 2. Free press       31%  │  │ Rights        27%    │ │
│  │ 3. Education        28%  │  │ Governance    19%    │ │
│  │ 4. Healthcare       22%  │  │ Foreign pol.  11%    │ │
│  │ ...                      │  │ Other          5%    │ │
│  └──────────────────────────┘  └──────────────────────┘ │
│                                                         │
│  ┌─ Recent Activity ────────────────────────────────┐  │
│  │ vote_cast      cluster_xyz   2 min ago           │  │
│  │ submission     user_abc      5 min ago           │  │
│  │ cycle_opened   cycle_004     1 hour ago          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Metric Card Pattern

Each card is a white (light) / slate-800 (dark) rounded box with:
- Small uppercase label in `text-secondary` at the top
- Large number in `text-primary` font-bold
- Optional trend indicator (up/down arrow + percentage change)

### Ranked List Pattern (Plausible breakdown tables)

- Full-width rows inside a card
- Left: item name (clickable link)
- Right: numeric value + optional bar visualization
- Alternating subtle hover backgrounds
- Horizontal progress bar showing relative percentage behind the text

## Component Architecture

Shared UI building blocks (all Tailwind-styled):

| Component | Purpose |
|-----------|---------|
| `MetricCard` | Big number + label + optional trend |
| `BreakdownTable` | Ranked list with bar visualization |
| `TimeSeriesChart` | Area/line chart for participation over time |
| `ChainStatusBadge` | Green/red indicator for evidence chain validity |
| `DomainBadge` | Colored pill showing policy domain |
| `PageShell` | Consistent page padding, max-width, heading |
| `Card` | Generic surface container with border/shadow |

## Cluster Metrics Vocabulary

All pages displaying cluster/policy metrics must use the same three metrics consistently:

| Metric | Translation Key | Source Field | Formula |
|--------|----------------|--------------|---------|
| Submissions | `submissions` | `member_count` | direct |
| Endorsements | `endorsements` | `endorsement_count` | direct |
| Total Support | `totalSupport` | — | `member_count + endorsement_count` |

**Pages that display cluster metrics** (grep for these keys when changing the vocabulary):
- `web/app/[locale]/collective-concerns/page.tsx` (cluster list)
- `web/app/[locale]/collective-concerns/clusters/[id]/page.tsx` (cluster detail)
- `web/app/[locale]/collective-concerns/community-votes/page.tsx` (community votes)

Legacy field `approval_count` is still returned by the API but should not be displayed on new pages. The canonical public metrics are Submissions + Endorsements = Total Support.

## RTL Considerations

- Tailwind `rtl:` prefix for directional utilities
- Use logical properties: `ms-*` / `me-*` (margin-inline-start/end), `ps-*` / `pe-*`
- Chart labels and axis should flip in RTL
- Navigation order remains the same (Farsi users expect LTR-like nav layouts)
- Vazirmatn font loaded for `fa` locale via `next/font/google`

## Charting Library

Use **Recharts** (lightweight, React-native, Tailwind-compatible). Only needed for:
- Time-series area chart on analytics overview
- Optional domain distribution bar chart

No heavier libraries. Keep bundle size minimal.

## Responsive Breakpoints

| Breakpoint | Behavior |
|-----------|----------|
| `< 640px` (mobile) | Single column, stacked metric cards, hamburger nav |
| `640–1024px` (tablet) | 2-column metric cards, side-by-side breakdown tables |
| `> 1024px` (desktop) | Full layout as shown in wireframe above |
