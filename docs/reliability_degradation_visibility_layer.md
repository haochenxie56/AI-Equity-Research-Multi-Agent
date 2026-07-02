# Degradation-Visibility Layer — foundation-agent degradation review

**Status:** IMPLEMENTED — awaiting review APPROVE before any merge. Standalone,
read-only, additive; the increment immediately after the six foundation agents
(MacroRegimeAgent, MoneyFlowAgent, MarketStructureAgent, SectorRotationAgent,
ThemeIntelligenceAgent, CandidateScreeningAgent), per ROADMAP §5.10 and Master
Memo v4 §8 / §10.3.

**Regression:** `scripts/test_degradation_view.py` — **19 tests** (the 8 required
numbered cases + 11 supporting, including the review-round FIX 1/2/4/5 tests),
fully offline. The load-ordering / grouping tests drive the real
`load_agent_outputs` → `build_view_*` path via temp-dir JSONL; the build-rule
tests call the build functions on real `AgentOutput` instances; a subprocess test
guards the lazy-import invariant. Also smoke-verified against the real
`data/agent_outputs/` trail and rendered under Streamlit `AppTest` during
development.

---

## Objective

Give a UI one uniform, comparable way to answer *"how degraded was each
foundation agent's read on date D?"* across six structurally different agents,
and — crucially — to distinguish **"the agent said this was uncertain / neutral"**
from **"the agent did not actually run at all."**

This is an **enabler + a review page**, not an agent and not a Cockpit change. It
ships as a **standalone READ-ONLY review page** reading persisted `AgentOutput`
JSONL from disk. It:

- does **not** touch the Cockpit refresh path,
- adds **no** new `session_state` keys,
- calls **no** LLM and makes **no** network call,
- performs **no** writes,
- modifies **none** of the six existing agent files.

It only **re-describes** what each agent already wrote into its own
`supporting_data`. It never recomputes a market signal.

---

## Files

- **New:** `lib/degradation_view.py` — the LLM-free, network-free enabler
  (stdlib + `lib.agent_framework.agent_output` only at import; **zero**
  `lib.reliability` import). All six per-agent build functions, shared
  `normalize_basis`, severity precedence, fail-closed `likely_bug`,
  `KNOWN_DEFENSIVE_FLAGS`, `load_and_build_all_views`, `list_available_dates`.
- **New:** `pages/12_Agent_Degradation.py` — the standalone read-only review page
  (touches only `lib.degradation_view` + `ui_utils`; reads embedded
  `EvidenceRef` / `AgentResult` via `getattr` / `.model_dump`, never a top-level
  `lib.reliability` import).
- **New:** `scripts/test_degradation_view.py` — the offline suite.
- **Edited:** `ui_utils.py` — registers the page in `render_sidebar()`
  (`st.page_link("pages/12_Agent_Degradation.py", ...)`) plus the `nav_p12`
  label in the `en` and `zh` translation dicts, mirroring how
  `pages/11_Audit_Review.py` is registered.

No other file is touched.

---

## Pre-implementation verification (three checks required by the phase prompt)

1. **Page scaffolding.** `pages/11_Audit_Review.py` uses: `sys.path` bootstrap →
   `from ui_utils import apply_theme, init_session, render_sidebar` →
   `st.set_page_config(...)` → `apply_theme()` → `init_session()` →
   `render_sidebar()`, and a page-local `_zh()` / `_tx()` bilingual helper (NOT
   the `ui_utils.bi()` reader, which is for bilingual *LLM* `{field}_en/_zh`
   pairs — irrelevant to an `AgentOutput.judgment`, a single string). Page 12
   mirrors this exactly. Nav is registered in `ui_utils.py::render_sidebar()` via
   `st.page_link(..., label=t("nav_pN"))` with the label in both translation
   dicts — page 12 follows suit with `nav_p12` ("🩺 Agent Degradation" /
   "🩺 智能体降级回顾"; both verified to resolve).

2. **SectorRotationAgent third basis value — CONFIRMED PRESENT.**
   `lib/agents/sector_rotation_agent.py::_compute_signal_basis` emits three
   values: `signal_present`, `degraded_insufficient`, and **`no_clear_leadership`**
   — a genuine neutral / wait state (data present, no confirmed stage nor clear
   wave; explicitly "NOT directional" in the source docstring). It is added to
   the shared normalization table as `no_clear_leadership -> "no_leadership"`,
   which sorts as a NEUTRAL state (never `likely_bug` on its own).
   `normalize_basis()` never crashes on an unrecognized string — it degrades to
   `"other:<sanitized>"`.

