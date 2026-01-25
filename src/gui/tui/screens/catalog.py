from textual import on
from textual.widgets import Label, DataTable, Static, ListView, ListItem
from textual.containers import Vertical, Horizontal
from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge

class StrategyItem(ListItem):
    """Custom list item to show strategy details in two lines."""
    def __init__(self, s_id: str, s_name: str, family: str, ready_str: str, feats: list[str], data2: bool):
        super().__init__()
        self.s_id = s_id
        self.s_name = s_name
        self.family = family
        self.ready_str = ready_str
        self.feats = feats
        self.data2 = data2

    def compose(self):
        with Vertical(classes="strategy_card"):
            with Horizontal(classes="card_header"):
                yield Label(f"[bold]{self.s_id}[/bold]", classes="id_col")
                yield Label(f"{self.s_name}", classes="name_col")
                yield Label(f"{self.family}", classes="family_col")
                yield Label(f"{self.ready_str}", classes="readiness_col")
                yield Label(f"Data2: {'YES' if self.data2 else 'NO'}", classes="data2_col")
            
            feat_text = ", ".join(self.feats) if self.feats else "None"
            yield Label(f"  [cyan]Features required:[/cyan] {feat_text}", classes="card_features")

class CatalogScreen(BaseScreen):
    """Strategy Catalog and Feature Library screen."""
    SCREEN_NAME = "catalog"
    
    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def main_compose(self):
        with Vertical(classes="full_panel"):
            yield Label("Strategy Catalog & Readiness Matrix", id="title")

            with Horizontal(id="catalog_header"):
                yield Label("ID", classes="id_col")
                yield Label("Display Name", classes="name_col")
                yield Label("Family", classes="family_col")
                yield Label("Readiness Index", classes="readiness_col")
                yield Label("Data2?", classes="data2_col")

            yield ListView(id="strategy_list")
            
            yield Label("Feature Library (Technical Indicators)", id="title_features", classes="section_title")
            yield DataTable(id="feature_table")

    def on_mount(self):
        super().on_mount()
        # Setup Feature Table
        ft = self.query_one("#feature_table", DataTable)
        ft.add_columns("Function ID", "Description")
        ft.cursor_type = "row"
        
        self.refresh_catalog()
        self.set_interval(30.0, self.refresh_catalog)

    def refresh_catalog(self):
        # Refresh Strategies
        sl = self.query_one("#strategy_list", ListView)
        try:
            catalog = self.bridge.get_strategy_catalog()
            readiness = self.bridge.get_strategy_readiness()
            feat_map = self.bridge.get_strategy_feature_map()
            
            sl.clear()
            for s in catalog:
                s_id = s.get("id", "N/A")
                ready_info = readiness.get(s_id, {"ready": False, "reason": "Unknown"})
                
                if ready_info["ready"]:
                    ready_str = f"[green]READY[/green] ({', '.join(ready_info.get('instr', []))})"
                else:
                    ready_str = f"[red]MISSING[/red] ({ready_info.get('reason', 'Check Data')})"

                feats = feat_map.get(s_id, [])
                
                sl.append(StrategyItem(
                    s_id, 
                    s.get("display_name", "N/A"),
                    s.get("family", "N/A"),
                    ready_str,
                    feats,
                    bool(s.get("requires_secondary_data"))
                ))
        except Exception as e:
            sl.clear()
            sl.append(ListItem(Label(f"[red]Error: {e}[/red]")))

        # Refresh Feature Library
        ft = self.query_one("#feature_table", DataTable)
        try:
            features = self.bridge.get_feature_library()
            ft.clear()
            for f in features:
                ft.add_row(
                    f.get("id", "N/A"),
                    f.get("description", "N/A")
                )
        except Exception as e:
            ft.clear()
            ft.add_row(f"[red]Error: {e}[/red]", "")

    @on(ListView.Selected, "#strategy_list")
    def _on_strategy_selected(self, event: ListView.Selected):
        # Could link to strategy detail report or config here
        pass
