"""Table helpers."""
from typing import List, Any, Optional
from nicegui import ui

from ..theme.nexus_tokens import TOKENS
from ..ui_compat import register_element


def render_simple_table(
    columns: List[str],
    rows: List[List[Any]],
    striped: bool = True,
    hover: bool = True,
    compact: bool = False,
) -> ui.table:
    """Render a simple styled table.
    
    Args:
        columns: List of column headers.
        rows: List of rows, each row is a list of cell values.
        striped: Apply zebra striping.
        hover: Highlight row on hover.
        compact: Use compact spacing.
    
    Returns:
        ui.table element.
    """
    table = ui.table(columns=columns, rows=rows).classes("w-full")
    register_element("tables", {"columns": columns, "rows": len(rows)})
    register_element("tables", {"columns": columns, "rows": len(rows)})
    
    if striped:
        table.classes("striped")
    if hover:
        table.classes("hover")
    if compact:
        table.classes("compact")
    
    # Add some default styling
    table.style("""
        border-collapse: collapse;
        background-color: var(--bg-panel-dark);
    """)
    
    return table


def render_interactive_table(
    columns: List[str],
    rows: List[List[Any]],
    on_row_click=None,
    selectable: bool = False,
) -> ui.table:
    """Render an interactive table with clickable rows and selection.
    
    Args:
        columns: Column headers.
        rows: Row data.
        on_row_click: Callback function(row_index, row_data).
        selectable: Whether rows can be selected.
    
    Returns:
        ui.table element.
    """
    table = ui.table(columns=columns, rows=rows).classes("w-full")
    
    if selectable:
        table.props("selection-mode='single'")
    
    if on_row_click:
        def handle_click(e):
            row_index = e.args['rowIndex']
            row_data = rows[row_index]
            on_row_click(row_index, row_data)
        table.on("rowClick", handle_click)
    
    return table