# Candidate Eligibility Gate — CandidateScreeningAgent enabler

**Status:** COMPLETE — deterministic, LLM-free enabler; Codex-APPROVED (after one
REJECT → fix round). Feature branch `phase-8b-candidate-eligibility` off
`main @ 0bcf01f09`; merging to `main` via `--no-ff`. Merge/feature hashes recorded
in the closeout report.

**Regression:** `scripts/test_phase_8b_candidate_eligibility.py` **18 tests / 87
assertions**, fully offline.

---

## Objective

Give the upcoming **CandidateScreeningAgent** a deterministic, four-state
eligibility gate that runs **before** its LLM stage — the numeric-firewall side of
the agent. This is an **enabler, not an agent**: it has no LLM, no `AgentOutput`,
no slate, and no Cockpit hook. It is merged on its own ahead of the agent body,
exactly like the prior deterministic enablers (`constituent_rs`,
`FragilityReading.offense_defense`).

It classifies a single candidate (one `OpportunityCard` + its matching
`CandidateSignal`) into one of four states **per horizon**, so the agent's LLM
only ever compares the survivors:

```
eligible    -> may become primary / secondary / watch
conditional -> may become watch only (never primary)
ineligible  -> rejected (known-bad)
unknown     -> rejected (cannot certify a required gate)
```

---

## Files

- **New:** `lib/candidate_eligibility.py` — the gate (stdlib-only at import).
- **New:** `scripts/test_phase_8b_candidate_eligibility.py` — the offline suite.
- **Zero** edits to any existing file. No `lib.reliability` / `lib.llm_orchestrator`
  / network / LLM import anywhere in the module.

---

## Public API

```python
@dataclass(frozen=True)
class EligibilityVerdict:
    ticker: str
    horizon: str          # "short" | "mid" | "long"
    strategy_type: str    # card.setup passthrough (for the agent's per-strategy logic)
    status: str           # "eligible" | "conditional" | "ineligible" | "unknown"
    blockers: tuple       # sorted reason codes from gates whose state == "fail"
    conditions: tuple     # sorted reason codes from gates whose state == "conditional"
    unknowns: tuple       # sorted reason codes from gates whose state == "unknown"
    data_quality: str     # "live" | "partial" | "degraded"
    as_of: str            # ISO date (YYYY-MM-DD)

def compute_eligibility(card, signal=None, *, horizon, as_of=None) -> EligibilityVerdict
def eligibility_by_horizon(card, signal=None, *, as_of=None) -> dict  # {"short":..,"mid":..,"long":..}
```

`card` / `signal` may be the real dataclasses OR plain dicts (tolerated via a
private `_field(obj, name, default)` reader). Reason codes come ONLY from a frozen
named vocabulary; reason tuples are always sorted for byte-stable output.

---

## The six gates — horizon × state matrix

Two tiers. **HARD** gates may produce `ineligible`; **SOFT** gates never do (only
`pass` / `conditional` / `unknown`).

### HARD gates

**thesis** (per-horizon via `status_by_horizon[horizon]`):
- a `risk_overlay_failed` blocker present → `fail` (`THESIS_RISK_OVERLAY_FAILED`),
  all horizons. **Dead-today/defensive:** the current `opportunity_ranker` never
  attaches this blocker code to a card — a risk-overlay failure surfaces as the
  `"Avoid Chasing"` status. Kept forward-compatible; its test feeds a manually
  constructed `Blocker`.
- `status_by_horizon[h] == "Avoid Chasing"` → `fail` (`THESIS_AVOID_CHASING`).
- `status_by_horizon[h] is None` → `unknown` (`THESIS_STATUS_UNKNOWN`).
- else → `pass`.

**eps** (horizon-asymmetric):
- `deteriorating` → SHORT `conditional`, MID+LONG `fail` (`EPS_DETERIORATING`).
- `unknown` or `signal is None` → `unknown` (`EPS_UNKNOWN`).
- else (`inflecting_up` / `improving` / `stable`) → `pass`.

**valuation** (horizon-asymmetric; requires a REAL percentile — see the firewall
section):
- percentile not certifiable → `unknown` (`VALUATION_UNKNOWN`).
- `>= _VALUATION_PROHIBITED_PCT (0.85)` → SHORT `conditional`, MID+LONG `fail`
  (`VALUATION_PROHIBITED`).
- `_VALUATION_ELEVATED_PCT (0.70) <= pct < 0.85` → SHORT `pass`, MID+LONG
  `conditional` (`VALUATION_ELEVATED`).
- `< 0.70` → `pass`.

