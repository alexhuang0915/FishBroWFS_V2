"""Cyberpunk UI 全域樣式注入"""

from nicegui import ui


def inject_global_styles() -> None:
    """注入全域樣式：Google Fonts + Tailwind CDN + 自訂 CSS"""
    
    # Google Fonts
    ui.add_head_html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    """, shared=True)
    
    # Tailwind CDN
    ui.add_head_html("""
    <script src="https://cdn.tailwindcss.com"></script>
    """, shared=True)
    
    # Tailwind config with custom colors
    ui.add_head_html("""
    <script>
    tailwind.config = {
        darkMode: 'class',
        theme: {
            extend: {
                colors: {
                    'nexus': {
                        50: '#f0f9ff',
                        100: '#e0f2fe',
                        200: '#bae6fd',
                        300: '#7dd3fc',
                        400: '#38bdf8',
                        500: '#0ea5e9',
                        600: '#0284c7',
                        700: '#0369a1',
                        800: '#075985',
                        900: '#0c4a6e',
                        950: '#082f49',
                    },
                    'cyber': {
                        50: '#f0fdfa',
                        100: '#ccfbf1',
                        200: '#99f6e4',
                        300: '#5eead4',
                        400: '#2dd4bf',
                        500: '#14b8a6',
                        600: '#0d9488',
                        700: '#0f766e',
                        800: '#115e59',
                        900: '#134e4a',
                        950: '#042f2e',
                    },
                    'fish': {
                        50: '#eff6ff',
                        100: '#dbeafe',
                        200: '#bfdbfe',
                        300: '#93c5fd',
                        400: '#60a5fa',
                        500: '#3b82f6',
                        600: '#2563eb',
                        700: '#1d4ed8',
                        800: '#1e40af',
                        900: '#1e3a8a',
                        950: '#172554',
                    }
                },
                fontFamily: {
                    'sans': ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'Noto Sans', 'sans-serif'],
                    'mono': ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
                },
                animation: {
                    'glow': 'glow 2s ease-in-out infinite alternate',
                    'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                },
                keyframes: {
                    'glow': {
                        'from': { 'box-shadow': '0 0 10px #0ea5e9, 0 0 20px #0ea5e9, 0 0 30px #0ea5e9' },
                        'to': { 'box-shadow': '0 0 20px #3b82f6, 0 0 30px #3b82f6, 0 0 40px #3b82f6' }
                    },
                    'pulse-glow': {
                        '0%, 100%': { 'opacity': 1 },
                        '50%': { 'opacity': 0.5 }
                    }
                }
            }
        }
    }
    </script>
    """, shared=True)
    
    # Custom CSS for cyberpunk theme
    ui.add_head_html("""
    <style>
    :root {
        --bg-nexus-950: #082f49;
        --text-slate-300: #cbd5e1;
        --border-cyber-500: #14b8a6;
        --glow-fish-500: #3b82f6;
    }
    
    body {
        font-family: 'Inter', sans-serif;
        background-color: var(--bg-nexus-950);
        color: var(--text-slate-300);
    }
    
    .fish-card {
        background: linear-gradient(145deg, rgba(8, 47, 73, 0.9), rgba(12, 74, 110, 0.9));
        border: 1px solid rgba(20, 184, 166, 0.3);
        border-radius: 0.75rem;
        padding: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    
    .fish-card:hover {
        border-color: rgba(20, 184, 166, 0.6);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3);
    }
    
    .fish-card.glow {
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    .fish-header {
        background: linear-gradient(90deg, rgba(8, 47, 73, 1), rgba(20, 184, 166, 0.3));
        border-bottom: 1px solid rgba(20, 184, 166, 0.5);
        padding: 1rem 1.5rem;
    }
    
    .nav-active {
        background: rgba(20, 184, 166, 0.2);
        border-left: 3px solid var(--border-cyber-500);
        font-weight: 600;
    }
    
    .btn-cyber {
        background: linear-gradient(90deg, #14b8a6, #0d9488);
        color: white;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }
    
    .btn-cyber:hover {
        background: linear-gradient(90deg, #0d9488, #0f766e);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4);
    }
    
    .btn-cyber:active {
        transform: translateY(0);
    }
    
    .toast-warning {
        background: linear-gradient(90deg, rgba(245, 158, 11, 0.9), rgba(217, 119, 6, 0.9));
        border: 1px solid rgba(245, 158, 11, 0.5);
        color: white;
    }
    
    .text-cyber-glow {
        text-shadow: 0 0 10px rgba(20, 184, 166, 0.7);
    }
    </style>
    """, shared=True)