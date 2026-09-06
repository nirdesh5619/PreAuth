# Design

Scene: a coordinator at a sunlit clinic desk, 10am, reviewing one prior-auth packet on a laptop. The room is warm and paper-cluttered. The UI should feel like a well-made chart folder, not a monitoring wall.

Color strategy: restrained. Tinted paper neutrals, ink-green text, copper used only for primary actions and the live node.

## Tokens

- Paper: `oklch(0.97 0.014 82)`
- Paper inset: `oklch(0.935 0.018 78)`
- Ink: `oklch(0.27 0.028 152)`
- Ink muted: `oklch(0.46 0.022 150)`
- Line: `oklch(0.86 0.016 80)`
- Copper: `oklch(0.57 0.13 52)`
- Copper deep: `oklch(0.46 0.12 48)`
- Met: `oklch(0.42 0.09 155)`
- Missing: `oklch(0.55 0.13 55)`
- Conflict: `oklch(0.5 0.14 25)`

Never `#000` or `#fff`.

## Typography

- Display (page titles only): Newsreader
- UI: Figtree
- Trace: IBM Plex Mono
- Scale: 12 / 14 / 16 / 18 / 28 / 40. Ratio ~1.2

## Motion

150–220ms ease-out. Node pulse while running. Timeline rows insert. No page-load choreography.

## Layout

Top bar with product name and new-case action. Case run is a three-column workbench: graph, artifacts, trace. HITL is an inline bottom panel, never a modal.
