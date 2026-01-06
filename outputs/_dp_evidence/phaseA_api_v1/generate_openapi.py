import json
import sys
sys.path.insert(0, '.')
from src.control.api import app

with open('outputs/_dp_evidence/phaseA_api_v1/02_openapi_current_before.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)