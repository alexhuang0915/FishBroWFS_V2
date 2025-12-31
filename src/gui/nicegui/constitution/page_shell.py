"""Page Shell: Consistent dark container wrapper for all pages.

Enforces Page Wrapper Guarantee:
- Every page content rendered inside same dark container
- Consistent padding/width
- Ensures min-height: 100vh
- Applies consistent background and text colors
"""
import logging
from typing import Optional, Callable

from nicegui import ui

from ..theme.nexus_tokens import TOKENS
# Note: We don't import get_global_constitution here to avoid circular import
# It will be imported lazily inside the function if needed

logger = logging.getLogger(__name__)

# Track which pages have used page_shell
_PAGES_USING_SHELL = set()

# Layout constants as required
DEFAULT_MAX_WIDTH_PX = 1200
DEFAULT_PADDING_PX = 24


def page_shell(title: Optional[str], content_fn: Callable[[], None]) -> None:
    """Render page content inside a consistent dark container shell.
    
    This function must be used by every page to ensure Page Wrapper Guarantee.
    
    Args:
        title: Optional page title (displayed as h1 if provided)
        content_fn: Function that renders the actual page content
    """
    # Record that this page is using the shell
    import inspect
    caller_frame = inspect.currentframe().f_back
    caller_info = inspect.getframeinfo(caller_frame)
    page_name = f"{caller_info.filename}:{caller_info.lineno}"
    _PAGES_USING_SHELL.add(page_name)
    
    # Get constitution for potential violation recording (lazy import to avoid circular import)
    constitution = None
    try:
        from .ui_constitution import get_global_constitution
        constitution = get_global_constitution()
    except (RuntimeError, ImportError):
        # Constitution not applied yet or import failed, but we can still render
        constitution = None
    
    # Main container with dark background guarantee using CSS classes
    with ui.element('div').classes('nexus-page-fill'):
        with ui.element('div').classes('nexus-content'):
            # Optional title
            if title:
                with ui.element('div').classes('nexus-page-title'):
                    ui.label(title).classes(
                        "text-2xl md:text-3xl font-bold text-primary "
                        "border-b-2 border-purple pb-2"
                    )
            
            # Page content area
            content_fn()
    
    # Log for debugging
    logger.debug(f"Page shell rendered for {page_name} (title: {title})")
    
    # Record in constitution if available
    if constitution and constitution.config.enforce_page_shell:
        # This page is compliant, no violation
        pass


def get_pages_using_shell() -> set:
    """Get set of pages that have used page_shell().
    
    Returns:
        Set of page identifiers (filename:lineno)
    """
    return _PAGES_USING_SHELL.copy()


def check_page_shell_compliance(page_names: Optional[list] = None) -> dict:
    """Check if specified pages are using page_shell.
    
    Args:
        page_names: List of page identifiers to check. If None, checks all tracked pages.
        
    Returns:
        Dictionary with compliance status
    """
    pages_using = get_pages_using_shell()
    
    if page_names is None:
        page_names = list(pages_using)
    
    non_compliant = []
    for page in page_names:
        if page not in pages_using:
            non_compliant.append(page)
    
    return {
        "total_pages": len(page_names),
        "compliant": len(page_names) - len(non_compliant),
        "non_compliant": non_compliant,
        "compliance_rate": (len(page_names) - len(non_compliant)) / max(len(page_names), 1),
    }


def create_page_shell_demo() -> None:
    """Create a demo of the page shell for testing."""
    def demo_content():
        ui.label("This is demo content inside the page shell.")
        with ui.row():
            ui.button("Button 1")
            ui.button("Button 2")
        ui.markdown("""
        ## Markdown Example
        
        - Item 1
        - Item 2
        - Item 3
        
        ```python
        def example():
            return "Code block"
        ```
        """)
    
    page_shell("Demo Page", demo_content)
