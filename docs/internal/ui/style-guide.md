# Foundry Style Guide

Foundry should use a restrained, professional visual system derived from the official United States Marine Corps digital style guide. The interface should feel authoritative, disciplined, readable, and operational—not decorative.

## 1. Brand Direction

Foundry is a private educational production webapp. The Marine Corps visual language should be used as a design influence for color, typography, hierarchy, and tone, not as a claim that Foundry is an official Marine Corps product unless formally authorized.

Design principles:

- **Disciplined:** clean layout, strong hierarchy, no visual clutter.
- **Authoritative:** bold headings, decisive contrast, minimal ornamentation.
- **Readable:** body text and learning material must remain easy to scan.
- **Operational:** interface patterns should feel like a professional knowledge system.
- **Respectful:** avoid parody, excessive militarization, or casual misuse of Marine Corps marks.

## 2. Core Color Palette

Use the official Marines.mil palette as the foundation.

| Token | Hex | Use |
|---|---:|---|
| `--color-black` | `#000000` | Primary text, high-contrast UI, dark surfaces |
| `--color-scarlet` | `#940000` | Primary accent, headings, CTAs, active states |
| `--color-dark-scarlet` | `#660000` | Hover states, pressed states, dark accent surfaces |
| `--color-gold` | `#84754E` | Secondary accent, dividers, badges, metadata highlights |
| `--color-navy` | `#001E2E` | App shell, sidebars, deep background panels |
| `--color-gray` | `#818283` | Secondary text, borders, muted controls |
| `--color-light-gray` | `#A7A7A7` | Disabled states, subtle borders, background separation |
| `--color-white` | `#FFFFFF` | Primary background, text on dark surfaces |

## 3. Recommended Foundry Theme

Use the official palette, but tune it for software usability.

```css
:root {
  --color-black: #000000;
  --color-scarlet: #940000;
  --color-dark-scarlet: #660000;
  --color-gold: #84754E;
  --color-navy: #001E2E;
  --color-gray: #818283;
  --color-light-gray: #A7A7A7;
  --color-white: #FFFFFF;

  --bg-app: #FFFFFF;
  --bg-shell: #001E2E;
  --bg-panel: #F7F7F5;
  --text-primary: #000000;
  --text-secondary: #4F5051;
  --text-inverse: #FFFFFF;
  --border-subtle: #D8D8D6;
  --accent-primary: #940000;
  --accent-primary-hover: #660000;
  --accent-secondary: #84754E;
}
```

Default interface pattern:

- White or off-white content canvas.
- Navy app shell/sidebar.
- Scarlet for primary actions and major section headers.
- Gold used sparingly for metadata, dividers, achievement markers, or premium emphasis.
- Black for primary text.
- Gray for secondary labels, timestamps, and helper text.

## 4. Typography

Official guide reference:

- H1-H5: **Colossalis**, scarlet.
- H6 and body: **Arial Regular**, black.

Webapp implementation:

```css
:root {
  --font-display: "Colossalis", "Arial Narrow", "Oswald", Arial, sans-serif;
  --font-body: Arial, Helvetica, sans-serif;
  --font-mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
}
```

Use Colossalis only if properly licensed and available. Do not bundle or redistribute restricted font files unless licensing permits it. If unavailable, use a strong condensed fallback such as Arial Narrow or Oswald.

### Type Scale

| Element | Font | Size | Weight | Color | Notes |
|---|---|---:|---:|---|---|
| Page H1 | Display | 48-64px | 700 | Scarlet | Use sparingly |
| Section H2 | Display | 32-40px | 700 | Scarlet | Major page sections |
| Card H3 | Display | 24-30px | 700 | Scarlet or Black | Module headings |
| Subhead H4 | Display | 20-24px | 700 | Black | Internal hierarchy |
| Body | Arial | 16-18px | 400 | Black | Learning content |
| Small Text | Arial | 13-14px | 400 | Gray | Labels, metadata |
| Code/Data | Mono | 13-15px | 400 | Black | Technical content |

Body text should prioritize readability over strict brand replication. Use 16px minimum for UI text and 18px for long-form educational content.

## 5. Layout System

Use a disciplined grid and generous spacing.

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 64px;

  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-panel: 0 8px 24px rgba(0, 0, 0, 0.08);
}
```

Layout rules:

- Use strong left alignment.
- Avoid overly rounded, playful shapes.
- Keep panels rectangular and structured.
- Use whitespace to create hierarchy instead of excessive borders.
- Use scarlet and gold accents as command signals, not decoration.

## 6. Buttons and Links

Official guide direction:

- Buttons use Colossalis, scarlet, 2px stroke, wide horizontal padding, letter spacing.
- Links use Colossalis, scarlet, letter spacing, and animated underline behavior.

Foundry implementation:

```css
.button-primary {
  font-family: var(--font-display);
  font-size: 18px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #FFFFFF;
  background: #940000;
  border: 2px solid #940000;
  padding: 10px 28px;
}

.button-primary:hover {
  background: #660000;
  border-color: #660000;
}

.button-secondary {
  font-family: var(--font-display);
  font-size: 18px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #940000;
  background: transparent;
  border: 2px solid #940000;
  padding: 10px 28px;
}

.link-action {
  font-family: var(--font-display);
  color: #940000;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-decoration: none;
  border-bottom: 2px solid transparent;
}

