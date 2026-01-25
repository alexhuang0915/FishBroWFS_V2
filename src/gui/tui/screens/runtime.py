import json
from textual.widgets import Label, DataTable
from textual.containers import Vertical, Horizontal, ScrollableContainer
from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel
from core.paths import get_runtime_root

class RuntimeIndexScreen(BaseScreen):
    """System configuration and data readiness screen."""
    SCREEN_NAME = "runtime"
    
    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def main_compose(self):
        with Vertical(classes="full_panel"):
            yield Label("SYSTEM STATUS & READINESS", id="title")
            
            with Horizontal():
                # Pillar 1: Data Readiness & Specs
                with Vertical(classes="half_panel"):
                    yield Label("DATA READINESS INDEX", classes="section_title")
                    yield DataTable(id="readiness_table")
                    
                    yield Label("INSTRUMENT SPECIFICATIONS", classes="section_title")
                    yield DataTable(id="instr_table")

                # Pillar 2: Profiles, Audit & Storage
                with Vertical(classes="half_panel"):
                    yield Label("TRADING PROFILES", classes="section_title")
                    yield DataTable(id="profiles_table")
                    
                    yield Label("CONFIGURATION HEALTH (AUDIT)", classes="section_title")
                    yield DataTable(id="audit_table")

                    yield Label("STORAGE USAGE (SHARED/)", classes="section_title")
                    yield DataTable(id="storage_table")

    def on_mount(self):
        super().on_mount()
        # Setup Readiness Table
        rt = self.query_one("#readiness_table", DataTable)
        rt.add_columns("Instrument", "RAW", "Prepared TFs", "Parquet")
        rt.cursor_type = "row"
        
        # Setup Instrument Table
        it = self.query_one("#instr_table", DataTable)
        it.add_columns("ID", "Name", "Exch", "Cur.", "BPV", "TickSz", "TickVal", "In.Margin", "Mt.Margin")
        it.cursor_type = "row"
        
        # Setup Audit Table
        at = self.query_one("#audit_table", DataTable)
        at.add_columns("Cat", "ID", "Issue")
        at.cursor_type = "row"

        # Setup Storage Table
        st = self.query_one("#storage_table", DataTable)
        st.add_columns("Season", "Size (MB)", "Datasets")
        st.cursor_type = "row"

        # Setup Profiles Table
        pt = self.query_one("#profiles_table", DataTable)
        pt.add_columns("Profile ID", "Symbol", "Timezone", "Slip(USD)", "Trading Sessions")
        pt.cursor_type = "row"
        
        self.refresh_all()
        self.set_interval(30.0, self.refresh_all)

    def refresh_all(self):
        self.refresh_index()
        self.refresh_instruments()
        self.refresh_profiles()
        self.refresh_audit()
        self.refresh_storage()

    def refresh_index(self):
        index_path = get_runtime_root() / "bar_prepare_index.json"
        table = self.query_one("#readiness_table", DataTable)
        if not index_path.exists():
            table.clear()
            table.add_row("[red]Index not found[/red]", "", "", "")
            return
        try:
            with open(index_path, "r") as f:
                data = json.load(f)
            instruments = data.get("instruments", {})
            table.clear()
            for name in sorted(instruments.keys()):
                info = instruments[name]
                raw = "[green]YES[/green]" if info.get("raw_available") else "[red]NO[/red]"
                tfs = sorted(info.get("timeframes", {}).keys(), key=lambda x: int(x) if x.isdigit() else 999)
                tfs_str = ", ".join(tfs) if tfs else "[yellow]None[/yellow]"
                parquet = "[green]READY[/green]" if info.get("parquet_status", {}).get("status") == "READY" else "[red]MISSING[/red]"
                table.add_row(name, raw, tfs_str, parquet)
        except Exception as e:
            table.clear()
            table.add_row(f"[red]Error: {e}[/red]", "", "", "")

    def refresh_instruments(self):
        table = self.query_one("#instr_table", DataTable)
        try:
            details = self.bridge.get_instrument_details()
            table.clear()
            for instr_id in sorted(details.keys()):
                d = details[instr_id]
                curr = d.get("currency", "")
                init = f"{d['initial_margin']:,.0f}" if d['initial_margin'] else "-"
                maint = f"{d['maintenance_margin']:,.0f}" if d['maintenance_margin'] else "-"
                table.add_row(
                    instr_id, d.get("name", ""), d.get("exchange", ""), curr,
                    f"{d.get('multiplier', 0):g}", f"{d.get('tick_size', 0):g}",
                    f"{d.get('tick_value', 0):g}", init, maint
                )
        except Exception as e:
            table.clear()
            table.add_row(f"[red]Error: {e}[/red]", "", "", "", "", "", "", "", "")

    def refresh_profiles(self):
        table = self.query_one("#profiles_table", DataTable)
        try:
            profiles = self.bridge.get_profile_details()
            table.clear()
            for p in profiles:
                table.add_row(p["id"], p["symbol"], p["tz"], f"{p['slippage']:g}", p["sessions"])
        except Exception as e:
            table.clear()
            table.add_row(f"[red]Error: {e}[/red]", "", "", "", "")

    def refresh_audit(self):
        table = self.query_one("#audit_table", DataTable)
        try:
            issues = self.bridge.get_config_audit()
            table.clear()
            if not issues:
                table.add_row("[green]Healthy[/green]", "All referenced files found", "")
            else:
                for iss in issues:
                    table.add_row(iss["cat"], iss["id"], f"[red]{iss['issue']}[/red]")
        except Exception as e:
            table.clear()
            table.add_row(f"[red]Error: {e}[/red]", "", "")

    def refresh_storage(self):
        table = self.query_one("#storage_table", DataTable)
        try:
            stats = self.bridge.get_storage_stats()
            table.clear()
            for s in stats:
                table.add_row(
                    s["season"],
                    f"{s['size_mb']:,.1f}",
                    ", ".join(s["datasets"][:3]) + (f" (+{len(s['datasets'])-3})" if len(s["datasets"]) > 3 else "")
                )
        except Exception as e:
            table.clear()
            table.add_row(f"[red]Error: {e}[/red]", "", "")
