import sys
sys.path.insert(0, 'src')
from features.registry import get_default_registry

reg = get_default_registry()

tfs = sorted(set([s.timeframe_min for s in reg.specs_for_tf(60)] + [60]))
dump_tfs = sorted(set([1,5,15,30,60,120,240] + [60]))

print("verification_enabled:", getattr(reg, "verification_enabled", None))
for tf in dump_tfs:
    specs = reg.specs_for_tf(tf)
    print("\n=== TF", tf, "count:", len(specs), "===")
    for s in specs:
        d = getattr(s, "model_dump", None)
        if callable(d):
            print(d())
        else:
            print(repr(s))