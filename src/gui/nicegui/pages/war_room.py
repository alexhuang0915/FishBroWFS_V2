from nicegui import ui
from gui.services.war_room_service import WarRoomService
import asyncio

service = WarRoomService()

# ==============================================================================
# 1. ASSETS & STYLES (THE NEXUS THEME)
# ==============================================================================
def inject_nexus_theme():
    # 注入字體
    ui.add_head_html(r"""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@300;400;500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        nexus: { 950: '#030014', 900: '#09041f', 800: '#150a38', 700: '#24125f' },
                        neon: { purple: '#a855f7', blue: '#3b82f6', cyan: '#06b6d4', pink: '#ec4899' },
                        signal: { success: '#10b981', danger: '#ef4444', warn: '#f59e0b' }
                    },
                    fontFamily: { mono: ['"JetBrains Mono"', 'monospace'], sans: ['"Inter"', 'sans-serif'] },
                    boxShadow: { 'neon-glow': '0 0 10px rgba(168, 85, 247, 0.3)', 'blue-glow': '0 0 10px rgba(59, 130, 246, 0.3)' }
                }
            }
        }
    </script>
    <style>
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #030014; }
        ::-webkit-scrollbar-thumb { background: #24125f; border-radius: 2px; }
        ::-webkit-scrollbar-thumb:hover { background: #a855f7; }
        body { background-color: #030014; color: #cbd5e1; }
        body::before {
            content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background-image: linear-gradient(rgba(168, 85, 247, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(168, 85, 247, 0.03) 1px, transparent 1px);
            background-size: 40px 40px; z-index: -1; pointer-events: none;
        }
        .fish-card {
            background: rgba(13, 7, 30, 0.7); border: 1px solid #24125f; border-radius: 4px; backdrop-filter: blur(5px);
            transition: all 0.2s ease; position: relative; overflow: hidden;
        }
        .fish-card:hover { border-color: #a855f7; box-shadow: 0 0 15px -5px rgba(168, 85, 247, 0.3); }
        .btn-neon { background: linear-gradient(90deg, #7e22ce, #3b82f6); color: #fff; border: none; box-shadow: 0 0 10px rgba(126, 34, 206, 0.4); }
        .btn-neon:hover { box-shadow: 0 0 20px rgba(59, 130, 246, 0.6); transform: translateY(-1px); }
        .nav-tab.active { color: #fff; text-shadow: 0 0 8px rgba(168, 85, 247, 0.6); border-bottom: 2px solid #a855f7; }
    </style>
    """)

# ==============================================================================
# 2. UI COMPONENTS (MAPPED FROM YOUR HTML)
# ==============================================================================

def status_header():
    with ui.header().classes('bg-nexus-900/90 border-b border-nexus-700 py-4 px-6 flex items-center justify-between shrink-0 z-30 shadow-lg backdrop-blur-sm'):
        # Title Area
        with ui.row().classes('items-center gap-6'):
            with ui.column().classes('gap-0'):
                with ui.row().classes('items-baseline gap-3'):
                    ui.label('FishBroCapital').classes('text-2xl font-bold text-white tracking-wider drop-shadow-[0_0_5px_rgba(168,85,247,0.5)]')
                    ui.label('(2026Q1)').classes('text-lg font-mono text-neon-purple tracking-tight')
                with ui.row().classes('items-center gap-2 mt-0.5'):
                    ui.element('span').classes('w-1.5 h-1.5 rounded-full bg-signal-success shadow-[0_0_5px_#10b981] animate-pulse')
                    ui.label('SYSTEM ONLINE').classes('text-[10px] uppercase tracking-[0.15em] text-slate-500 font-bold')

        # Status Metrics
        with ui.row().classes('gap-8 pr-2'):
            def metric(label, value, color_class):
                with ui.column().classes('items-end cursor-default group'):
                    ui.label(label).classes('text-[10px] text-slate-500 uppercase font-bold tracking-widest mb-0.5')
                    # 這裡綁定數據更新
                    return ui.label(value).classes(f'font-mono font-bold leading-none drop-shadow-md {color_class}')

            ui.element('div').classes('h-8 w-px bg-nexus-700')
            metric('RUNS', '0', 'text-white text-xl')
            ui.element('div').classes('h-8 w-px bg-nexus-700')
            metric('PORTFOLIO', 'Empty', 'text-xs text-neon-blue italic')
            ui.element('div').classes('h-8 w-px bg-nexus-700')
            metric('DEPLOY', 'Undeployed', 'text-xs text-slate-600 italic')

