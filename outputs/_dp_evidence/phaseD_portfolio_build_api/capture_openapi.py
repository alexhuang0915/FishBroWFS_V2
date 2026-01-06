import json
import sys
sys.path.insert(0, '.')
from src.control.api import app

with open('outputs/_dp_evidence/phaseD_portfolio_build_api/03_openapi_before.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)