3. **`load_agent_outputs()` + `AgentOutput` fields — CONFIRMED, no drift.** The
   field list (`agent_id`, `timestamp`, `horizon`, `judgment`, `confidence`,
   `evidence_refs`, `supporting_data`, `requires_human_confirmation`,
   `judgment_source`, `valid_until`, `agent_result`, `debate_report`) matches
   what this layer assumes. `load_agent_outputs(agent_id, base_dir, date)` returns
   records **ascending by timestamp** (latest-wins relies on this), and
   `agent_output_from_dict` does `d.get("supporting_data") or {}` with no further
   validation (why every read here is `.get()`-with-default).

Each agent's real `supporting_data` keys were dumped from the live
`data/agent_outputs/` trail and matched to the per-agent build rules
(`regime`/`data_coverage`; `degraded`/`signals_agree_count`/`dark_pool_direction`;
`signal_basis`/`short_confidence`;
`theme_key`/`signal_basis_short`/`signal_basis_mid`/`short_slate.no_trade_reason`/
`unavailable_dimensions`). Test fixtures mirror those real shapes. Note:
MarketStructureAgent's `vintage_mismatch` / `adjacency_degraded` are computed into
its `health_payload` ToolResult but NOT persisted into `supporting_data`, so the
reader deliberately does not read them — see the Known Follow-up section below.

---

## Data model — `AgentDegradationView` (frozen dataclass)

One per agent, or **per theme** for CandidateScreeningAgent. Fields: `agent_id`,
`theme_key` (None except CandidateScreening), `has_output`, `basis_state`
(`"missing"` when no output), `horizon_basis` (CandidateScreening only),
`coverage`, `degrade_flags`, `judgment_source`, `likely_bug`, `detail`
(display-only), `source` (the underlying `AgentOutput`, None iff no output).

### Normalization table (`normalize_basis`) — shared, defined ONCE

```
signal_present        -> ok
degraded_insufficient -> degraded
no_clear_winner       -> no_winner        (CandidateScreeningAgent vocabulary)
no_role_signal        -> no_signal        (ThemeIntelligenceAgent neutral/wait)
full_data_no_signal   -> no_signal        (MarketStructureAgent neutral/wait)
no_clear_leadership   -> no_leadership     (SectorRotationAgent neutral/wait)
None                  -> other:missing
anything else         -> other:<sanitized, lowercased>
```

#### Exhaustive `signal_basis` audit (FIX 1)

The table above was originally reverse-engineered from agent output, and a
missed value (`full_data_no_signal`) was found in review — it fell into
`other:*` and false-tripped `likely_bug` on every normal MarketStructure
no-alert day. After adding it, **every** string literal each of the three
`signal_basis`-emitting agents' `_compute_signal_basis` can return was
enumerated directly from source and confirmed mapped (nothing silently falls to
`other:*`):

| Agent (`_compute_signal_basis`) | Emitted literal | Normalized | Bucket |
|---|---|---|---|
| MarketStructureAgent (`market_structure_agent.py:250/252/253`) | `signal_present` | `ok` | ok |
| | `degraded_insufficient` | `degraded` | degraded |
| | `full_data_no_signal` | `no_signal` | neutral/wait ← **added by FIX 1** |
| SectorRotationAgent (`sector_rotation_agent.py:208/210/211`) | `signal_present` | `ok` | ok |
| | `degraded_insufficient` | `degraded` | degraded |
| | `no_clear_leadership` | `no_leadership` | neutral/wait |
| ThemeIntelligenceAgent (`theme_intelligence_agent.py:299/301/302`) | `signal_present` | `ok` | ok |
| | `degraded_insufficient` | `degraded` | degraded |
| | `no_role_signal` | `no_signal` | neutral/wait |
| CandidateScreeningAgent (per-horizon) | `signal_present` / `degraded_insufficient` / `no_clear_winner` | `ok` / `degraded` / `no_winner` | ok / degraded / neutral |

No additional unmapped value exists across the three agents as of this audit.

### Severity precedence

`degraded` > `other:*` > `no_winner`/`no_signal`/`no_leadership` > `ok`. Used to
collapse CandidateScreeningAgent's short + mid into one overall `basis_state` (the
worst of the two); `horizon_basis` retains both individual values.

### `likely_bug` — fail-closed, OR of all signals

```
likely_bug = (
    not has_output
    or judgment_source == "rule_based"
    or basis_state == "degraded"
    or basis_state.startswith("other:")
    or any(flag not in KNOWN_DEFENSIVE_FLAGS for flag in degrade_flags)
)
```

The `basis_state == "degraded"` clause is **kept even where it looks redundant**
with the flags check: an agent can report a degraded basis WITHOUT appending a
named flag (e.g. MarketStructureAgent's `signal_basis` alone can say
`degraded_insufficient` with no `vintage_mismatch`), so relying only on the flags
list would silently under-report that case. Test case 1 pins this exact gap; test
case 8 pins that the basis and flags triggers are independent.