**event** (earnings proximity — the canonical horizon gate):
- LONG → always `pass` (a single earnings print is noise over 6–18 months).
- `days_to_earnings is None`: SHORT `unknown` (`EVENT_EARNINGS_DATE_UNKNOWN`),
  MID `pass`.
- `<= _EARNINGS_IMMINENT_DAYS (2)`: SHORT `conditional`
  (`EVENT_EARNINGS_IMMINENT`), MID `conditional` (`EVENT_EARNINGS_PENDING_MID`).
- `2 < d2e <= _EARNINGS_WINDOW_DAYS (7)`: SHORT `conditional`
  (`EVENT_EARNINGS_WITHIN_WINDOW`), MID `pass`.
- `> 7` → `pass`.
- **DELIBERATE EXCLUSION:** FOMC/CPI (`days_to_fomc` / `days_to_cpi`) are NOT
  consulted — they are market-wide and identical across every candidate in a
  theme, so they cannot differentiate A vs B in the relative comparison. That is
  MarketStructure's lane.

### SOFT gates

**liquidity** (horizon-uniform proxy):
- `candidate_type ∈ {FUNNEL, BOTH}` → `pass` (`LIQUIDITY_FUNNEL_VERIFIED`); a
  "pass" means the funnel liquidity filter (market-cap + $ADV in `passes_layer1`)
  was satisfied at GENERATION, NOT a fresh re-read.
- `ALT_SIGNAL` → `conditional` (`LIQUIDITY_UNVERIFIED_ALT`).
- missing/None → `unknown` (`LIQUIDITY_UNKNOWN`). Never emits `fail`.

**distribution** (horizon-uniform proxy):
- `entry_quality_label == "avoid"` → `conditional` (`DISTRIBUTION_PROXY_AVOID`).
- `== "extended"` → `conditional` (`DISTRIBUTION_PROXY_EXTENDED`).
- missing/None → `unknown` (`DISTRIBUTION_UNKNOWN`). Never emits `fail`. There is
  no per-ticker distribution-day field (that signal is market-wide in
  MarketStructure); a "pass" means "no proxy flag", not confirmed absence.

---

## Aggregation precedence (core invariant)

```
1. any HARD gate == "fail"      -> "ineligible"
2. elif any HARD gate == "unknown" -> "unknown"     (a required gate could not certify)
3. elif any gate == "conditional"  -> "conditional" (hard OR soft)
4. elif any SOFT gate == "unknown" -> "conditional" (soft uncertainty is a watchable caveat)
5. else                            -> "eligible"
```

`blockers` / `conditions` / `unknowns` are populated from **ALL** gates (sorted,
de-duplicated), not just the dominant one, so the reason lists are complete.

`data_quality`: `degraded` if `rs_degraded` OR `enriched is False`; else `partial`
if any unknowns; else `live`.

**"Never default to pass":** fields that live only on `signal`
(`eps_revision_direction`, `valuation_percentile`, `entry_quality_label`) evaluate
to their UNKNOWN state when `signal is None` — never to a pass.

---

## Numeric-firewall provenance guard (the Codex REJECT → fix)

### The leak (Codex, verified against production)

`fetch_fundamental` sets `data_source["valuation"]="live"` whenever `info` is
truthy — **even if `forwardPE` is invalid, non-positive, or non-numeric**.
`_valuation_percentile` then defaults the percentile to **0.5** in exactly those
cases. The first-cut gate treated valuation as `UNKNOWN` only when `signal is
None`, provenance `== "fixture"`, or `forward_pe is None` — so a fabricated /
defaulted 0.5 with a present-but-unusable `forward_pe` (e.g. `0`, `-5`, a string)
rode through as a REAL valuation and yielded a pass. A defaulted 0.5 must never be
read as a real valuation — this is a numeric-firewall leak.

### The fix (one code change)

`_valuation_missing(signal)` now returns `True` (→ `VALUATION_UNKNOWN`) when a
fundamental is reachable AND either:
- `data_source.get("valuation") ∈ {"fixture", None}` (no certified-live
  valuation), OR
- the reachable `forward_pe` is **unusable** per `_forward_pe_is_usable`.

```python
def _forward_pe_is_usable(value) -> bool:
    # None, non-numeric, bool (a True/False forward_pe is a data error, NOT 1/0),
    # or <= 0 are all UNUSABLE. Mirrors the exact conditions under which
    # signal_engine._valuation_percentile defaults the percentile to 0.5.
    if value is None or isinstance(value, bool):
        return False
    if not isinstance(value, numbers.Real):
        return False
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False
```

