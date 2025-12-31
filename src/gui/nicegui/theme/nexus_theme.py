"""Nexus Theme injection for NiceGUI.

Applies global CSS, fonts, and Tailwind utilities to match the visual contract.
"""
import logging
import os
from typing import Optional

from nicegui import ui

from .nexus_tokens import TOKENS, SHADOW_ELEVATED

logger = logging.getLogger(__name__)
NEXUS_THEME_VERSION = "v1"
_THEME_APPLIED = False
_THEME_APPLY_COUNT = 0


def build_global_css() -> str:
    """Build Nexus global CSS as a string (pure function).
    
    Includes BOTH Quasar and NiceGUI wrapper failsafes:
    - Standard base selectors: html, body, #q-app, .q-layout, .q-page, .q-page-container
    - Dynamic Quasar/SPA selectors: .q-page--active, .q-layout-padding, .q-scrollarea, .q-scrollarea__content, .q-page-sticky
    - Root Wrapper Failsafe (KEY): #q-app > div, #q-app > div > div, #q-app > div > div > div, [role="main"]
    - All must have background-color: var(--bg-primary) !important; color: var(--text-primary); min-height: 100vh;
    - Utility classes: .bg-nexus-primary, .bg-nexus-panel-dark, .bg-nexus-panel-medium, .bg-nexus-panel-light
    
    Returns:
        CSS string ready for injection
    """
    css = f"""
    :root {{
        /* Backgrounds */
        --bg-primary: {TOKENS['backgrounds']['primary']};
        --bg-panel-dark: {TOKENS['backgrounds']['panel_dark']};
        --bg-panel-medium: {TOKENS['backgrounds']['panel_medium']};
        --bg-panel-light: {TOKENS['backgrounds']['panel_light']};
        
        /* Text */
        --text-primary: {TOKENS['text']['primary']};
        --text-secondary: {TOKENS['text']['secondary']};
        --text-tertiary: {TOKENS['text']['tertiary']};
        --text-muted: {TOKENS['text']['muted']};
        
        /* Accents */
        --accent-purple: {TOKENS['accents']['purple']};
        --accent-cyan: {TOKENS['accents']['cyan']};
        --accent-blue: {TOKENS['accents']['blue']};
        --accent-success: {TOKENS['accents']['success']};
        --accent-danger: {TOKENS['accents']['danger']};
        --accent-warning: {TOKENS['accents']['warning']};
        
        /* Fonts */
        --font-ui: {TOKENS['fonts']['ui']};
        --font-mono: {TOKENS['fonts']['mono']};
        
        /* Spacing */
        --spacing-1: {TOKENS['spacing']['1']};
        --spacing-2: {TOKENS['spacing']['2']};
        --spacing-4: {TOKENS['spacing']['4']};
        --spacing-6: {TOKENS['spacing']['6']};
        --spacing-8: {TOKENS['spacing']['8']};
        
        /* Radii */
        --radius-sm: {TOKENS['radii']['sm']};
        --radius-md: {TOKENS['radii']['md']};
        --radius-lg: {TOKENS['radii']['lg']};
        --radius-xl: {TOKENS['radii']['xl']};
        
        /* Shadows */
        --shadow-elevated: {SHADOW_ELEVATED};
    }}
    
    /* Base styles - ensure full coverage */
    html, body {{
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-ui);
        margin: 0;
        overflow-x: hidden;
        height: 100%;
        min-height: 100vh;
    }}
    
    /* Quasar/NiceGUI container selectors */
    #q-app, .q-layout, .q-page, .q-page-container,
    .nicegui-content, .nicegui-page {{
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
        min-height: 100vh;
    }}
    
    /* Dynamic Quasar/SPA selectors */
    .q-page--active, .q-layout-padding,
    .q-scrollarea, .q-scrollarea__content,
    .q-page-sticky, .q-page-sticky--active {{
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
    }}
    
    /* ROOT WRAPPER FAILSAFE (KEY) - covers all nested divs */
    #q-app > div,
    #q-app > div > div,
    #q-app > div > div > div,
    #q-app > div > div > div > div,
    [role="main"],
    .q-page-container > div,
    .q-page-container > div > div,
    .nicegui-content > div,
    .nicegui-content > div > div {{
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
        /* min-height removed from nested selectors - only top-level containers have it */
    }}
    
    /* Ensure any nested containers also inherit */
    .q-drawer, .q-header, .q-footer, .q-toolbar {{
        background-color: var(--bg-panel-dark) !important;
        color: var(--text-primary) !important;
    }}
    
    /* Cyber scrollbar */
    ::-webkit-scrollbar {{
        width: 6px;
        height: 6px;
    }}
    ::-webkit-scrollbar-track {{
        background: {TOKENS['backgrounds']['panel_dark']};
        border-radius: 3px;
    }}
    ::-webkit-scrollbar-thumb {{
        background: {TOKENS['backgrounds']['panel_light']};
        border-radius: 3px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: {TOKENS['accents']['purple']};
    }}
    
    /* fish-card base */
    .fish-card {{
        background: linear-gradient(145deg, var(--bg-panel-medium), var(--bg-panel-dark));
        border: 1px solid {TOKENS['accents']['purple']}20;
        border-radius: var(--radius-lg);
        padding: var(--spacing-4);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }}
    .fish-card:hover {{
        border-color: {TOKENS['accents']['purple']}80;
        box-shadow: 0 0 15px {TOKENS['accents']['purple']}50;
        transform: translateY(-2px);
    }}
    .fish-card.selected {{
        border-left: 4px solid {TOKENS['accents']['success']};
    }}
    .fish-card.selected.short {{
        border-left-color: {TOKENS['accents']['danger']};
    }}
    
    /* Neon strip for selected */
    .fish-card.selected::before {{
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: {TOKENS['accents']['success']};
        border-radius: var(--radius-sm) 0 0 var(--radius-sm);
        box-shadow: 0 0 8px {TOKENS['accents']['success']};
    }}
    .fish-card.selected.short::before {{
        background: {TOKENS['accents']['danger']};
        box-shadow: 0 0 8px {TOKENS['accents']['danger']};
    }}
    
    /* Typography */
    h1, h2, h3, h4, h5, h6 {{
        font-weight: 600;
        color: var(--text-primary);
        margin-top: 0;
    }}
    
    code, pre, .mono {{
        font-family: var(--font-mono);
    }}
    
    /* Tailwind-like utilities */
    .bg-panel-dark {{ background-color: var(--bg-panel-dark); }}
    .bg-panel-medium {{ background-color: var(--bg-panel-medium); }}
    .bg-panel-light {{ background-color: var(--bg-panel-light); }}
    
    /* Nexus-specific background utilities */
    .bg-nexus-primary {{ background-color: var(--bg-primary) !important; }}
    .bg-nexus-panel-dark {{ background-color: var(--bg-panel-dark) !important; }}
    .bg-nexus-panel-medium {{ background-color: var(--bg-panel-medium) !important; }}
    .bg-nexus-panel-light {{ background-color: var(--bg-panel-light) !important; }}
    
    .text-primary {{ color: var(--text-primary) !important; }}
    .text-secondary {{ color: var(--text-secondary) !important; }}
    .text-tertiary {{ color: var(--text-tertiary) !important; }}
    .text-muted {{ color: var(--text-muted) !important; }}
    
    .text-purple {{ color: var(--accent-purple); }}
    .text-cyan {{ color: var(--accent-cyan); }}
    .text-blue {{ color: var(--accent-blue); }}
    .text-success {{ color: var(--accent-success); }}
    .text-danger {{ color: var(--accent-danger); }}
    .text-warning {{ color: var(--accent-warning); }}
    
    .border-purple {{ border-color: var(--accent-purple); }}
    .border-cyan {{ border-color: var(--accent-cyan); }}
    
    .hover-glow:hover {{
        box-shadow: 0 0 15px var(--accent-purple);
    }}

    /* Global dark overrides for Quasar content components */
    .q-card, .q-stepper, .q-stepper__content, .q-panel,
    .q-stepper__step-content, .q-item {{
        background-color: var(--bg-panel-dark) !important;
        color: var(--text-primary) !important;
    }}

    /* Layout constitution classes */
    .nexus-page-fill {{
        width: 100%;
        min-height: 100vh;
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 24px;
    }}

    .nexus-content {{
        width: 100%;
        max-width: 1200px;
        flex-grow: 1;
        display: flex;
        flex-direction: column;
        gap: 24px;
    }}

    .nexus-page-title {{
        width: 100%;
        margin-bottom: 24px;
        border-bottom: 2px solid var(--accent-purple);
        padding-bottom: 12px;
    }}

    /* Nexus islands grid CSS with responsive breakpoints */
    .nexus-islands {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 24px;
        width: 100%;
        min-height: 200px;
        margin-top: 24px;
        margin-bottom: 24px;
    }}

    @media (max-width: 768px) {{
        .nexus-islands {{
            grid-template-columns: 1fr;
            gap: 16px;
        }}
    }}

    @media (min-width: 769px) and (max-width: 1024px) {{
        .nexus-islands {{
            grid-template-columns: repeat(2, 1fr);
        }}
    }}

    /* Toast notifications */
    .nicegui-toast {{
        font-family: var(--font-ui);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-elevated);
    }}
    """
    return css


