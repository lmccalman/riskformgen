# Plan: Replace TailwindCSS with Pico CSS (jade theme)

## Context

The project currently uses TailwindCSS v4 (~110 utility classes across 7 templates) compiled via
the `tailwindcss` CLI at build time. We're replacing it with Pico CSS (jade theme, v2.1.1) to get
classless/semantic styling — Pico styles standard HTML elements directly, so we can strip most
classes and rely on proper semantic markup (`<article>`, `<section>`, `<nav>`, `<details>`, etc.).

The `pico.jade.min.css` file is already downloaded at the project root.

## Semantic HTML improvements

| Current | Pico replacement | Why |
|---|---|---|
| `<div>` tab bar | `<nav class="tabs">` | Semantically navigation; Pico styles `<nav>` |
| `<div>` subsection wrapper | `<section>` | Semantic grouping within a form |
| `<div>` risk card | `<article>` | Pico styles articles as cards (border, padding, shadow) |
| `<div>` risk card header | `<header>` inside `<article>` | Pico styles `article > header` distinctly |
| `<div>` debug panel | `<details data-theme="dark">` | Collapsible, dark-themed via Pico's per-element theming |
| `<span>` around label text | bare text after `<input>` | Pico expects `<label><input/> Text</label>` pattern |

## Files to modify (10 total)

### 1. `config.py` — add Pico path constant
- Add `pico_src = project_root / "pico.jade.min.css"` alongside existing `alpine_src`

### 2. `main.py` — replace build step
- Replace `compile_css()` (tailwindcss CLI subprocess) with `copy_css()` that copies both
  `pico.jade.min.css` and `input.css` into `output/`
- Remove `subprocess` import (no longer needed)

### 3. `input.css` — rewrite: Tailwind import → custom CSS
Replace `@import "tailwindcss"` with ~160 lines of custom CSS for things Pico doesn't cover:

- **Container width**: `--pico-container-max-width: 42rem` (matches current `max-w-2xl`)
- **Tab navigation**: `.tabs` flex container, `.tabs button` styling, `.active` state, `.tab-risk` variant
- **Badge/pill component**: `.badge` base + `.badge-{blue,purple,gray,green,amber,red}` colour variants
  (needed for Alpine.js `:class` bindings on risk levels)
- **Risk grid**: `.risk-grid` 3-column grid for likelihood/consequence/level
- **Dimension labels**: `.dim-label` small uppercase labels ("Likelihood", "Controls", etc.)
- **Control rows**: `.control-row`, `.control-icon`, `.control-icon-{active,inactive}`, `.control-effect`
- **Linked answers**: `.linked-answer` flex row, `.answer-missing` muted italic
- **Spacing stacks**: `.stack-lg/md/sm` (margin-top on siblings — replaces Tailwind `space-y-*`)
- **Options layout**: `.options-row` (horizontal, for yes/no) and `.options-col` (vertical, for multi-choice)
- **Assessed risk**: `.assessed-row` flex + `select { width: auto }` override (Pico defaults select to 100%)
- **Alpine cloak**: `[x-cloak] { display: none !important }` (currently provided by Tailwind preflight)
- **Debug panel**: `details[data-theme="dark"] pre` green text

### 4. `templates/page.html.j2` — main structural changes
- `<head>`: two `<link>` tags: `pico.jade.min.css` + `input.css` (replaces single `styles.css`)
- `<body>`: strip Tailwind classes
- `<main class="container">`: Pico container (replaces `mx-auto max-w-2xl px-4 py-12`)
- `<h1>`: strip classes (Pico styles natively)
- Tab bar: `<div>` → `<nav class="tabs">`; `:class` bindings simplified to toggle `'active'` class
- Section forms: `class="space-y-8"` → `class="stack-lg"`
- Section description: `<p class="text-sm text-gray-500">` → `<p><small>...</small></p>`
- Debug panel: `<div class="bg-gray-800...">` → `<details data-theme="dark"><summary>Debug</summary>...</details>`
- Risks container: `class="space-y-4"` → `class="stack-md"`

### 5. `templates/subsection.html.j2`
- `<div class="space-y-4">` → `<section class="stack-md">`
- `<h2>`: strip all Tailwind classes (Pico styles headings natively)
- Description: `<p class="text-sm text-gray-500">` → `<p><small>...</small></p>`

### 6–9. `templates/questions/{yes_no,free_text,multiple_choice,multiple_select}.html.j2`
All four follow the same pattern:
- `<fieldset>`: strip all Tailwind classes (Pico styles fieldsets natively)
- `<legend>`: strip classes (Pico styles natively)
- Guidance `<p>`: → `<p><small><em>...</em></small></p>`
- Options container: `class="mt-4 flex gap-6"` → `class="options-row"` (yes/no) or `class="options-col"` (multi)
- Labels: strip classes; remove `<span>` wrapper around text (Pico expects `<label><input/> Text</label>`)
- Inputs: strip all Tailwind classes (Pico styles radio/checkbox/textarea natively)
- `<textarea>`: remove wrapper `<div>`, strip classes

### 10. `templates/risk_summary.html.j2`
Most complex — full rewrite of classes:
- Outer `<div>` → `<article>`
- Header `<div>` → `<header>` with `<h3>` and `<p><small>` (strip classes)
- Grid: `class="grid grid-cols-3 gap-4"` → `class="risk-grid"`
- Badges: Tailwind colour classes → `.badge .badge-{color}` classes
- `:class` bindings: `'bg-green-100 text-green-700'` → `'badge-green'` (etc.)
- Controls: Tailwind flex/sizing → `.control-row`, `.control-icon-{active,inactive}`, `.control-effect`
- `<select>`: strip classes (Pico styles natively); wrap in `.assessed-row`
- `<textarea>`: strip classes (Pico styles natively); use `<label class="dim-label">` → `<textarea>`
- Linked answers: Tailwind flex → `.linked-answer`, `.answer-missing`
- `<hr>`: strip class
- `<ul>`: `class="space-y-1"` → `class="stack-sm"`

## Files NOT changed
- `models.py`, `render.py`, `parse.py`, `question.html.j2` — no CSS references

## Post-migration cleanup
- Update `CLAUDE.md`: TailwindCSS → Pico CSS references throughout
- The `tailwindcss` CLI is no longer needed in the build

## Verification
1. `uv run main.py` — should build without errors (no tailwindcss subprocess)
2. `python -m http.server -d output` — serve and check in browser:
   - Tabs switch correctly (Alpine.js preserved)
   - Questions render with Pico's native form styling
   - Conditional visibility (`x-show`) works
   - Risk cards display as Pico `<article>` cards
   - Badges are colour-coded per risk level
   - Controls show active/inactive states
   - Debug panel is collapsible via `<details>`
   - Overall layout is centred at 42rem max-width
