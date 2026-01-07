#!/usr/bin/env python3
import os
import sys

root = "/home/fishbro/FishBroWFS_V2"
keep_file = sys.argv[1]
delete_file = sys.argv[2]
output_file = sys.argv[3]

with open(keep_file, 'r') as f:
    keeps = [line.rstrip('\n') for line in f if line.strip()]

with open(delete_file, 'r') as f:
    deletes = [line.rstrip('\n') for line in f]

def is_kept(abs_path):
    # convert to relative to root
    if abs_path.startswith(root + '/'):
        rel = abs_path[len(root)+1:]
    else:
        rel = abs_path
    for k in keeps:
        if rel == k:
            return True
        if rel.startswith(k + '/'):
            return True
        if k.startswith(rel + '/'):
            return True
    return False

filtered = []
for d in deletes:
    if not is_kept(d):
        filtered.append(d)

with open(output_file, 'w') as f:
    for d in filtered:
        f.write(d + '\n')

print(f"Original: {len(deletes)}")
print(f"Filtered: {len(filtered)}")