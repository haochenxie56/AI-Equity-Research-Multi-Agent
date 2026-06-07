# Phase 6C-A — Trading Desk

**Status:** Implemented; Awaiting Codex Review.
**Phase 6C-B has not started.**

---

## Purpose

Phase 6C-A adds the **execution layer** of the investment workflow as a new
Streamlit page, `pages/9_Trading_Desk.py`. It closes the loop between *finding*
opportunities (Scanner / Cockpit) and *holding* them: the user records a position
with a thesis, and the next time they open the app they immediately see whether
that thesis is intact or weakening and what order to consider.

**Single acceptance criterion:**

> "The user can record a position in MU with a thesis, open the app the next day,
> and immediately see whether the thesis is intact or weakening, and what order to
> consider."

The Trading Desk is **review-only**. It is not a broker, it places no orders, and
it never authorizes execution. Every order recommendation must be placed manually
by the user with their own broker.

---

## What Phase 6C-A changes

Three new library modules + one new page + one test, plus additive `ui_utils.py`
translation keys and one sidebar link.

| File | Role |
|------|------|
| `lib/holdings.py` (new) | `HoldingRecord` dataclass + the single read/write API for `data/holdings.json`. |
| `lib/thesis_monitor.py` (new) | `ThesisCheckResult` + the four-signal Thesis Invalidation Monitor with a deterministic `thesis_status`. |
| `lib/order_advisor.py` (new) | `PriceLevelResult` / `OrderNarrative` / `OrderRecommendation` — code-computed levels + an LLM narrative. |
| `pages/9_Trading_Desk.py` (new) | The three-section Trading Desk page. |
| `scripts/test_reliability_phase_6c_trading_desk.py` (new) | Mock-only test suite (115 checks). |
| `ui_utils.py` (modified) | Additive EN/ZH `nav_p9` + `td_*` translation keys; one `st.page_link` for page 9. |

The page is registered in the sidebar between **Individual Stock Research**
(`pages/4_Equity.py`) and **Investment Cockpit** (`pages/7_Investment_Cockpit.py`),
labeled **交易台** (ZH) / **Trading Desk** (EN).

---

## What Phase 6C-A does NOT change

- It does **not** modify `lib/macro_regime.py`, `lib/macro_data.py`,
  `lib/workflow_state.py`, or `.claude/agents/*`.
- It does **not** modify `lib/llm_orchestrator.py` (no new functions were even
  required — the news/order LLM calls reuse the existing `_get_client` /
  `_llm_json_call` helpers from `lib/thesis_monitor.py` and `lib/order_advisor.py`).
- It does **not** modify pages 1–8.
- `ui_utils.py` is modified **only** to add new `t()` translation keys and one
  sidebar `st.page_link`.
- It introduces **no** broker / order / execution capability, **no** order ticket
  or broker payload, and **no** `approved_for_execution` field anywhere.
- It introduces **no** database and **no** vector store. Persistence is a single
  local JSON file.

---

## Holdings persistence (JSON, not DB)

Holdings are stored in **`data/holdings.json`** as a list of `HoldingRecord`
dicts. The `data/` directory is created on first write if absent. There is **no
database and no vector store** — `lib/holdings.py` is the *only* module that reads
or writes the file, and the page never touches it directly.

`HoldingRecord` fields: `id` (uuid4 hex, auto-generated on creation), `ticker`,
`shares`, `cost_basis` (per share), `entry_date` (YYYY-MM-DD), `horizon`
(`short`|`mid`|`long`), `thesis_text` (free, editable), `thesis_source`
(`manual`|`cockpit`|`scanner`), `thesis_signals` (inherited `key_signals` when the
source is not manual), `status` (`active`|`closed`), `closed_date`, `closed_price`,
`notes`.

All read/write functions are **fail-closed**:

- `load_holdings()` → `[]` on a missing / corrupt / non-list file (never raises).
- `save_holdings()` → `False` on any write failure (never raises); writes to a
  temp file then `os.replace` so a crash mid-write cannot truncate the file.
- `add_holding` / `update_holding` (partial) / `close_holding` / `get_active_holdings`
  all wrap their work in `try/except` and return `False` / `[]` on failure.

---

## Thesis Monitor — signal sources and `thesis_status` rules

For each **active** holding the monitor (`lib/thesis_monitor.py`) checks four
independent signals:

