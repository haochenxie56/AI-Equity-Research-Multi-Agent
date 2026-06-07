# Phase 3R Closeout — Roadmap v4 Phase 3 Backfill

**Date**: 2026-05-24
**Status**: Accepted

---

## 1. Phase 3R Summary

Phase 3R was inserted **after** Phase 3 Closeout and after early Phase 4A infrastructure
was accepted, in order to realign the project with Roadmap v4 Phase 3 requirements.

### Background

- **Phase 0–3** were fully implemented and accepted before Phase 3R was conceived.
- **Phase 4A** (Reliability Integration Boundary Contract) was accepted as **early
  integration infrastructure** — not treated as the start of Roadmap Phase 4 Memory.
  It is standalone, no-op by default, and frozen in its current state.
- **Phase 3R** was inserted to backfill the Roadmap v4 Phase 3 validated agent / module
  skeletons that were not delivered before the Phase 3 Closeout. These cover event
  intelligence agents (catalyst, news, earnings, estimate revision), trade plan drafting,
  allocation, and option expression.
- **Roadmap Phase 4 Memory + Human Feedback** remains not started. It is paused until
  Phase 3R Closeout is accepted.

All Phase 3R deliverables are offline / mock-only. They do not modify live app behavior,
call the Claude API, call external APIs, or introduce broker / order / execution logic.

---

## 2. Accepted Phase 3R Subphases

| Subphase | Name | Status |
|----------|------|--------|
| Phase 3R-0 | Roadmap Alignment Reconciliation | **Accepted** |
| Phase 3R-A | Event Intelligence Agents Skeleton | **Accepted** |
| Phase 3R-B | Trade Plan Drafting Agent Skeleton | **Accepted** |
| Phase 3R-C | Allocation Agent v0.1 Non-live | **Accepted** |
| Phase 3R-D | Option Expression Agent v0.1 Non-live | **Accepted** |
| Phase 3R-E | Roadmap Alignment Closeout | This document |

---

## 3. Roadmap v4 Phase 3 Coverage Map

### Phase 3A–3G (accepted before Phase 3R)

| Roadmap v4 Phase 3 Capability | Delivered In |
|-------------------------------|-------------|
| Validated Agent Orchestration Skeleton | Phase 3A |
| Horizon-aware Synthesis Skeleton | Phase 3B |
| Macro Agent v0.1 Skeleton | Phase 3C |
| Bull / Bear / Risk Debate by Horizon | Phase 3D |
| DecisionPacket / Decision Synthesis Skeleton | Phase 3E |
| Human Review / Feedback Schema Skeleton | Phase 3F |
| Offline Review Loop / Reliability Run Report | Phase 3G |

### Phase 3R backfill (new in Phase 3R)

| Roadmap v4 Phase 3 Capability | Delivered In |
|-------------------------------|-------------|
| Catalyst Agent | Phase 3R-A |
| News Impact Agent | Phase 3R-A |
| Earnings Playbook Agent | Phase 3R-A |
| Estimate Revision Agent | Phase 3R-A |
| Trade Plan Drafting Agent | Phase 3R-B |
| Allocation Agent v0.1 Non-live | Phase 3R-C |
| Option Expression Agent v0.1 Non-live | Phase 3R-D |

### Reliability composition backbone (Phase 3)

The following reliability-layer components were established in Phase 3A–3G and form
the backbone on which Phase 3R agents are composed:

- Orchestration Skeleton (Phase 3A)
- DecisionPacket (Phase 3E)
- Human Review / Feedback Schema (Phase 3F)
- Offline Review Loop / Reliability Run Report (Phase 3G)

---

## 4. Key Artifacts

### Phase 3R-0 — Roadmap Alignment Reconciliation

| File | Type |
|------|------|
| `docs/ai_dev_state/ROADMAP_V4_ALIGNMENT.md` | Design / reconciliation doc |

### Phase 3R-A — Event Intelligence Agents Skeleton

