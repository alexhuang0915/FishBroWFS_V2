#!/usr/bin/env python3
import json
import sys
sys.path.insert(0, 'src')
from src.control.api import app

with open('outputs/_dp_evidence/phaseD_portfolio_build_api/12_openapi_after.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)