When **no** fundamental is reachable (a directly-constructed test signal, or an
ALT_SIGNAL with `track_a=None`), the percentile is treated as a REAL read — the
bare-percentile path is preserved (test #5: percentile 0.50 → pass).

**Auditable provenance path:** `signal.track_a.layer3_fundamental.data_source
["valuation"]` for provenance and `signal.track_a.layer3_fundamental.forward_pe`
for usability, reached generically via `_locate_fundamental` + `_field` (also
honoring a flat `signal.fundamental` fallback).

---

## Thresholds (named, tunable, documented)

- `_VALUATION_ELEVATED_PCT = 0.70` — grounds to
  `lib.opportunity_ranker._VALUATION_HIGH_PCT` (0.70). *(Preflight note: this
  constant lives in `opportunity_ranker.py`, not `signal_engine.py`; value
  matches.)*
- `_VALUATION_PROHIBITED_PCT = 0.85` — **NEW band ceiling; calibration debt** (an
  unvalidated first guess with no upstream anchor; revisit once the agent body
  produces real slate outcomes).
- `_EARNINGS_IMMINENT_DAYS = 2`, `_EARNINGS_WINDOW_DAYS = 7` — grounds to the
  existing `earnings_within_window` (<= 7d) blocker.

---

## Tests (discriminability, all offline, REAL instances)

Builds real `OpportunityCard` / `CandidateSignal` / `Blocker` /
`FundamentalResult` / `TrackAResult` (no mocks — a field rename breaks the suite).
Each case is annotated with the mutation it catches:

1. **Event horizon asymmetry** — `d2e=2`: SHORT `EVENT_EARNINGS_IMMINENT`, MID
   `EVENT_EARNINGS_PENDING_MID`, LONG carries no earnings code.
2. **Hard-fail dominates score** — strong grades + `deteriorating` EPS at MID →
   `ineligible`.
3. **Hard-unknown vs soft-unknown asymmetry** — `signal=None` → `unknown`;
   `candidate_type=None` with all hard gates passing → `conditional` (NOT unknown).
4. **Soft gates never fail** — `avoid`/`extended`/`ALT_SIGNAL` → conditions, never
   blockers.
5. **Valuation two-band × horizon** — 0.50 pass all; 0.75 SHORT pass / MID+LONG
   `VALUATION_ELEVATED`; 0.90 SHORT conditional / MID+LONG `VALUATION_PROHIBITED`
   blocker.
   - **5b provenance UNKNOWN** — fixture-provenance 0.5 → `VALUATION_UNKNOWN`; bare
     real 0.5 → pass.
   - **5c firewall leak guard (FIX 1)** — live-provenance 0.5 with `forward_pe ∈
     {0, −5, non-numeric string, bool}` → `VALUATION_UNKNOWN`; a usable
     `forward_pe=25.0` live read stays eligible (guard does not over-fire).
6. **Avoid Chasing → ineligible** for that horizon.
   - **6b** — the defensive `risk_overlay_failed` blocker branch (manually
     constructed Blocker; noted as not emitted by the ranker today).
7. **Never default to pass** — sparse card + `signal=None` → `unknown`, never
   eligible.
8. **Clean eligible, then flip exactly one hard gate** → no longer eligible (proves
   each hard gate is required).
9. **data_quality** — `rs_degraded` → degraded; all-clean → live.
10. **Determinism** — same inputs → identical frozen verdict; reason tuples sorted.
11. **Dict inputs tolerated.**
- **M1 (precedence step 1 over 3)** — a hard fail co-present with conditionals →
  `ineligible`, conditionals still recorded.
- **E2** — `d2e=5` SHORT → `EVENT_EARNINGS_WITHIN_WINDOW`, not `IMMINENT` (band
  separation).
- **E4** — MID + `d2e=None` → no event code, eligible (mid unknown-earnings passes).
- **Multi-condition completeness** — `ALT_SIGNAL` + `avoid` on SHORT → BOTH
  `LIQUIDITY_UNVERIFIED_ALT` and `DISTRIBUTION_PROXY_AVOID` in conditions.

---

## Review arc

**Codex REJECT** (valuation-provenance firewall leak — a defaulted 0.5 with an
unusable-but-present `forward_pe` read as a real pass) → **fix round** (ONE code
fix: `_valuation_missing` rewrite + `_forward_pe_is_usable` / `_has_field`; FOUR
added tests: the leak guard + M1/E2/E4/multi-condition; ONE clarifying comment on
the dead-today `risk_overlay_failed` branch) → **APPROVE**. Assertions 65 → 87.

---

## Not in scope (belongs to the agent body — the next phase)

Theme grouping / active-theme selection / per-theme constituent universe; the
comparison table + deterministic frontrunner + code-decided `no_clear_winner`; any
LLM call, `AgentOutput`, slate, or Cockpit hook; Stage-2 ticker-level MoneyFlow.
This phase delivers ONLY the deterministic four-state gate + its tests.