def inject_global_css() -> None:
    """Inject Nexus global CSS as a style tag."""
    css = build_global_css()
    ui.add_head_html(f"<style>{css}</style>")


def inject_fonts() -> None:
    """Inject Inter and JetBrains Mono fonts from Google Fonts."""
    font_html = """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    """
    ui.add_head_html(font_html)


def inject_tailwind() -> None:
    """Inject Tailwind CSS for utility classes (optional).
    
    Note: Tailwind can be included via CDN for development.
    However, we already provide custom CSS; this is a fallback.
    """
    tailwind_cdn = """
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        'nexus-primary': '#030014',
                        'nexus-panel-dark': '#09041f',
                        'nexus-panel-medium': '#150a38',
                        'nexus-panel-light': '#24125f',
                        'nexus-purple': '#a855f7',
                        'nexus-cyan': '#06b6d4',
                        'nexus-blue': '#3b82f6',
                        'nexus-success': '#10b981',
                        'nexus-danger': '#ef4444',
                        'nexus-warning': '#f59e0b',
                    },
                    fontFamily: {
                        'sans': ['Inter', 'sans-serif'],
                        'mono': ['JetBrains Mono', 'monospace'],
                    },
                }
            }
        }
    </script>
    """
    ui.add_head_html(tailwind_cdn)


def inject_nexus_theme(use_tailwind: bool = False) -> None:
    """Inject Nexus theme CSS globally (single source of truth).
    
    This function should be called once at app startup.
    It injects all theme CSS via ui.add_head_html() in one place.
    
    Args:
        use_tailwind: Whether to include Tailwind CSS (CDN). Default False.
    """
    global _THEME_APPLIED, _THEME_APPLY_COUNT
    if _THEME_APPLIED:
        logger.debug("Nexus theme already applied, skipping")
        return
    _THEME_APPLY_COUNT += 1
    logger.info("Injecting Nexus theme v%s (pid=%d, call #%d)", NEXUS_THEME_VERSION, os.getpid(), _THEME_APPLY_COUNT)
    inject_fonts()
    inject_global_css()
    if use_tailwind:
        inject_tailwind()
    logger.info("Nexus theme injected")
    _THEME_APPLIED = True


# Backward compatibility alias
apply_nexus_theme = inject_nexus_theme