### `KNOWN_DEFENSIVE_FLAGS` — starter list, deliberately conservative

```
unavailable:short_crowding
unavailable:options_structure
vintage_mismatch
```

This is a STARTER allow-list, **not exhaustive**, and it fails **closed**: a flag
NOT in the set is treated as NON-defensive on purpose, so an ambiguous/unknown
flag pushes `likely_bug` true (favor visibility) rather than being silently
excused. Deliberately **excluded**: `gex_dex_degraded`, `dark_pool_insufficient`,
`regime_degraded`, `adjacency_degraded`. Whether those are benign depends on which
optional API keys are configured — which this module does **not** introspect in
v1. That introspection is the ROADMAP §5.10 "runtime zero-degradation acceptance
protocol" future work, explicitly out of scope here; on the page a human who knows
their own key configuration makes the final call for those flags.

### Documented wart: the `coverage` field-shape asymmetry

`coverage` is a **`float`** for the five single-record agents (a `data_coverage`,
a `short_confidence`, or a `signals_agree_count / 3.0` ratio) but a
**`dict` `{"short": ..., "mid": ...}`** for CandidateScreeningAgent, which carries
two independently-meaningful confidences. This asymmetry is intentional (collapsing
the two candidate confidences to one number would lose information) but it IS a
wart: it is called out inline where the field is defined in
`lib/degradation_view.py`, documented on the `AgentDegradationView.coverage`
annotation, and handled explicitly on the page (`_coverage_str` branches on
`isinstance(coverage, dict)`). Recorded here so it is a documented wart, not a
hidden one.

### `runner_error` handling — generic, not agent-specific

A non-empty `supporting_data["runner_error"]` is surfaced into `detail` for **any**
agent (via a single `_add_runner_error(detail, sd)` helper called by all six
builders); a falsy/empty value is dropped. It is display-only and never feeds
`likely_bug` / severity. This is keyed off the presence of the field, not off any
`agent_id`.

---

## Entry points

- `load_and_build_all_views(date, base_dir="data/agent_outputs") -> dict` —
  one `load_agent_outputs` call per agent, dispatched to the matching
  `build_view_*`. Returns a dict keyed by the six canonical `agent_id`s; every
  value is a **non-empty** list (≥ one placeholder). Never raises. **`date` is
  REQUIRED (FIX 3)** — it deliberately has no `None` default: an all-dates load
  would let `build_view_candidate_screening` (which groups by `theme_key` only)
  merge the same theme across different dates. Forbidding `None` in the signature
  eliminates that footgun structurally rather than guarding against it.
- `list_available_dates(base_dir="data/agent_outputs") -> list[str]` — sorted union
  of every `*.jsonl` stem across the six agent dirs; safe on a missing
  base_dir/subdir; never raises.

---

## The page (`pages/12_Agent_Degradation.py`)

- **Date picker:** `list_available_dates()` ∪ **today's actual date**, sorted
  most-recent-first, **defaulting to today** even when no file exists yet. This is
  an intentional product decision — the "today, nothing yet" empty state is itself
  meaningful and must not be papered over by jumping to the last good day.
- **Global empty-state check runs BEFORE any section:** if every view across all
  six agents is `has_output == False`, the page renders a single bilingual "No
  agent output for this date yet" / "该日期暂无 agent 输出" message and `st.stop()`s
  — it does not emit six empty section headers.
- **Section 0 — Summary:** one row per `(agent, theme)` view (five agents one row
  each; CandidateScreening one row per theme). Columns: Agent / Theme / Status /
  Basis / Coverage / # Flags. The status badge is a **four-way, non-collapsed**
  distinction — `⚫ No Output`, `⚠️ Possible Bug`, `⚪ Neutral · Wait`, `🟢 OK` —
  with "no output" and "degraded/bug" kept in visually distinct buckets because
  they mean different things to a reviewer.
- **Sections 1–6 — per agent (canonical roster order):** the five single-record
  agents render one card (judgment / timestamp / valid_until / source / confidence
  from `source`, then basis / coverage / flags with a "known design limitation"
  note on any `KNOWN_DEFENSIVE_FLAGS` member, then collapsed **Evidence** and
  **Raw supporting_data** expanders, plus an optional **Agent findings** expander
  when `source.agent_result` is present — core value never depends on it).
  CandidateScreening renders **one card per theme**: labeled short/mid
  `horizon_basis`, both short & mid coverage, flags, `no_trade_reason_*` as plain
  informational text (not a warning), judgment + evidence, a first-level **Slate
  detail** expander (short/mid slate) with the large **comparison_table** in a
  **second-level expander NESTED inside it** (verified two levels deep under
  Streamlit 1.57 `AppTest` — nested expanders render there without raising).
