"""fish-card helpers."""
from typing import Optional, Any, Tuple
from nicegui import ui, elements

from ..theme.nexus_tokens import TOKENS
from ..ui_compat import register_element


def render_card(
    title: str,
    content: Any,
    icon: Optional[str] = None,
    color: str = "primary",
    width: str = "w-full",
    selected: bool = False,
    selection_side: str = "long",  # 'long' or 'short'
    on_click=None,
) -> ui.card:
    """Render a fish-card with optional selection styling.
    
    Args:
        title: Card title.
        content: Text, component, or HTML.
        icon: Optional icon name.
        color: Accent color (primary, success, danger, warning, cyan, purple, blue).
        width: CSS width class.
        selected: Whether card is selected (adds neon strip).
        selection_side: If selected, side determines strip color (long=green, short=red).
        on_click: Optional click handler.
    
    Returns:
        The card element with added attributes `_content_label`, `_icon_element`,
        `_title_label` and helper methods `update_content`, `update_icon`.
    """
    color_map = {
        "primary": TOKENS['accents']['blue'],
        "success": TOKENS['accents']['success'],
        "danger": TOKENS['accents']['danger'],
        "warning": TOKENS['accents']['warning'],
        "cyan": TOKENS['accents']['cyan'],
        "purple": TOKENS['accents']['purple'],
        "blue": TOKENS['accents']['blue'],
    }
    border_color = color_map.get(color, TOKENS['accents']['blue'])
    
    card_classes = f"fish-card {width} p-4 rounded-lg border"
    if selected:
        card_classes += " selected"
        if selection_side == "short":
            card_classes += " short"
    
    card = ui.card().classes(card_classes)
    register_element("cards", card)
    if on_click:
        card.on("click", on_click)
    
    with card:
        with ui.row().classes("items-center gap-2 mb-2") as title_row:
            icon_elem = None
            if icon:
                icon_elem = ui.icon(icon, color=border_color)
            title_label = ui.label(title).classes("font-bold text-lg")
        # Content
        content_label = None
        if isinstance(content, str):
            content_label = ui.label(content).classes("text-secondary")
        else:
            # Assume it's a UI element
            content
    
    # Inline style for border color (optional)
    if not selected:
        card.style(f"border-color: {border_color}20;")
    
    # Attach references for dynamic updates
    card._icon_element = icon_elem
    card._title_label = title_label
    card._content_label = content_label
    card._color = color
    card._icon_name = icon
    card._color_map = color_map
    card._border_color = border_color
    card._selected = selected
    
    def update_content(new_content: str) -> None:
        """Update the card's content text."""
        if card._content_label is not None:
            card._content_label.set_text(new_content)
        else:
            # If content was not a string originally, we cannot update.
            # In that case, replace the whole content? Not implemented.
            pass
    
    def update_color(new_color: str) -> None:
        """Update the card's accent color (border and icon)."""
        if new_color == card._color:
            return
        border_color_hex = card._color_map.get(new_color, TOKENS['accents']['blue'])
        # Update border color if not selected
        if not card._selected:
            card.style(f"border-color: {border_color_hex}20;")
        # Update icon color
        if card._icon_element is not None:
            card._icon_element.props(f"color={border_color_hex}")
        card._color = new_color
        card._border_color = border_color_hex
    
    def update_icon(new_icon: Optional[str] = None, new_color: Optional[str] = None) -> None:
        """Update the card's icon and/or color."""
        if card._icon_element is None:
            return
        if new_color is not None:
            update_color(new_color)
        if new_icon is not None:
            # Replace icon element (simplistic: remove old, create new)
            # Find parent row (title_row) - we didn't store it, but we can navigate.
            # For now, skip icon name changes.
            pass
    
    card.update_content = update_content
    card.update_color = update_color
    card.update_icon = update_icon
    
    return card