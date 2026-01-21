# Discovery Summary
- `ControlStation.handle_router_url` still routed `internal://gate_dashboard` to the hidden gate tab, and the action router only opened that tab without invoking any panel on the visible Operation tab.
- `BarPrepareTab` retained the “CONFIRM” button and `state.confirmed` semantics even though the build-gating logic no longer needed confirmation, and the static smoke script merely logged the reference instead of failing.
- Running `make check` before this patch failed because the updated `AllocationTab` added a `QFrame`-backed portfolio summary panel without importing `QFrame`, so several portfolio tests raised `NameError` before our other checks could complete.