- No write paths; no button that triggers computation; no `llm_orchestrator` /
  `signal_engine` / network import.

---

## Real-path validation & the eight required cases

`scripts/test_degradation_view.py` covers, as individually-named functions:

| # | required case | test function |
|---|---|---|
| 1 | degraded basis, NO `vintage_mismatch` key → `degraded` + `likely_bug` | `test_case1_marketstructure_degraded_no_vintage_key` |
| 2 | `rule_based` on a textbook-normal read → `likely_bug` | `test_case2_rule_based_textbook_normal` |
| 3 | later same-day timestamp wins (file written out of order) | `test_case3_same_agent_later_timestamp_wins` |
| 4 | two themes → exactly two views, theme A reflects its later record | `test_case4_candidate_two_themes_later_wins` |
| 5 | unknown basis → `other:<value>`, `likely_bug` via `other:*` | `test_case5_unknown_basis_other_bucket` |
| 6 | empty `supporting_data` degrades (no raise) everywhere | `test_case6_empty_supporting_data` |
| 7 | zero records → single `has_output=False` view (candidate `theme_key` None) | `test_case7_zero_records_placeholder` |
| 8 | defensive flags + degraded basis → `likely_bug` via basis, independent of flags | `test_case8_defensive_flag_plus_degraded_basis` |

Supporting tests: `normalize_basis`, severity precedence, an all-six-agent
integration on real shapes, missing-agent placeholders, malformed-line skip +
partial-record degrade, and `list_available_dates`. Review-round additions:
`test_full_data_no_signal_neutral` (FIX 1), `test_marketstructure_ignores_nonpersisted_flags`
(FIX 2), `test_lazy_import_no_reliability` (FIX 4 — subprocess import guard),
`test_latest_wins_all_builders` (FIX 5a — parametrized over all six builders), and
`test_candidate_none_or_empty_theme_key` (FIX 5b).

---

## Real-data smoke-test finding (this session) — FOLLOW-UP, not this phase's fix

Run against the live trail on **2026-07-01**, the layer flagged
**CandidateScreeningAgent's `ai_chips` theme** as `likely_bug` because its
`judgment_source` was **`rule_based`** (a fallback), with a `detail.runner_error`
of `"RuntimeError: stubbed LLM boundary failure"`. MoneyFlowAgent the same day was
correctly `degraded` (`gex_dex_degraded` + `dark_pool_insufficient`).

The MoneyFlow degraded read is expected (missing optional data). The
CandidateScreening **`rule_based` fallback with an LLM-boundary `runner_error` is a
genuine signal worth investigating separately** — it means that agent's LLM stage
did not complete and it fell back to a deterministic judgment on that run. This
layer's job is precisely to make that visible; **fixing the underlying fallback is
out of scope for this phase** and is filed here as a follow-up.

---

## Known follow-up — MarketStructure `vintage_mismatch` / `adjacency_degraded` not persisted (FIX 2)

MarketStructureAgent computes `vintage_mismatch` and `adjacency_degraded` into its
`health_payload` **ToolResult** (`market_structure_agent.py:484-485`) but does
**not** persist them into `supporting_data` (`:527+`). An earlier draft of
`build_view_market_structure` read those two keys off `supporting_data`, so on
real records they were **always** absent — the flags could never appear.

Per the no-agent-change rule for this phase, the resolution is **reader-side**:
`build_view_market_structure` no longer reads them, so MarketStructure's
`degrade_flags` is empty for now. Its `basis_state` alone still correctly
expresses `degraded_insufficient`, so `likely_bug` correctness is unaffected
(`test_case1_*` + `test_marketstructure_ignores_nonpersisted_flags` pin this).

**Follow-up (separate future task, NOT this phase):** have MarketStructureAgent
persist `vintage_mismatch` / `adjacency_degraded` into `supporting_data` so the
degradation layer can surface them. Until then this layer cannot show them and
does not pretend to.

---

## Deferred (explicitly NOT this phase)

- Persisting MarketStructure `vintage_mismatch` / `adjacency_degraded` into
  `supporting_data` so they can be surfaced (see "Known follow-up" above).
- Key-configuration-aware defensiveness for `gex_dex_degraded` /
  `dark_pool_insufficient` / `regime_degraded` / `adjacency_degraded` (ROADMAP
  §5.10 "runtime zero-degradation acceptance protocol").
- Investigating the CandidateScreening `rule_based` / LLM-boundary fallback above.
- Any Cockpit-embedded banner (standalone page by decision).
- Cross-date trend/history of degradation (this page is single-date).