| File | Type |
|------|------|
| `lib/reliability/event_intelligence.py` | Runtime implementation |
| `scripts/test_reliability_event_intelligence.py` | Test suite (152/152) |
| `docs/reliability_phase_3r_event_intelligence.md` | Design doc |

### Phase 3R-B — Trade Plan Drafting Agent Skeleton

| File | Type |
|------|------|
| `lib/reliability/trade_plan.py` | Runtime implementation |
| `scripts/test_reliability_trade_plan.py` | Test suite (689/689) |
| `docs/reliability_phase_3r_trade_plan.md` | Design doc |

### Phase 3R-C — Allocation Agent v0.1 Non-live

| File | Type |
|------|------|
| `lib/reliability/allocation_report.py` | Runtime implementation |
| `scripts/test_reliability_allocation_report.py` | Test suite (392/392) |
| `docs/reliability_phase_3r_allocation.md` | Design doc |

### Phase 3R-D — Option Expression Agent v0.1 Non-live

| File | Type |
|------|------|
| `lib/reliability/option_expression.py` | Runtime implementation |
| `scripts/test_reliability_option_expression.py` | Test suite (277/277) |
| `docs/reliability_phase_3r_option_expression.md` | Design doc |

### Cross-phase

| File | Type |
|------|------|
| `lib/reliability/__init__.py` | Package entry point — all Phase 0–3R exports |

---

## 5. Architectural Boundaries

All Phase 3R components honor the following constraints, identical to Phase 3:

- **Offline / mock-only.** No live runtime component modified.
- **Does not modify Streamlit app behavior.** `app.py` and `pages/*` are untouched.
- **Does not modify live LLM orchestration behavior.** `lib/llm_orchestrator.py` is
  untouched.
- **Does not call the Claude API.** No `anthropic` SDK usage anywhere in Phase 3R.
- **Does not call external APIs.** No network calls, no HTTP, no data fetching.
- **Does not import live brokerage, portfolio, or option-chain data.**
- **Does not introduce broker / order / trade execution logic.**
- **Does not authorize execution.** `approved_for_execution` is always `False` and is
  schema-enforced in all models where it appears (TradePlanDraft, AllocationReport,
  OptionExpressionReport, OptionExpressionAssessment, OptionExpressionSummary).
- **Phase 3R outputs are research / review / audit artifacts only.**
- **Phase 4A** (Integration Boundary) remains accepted as early infrastructure and is
  frozen in its current standalone state. It is not wired into the live app.
- **Roadmap Phase 4 Memory** remains not started.

---

## 6. Safety-Specific Notes by Module

### Event Intelligence (Phase 3R-A)

- Consumes caller-provided evidence / source IDs; does not fetch news, earnings, or
  catalyst data from any external API.
- CatalystAssessment, NewsImpactAssessment, EarningsPlaybookAssessment, and
  EstimateRevisionAssessment all reference caller-supplied source IDs only.
- EventIntelligenceBundle, EventIntelligenceSummary, and EventIntelligenceReport chain
  and aggregate these source IDs without contacting live data.

### Trade Plan (Phase 3R-B)

- Produces a **research trade plan only** — not an order ticket.
- TradePlanDraft contains no order fields, no account fields, and no execution fields.
- `approved_for_execution` is permanently `False` (schema-enforced via `model_validator`).
- Prior artifact source IDs require caller-provided source IDs.

### Allocation (Phase 3R-C)

- Uses deterministic mock allocation / risk-budget calculators only.
- No live portfolio or brokerage data is imported or used.
- `current_allocation_pct` is an optional field; the validator handles its absence.
- `approved_for_execution` is permanently `False` (schema-enforced via `model_validator`).

### Option Expression (Phase 3R-D)