def dashboard_cards():
    with ui.grid(columns=4).classes('w-full gap-4 shrink-0'):
        # Card 1: Runs Executed
        with ui.element('div').classes('fish-card p-4 flex flex-col justify-between h-28 group'):
            ui.icon('terminal').classes('absolute right-2 top-2 text-nexus-700 group-hover:text-neon-purple transition-colors text-2xl')
            ui.label('RUNS EXECUTED').classes('text-slate-500 text-[10px] uppercase font-bold tracking-widest')
            with ui.column().classes('gap-0'):
                ui.label('0').classes('text-3xl font-mono text-white font-light tracking-tighter')
                ui.label('System Idle').classes('text-[10px] text-slate-600 font-mono mt-1')
        
        # Card 2: Portfolio
        with ui.element('div').classes('fish-card p-4 flex flex-col justify-between h-28 group'):
            ui.icon('pie_chart').classes('absolute right-2 top-2 text-nexus-700 group-hover:text-neon-blue transition-colors text-2xl')
            ui.label('PORTFOLIO').classes('text-slate-500 text-[10px] uppercase font-bold tracking-widest')
            with ui.column().classes('gap-0 w-full'):
                ui.label('Pending').classes('text-lg text-neon-blue font-medium')
                with ui.element('div').classes('w-full bg-nexus-950 h-1 rounded-full overflow-hidden border border-nexus-700 mt-2'):
                    ui.element('div').classes('bg-neon-blue h-full w-0')

        # Card 3: Deployment
        with ui.element('div').classes('fish-card p-4 flex flex-col justify-between h-28 group'):
            ui.icon('rocket_launch').classes('absolute right-2 top-2 text-nexus-700 group-hover:text-neon-pink transition-colors text-2xl')
            ui.label('DEPLOYMENT').classes('text-slate-500 text-[10px] uppercase font-bold tracking-widest')
            with ui.column().classes('gap-0'):
                ui.label('Not Deployed').classes('text-lg text-slate-400 font-light')
                with ui.row().classes('items-center gap-2 mt-2'):
                    ui.element('span').classes('h-1.5 w-1.5 rounded-full bg-nexus-700')
                    ui.label('Offline').classes('text-[10px] text-slate-600')

        # Card 4: Actions (The Wizard Trigger)
        with ui.element('div').classes('fish-card p-4 flex flex-col justify-center gap-2 h-28 border-neon-purple/30 bg-neon-purple/5'):
            ui.button('New Operation', icon='add').classes('btn-neon w-full py-2 rounded text-xs font-bold tracking-wide') \
                .on('click', lambda: ui.notify('Initializing Wizard...', color='purple'))
            ui.button('Go to Portfolio').classes('bg-nexus-800 text-slate-300 border border-nexus-700 hover:border-neon-purple hover:text-white w-full py-1 text-xs rounded transition-all')

def production_pipeline_deck(log_area, status_label):
    """
    對應你的 'Run Wizard' 和 'Active Ops' 概念，這裡是實際操作區
    """
    ui.label('PRODUCTION PIPELINE (ACTIVE OPS)').classes('text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2 mt-4')
    
    with ui.grid(columns=4).classes('w-full gap-4'):
        # Helper for Command Buttons
        def cmd_btn(name, script_key, color, icon):
            btn = ui.element('div').classes(f'fish-card p-4 cursor-pointer group hover:bg-nexus-800 border-{color}-500/50')
            with btn:
                with ui.row().classes('items-center gap-3'):
                    ui.icon(icon).classes(f'text-{color}-500 text-2xl group-hover:text-white transition-colors')
                    with ui.column().classes('gap-0'):
                        ui.label(name).classes(f'text-sm font-bold text-{color}-400 group-hover:text-white')
                        ui.label(f'EXECUTE {script_key.upper()}').classes('text-[9px] text-slate-600 font-mono group-hover:text-slate-400')
            # Bind Click
            btn.on('click', lambda: run_script(script_key, log_area, status_label))

        cmd_btn('PHASE 2: RESEARCH', 'research', 'neon-cyan', 'science')
        cmd_btn('PHASE 3A: PLATEAU', 'plateau', 'neon-purple', 'psychology')
        cmd_btn('PHASE 3B: FREEZE', 'freeze', 'signal-warn', 'ac_unit')
        cmd_btn('PHASE 3C: COMPILE', 'compile', 'signal-success', 'factory')

