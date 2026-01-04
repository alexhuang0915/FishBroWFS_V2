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
        columns: List of column headers (strings).
        rows: List of rows, each row is a list of cell values.
        striped: Apply zebra striping.
        hover: Highlight row on hover.
        compact: Use compact spacing.
    
    Returns:
        ui.table element.
    """
    # Convert string columns to dict format expected by NiceGUI table
    column_dicts = []
    for col in columns:
        if isinstance(col, str):
            # Create a safe field name (lowercase, underscores)
            field = col.lower().replace(' ', '_').replace('(', '').replace(')', '')
            column_dicts.append({
                'name': field,
                'label': col,
                'field': field,
                'align': 'left',
            })
        else:
            # Assume it's already a dict
            column_dicts.append(col)
    
    # Convert rows from list of lists to list of dicts if needed
    # Determine if rows are list of lists (not dicts)
    if rows and isinstance(rows[0], list):
        # Transform each row list to dict mapping field to value
        dict_rows = []
        for row in rows:
            row_dict = {}
            for idx, col_dict in enumerate(column_dicts):
                field = col_dict['field']
                row_dict[field] = row[idx] if idx < len(row) else None
            dict_rows.append(row_dict)
        rows_data = dict_rows
    else:
        rows_data = rows
    
    table = ui.table(columns=column_dicts, rows=rows_data).classes("w-full")
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
        columns: Column headers (strings).
        rows: Row data as list of lists.
        on_row_click: Callback function(row_index, row_data).
        selectable: Whether rows can be selected.
    
    Returns:
        ui.table element.
    """
    # Convert string columns to dict format expected by NiceGUI table
    column_dicts = []
    for col in columns:
        if isinstance(col, str):
            field = col.lower().replace(' ', '_').replace('(', '').replace(')', '')
            column_dicts.append({
                'name': field,
                'label': col,
                'field': field,
                'align': 'left',
            })
        else:
            column_dicts.append(col)
    
    # Convert rows from list of lists to list of dicts
    if rows and isinstance(rows[0], list):
        dict_rows = []
        for row in rows:
            row_dict = {}
            for idx, col_dict in enumerate(column_dicts):
                field = col_dict['field']
                row_dict[field] = row[idx] if idx < len(row) else None
            dict_rows.append(row_dict)
        rows_data = dict_rows
    else:
        rows_data = rows
    
    table = ui.table(columns=column_dicts, rows=rows_data).classes("w-full")
    
    if selectable:
        table.props("selection-mode='single'")
    
    if on_row_click:
        def handle_click(e):
            row_index = e.args['rowIndex']
            row_data = rows[row_index]  # original row list (preserve UI elements?)
            on_row_click(row_index, row_data)
        table.on("rowClick", handle_click)
    
    return table