.link-action:hover {
  border-bottom-color: #940000;
}
```

Button rules:

- Primary actions: scarlet filled button.
- Secondary actions: scarlet outline button.
- Destructive actions: dark scarlet or black, but require clear labeling.
- Do not overuse scarlet; one dominant call-to-action per view.

## 7. Components

### App Shell

- Navy sidebar or top bar.
- White content area.
- Scarlet active navigation indicator.
- Gold may indicate selected workspace, premium marker, or source trust status.

### Cards and Panels

- White or off-white background.
- Thin neutral border.
- Strong heading.
- Optional scarlet top rule for important cards.

#### Registry card footers (workspace, source, stage, artifact)

Console registry cards pin a metadata footer (`.as-console__artifact-foot`) to the card bottom with a top border divider. Spacing above that divider must stay consistent—this has been a recurring layout issue.

Rules:

- The **last body block** before the footer (description, tags/chips, or stats row) gets `margin-bottom: var(--space-3)` (12px). Do not rely on the footer’s `padding-top` alone; the border sits at the top edge of the footer.
- In equal-height grid cards (`display: flex; flex-direction: column; height: 100%`), insert `.as-console__card-fill` between the last body block and the footer so `margin-top: auto` on the footer pins it to the bottom **without** opening a large gap above the divider.
- Do not stack `margin-bottom` on the description **and** `margin-top` on the next row (e.g. stats)—use one intentional gap (typically `margin-top: var(--space-3)` on the secondary row only).
- Match source cards as the reference: description → metadata/tags → **12px** → divider → footer segments.

### Lesson Artifacts

Generated lesson artifacts should use:

- Clear title block.
- Scarlet section headings.
- Gold dividers or callout labels.
- High-contrast diagrams.
- Minimal background noise.
- Consistent icon and illustration style.

### Alerts

| Type | Treatment |
|---|---|
| Info | Navy border, white background |
| Success | Gold accent, restrained use |
| Warning | Gold border, bold label |
| Error | Scarlet or dark scarlet border |
| Critical | Dark scarlet fill with white text |

### Loading states

Use the shared `FoundryLoader` Primer ring for loading data or a bounded component inside Foundry. Typical uses include fetching workspace records, sources, production runs, API requests, stage settings, templates, previews, and other database-backed assets.

- Use `size="sm"` for registries, empty-state panels, previews, and other inline component loading.
- Use the default large size only for a substantial panel-bound process, such as generating or validating an artifact.
- Keep the visible label specific to the resource or operation being loaded.
- Preserve the component's `role="status"`, polite live region, and reduced-motion behavior.
- Do not use `FoundryLoader` for app startup, route-level or full-page loading, the home page, authentication, workspace access gates, or security checks. Those processes retain their dedicated full-page treatments.
- Do not replace short button progress labels such as "Uploading…" or "Saving…" with the Primer ring.

## 8. Icons

Use Font Awesome 5 Free medium-weight icons when possible. Icons should be functional, not decorative.

Rules:

- Use icons to clarify actions, status, and navigation.
- Keep stroke/weight visually consistent.
- Pair icons with text for critical actions.
- Avoid novelty icons or excessive military symbolism.

## 9. Imagery and Visual Artifacts

Use imagery that supports instruction and comprehension.

Preferred style:

- Clean vector art.
- High contrast.
- Navy, scarlet, white, black, gray, and limited gold.
- Sharp silhouettes and disciplined composition.
- Minimal gradients unless needed for depth.

Avoid:

- Cartoonish military aesthetics.
- Overly busy backgrounds.
- Misuse of official insignia or marks.
- Visuals that imply official endorsement unless authorized.

## 10. Voice and Copy

Foundry copy should be direct, precise, and professional.

Preferred language:

- “Generate lesson”
- “Review source”
- “Build assessment”
- “Export artifact”
- “Source confidence”
- “Knowledge base”

Avoid:

- Cute microcopy.
- Excessive hype.
- Casual gamified language.
- Claims of official Marine Corps affiliation.

## 11. Accessibility

Minimum standards:

- Maintain WCAG AA color contrast.
- Never rely on color alone for status.
- Provide visible keyboard focus states.
- Use semantic HTML.
- Use alt text for instructional imagery.
- Keep body text at 16px minimum.
- Support reduced-motion preferences.

Focus state example:

```css
:focus-visible {
  outline: 3px solid #84754E;
  outline-offset: 3px;
}
```

## 12. Implementation Checklist

Before merging UI work, verify:

- Colors use defined design tokens.
- Headings use display font or approved fallback.
- Body text uses Arial/Helvetica fallback stack.
- Primary actions are scarlet and visually dominant.
- Layout is clean, left-aligned, and structured.
- Registry cards keep `var(--space-3)` between the last body block and the footer divider; grid cards use `.as-console__card-fill` so the footer stays bottom-aligned without extra vertical gap.
- Icons are functional and consistent.
- Inline Foundry data and component loading uses `FoundryLoader`; full-page, authentication, and security loading patterns remain separate.
- UI does not imply official Marine Corps endorsement.
- Accessibility contrast and keyboard navigation are acceptable.
- Generated artifacts follow the same visual system.

## 13. Design Rule of Thumb

Foundry should look like a disciplined Marine Corps-inspired knowledge production system: scarlet for command emphasis, navy for operational structure, gold for prestige and metadata, black and white for clarity, and typography that communicates authority without sacrificing usability.
