#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

# Monkey-patch to avoid gui import errors
import builtins
real_import = builtins.__import__
def patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'gui':
        raise ImportError('skip')
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = patched_import

try:
    from nicegui import app, ui
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# Create a dummy FastAPI app to mount
from fastapi import FastAPI
fastapi_app = FastAPI()

# Call ui.run_with to see what happens
ui.run_with(fastapi_app, mount_path='/')

# Now inspect the sio object from nicegui.core
from nicegui import core
print(f"sio: {core.sio}")
print(f"sio.async_mode: {core.sio.async_mode}")
try:
    print(f"sio.transport: {core.sio.transport}")
except AttributeError:
    pass
try:
    print(f"sio.cors_allowed_origins: {core.sio.cors_allowed_origins}")
except AttributeError:
    pass
try:
    print(f"sio._async: {core.sio._async}")
except AttributeError:
    pass

# Check if there is an ASGI app attached
if hasattr(core.sio, 'asgi_app'):
    print(f"asgi_app: {core.sio.asgi_app}")
    # Try to see its routes
    if hasattr(core.sio.asgi_app, 'routes'):
        for route in core.sio.asgi_app.routes:
            print(f"  Route: {route}")

# Also inspect the app's router
from nicegui.app import app as nicegui_app
print(f"NiceGUI app routes:")
for route in nicegui_app.routes:
    print(f"  {route}")
    if hasattr(route, 'path'):
        print(f"    path: {route.path}")
    if hasattr(route, 'app'):
        print(f"    app: {route.app}")