- Stock, option, and no_trade are all first-class decision outputs.
- `no_trade` is a first-class choice, not an error path.
- The Option Agent does not decide thesis or total portfolio allocation.
- No option-chain API calls; no option order ticket fields.
- `approved_for_execution` is permanently `False` in OptionExpressionReport,
  OptionExpressionAssessment, and OptionExpressionSummary (schema-enforced via
  `model_validator`).

---

## 7. Test Matrix (confirmed passing — 2026-05-24)

### Phase 3R primary tests

| Script | Tests | Result |
|--------|-------|--------|
| `python3 scripts/test_reliability_event_intelligence.py` | 152 | PASS |
| `python3 scripts/test_reliability_trade_plan.py` | 689 | PASS |
| `python3 scripts/test_reliability_allocation_report.py` | 392 | PASS |
| `python3 scripts/test_reliability_allocation.py` | 288 | PASS |
| `python3 scripts/test_reliability_option_expression.py` | 277 | PASS |
| **Phase 3R subtotal** | **1798** | **PASS** |

### Phase 3 regression (confirmed passing — 2026-05-24)

| Script | Tests | Result |
|--------|-------|--------|
| `python3 scripts/test_reliability_review_loop.py` | 151 | PASS |
| `python3 scripts/test_reliability_human_review.py` | 113 | PASS |
| `python3 scripts/test_reliability_decision_packet.py` | 58 | PASS |

---

## 8. Known Non-Blocking Notes

- **Event Intelligence source IDs**: Uses lightweight caller-provided source / evidence
  IDs. Richer field-path `EvidenceRef` may be considered later if the Memory layer
  (Phase 4) requires it. Accepted as-is.
- **Trade Plan source IDs**: Prior artifact source IDs rely on caller-provided IDs.
  This is consistent with the rest of the reliability layer and is accepted as-is.
- **Allocation `current_allocation_pct`**: The field is optional in
  `AllocationPositionSnapshot`; the validator handles `None` correctly. Accepted as-is.
- **Option Expression stock / option / no_trade path**: All three are first-class outputs.
  Documentation and status wording are aligned. Accepted as-is.

None of these are blockers.

---

## 9. Phase 4 Readiness

After Phase 3R Closeout is accepted, the project is ready to resume:

**Phase 4 — Memory + Human Feedback + Review**

### Recommended first subphase

**Phase 4M-A** (or equivalent label) — Research Run Memory Schema.

### Scope for Phase 4 Memory

The following memory schemas are the expected Phase 4 focus areas:

| Schema | Description |
|--------|-------------|
| Research Run Memory | Persist ReliabilityRunReport summaries across runs |
| Thesis Memory by Horizon | Record thesis evolution per horizon per ticker |
| Catalyst / News / Earnings Memory | Persist event intelligence findings |
| Allocation Decision Memory | Persist allocation decisions and constraint history |
| Option Trade Plan Memory | Persist option expression decisions |
| Human Feedback Layer | Record human corrections and feedback for agent improvement |
| Agent Evaluation | Offline evaluation of agent output quality over time |

### Clarifications

- **Do not continue the old "integration boundary" branch as the main Phase 4 work.**
  Phase 4A Integration Boundary is frozen as early infrastructure; it is not the
  main Phase 4 Memory implementation.
- **Existing Phase 4A** is accepted and frozen. No rollback. No further Phase 4A work.
- **Phase 4 Memory work** begins fresh after Phase 3R Closeout acceptance, scoped to
  the Memory schemas above.

---

## Global Guardrails (repeated from Phase 3 Closeout)

Do **not** modify:

- `app.py`, `pages/*`, `lib/llm_orchestrator.py`
- `.claude/agents/*`, existing live prompt files
- `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`
- `lib/data_fetcher.py`, `lib/workflow_state.py`
- Existing Streamlit UI or live workflow behavior

Do **not** introduce (unless explicitly scoped):

- Live app integration, Streamlit UI changes, live LLM calls
- Live API / data fetching, broker integration, order placement
- Any pathway that sets `approved_for_execution = True`
- Phase 4 Memory implementation before Phase 3R-E is accepted
