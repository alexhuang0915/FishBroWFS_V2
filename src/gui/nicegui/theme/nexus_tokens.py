"""Nexus UI design tokens.

Defines the visual contract for the Nexus theme.
All values are sourced from the provided HTML reference.
"""

# Backgrounds
BACKGROUND_PRIMARY = "#030014"
BACKGROUND_PANEL_DARK = "#09041f"
BACKGROUND_PANEL_MEDIUM = "#150a38"
BACKGROUND_PANEL_LIGHT = "#24125f"

# Text colors (Tailwind slate equivalents)
TEXT_PRIMARY = "#f1f5f9"  # slate-100
TEXT_SECONDARY = "#cbd5e1"  # slate-300
TEXT_TERTIARY = "#94a3b8"  # slate-400
TEXT_MUTED = "#64748b"  # slate-500

# Accent colors
ACCENT_PURPLE = "#a855f7"
ACCENT_CYAN = "#06b6d4"
ACCENT_BLUE = "#3b82f6"
ACCENT_SUCCESS = "#10b981"
ACCENT_DANGER = "#ef4444"
ACCENT_WARNING = "#f59e0b"

# Strategy colors
STRATEGY_LONG_SELECTED = "#10b981"  # green
STRATEGY_SHORT_SELECTED = "#ef4444"  # red
STRATEGY_NEUTRAL = "#3b82f6"  # blue

# Borders & glows
BORDER_COLOR = "#334155"  # slate-700
BORDER_GLOW = "rgba(168, 85, 247, 0.3)"  # purple with opacity
CARD_HOVER_GLOW = "0 0 15px rgba(168, 85, 247, 0.5)"

# Fonts
FONT_UI = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
FONT_MONO = "'JetBrains Mono', 'Courier New', monospace"

# Spacing (rem units)
SPACING_1 = "0.25rem"
SPACING_2 = "0.5rem"
SPACING_3 = "0.75rem"
SPACING_4 = "1rem"
SPACING_6 = "1.5rem"
SPACING_8 = "2rem"
SPACING_12 = "3rem"
SPACING_16 = "4rem"

# Border radii
RADIUS_SM = "0.25rem"
RADIUS_MD = "0.5rem"
RADIUS_LG = "1rem"
RADIUS_XL = "1.5rem"

# Shadows
SHADOW_CARD = "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)"
SHADOW_ELEVATED = "0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1)"

# Scrollbar
SCROLLBAR_WIDTH = "6px"
SCROLLBAR_TRACK = "#09041f"
SCROLLBAR_THUMB = "#24125f"
SCROLLBAR_THUMB_HOVER = "#a855f7"

# Z-indices
Z_INDEX_TOAST = 9999
Z_INDEX_MODAL = 9990
Z_INDEX_HEADER = 100
Z_INDEX_SIDEBAR = 90

# Animation durations
ANIMATION_FAST = "150ms"
ANIMATION_NORMAL = "300ms"
ANIMATION_SLOW = "500ms"

# Export all tokens as a dict for easy injection
TOKENS = {
    "backgrounds": {
        "primary": BACKGROUND_PRIMARY,
        "panel_dark": BACKGROUND_PANEL_DARK,
        "panel_medium": BACKGROUND_PANEL_MEDIUM,
        "panel_light": BACKGROUND_PANEL_LIGHT,
    },
    "text": {
        "primary": TEXT_PRIMARY,
        "secondary": TEXT_SECONDARY,
        "tertiary": TEXT_TERTIARY,
        "muted": TEXT_MUTED,
    },
    "accents": {
        "purple": ACCENT_PURPLE,
        "cyan": ACCENT_CYAN,
        "blue": ACCENT_BLUE,
        "success": ACCENT_SUCCESS,
        "danger": ACCENT_DANGER,
        "warning": ACCENT_WARNING,
    },
    "fonts": {
        "ui": FONT_UI,
        "mono": FONT_MONO,
    },
    "spacing": {
        "1": SPACING_1,
        "2": SPACING_2,
        "3": SPACING_3,
        "4": SPACING_4,
        "6": SPACING_6,
        "8": SPACING_8,
        "12": SPACING_12,
        "16": SPACING_16,
    },
    "radii": {
        "sm": RADIUS_SM,
        "md": RADIUS_MD,
        "lg": RADIUS_LG,
        "xl": RADIUS_XL,
    },
}