"""Nexus Theme injection for NiceGUI.

Applies global CSS, fonts, and Tailwind utilities to match the visual contract.
"""
import logging
import os
from typing import Optional

from nicegui import ui

from .nexus_tokens import TOKENS

logger = logging.getLogger(__name__)
_THEME_APPLIED = False
_THEME_APPLY_COUNT = 0


def inject_global_css() -> None:
    """Inject Nexus global CSS as a style tag."""
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
    }}
    
    /* Base styles */
    body {{
        background-color: var(--bg-primary);
        color: var(--text-primary);
        font-family: var(--font-ui);
        margin: 0;
        overflow-x: hidden;
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
    
    .text-primary {{ color: var(--text-primary); }}
    .text-secondary {{ color: var(--text-secondary); }}
    .text-tertiary {{ color: var(--text-tertiary); }}
    .text-muted {{ color: var(--text-muted); }}
    
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
    """
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


def apply_nexus_theme(use_tailwind: bool = False) -> None:
    """Apply the Nexus theme globally.
    
    This function should be called once at app startup.
    
    Args:
        use_tailwind: Whether to include Tailwind CSS (CDN). Default False.
    """
    global _THEME_APPLIED, _THEME_APPLY_COUNT
    if _THEME_APPLIED:
        logger.debug("Nexus theme already applied, skipping")
        return
    _THEME_APPLY_COUNT += 1
    logger.info("Applying Nexus theme (pid=%d, call #%d)", os.getpid(), _THEME_APPLY_COUNT)
    inject_fonts()
    inject_global_css()
    if use_tailwind:
        inject_tailwind()
    logger.info("Nexus theme applied")
    _THEME_APPLIED = True