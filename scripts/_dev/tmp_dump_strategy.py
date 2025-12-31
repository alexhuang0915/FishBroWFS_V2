import json
import sys
sys.path.insert(0, 'src')
from strategy.registry import get, list_strategies, load_builtin_strategies

load_builtin_strategies()
items = list_strategies()
print("STRATEGY COUNT:", len(items))
for spec in items:
    print("\n---", spec.strategy_id, "---")
    # print minimal schema
    if hasattr(spec, "model_dump"):
        print(json.dumps(spec.model_dump(), indent=2, sort_keys=True))
    else:
        print(repr(spec))