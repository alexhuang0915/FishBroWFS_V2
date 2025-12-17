"""
Engine Constitution v1.1 (FROZEN)

Activation:
- Orders are created at Bar[T] close and become active at Bar[T+1].

STOP fills (Open==price is treated as GAP branch):
Buy Stop @ S:
- if Open >= S: fill = Open
- elif High >= S: fill = S
Sell Stop @ S:
- if Open <= S: fill = Open
- elif Low <= S: fill = S

LIMIT fills (Open==price is treated as GAP branch):
Buy Limit @ L:
- if Open <= L: fill = Open
- elif Low <= L: fill = L
Sell Limit @ L:
- if Open >= L: fill = Open
- elif High >= L: fill = L

Priority:
- STOP wins over LIMIT (risk-first pessimism).

Same-bar In/Out:
- If entry and exit are both triggerable in the same bar, execute Entry then Exit.

Same-kind tie rule:
- If multiple orders of the same role are triggerable in the same bar, execute EXIT-first.
- Within the same role+kind, use deterministic order: smaller order_id first.
"""

NEXT_BAR_ACTIVE = True
PRIORITY_STOP_OVER_LIMIT = True
SAME_BAR_ENTRY_THEN_EXIT = True
SAME_KIND_TIE_EXIT_FIRST = True

