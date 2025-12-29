"""Candidates page - Top‑K view."""
import logging
from typing import List, Dict, Any
from nicegui import ui

from ..layout.tables import render_simple_table
from ..layout.cards import render_card
from ..services.candidates_service import get_top_candidates, get_candidate_stats
from ..state.app_state import AppState

logger = logging.getLogger(__name__)


def render() -> None:
    """Render the Candidates page."""
    app_state = AppState.get()
    
    ui.label("Candidate Strategies").classes("text-2xl font-bold text-primary mb-6")
    ui.label("Top‑K candidates from latest runs (read‑only)").classes("text-secondary mb-8")
    
    # Truth banner when backend offline
    from ..services.status_service import get_status
    status = get_status()
    if not status.backend_up:
        with ui.card().classes("w-full bg-warning/10 border-warning border-l-4 mb-6"):
            ui.label("⚠️ Backend offline – displaying mock data").classes("text-warning font-medium")
    
    # Controls
    with ui.row().classes("w-full gap-4 mb-6"):
        top_k_input = ui.number("Top K", value=20, min=1, max=100).classes("w-1/6")
        side_select = ui.select(["All", "Long", "Short"], label="Side", value="All").classes("w-1/6")
        sort_select = ui.select(["Sharpe", "Win Rate", "Max DD", "Profit Factor"], label="Sort By", value="Sharpe").classes("w-1/6")
        dedup_check = ui.checkbox("Deduplicate").classes("items-center")
        refresh_btn = ui.button("Refresh", icon="refresh").classes("w-1/6")
        export_btn = ui.button("Export CSV", icon="download").classes("w-1/6")
    
    # Stats summary
    with ui.row().classes("w-full gap-4 mb-6"):
        total_card = render_card(
            title="Total Candidates",
            content="",
            icon="stacked_line_chart",
            color="purple",
            width="w-1/4",
        )
        sharpe_card = render_card(
            title="Avg Sharpe",
            content="",
            icon="trending_up",
            color="success",
            width="w-1/4",
        )
        winrate_card = render_card(
            title="Avg Win Rate",
            content="",
            icon="percent",
            color="cyan",
            width="w-1/4",
        )
        best_card = render_card(
            title="Best Strategy",
            content="",
            icon="emoji_events",
            color="warning",
            width="w-1/4",
        )
    
    # Candidates table
    columns = ["Rank", "Strategy ID", "Side", "Sharpe", "Win Rate", "Max DD", "Profit Factor", "Actions"]
    table_container = ui.column().classes("w-full")
    
    # Chart placeholder
    chart_container = ui.card().classes("w-full mt-6")
    
    # Note
    ui.label("Candidates page is read‑only. Use Portfolio page to select instances for deployment.").classes("text-xs text-muted mt-8")
    
    def update_candidates():
        """Fetch candidates and update UI."""
        from ..services.status_service import get_status
        try:
            top_k = int(top_k_input.value)
            side = side_select.value
            sort_by = sort_select.value
            dedup = dedup_check.value
            
            candidates = get_top_candidates(
                top_k=top_k,
                side=side if side != "All" else None,
                sort_by=sort_by,
                dedup=dedup,
            )
            stats = get_candidate_stats(candidates)
            
            # Update stats cards
            total_card.update_content(str(stats.get("total", 0)))
            sharpe_card.update_content(f"{stats.get('avg_sharpe', 0):.2f}")
            winrate_card.update_content(f"{stats.get('avg_win_rate', 0):.1%}")
            best_card.update_content(stats.get("best_strategy", "N/A"))
            
            # Update table
            table_container.clear()
            rows = []
            for idx, cand in enumerate(candidates, start=1):
                rows.append([
                    str(idx),
                    cand.get("strategy_id", ""),
                    cand.get("side", ""),
                    f"{cand.get('sharpe', 0):.2f}",
                    f"{cand.get('win_rate', 0):.1%}",
                    f"{cand.get('max_dd', 0):.1%}",
                    f"{cand.get('profit_factor', 0):.2f}",
                    "View",
                ])
            with table_container:
                render_simple_table(columns, rows)
            
            # Update chart (placeholder)
            chart_container.clear()
            with chart_container:
                ui.label("Performance Distribution").classes("text-lg font-bold mb-2")
                # Chart warning when backend offline
                if not get_status().backend_up:
                    ui.label("⚠️ Chart displays mock data only").classes("text-warning text-sm mb-2")
                # Dummy chart
                ui.echart({
                    "xAxis": {"type": "category", "data": ["L1", "L2", "L3", "S1", "S2", "S3"]},
                    "yAxis": {"type": "value"},
                    "series": [{"data": [1.2, 1.8, 1.5, 1.9, 1.3, 2.1], "type": "bar"}],
                }).classes("w-full h-64")
                
        except Exception as e:
            logger.exception("Failed to update candidates")
            ui.notify(f"Failed to load candidates: {e}", type="negative")
    
    refresh_btn.on("click", update_candidates)
    # Initial load
    update_candidates()