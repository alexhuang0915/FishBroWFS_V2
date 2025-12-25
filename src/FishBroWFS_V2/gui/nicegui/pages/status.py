"""System Status Page - Shows dataset and strategy status with reload and build capabilities."""

from __future__ import annotations

from nicegui import ui

from FishBroWFS_V2.gui.nicegui.layout import render_topbar
from FishBroWFS_V2.gui.services.reload_service import (
    get_system_snapshot,
    reload_everything,
    build_parquet,
    build_all_parquet
)


@ui.page('/status')
def status_page():
    """System status page."""
    # Use render_topbar for consistent header
    render_topbar(active='status')
    
    # State for snapshot data
    snapshot = {'data': None}
    
    def refresh():
        """Refresh snapshot data."""
        try:
            snapshot['data'] = get_system_snapshot()
            ui.notify('Snapshot refreshed', type='positive')
            update_display()
        except Exception as e:
            ui.notify(f'Failed to refresh: {str(e)}', type='negative')
    
    def do_reload():
        """Reload all caches and registries."""
        try:
            r = reload_everything(reason='manual_ui')
            if r.ok:
                ui.notify('Reload OK', type='positive')
            else:
                ui.notify(f'Reload failed: {r.error}', type='negative')
            # Refresh snapshot after reload
            refresh()
        except Exception as e:
            ui.notify(f'Reload error: {str(e)}', type='negative')
    
    def do_build_all():
        """Build Parquet for all datasets."""
        try:
            ui.notify('Starting Parquet build for all datasets...', type='info')
            results = build_all_parquet(reason='manual_ui')
            
            # Count results
            success = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)
            
            if failed == 0:
                ui.notify(f'Build completed: {success} successful, {failed} failed', type='positive')
            else:
                ui.notify(f'Build completed with errors: {success} successful, {failed} failed', type='warning')
            
            # Refresh snapshot after build
            refresh()
        except Exception as e:
            ui.notify(f'Build error: {str(e)}', type='negative')
    
    def do_build_dataset(dataset_id: str):
        """Build Parquet for a single dataset."""
        try:
            ui.notify(f'Building Parquet for {dataset_id}...', type='info')
            result = build_parquet(dataset_id, reason='manual_ui')
            
            if result.success:
                ui.notify(f'Build successful for {dataset_id}', type='positive')
            else:
                ui.notify(f'Build failed for {dataset_id}: {result.error}', type='negative')
            
            # Refresh snapshot after build
            refresh()
        except Exception as e:
            ui.notify(f'Build error for {dataset_id}: {str(e)}', type='negative')
    
    # Create containers for dynamic content
    summary_container = ui.column().classes('w-full')
    datasets_container = ui.column().classes('w-full mt-6')
    strategies_container = ui.column().classes('w-full mt-6')
    
    def update_display():
        """Update UI with current snapshot data."""
        summary_container.clear()
        datasets_container.clear()
        strategies_container.clear()
        
        if not snapshot['data']:
            with summary_container:
                ui.label('No snapshot data available').classes('text-lg text-yellow-500')
            return
        
        data = snapshot['data']
        
        # Summary section
        with summary_container:
            with ui.card().classes('w-full bg-nexus-900 p-4'):
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.column().classes('gap-2'):
                        ui.label('System Snapshot').classes('text-2xl font-bold text-cyber-300')
                        ui.label(f'Created: {data.created_at.strftime("%Y-%m-%d %H:%M:%S")}').classes('text-sm text-slate-400')
                    
                    with ui.row().classes('gap-2'):
                        ui.button('Refresh Snapshot', icon='refresh').on('click', lambda: refresh())
                        ui.button('Reload All', icon='cached', color='primary').on('click', lambda: do_reload())
                        ui.button('Build All Parquet', icon='build', color='secondary').on('click', lambda: do_build_all())
                
                with ui.row().classes('w-full mt-4 gap-6'):
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Datasets').classes('text-lg font-bold text-cyber-300')
                        ui.label(f'Total: {data.total_datasets}').classes('text-2xl')
                        txt_present = sum(1 for ds in data.dataset_statuses if ds.txt_present)
                        parquet_present = sum(1 for ds in data.dataset_statuses if ds.parquet_present)
                        ui.label(f'TXT: {txt_present}').classes('text-sm text-blue-400')
                        ui.label(f'Parquet: {parquet_present}').classes('text-sm text-green-400')
                    
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Strategies').classes('text-lg font-bold text-cyber-300')
                        ui.label(f'Total: {data.total_strategies}').classes('text-2xl')
                        working = sum(1 for ss in data.strategy_statuses if ss.can_import and ss.can_build_spec)
                        ui.label(f'Working: {working}').classes('text-sm text-green-400')
                        ui.label(f'Errors: {data.total_strategies - working}').classes('text-sm text-red-400')
                    
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Build Status').classes('text-lg font-bold text-cyber-300')
                        up_to_date = sum(1 for ds in data.dataset_statuses if ds.up_to_date)
                        ui.label(f'Up-to-date: {up_to_date}').classes('text-2xl')
                        ui.label(f'Needs build: {data.total_datasets - up_to_date}').classes('text-sm text-yellow-400')
                        ui.label(f'Missing TXT: {data.total_datasets - txt_present}').classes('text-sm text-red-400')
                
                if data.notes:
                    with ui.card().classes('w-full mt-4 bg-nexus-800 p-3'):
                        for note in data.notes:
                            ui.label(f'• {note}').classes('text-sm text-slate-300')
        
        # Datasets table
        with datasets_container:
            ui.label('Datasets').classes('text-xl font-bold text-cyber-300 mb-4')
            
            if not data.dataset_statuses:
                ui.label('No datasets found').classes('text-slate-400')
            else:
                # Create table header
                with ui.row().classes('w-full bg-nexus-800 p-3 rounded-t-lg font-bold'):
                    ui.label('ID').classes('w-1/5')
                    ui.label('Kind').classes('w-1/10')
                    ui.label('TXT').classes('w-1/10')
                    ui.label('Parquet').classes('w-1/10')
                    ui.label('Up-to-date').classes('w-1/10')
                    ui.label('Schema').classes('w-1/10')
                    ui.label('Actions').classes('w-1/5')
                
                # Create table rows
                for ds in data.dataset_statuses:
                    txt_color = 'text-green-400' if ds.txt_present else 'text-red-400'
                    txt_text = '✓' if ds.txt_present else '✗'
                    parquet_color = 'text-green-400' if ds.parquet_present else 'text-red-400'
                    parquet_text = '✓' if ds.parquet_present else '✗'
                    uptodate_color = 'text-green-400' if ds.up_to_date else 'text-yellow-400'
                    uptodate_text = '✓' if ds.up_to_date else '✗'
                    schema_color = 'text-green-400' if ds.schema_ok else 'text-yellow-400'
                    schema_text = 'OK' if ds.schema_ok else 'Unknown'
                    
                    with ui.row().classes('w-full bg-nexus-900 p-3 border-b border-nexus-800 hover:bg-nexus-850'):
                        ui.label(ds.id).classes('w-1/5 font-mono text-sm')
                        ui.label(ds.kind).classes('w-1/10 text-slate-300')
                        ui.label(txt_text).classes(f'w-1/10 {txt_color} text-center')
                        ui.label(parquet_text).classes(f'w-1/10 {parquet_color} text-center')
                        ui.label(uptodate_text).classes(f'w-1/10 {uptodate_color} text-center')
                        ui.label(schema_text).classes(f'w-1/10 {schema_color} text-center')
                        
                        with ui.row().classes('w-1/5 gap-1'):
                            details_btn = ui.button('Details', icon='info', size='sm').props('dense outline')
                            details_btn.on('click', lambda d=ds: show_dataset_details(d))
                            
                            if ds.txt_present and not ds.up_to_date:
                                build_btn = ui.button('Build', icon='build', size='sm').props('dense outline color=primary')
                                build_btn.on('click', lambda d=ds: do_build_dataset(d.dataset_id))
                            else:
                                # Disabled button
                                build_btn = ui.button('Build', icon='build', size='sm').props('dense outline disabled')
                    
                    # Error row if present
                    if ds.error:
                        with ui.row().classes('w-full bg-red-900/20 p-2'):
                            ui.label(f'Error: {ds.error}').classes('text-sm text-red-300')
        
        # Strategies table
        with strategies_container:
            ui.label('Strategies').classes('text-xl font-bold text-cyber-300 mb-4 mt-8')
            
            if not data.strategy_statuses:
                ui.label('No strategies found').classes('text-slate-400')
            else:
                # Create table header
                with ui.row().classes('w-full bg-nexus-800 p-3 rounded-t-lg font-bold'):
                    ui.label('ID').classes('w-1/4')
                    ui.label('Import').classes('w-1/6')
                    ui.label('Build').classes('w-1/6')
                    ui.label('Features').classes('w-1/6')
                    ui.label('Signature').classes('w-1/6')
                    ui.label('Actions').classes('w-1/6')
                
                # Create table rows
                for ss in data.strategy_statuses:
                    import_color = 'text-green-400' if ss.can_import else 'text-red-400'
                    import_text = '✓' if ss.can_import else '✗'
                    build_color = 'text-green-400' if ss.can_build_spec else 'text-red-400'
                    build_text = '✓' if ss.can_build_spec else '✗'
                    
                    with ui.row().classes('w-full bg-nexus-900 p-3 border-b border-nexus-800 hover:bg-nexus-850'):
                        ui.label(ss.id).classes('w-1/4 font-mono text-sm')
                        ui.label(import_text).classes(f'w-1/6 {import_color} text-center')
                        ui.label(build_text).classes(f'w-1/6 {build_color} text-center')
                        ui.label(str(ss.feature_requirements_count)).classes('w-1/6 text-slate-300 text-center')
                        ui.label(ss.signature[:12] + '...' if len(ss.signature) > 12 else ss.signature).classes('w-1/6 font-mono text-xs')
                        
                        with ui.row().classes('w-1/6 gap-1'):
                            details_btn = ui.button('Details', icon='info', size='sm').props('dense outline')
                            details_btn.on('click', lambda s=ss: show_strategy_details(s))
                    
                    # Error row if present
                    if ss.error:
                        with ui.row().classes('w-full bg-red-900/20 p-2'):
                            ui.label(f'Error: {ss.error}').classes('text-sm text-red-300')
    
    def show_dataset_details(dataset):
        """Show dataset details in a dialog."""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(f'Dataset: {dataset.id}').classes('text-xl font-bold mb-4')
            
            with ui.column().classes('w-full gap-3'):
                # Basic info
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Basic Information').classes('font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        ui.label('Kind:').classes('font-medium')
                        ui.label(dataset.kind)
                        ui.label('TXT present:').classes('font-medium')
                        ui.label('Yes' if dataset.txt_present else 'No')
                        ui.label('Parquet present:').classes('font-medium')
                        ui.label('Yes' if dataset.parquet_present else 'No')
                        ui.label('Up-to-date:').classes('font-medium')
                        ui.label('Yes' if dataset.up_to_date else 'No')
                        ui.label('Schema OK:').classes('font-medium')
                        ui.label('Yes' if dataset.schema_ok else 'No')
                        ui.label('Bars count:').classes('font-medium')
                        ui.label(str(dataset.bars_count) if dataset.bars_count else 'Unknown')
                
                # TXT files
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('TXT Source Files').classes('font-bold mb-2')
                    if not dataset.txt_required_paths:
                        ui.label('No TXT files defined').classes('text-slate-400')
                    else:
                        for txt_path in dataset.txt_required_paths:
                            from pathlib import Path
                            txt_file = Path(txt_path)
                            exists = txt_file.exists()
                            status_color = 'text-green-400' if exists else 'text-red-400'
                            status_icon = '✓' if exists else '✗'
                            with ui.row().classes('w-full items-center gap-2 p-1'):
                                ui.label(status_icon).classes(status_color)
                                ui.label(txt_path).classes('flex-1 font-mono text-sm')
                                if exists:
                                    stat = txt_file.stat()
                                    ui.label(f'{stat.st_size:,} bytes').classes('text-xs text-slate-400')
                
                # Parquet files
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Parquet Output Files').classes('font-bold mb-2')
                    if not dataset.parquet_expected_paths:
                        ui.label('No Parquet files defined').classes('text-slate-400')
                    else:
                        for parquet_path in dataset.parquet_expected_paths:
                            from pathlib import Path
                            parquet_file = Path(parquet_path)
                            exists = parquet_file.exists()
                            status_color = 'text-green-400' if exists else 'text-red-400'
                            status_icon = '✓' if exists else '✗'
                            with ui.row().classes('w-full items-center gap-2 p-1'):
                                ui.label(status_icon).classes(status_color)
                                ui.label(parquet_path).classes('flex-1 font-mono text-sm')
                                if exists:
                                    stat = parquet_file.stat()
                                    ui.label(f'{stat.st_size:,} bytes').classes('text-xs text-slate-400')
                
                # Build action if needed
                if dataset.txt_present and not dataset.up_to_date:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Build Action').classes('font-bold mb-2')
                        with ui.row().classes('w-full gap-2'):
                            build_btn = ui.button('Build Parquet', icon='build', color='primary')
                            build_btn.on('click', lambda d=dataset: do_build_dataset(d.dataset_id))
                            ui.label('Converts TXT to Parquet format').classes('text-sm text-slate-400')
                
                # Error if present
                if dataset.error:
                    with ui.card().classes('w-full bg-red-900/30 p-3'):
                        ui.label('Error').classes('font-bold text-red-300 mb-1')
                        ui.label(dataset.error).classes('text-sm')
            
            ui.button('Close', on_click=dialog.close).classes('mt-4')
        
        dialog.open()
    
    def show_strategy_details(strategy):
        """Show strategy details in a dialog."""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(f'Strategy: {strategy.id}').classes('text-xl font-bold mb-4')
            
            with ui.column().classes('w-full gap-3'):
                # Basic info
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Basic Information').classes('font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        ui.label('Can import:').classes('font-medium')
                        ui.label('Yes' if strategy.can_import else 'No')
                        ui.label('Can build spec:').classes('font-medium')
                        ui.label('Yes' if strategy.can_build_spec else 'No')
                        ui.label('Feature requirements:').classes('font-medium')
                        ui.label(str(strategy.feature_requirements_count))
                        ui.label('Last modified:').classes('font-medium')
                        if strategy.mtime:
                            from datetime import datetime
                            dt = datetime.fromtimestamp(strategy.mtime)
                            ui.label(dt.strftime('%Y-%m-%d %H:%M:%S'))
                        else:
                            ui.label('Unknown')
                
                # Signature
                if strategy.signature:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Signature').classes('font-bold mb-2')
                        ui.label(strategy.signature).classes('font-mono text-sm break-all')
                
                # Error if present
                if strategy.error:
                    with ui.card().classes('w-full bg-red-900/30 p-3'):
                        ui.label('Error').classes('font-bold text-red-300 mb-1')
                        ui.label(strategy.error).classes('text-sm')
                
                # Show spec details if available
                if strategy.spec:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Specification').classes('font-bold mb-2')
                        if hasattr(strategy.spec, 'params') and strategy.spec.params:
                            ui.label('Parameters:').classes('font-medium mt-2')
                            for param in strategy.spec.params:
                                with ui.row().classes('w-full gap-4 p-1'):
                                    ui.label(f'{param.name}:').classes('w-1/3 font-medium')
                                    ui.label(f'{param.type} (default: {param.default})').classes('w-2/3 text-slate-300')
            
            ui.button('Close', on_click=dialog.close).classes('mt-4')
        
        dialog.open()
    
    # Main layout
    with ui.column().classes('w-full gap-4 p-6'):
        # Initial load
        refresh()
        
        # Dynamic containers will be filled by update_display
        ui.element('div').classes('w-full')  # Spacer


def register() -> None:
    """Register status page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass