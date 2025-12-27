
"""
Engine integer constants (hot-path friendly).

These constants are used in array/SoA pathways to avoid Enum.value lookups in tight loops.
"""

ROLE_EXIT = 0
ROLE_ENTRY = 1

KIND_STOP = 0
KIND_LIMIT = 1

SIDE_SELL = -1
SIDE_BUY = 1