| Signal | Source | Flag condition |
|--------|--------|----------------|
| **A. News** | Finnhub `/company-news` (last 7 days) → **one LLM call** per holding returns `news_sentiment` / `thesis_relevant` / `key_development`. Cached TTL=14400 (4h) keyed on `(ticker, date)`. | `news_sentiment == "negative"` AND `thesis_relevant`. |
| **B. EPS revision** | `signal_engine.fetch_fundamental_signals` (Finnhub `/stock/earnings`; cached ~24h). | EPS revision direction is `deteriorating`. |
| **C. Technical breakdown** | `lib.technical.snapshot()`. | Loss of the 200-day SMA (entered at/above it), RSI(14) < 30, or ADX > 30 with price > 10% below cost. |
| **D. Macro regime** | shared `st.session_state["macro_regime_result"]`. | Regime is `risk_off`/`transition` AND horizon is `short`/`mid`. Long-horizon holdings are **not** flagged by macro alone. |

`thesis_status` is computed **deterministically** by
`compute_thesis_status(...)` — the LLM never decides the status:

- **intact** — no flags triggered.
- **watch** — exactly 1 flag triggered.
- **weakening** — exactly 2 flags triggered.
- **broken** — 3+ flags, OR `technical_breakdown=True` on its own, OR
  `news_sentiment="negative"` AND `thesis_relevant=True`.

`run_thesis_monitor(holdings, macro_result)` runs all active holdings in parallel
(`ThreadPoolExecutor(max_workers=4)`) and memoizes the full result in-process for
4 hours, keyed on `(holdings signature, macro regime, date)`. The memoization is
**not persisted** — it is a same-process cache only (no DB).

---

## Order Advisor — computation methodology

`compute_price_levels(ticker, holding)` is **pure code, no LLM**. From yfinance
OHLCV (6-month) + the `lib.technical` snapshot it computes:

- **current_price** — last close.
- **entry_zone_low** — nearest swing-low support below price, else `cost_basis × 0.97`.
- **entry_zone_high** — `current_price × 1.01` (a limit-order band).
- **stop_loss** — `cost_basis − 2×ATR(14)` OR the 200-day SMA, **whichever is
  closer to the current price**.
- **target_price** — nearest swing-high resistance above price, else
  `cost_basis + 3×ATR(14)`.
- **atr_14**, **support_levels** (last 3 swing lows, 20-day window),
  **resistance_levels** (last 3 swing highs), **volume_trend**
  (last-5 vs prior-20 average volume → increasing/decreasing/neutral),
  **candlestick_pattern**, **risk_reward_ratio**, **position_size_pct**.
- **data_source** — `"live"` when OHLCV was available, `"fixture"` (cost-basis
  derived) on any data failure (fail-closed).

`risk_reward_ratio = (target − entry) / (entry − stop)`, with `entry` = the
current price; a non-positive risk or reward yields `0.0` (no valid long setup).

---

## Kelly-lite sizing assumptions and clamp rules

`position_size_pct` is computed by `kelly_lite_position_size(risk_reward_ratio)`:

```
win_rate  = 0.55            # ASSUMED base win rate (documented assumption)
avg_win   = risk_reward_ratio × 1.0
avg_loss  = 1.0             # one risk unit = the distance to the stop
kelly     = win_rate − (1 − win_rate) / avg_win
position  = clamp(kelly × 0.5, 0.02, 0.10)   # half-Kelly, 2%–10% of portfolio
```

Half-Kelly is used for safety. The `win_rate` is a fixed assumption (we do not
have a per-name backtested edge). The result is always clamped to the
conservative **2%–10%** band; a non-positive / tiny R:R degrades to the 2% floor.

---

## LLM usage (narrative only, not computation)

The only LLM use in the Trading Desk is:

1. **Thesis Monitor news signal** — interprets recent headlines into
   sentiment / relevance / a one-line development. It computes no numbers.
2. **Order narrative** (`generate_order_narrative`) — synthesizes a narrative over
   the **already-computed** price levels: whether current levels support acting
   now, the stop-loss rationale, an R:R < 1.5 warning, candlestick significance,
   and an action suggestion (`add|hold|trim|exit|wait`). The system prompt
   explicitly forbids changing any number. Cached TTL=3600 keyed on
   `(ticker, thesis_status, baseline_action, macro_regime, lang)`; translated to
   Chinese via `lib/translator.py` when `lang == "zh"`. Fail-closed to a
   deterministic, code-only baseline narrative when no LLM key is present.