async def run_script(key, log_view, status_lbl):
    if service.get_script_status()['running']:
        ui.notify('SYSTEM BUSY: Pipeline in use.', type='warning', classes='bg-nexus-800 border border-signal-warn text-white')
        return
    
    log_view.push(f'\n>>> INITIATING {key.upper()} SEQUENCE...\n')
    status_lbl.text = f'RUNNING: {key.upper()}'
    status_lbl.classes('text-neon-cyan', remove='text-slate-500')
    
    await service.run_script(key)

# ==============================================================================
# 3. MAIN PAGE STRUCTURE
# ==============================================================================
def war_room_page():
    inject_nexus_theme()
    
    # Body Container
    with ui.column().classes('w-full h-screen bg-nexus-950 text-slate-300 p-0 gap-0 overflow-hidden'):
        
        # 1. Header
        status_header()

        # 2. Tabs (Navigation)
        with ui.row().classes('bg-nexus-900 border-b border-nexus-700 px-6 gap-1 w-full h-10 items-center shrink-0'):
            def tab_btn(label, active=False):
                classes = 'nav-tab text-[11px] font-bold uppercase tracking-wider px-4 h-full flex items-center cursor-pointer'
                if active: classes += ' active'
                ui.label(label).classes(classes)
            
            tab_btn('DASHBOARD', True)
            tab_btn('WIZARD')
            tab_btn('HISTORY')
            tab_btn('CANDIDATES')
            tab_btn('PORTFOLIO')
            tab_btn('DEPLOY')

        # 3. Main Content Area
        with ui.row().classes('w-full flex-1 overflow-hidden p-6 gap-6'):
            
            # LEFT COLUMN: Controls & Status
            with ui.column().classes('w-2/3 h-full gap-6 overflow-y-auto pr-2'):
                # Top Cards
                dashboard_cards()
                
                # Active Ops / Pipeline
                # Log Area defined here to be passed to buttons
                with ui.row().classes('items-center justify-between w-full'):
                     ui.label('SYSTEM LOGS').classes('text-xs font-bold text-slate-400 uppercase tracking-widest')
                     status_label = ui.label('IDLE').classes('text-xs font-mono font-bold text-slate-500')

                log_area = ui.log().classes('w-full h-64 bg-nexus-950 font-mono text-[10px] text-green-400 p-3 border border-nexus-700 rounded inner-shadow overflow-y-auto')
                
                # Buttons Deck
                production_pipeline_deck(log_area, status_label)

            # RIGHT COLUMN: Real-time Intelligence
            with ui.column().classes('w-1/3 h-full gap-4'):
                ui.label('REAL-TIME INTELLIGENCE').classes('text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2')
                
                # Candidates Table Mockup
                with ui.element('div').classes('fish-card flex-1 flex flex-col w-full'):
                    with ui.row().classes('p-3 border-b border-nexus-700 bg-nexus-800/50 justify-between items-center shrink-0 w-full'):
                        ui.label('TOP CANDIDATES').classes('text-[10px] font-bold text-slate-400 uppercase')
                        ui.label('PROVISIONAL').classes('text-[9px] font-mono text-neon-blue')
                    
                    # Table Content
                    with ui.column().classes('p-0 gap-0 w-full'):
                        def row(rank, name, score, color):
                            with ui.row().classes('w-full justify-between px-4 py-2 border-b border-nexus-800 hover:bg-nexus-800 transition-colors'):
                                ui.label(rank).classes(f'font-mono text-xs font-bold {color}')
                                ui.label(name).classes('font-mono text-xs text-slate-300')
                                ui.label(score).classes('font-mono text-xs font-bold text-signal-success')
                        
                        row('#01', 'L1_MNQ_60m_P1', '8.45', 'text-neon-purple')
                        row('#02', 'S2_MNQ_60m_P4', '8.12', 'text-neon-blue')
                        row('#03', 'L3_MES_120m_V9', '7.94', 'text-slate-500')

    # Timer for Log Updates
    def update_logs():
        logs = service.get_script_log()
        if logs: log_area.push(logs)
        
        # Update Status Indicator based on service
        st = service.get_script_status()
        if not st['running'] and status_label.text.startswith('RUNNING'):
            status_label.text = 'READY' if st['exit_code'] == 0 else 'FAILED'
            status_label.classes('text-signal-success' if st['exit_code'] == 0 else 'text-signal-danger', remove='text-neon-cyan')

    ui.timer(0.5, update_logs)