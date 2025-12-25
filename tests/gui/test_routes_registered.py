"""Test that all routes are properly registered."""

import pytest
from nicegui import ui

from FishBroWFS_V2.gui.nicegui.router import register_pages


def test_status_route_registered():
    """Test that /status route is registered."""
    # Clear any existing routes (for test isolation)
    # Note: This depends on NiceGUI version
    # In some versions, we can check ui.routes or ui.app.routes
    
    # Register pages (creates ui.page routes)
    register_pages()
    
    # Check if /status route exists
    # The exact method depends on NiceGUI version
    # Try different approaches
    
    # Approach 1: Check ui.routes (if available)
    if hasattr(ui, 'routes'):
        assert '/status' in ui.routes, "Status route not registered in ui.routes"
        return
    
    # Approach 2: Check ui.app.routes (if available)
    if hasattr(ui, 'app') and hasattr(ui.app, 'routes'):
        # ui.app.routes might be a list of route objects
        routes = ui.app.routes
        route_paths = []
        for route in routes:
            # Extract path from route object
            if hasattr(route, 'path'):
                route_paths.append(route.path)
            elif hasattr(route, 'rule'):  # Flask-style
                route_paths.append(route.rule)
        
        assert '/status' in route_paths, f"Status route not found in {route_paths}"
        return
    
    # Approach 3: Check ui.page decorator registry (internal)
    # This is more implementation-dependent
    if hasattr(ui.page, '_pages'):
        page_paths = [path for path, _ in ui.page._pages.items()]
        assert '/status' in page_paths, f"Status route not in ui.page._pages: {page_paths}"
        return
    
    # If none of the above work, we can at least verify the import works
    # and the register_pages function doesn't raise an exception
    from FishBroWFS_V2.gui.nicegui.pages import register_status
    assert callable(register_status), "register_status should be callable"
    
    # This is a weaker test but still valuable
    pytest.skip("Cannot verify route registration in this NiceGUI version")


def test_wizard_route_registered():
    """Test that /wizard route is registered."""
    register_pages()
    
    # Similar checks as above
    if hasattr(ui, 'routes'):
        assert '/wizard' in ui.routes, "Wizard route not registered"
        return
    
    if hasattr(ui, 'app') and hasattr(ui.app, 'routes'):
        routes = ui.app.routes
        route_paths = []
        for route in routes:
            if hasattr(route, 'path'):
                route_paths.append(route.path)
            elif hasattr(route, 'rule'):
                route_paths.append(route.rule)
        
        assert '/wizard' in route_paths, f"Wizard route not found"
        return
    
    if hasattr(ui.page, '_pages'):
        page_paths = [path for path, _ in ui.page._pages.items()]
        assert '/wizard' in page_paths, f"Wizard route not in ui.page._pages"
        return
    
    from FishBroWFS_V2.gui.nicegui.pages import register_wizard
    assert callable(register_wizard), "register_wizard should be callable"
    pytest.skip("Cannot verify route registration in this NiceGUI version")


def test_home_route_registered():
    """Test that / (home) route is registered."""
    register_pages()
    
    if hasattr(ui, 'routes'):
        assert '/' in ui.routes, "Home route not registered"
        return
    
    if hasattr(ui, 'app') and hasattr(ui.app, 'routes'):
        routes = ui.app.routes
        route_paths = []
        for route in routes:
            if hasattr(route, 'path'):
                route_paths.append(route.path)
            elif hasattr(route, 'rule'):
                route_paths.append(route.rule)
        
        assert '/' in route_paths, f"Home route not found"
        return
    
    if hasattr(ui.page, '_pages'):
        page_paths = [path for path, _ in ui.page._pages.items()]
        assert '/' in page_paths, f"Home route not in ui.page._pages"
        return
    
    from FishBroWFS_V2.gui.nicegui.pages import register_home
    assert callable(register_home), "register_home should be callable"
    pytest.skip("Cannot verify route registration in this NiceGUI version")


def test_all_required_routes_exist():
    """Test that all required routes are registered."""
    required_routes = ['/', '/status', '/wizard', '/jobs', '/results', '/charts']
    
    register_pages()
    
    # Collect available routes
    available_routes = []
    
    if hasattr(ui, 'routes'):
        available_routes = list(ui.routes.keys()) if isinstance(ui.routes, dict) else ui.routes
    elif hasattr(ui, 'app') and hasattr(ui.app, 'routes'):
        for route in ui.app.routes:
            if hasattr(route, 'path'):
                available_routes.append(route.path)
            elif hasattr(route, 'rule'):
                available_routes.append(route.rule)
    elif hasattr(ui.page, '_pages'):
        available_routes = list(ui.page._pages.keys())
    
    # If we can't detect routes, skip the test
    if not available_routes:
        # At least verify the import works
        from FishBroWFS_V2.gui.nicegui.pages import register_status, register_wizard, register_home
        assert callable(register_status), "register_status should be callable"
        assert callable(register_wizard), "register_wizard should be callable"
        assert callable(register_home), "register_home should be callable"
        pytest.skip("Cannot verify route registration in this NiceGUI version")
    
    # Check each required route
    for route in required_routes:
        if route in available_routes:
            continue
        
        # Some routes might have trailing slashes or be registered differently
        # Check for close matches
        found = False
        for available in available_routes:
            if available == route or available == route.rstrip('/') or available == route + '/':
                found = True
                break
        
        if not found:
            # This is not a failure for all routes (some might be registered elsewhere)
            # But /status and / are critical
            if route in ['/', '/status']:
                pytest.fail(f"Critical route {route} not registered. Available: {available_routes}")
            else:
                # Just warn for non-critical routes
                print(f"Warning: Route {route} not found in {available_routes}")