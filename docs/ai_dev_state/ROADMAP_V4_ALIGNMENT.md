# Roadmap v4 Alignment Reconciliation

**Date**: 2026-05-24
**Status**: Reconciliation complete. Phase 3R backfill sequence established.

---

## 1. Summary

| Phase Block | Status |
|-------------|--------|
| Phase 0–3 | Accepted |
| Phase 3 Closeout | Accepted |
| Phase 4A Integration Boundary Contract | Accepted as early infrastructure (see Section 3) |
| Roadmap v4 Phase 4 Memory + Human Feedback mainline | **Not started** |
| Phase 3R Roadmap Backfill | **Inserted before Phase 4** |

**Decision**: The project will insert Phase 3R Roadmap Backfill before continuing
Roadmap Phase 4 Memory + Human Feedback + Review work.

Phase 3R exists because Roadmap v4 Phase 3 specified additional validated agent
skeletons that were not delivered before the Phase 3 Closeout. These are offline/
mock-only stubs with no live integration, consistent with the existing Phase 3
architectural boundary.

---

## 2. Why No Rollback of Phase 4A

Phase 4A (Reliability Integration Boundary Contract,
`lib/reliability/integration_boundary.py`) is retained and accepted. Rolling it back
would add unnecessary churn for the following reasons:

1. **Standalone and isolated.** Phase 4A has no imports from `app.py`, `pages/*`,
   `lib/llm_orchestrator.py`, `lib/workflow_state.py`, or any Streamlit module. It
   depends only on `pydantic` and the reliability package itself.
2. **No-op / pass-through by default.** In `DISABLED` mode (the default) the adapter
   returns a pass-through result with no side effects. Live app behavior is unchanged.
3. **Deterministic and side-effect-free.** All three public functions produce the same
   output for the same input, make no file writes, no network calls, and do not mutate
   their inputs.
4. **Useful future infrastructure.** The `DISABLED` / `SHADOW` / `ENFORCED` mode
   framework and the source-workflow enum are the correct foundation for future Phase 4
   live integration when that phase is explicitly started.
5. **64/64 tests pass.** Acceptance criteria were met; the implementation is stable.

---

## 3. Phase 4A Reclassification

| Attribute | Value |
|-----------|-------|
| Label | Accepted early integration infrastructure |
| Treats as | **Not** the start of Roadmap Phase 4 Memory |
| Phase 4 Memory mainline | Frozen until Phase 3R closeout is accepted |
| Live app wiring | Explicitly prohibited until a Phase 4 task explicitly permits it |

Phase 4A is frozen in its current standalone state. No further Phase 4A work will be
done during Phase 3R.

---

## 4. Roadmap v4 Phase 3 Gap Analysis

### Covered by Phase 3A–3G

| Capability | Delivered In |
|------------|-------------|
| Validated Agent Orchestration Skeleton | Phase 3A |
| Horizon-aware Synthesis Skeleton | Phase 3B |
| Macro Agent v0.1 Skeleton | Phase 3C |
| Bull / Bear / Risk Debate by Horizon | Phase 3D |
| DecisionPacket / Decision Synthesis Skeleton | Phase 3E |
| Human Review / Feedback Schema Skeleton | Phase 3F |
| Offline Review Loop / Reliability Run Report | Phase 3G |

### Missing from Roadmap v4 Phase 3 (to be delivered in Phase 3R)

| Agent / Component | Phase 3R Sub-phase |
|-------------------|--------------------|
| Catalyst Agent skeleton | Phase 3R-A |
| News Impact Agent skeleton | Phase 3R-A |
| Earnings Playbook Agent skeleton | Phase 3R-A |
| Estimate Revision Agent skeleton | Phase 3R-A |
| Trade Plan Drafting Agent skeleton | Phase 3R-B |
| Allocation Agent v0.1 non-live | Phase 3R-C |
| Option Expression Agent v0.1 non-live | Phase 3R-D |

All Phase 3R deliverables are **offline / mock-only**. They must not modify live app
behavior, call the Claude API, call external APIs, or introduce broker / order /
execution logic.

---

## 5. Revised Roadmap Sequence

```
[Accepted]
  Phase 0–3       Reliability foundation through review loop
  Phase 3 Closeout
  Phase 4A        Reliability Integration Boundary Contract (early infrastructure)

[Inserted — Phase 3R Backfill]
  Phase 3R-0      Roadmap Alignment Reconciliation         ← THIS DOCUMENT (complete)
  Phase 3R-A      Event Intelligence Agents Skeleton
                  (Catalyst / News Impact / Earnings Playbook / Estimate Revision)
  Phase 3R-B      Trade Plan Drafting Agent Skeleton
  Phase 3R-C      Allocation Agent v0.1 Non-live
  Phase 3R-D      Option Expression Agent v0.1 Non-live
  Phase 3R-E      Roadmap Alignment Closeout

[Paused — resume after Phase 3R-E]
  Phase 4         Memory + Human Feedback + Review (Roadmap v4 Phase 4 mainline)
  Phase 4B+       (not yet scoped)
```

---

## 6. Guardrails for Phase 3R

All Phase 3R sub-phases must honor the following constraints (identical to Phase 3):

- **Do not modify live runtime / app files:**
  - `app.py`
  - `pages/*`
  - `lib/llm_orchestrator.py`
  - `lib/valuation.py`
  - `lib/technical.py`
  - `lib/rotation.py`
  - `lib/data_fetcher.py`
  - `lib/workflow_state.py`
  - `.claude/agents/*`
- **Do not wire Phase 4A into the live app.** `integration_boundary.py` must remain
  standalone with no callers in the live workflow.
- **Do not start Phase 4 Memory work** until Phase 3R-E is accepted.
- **Do not add broker / order / execution logic.**
- **Do not authorize execution.** `approved_for_execution` must remain `False`
  in all output schemas; no pathway to set it `True` may be introduced.
- **Keep all Phase 3R work offline / mock-only / non-live.**
- **Do not call the Claude API or external data APIs.**
- **Do not add Streamlit UI components.**
