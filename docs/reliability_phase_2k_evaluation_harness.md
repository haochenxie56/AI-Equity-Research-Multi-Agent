# Phase 2K — Reliability Evaluation Harness

**Status**: Implemented, awaiting Codex review.
**Phase**: 2K (inserted after Phase 2J Critic Agent v0.1, before Phase 2 Closeout).

---

## Purpose

Phase 2K builds a **deterministic evaluation harness** with fixed synthetic test cases
that prove the reliability layer can detect common agentic failure modes before
Phase 2 closes out.

The harness answers: *"Given a synthetic input that represents a known failure mode, does
the reliability stack (validators + validation aggregator + staleness checker + critic) catch
it reliably and deterministically?"*

This is **not** a live app integration, not a live LLM evaluation, and not Phase 3
orchestration. It is a standalone off-line test fixture that runs without any network access.

---

## Why Fixed Evals Before Phase 2 Closeout

Before integrating the reliability layer into Phase 3 orchestration:

1. **Regression safety** — any change to validators, critic, or staleness checker should
   not silently break detection of known failure modes.
2. **Coverage assurance** — the 12 required failure modes span all major reliability concerns
   (evidence, staleness, overconfidence, horizon, risk, options safety, conflicts).
3. **Determinism guarantee** — all cases use synthetic data, so results are reproducible
   without external API keys or live market data.
4. **Documentation of detection scope** — expected output files explicitly record what each
   component is supposed to catch.

---

## Case Format

Each case file in `evals/cases/` is a JSON object:

```json
{
  "case_id": "unsupported_numeric_claim",
  "description": "Agent makes a numeric valuation claim without evidence.",
  "failure_mode": "unsupported_numeric_claim",
  "inputs": {
    "agent_result": { ... },
    "tool_results": [ ... ],
    "validation_aggregate": { ... },
    "staleness_report": { ... }
  },
  "metadata": {
    "severity_expected": "warning",
    "notes": "..."
  }
}
```

All inputs are synthetic. No live prices, no API calls.

---

## Expected Output Format

Each file in `evals/expected/` is a JSON object:

```json
{
  "case_id": "unsupported_numeric_claim",
  "expected_status": "fail",
  "expected_issue_types": ["numeric_claim_issue"],
  "allowed_issue_types": ["unsupported_claim", "weak_evidence"],
  "expected_min_critical": 0,
  "expected_min_warnings": 1,
  "expected_detected": true,
  "metadata": { "notes": "..." }
}
```

Comparison is **tolerant**: it checks issue type presence and severity minimums,
not exact message strings.

---

## Supported Failure Modes

| Failure Mode | What it exercises | Expected detection |
|---|---|---|
| `unsupported_numeric_claim` | Finding has numeric content, no evidence refs | `numeric_claim_issue` |
| `hallucinated_evidence_id` | Finding cites non-existent evidence_id | `validation_failure` |
| `stale_news_used_as_fresh` | Expired staleness finding in news domain | `stale_evidence` |
| `missing_downside_risk` | Empty risks list | `missing_risk` |
| `missing_assumption` | Empty assumptions list | `missing_assumption` |
| `overconfidence_with_validation_warnings` | High confidence + validation warnings | `overconfidence` |
| `overconfidence_with_stale_data` | High confidence + stale staleness report | `overconfidence` |
| `horizon_mismatch` | Short-term rec with long-term-only evidence | `conflicting_evidence` |
| `unsupported_trade_plan` | Dollar price levels without tool evidence | `numeric_claim_issue` |
| `option_strategy_without_risk_budget` | Option output with no risk section | `missing_risk` |
| `conflicting_evidence` | Bullish conclusion with conflicting validation warning | `conflicting_evidence` |
| `clean_minimal_case` | Valid case with real evidence refs | No critical/warning |

---

## Fail-Closed Contract

The harness is a **regression gate**, not a best-effort smoke test.

### Required invariants

- **Expected outputs are mandatory.** Every case in `evals/cases/` must have exactly one
  matching file in `evals/expected/`. A case with no expected output produces
  `status="error"` and `passed_expectation=False`; the CLI exits nonzero.

- **Orphan expected outputs are errors.** An expected output file with no matching case
  produces `status="error"` and `passed_expectation=False`; the CLI exits nonzero.

- **Malformed fixtures fail the suite.** Both `load_eval_cases()` and
  `load_expected_outputs()` raise `ValueError` on missing directories, empty directories,
  or malformed JSON files. The runner converts these to an error summary; the CLI exits nonzero.