Every price level, score, ratio, and size is produced by deterministic code. The
LLM only *interprets and narrates*.

---

## Candlestick pattern detection rules

Detection is **code, not LLM** (`order_advisor._candlestick_pattern`), evaluated
on the most recent candle (engulfing also reads the prior candle). With
`rng = high − low` and `body = abs(close − open)`:

- **doji** — `body ≤ 0.1 × rng` (indecision).
- **bullish_engulfing** — prior red, current green, current body engulfs prior
  (`open ≤ prev_close` and `close ≥ prev_open`).
- **bearish_engulfing** — prior green, current red, current body engulfs prior.
- **hammer** — small body in the top third with a long lower shadow
  (`lower_shadow ≥ 2×body`, `upper_shadow ≤ body`).
- **shooting_star** — small body in the bottom third with a long upper shadow.
- **none** — no pattern matches.

Precedence: doji → engulfing → hammer/shooting_star → none. Fail-closed → `none`.

---

## `is_normal_pullback` definition

`is_normal_pullback` distinguishes ordinary price noise from a real thesis break:

> **True** when price is below the cost basis **AND** still above the 200-day SMA
> **AND** RSI(14) is between 35 and 50.

This is the "price down but the uptrend is intact" case — surfaced on the holding
card as *📉 Normal pullback, thesis intact* so a routine dip is not mistaken for a
broken thesis. It is mutually informative with `technical_breakdown`: a normal
pullback never sets the technical breakdown flag.

---

## Files created or modified

**Created:**

- `lib/holdings.py`
- `lib/thesis_monitor.py`
- `lib/order_advisor.py`
- `pages/9_Trading_Desk.py`
- `scripts/test_reliability_phase_6c_trading_desk.py`
- `docs/reliability_phase_6c_a_trading_desk.md` (this file)

**Modified (additive only):**

- `ui_utils.py` — new EN/ZH `nav_p9` + `td_*` translation keys and one
  `st.page_link("pages/9_Trading_Desk.py", ...)` in `render_sidebar`.
- `docs/ai_dev_state/PROJECT_STATE.md`, `docs/ai_dev_state/CURRENT_TASK.md` (state).

**Runtime persistence (created at runtime, git-ignored):** `data/holdings.json`.

---

## Validation summary

Run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`:

```bash
git status --short
python3 -B scripts/test_reliability_phase_6c_trading_desk.py     # 115/115
python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py # 189/189 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py          # 336/336 regression
python3 -B scripts/test_reliability_phase_5s_closeout.py           # 116/116 regression
```

All four suites pass. `pages/9_Trading_Desk.py`, `lib/holdings.py`,
`lib/thesis_monitor.py`, and `lib/order_advisor.py` compile cleanly.

---

## Next phase recommendation

Codex review of Phase 6C-A. After acceptance, the recommended next phase is
**Phase 6C-B — Investment Cockpit Rebuild** (not started).

---

## Guardrails

- No paid APIs (yfinance + Finnhub free tier only); no LLM beyond the news +
  order-narrative interpretive calls (which compute nothing).
- No broker / order / execution capability; no order ticket; no broker payload;
  no `approved_for_execution` field; `approved_for_execution` remains absent.
- No DB / vector store. Holdings persist only to local `data/holdings.json`.
- All data calls fail-closed with a fixture fallback.
- `lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
  `lib/llm_orchestrator.py`, `.claude/agents/*`, and pages 1–8 are not modified.
- `ui_utils.py` is modified only to add `t()` keys and one sidebar link.
- Phase 6C-B and beyond are not implemented.

---

## Acceptance criteria

> "The user can record a position in MU with a thesis, open the app the next day,
> and immediately see whether the thesis is intact or weakening, and what order to
> consider."

- A position in MU is recorded via **Add Position** and persisted to
  `data/holdings.json` through `lib/holdings.py`.
- On the next page load the Thesis Monitor runs automatically (4-hour TTL) and the
  MU row in the **Holdings Monitor table** shows an
  `intact`/`watch`/`weakening`/`broken` colored badge, P&L%, and a truncated key
  alert (key development or first technical-breakdown reason). The table is
  filterable by status / horizon; a per-row **Edit** opens an inline edit/close
  form below the table (mutually exclusive with the **Add Position** form).
- Section 2 renders a code-computed entry zone / ATR stop / target / R:R /
  Kelly-lite size with an LLM narrative and an action suggestion — what order to
  consider, placed manually by the user.
