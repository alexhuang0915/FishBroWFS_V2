import numpy as np, os, glob
# Find the most recent features_60m.npz under outputs/shared
paths = sorted(glob.glob("outputs/shared/**/features/features_60m.npz", recursive=True))
print("FOUND:", len(paths))
if paths:
    p = paths[-1]
    print("LATEST:", p)
    z = np.load(p)
    keys = sorted(list(z.files))
    print("KEYS COUNT:", len(keys))
    for k in keys:
        print(k)