- **Missing expected directory fails.** If `evals/expected/` does not exist or is empty,
  the CLI exits nonzero before running any cases.

- **The clean case is a false-positive control.** `clean_minimal_case` must produce no
  critical or warning issues. If it does, that is a `false_positive` detection failure.

### Failure classification (in `run_evals.py` output)

| Category | Meaning |
|---|---|
| `Missing expected outputs` | case file has no matching expected file |
| `Orphan expected files` | expected file has no matching case |
| `Fixture load errors` | directory missing / empty / malformed JSON |
| `Failed cases` | detection comparison failed |
| `Error cases` | runtime error during case execution |

---

## Scoring Logic

```
detection_rate = detected_count / (detected_count + missed_count)
```

- A case has `detection_status = "detected"` if at least one expected or allowed issue
  type was found in the actual output, and severity minimums are met.
- A case has `detection_status = "missed"` if the failure was not caught.
- A clean case has `detection_status = "false_positive"` if it produced unexpected issues.
- A clean case has `detection_status = "not_applicable"` if clean as expected.

---

## ReliabilityScoreSummary

```python
class ReliabilityScoreSummary(BaseModel):
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    skipped_cases: int
    detection_rate: float           # 0.0–1.0
    false_positive_count: int
    missed_count: int
    results: list[ReliabilityEvalCaseResult]
    metadata: dict[str, Any]
```

Target: `detection_rate == 1.0`, `false_positive_count == 0`.

---

## How Evals Use Reliability Components

For each case, `run_single_eval_case` calls:

1. **`validate_agent_result(agent_result, EvidenceStore)`** — validates evidence binding,
   catches hallucinated evidence IDs, unsupported numeric claims.
2. **`run_mock_critic(...)`** — runs:
   - `critique_agent_result_structure` — structural issues (missing risk, missing assumption,
     overconfidence, numeric claims).
   - `critique_validation_aggregate` — converts ValidationAggregate items to CriticIssues.
   - `critique_staleness_report` — converts StalenessReport findings to CriticIssues.
   - `detect_overconfidence` — cross-checks high confidence against validation/staleness.

All inputs are deserialized from case JSON into Pydantic models before running.

---

## How to Run Evals

```bash
# Quick run
python3 evals/run_evals.py

# With output file
python3 evals/run_evals.py --output evals/latest_summary.json

# With custom dirs
python3 evals/run_evals.py --cases-dir evals/cases --expected-dir evals/expected

# Full test (includes regression)
python3 scripts/test_reliability_evaluation_harness.py
```

---

## How to Add New Cases

1. Create `evals/cases/<case_id>.json` with the `ReliabilityEvalCase` schema.
2. Create `evals/expected/<case_id>.json` with the `ReliabilityExpectedOutput` schema.
3. Run `python3 evals/run_evals.py` to verify the new case is loaded and passes.
4. Update `REQUIRED_FAILURE_MODES` in `lib/reliability/evaluation.py` if adding a new mode.

---

## What This Phase Does NOT Do

- **No live app integration** — `app.py` and `pages/*` are not touched.
- **No live LLM calls** — no Claude API, no `anthropic` SDK usage.
- **No live data fetching** — no yfinance, no polygon.io, no Finnhub.
- **No investment advice** — all data is synthetic; nothing here should be acted on.
- **No broker/order behavior** — no trade execution logic.
- **No Streamlit UI changes** — existing UI is untouched.
- **No Phase 3 orchestration** — no validated agent orchestration is wired in this phase.

---

## Future Relationship

| Future Phase | How this harness connects |
|---|---|
| Phase 3A: Validated Agent Orchestration Skeleton | Evals provide a regression gate before 3A agents are wired |
| Debate Layer | New debate failure modes can be added as eval cases |
| Memory / Human Feedback | Memory-related failure modes can be added as new cases |
| Cockpit QA | Harness detection_rate is a gate condition for Cockpit readiness |

---

## Key Files

| File | Purpose |
|------|---------|
| `lib/reliability/evaluation.py` | Schemas and helper functions |
| `evals/cases/*.json` | 12 synthetic failure mode cases |
| `evals/expected/*.json` | 12 expected detection outputs |
| `evals/run_evals.py` | CLI runner |
| `scripts/test_reliability_evaluation_harness.py` | Direct test suite (20 assertions + regression) |
