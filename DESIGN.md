# Easy Single — Design Specification

## Aesthetic direction
**Soft claymorphism × sakura motif**
- Gentle colours, delicate light and shadow, a warm and reassuring mood
- UI mapping: soft pink palette, generous corner radii, soft shadows, sakura accents

## Colour system

| Token | Hex | Usage |
|--------|-----|------|
| --color-primary | #FF7DAF | Primary · sakura pink |
| --color-primary-light | #FFB8D4 | Light sakura |
| --color-accent | #C4A1FF | Accent · soft lavender |
| --color-gold | #FFD4A8 | Detail · warm gold |
| --color-bg | #FFF5F8 | Background · warm off-white pink |
| --color-sakura | #FFE8F0 | Sakura surface |
| --color-text | #4A2535 | Body text · warm brown |
| --color-text-muted | #C495A8 | Secondary text |

## Typography

| Usage | Font | Fallback |
|------|------|----------|
| Headings | Varela Round | Trebuchet MS, system-ui |
| Body | Nunito Sans | system-ui, -apple-system, sans-serif |
| Numerals / code | system monospace | ui-monospace, SFMono-Regular |

The app ships in English only. Sans-serif stacks are loaded from Google Fonts
in `frontend/index.html`; always keep a local fallback so the UI degrades
gracefully when the font CDN is blocked.

## Corner radii
- xs: 8px | sm: 14px | base: 20px | lg: 28px | xl: 36px | full: 9999px
- Avatars use 14px (rounded rectangle)
- Message bubbles use 20px with an 8px corner on one side

## Shadows
- All shadows carry a pink tint (`rgba(255,125,175,...)`)
- Glow effects are reserved for the logo and primary buttons
- Light shadows on bubbles, deeper shadows on cards

## Motion
- Easing: cubic-bezier(0.25, 0.8, 0.25, 1.2) — a slight spring
- Bounce: cubic-bezier(0.34, 1.56, 0.64, 1) — button hover
- Message entrance: slide up + fade + subtle scale (0.35s)
- Typing indicator: three bouncing dots in pink / lavender / gold
- Multi-message replies are revealed character by character to mimic real typing

## Icons
- SVG icons (Lucide set), 24x24 viewBox, stroke-width 1.5–2
- Never use emoji as UI icons
- Decorative emoji (🌸 💕) are atmosphere only

## Anti-patterns — do not use
- Purple-blue gradients
- Glassmorphism
- Pure black or pure white
- The Inter typeface
- Sharp corners