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

# Inspect routes
for route in fastapi_app.routes:
    print(route)
    if hasattr(route, 'path'):
        print(f"  path: {route.path}")
    if hasattr(route, 'app'):
        print(f"  app: {route.app}")