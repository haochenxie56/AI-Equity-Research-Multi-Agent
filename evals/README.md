# Reliability Evaluation Harness

Phase 2K — deterministic evaluation suite for the reliability layer.

## Folder Layout

```
evals/
├── cases/          # Synthetic eval case JSON files (one per failure mode)
├── expected/       # Expected detection output JSON files (one per case)
├── run_evals.py    # CLI runner
└── README.md       # This file
```

## How to Run

```bash
# Run all cases, print summary
python3 evals/run_evals.py

# Custom directories
python3 evals/run_evals.py --cases-dir evals/cases --expected-dir evals/expected

# Write summary to JSON
python3 evals/run_evals.py --output evals/latest_summary.json
```

Exits `0` if all cases pass expectations, nonzero otherwise.

## Fail-Closed Contract

This harness is a **regression gate**, not a best-effort smoke test:

- **Every case must have a matching expected output.** Missing expected → error, nonzero exit.
- **Orphan expected outputs fail the suite.** An expected file with no matching case → error.
- **Malformed fixture files fail the suite.** Invalid JSON → error, nonzero exit.
- **Missing or empty `evals/expected/` fails.** The runner exits immediately with nonzero.
- **`clean_minimal_case` is a false-positive control.** It must produce no critical/warning issues.

## Cases and Expected Outputs

Each case in `cases/` is a JSON file with:

| Field          | Description |
|----------------|-------------|
| `case_id`      | Unique identifier (matches expected output) |
| `description`  | Human-readable description |
| `failure_mode` | Which `ReliabilityFailureMode` this exercises |
| `inputs`       | `agent_result`, `tool_results`, `validation_aggregate`, `staleness_report` |
| `metadata`     | `severity_expected`, `notes` |

Each expected output in `expected/` is a JSON file with:

| Field                  | Description |
|------------------------|-------------|
| `case_id`              | Matches case |
| `expected_issue_types` | Issue types that must be detected |
| `allowed_issue_types`  | Additional acceptable issue types |
| `expected_min_critical`| Minimum critical count |
| `expected_min_warnings`| Minimum warning count |
| `expected_detected`    | `false` for clean cases |

## Failure Modes Covered

| case_id | failure_mode |
|---------|-------------|
| `unsupported_numeric_claim` | Numeric claim without evidence |
| `hallucinated_evidence_id` | Citation of non-existent evidence |
| `stale_news_used_as_fresh` | Expired news treated as current |
| `missing_downside_risk` | Bullish thesis with no risk section |
| `missing_assumption` | Conclusion with no assumptions |
| `overconfident_with_validation_warnings` | High confidence vs. validation warnings |
| `overconfident_with_stale_data` | High confidence vs. stale data |
| `horizon_mismatch` | Short-term recommendation on long-term evidence |
| `unsupported_trade_plan` | Price levels without tool evidence |
| `option_strategy_without_risk_budget` | Option output without max loss |
| `conflicting_evidence` | Bullish conclusion vs. conflicting validation warning |
| `clean_minimal_case` | Valid case — should produce no critical/warning issues |

## Interpreting ReliabilityScoreSummary

| Field | Meaning |
|-------|---------|
| `total_cases` | Cases loaded |
| `passed_cases` | Cases where `passed_expectation=True` |
| `failed_cases` | Cases where `status=fail` |
| `detection_rate` | `detected / (detected + missed)` |
| `missed_count` | Failure modes not caught |
| `false_positive_count` | Clean case incorrectly flagged |

Detection rate 1.0 means all failure modes were caught with zero misses.

## Adding New Cases

1. Create `evals/cases/<name>.json` matching `ReliabilityEvalCase` schema.
2. Create `evals/expected/<name>.json` matching `ReliabilityExpectedOutput` schema.
3. Run `python3 evals/run_evals.py` to verify.
