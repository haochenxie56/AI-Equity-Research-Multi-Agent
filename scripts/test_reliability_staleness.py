"""
scripts/test_reliability_staleness.py

Test suite for lib/reliability/staleness.py — Phase 2I: Staleness Checker.

Tests use synthetic payloads; no real network calls are made.
No live app files are imported or modified.

Run:
    python3 scripts/test_reliability_staleness.py

Expected: all assertions pass, 0 failures.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.reliability.staleness import (
    # Literal type aliases
    StalenessStatus,
    StalenessDomain,
    StalenessSeverity,
    TimestampRole,
    # Models
    StalenessPolicy,
    StalenessFinding,
    StalenessReport,
    # Helpers
    parse_iso_like_datetime,
    days_between,
    make_staleness_finding_id,
    evaluate_timestamp_staleness,
    evaluate_expiration_status,
    aggregate_staleness_findings,
    default_staleness_policy_for_domain,
    check_tool_result_staleness,
    check_news_snapshot_staleness,
    check_option_decision_set_staleness,
    check_catalyst_snapshot_staleness,
    check_allocation_decision_set_staleness,
    check_macro_snapshot_staleness,
    staleness_findings_to_validation_items,
    staleness_report_tool_result_from_report,
    summarize_staleness_report,
)
from lib.reliability.validation_aggregator import AggregatedValidationItem
from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.run_context import create_run_context

_PASS = 0
_FAIL = 0


def _check(label: str, condition: bool) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {label}")


def _expect_error(label: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _FAIL += 1
        print(f"  FAIL (no error raised): {label}")
    except Exception:
        _PASS += 1


# ---------------------------------------------------------------------------
# Fixtures — updated to use as_of (canonical field name)
# ---------------------------------------------------------------------------

def _make_finding(
    domain: str = "news",
    status: str = "fresh",
    severity: str = "info",
    timestamp_role: str = "as_of",
    timestamp_value: str = "2026-05-22",
    as_of: str = "2026-05-22",
    age_days: float = 0.0,
    max_age_days: float = 7.0,
    message: str = "Test finding.",
    source_name: str = "test_source",
    object_id: str = "obj_001",
    field_path: str | None = None,
    evidence_id: str | None = None,
) -> StalenessFinding:
    fid = make_staleness_finding_id(
        domain=domain, timestamp_role=timestamp_role,
        timestamp_value=timestamp_value, as_of=as_of,
        source_name=source_name, object_id=object_id, field_path=field_path,
    )
    return StalenessFinding(
        finding_id=fid,
        domain=domain,
        status=status,
        severity=severity,
        timestamp_role=timestamp_role,
        timestamp_value=timestamp_value,
        as_of=as_of,
        age_days=age_days,
        max_age_days=max_age_days,
        message=message,
        source_name=source_name,
        object_id=object_id,
        field_path=field_path,
        evidence_id=evidence_id,
    )


# ---------------------------------------------------------------------------
# T01-T05: parse_iso_like_datetime
# ---------------------------------------------------------------------------

print("T01-T05: parse_iso_like_datetime")

from datetime import datetime, timezone

dt1 = parse_iso_like_datetime("2026-05-22")
_check("T01 date-only returns UTC midnight",
       dt1 == datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc))

dt2 = parse_iso_like_datetime("2026-05-22T10:30:00Z")
_check("T02 Z suffix parses to UTC",
       dt2 == datetime(2026, 5, 22, 10, 30, 0, tzinfo=timezone.utc))

dt3 = parse_iso_like_datetime("2026-05-22T10:30:00+05:30")
_check("T03 offset-aware datetime preserved",
       dt3.utcoffset() is not None and dt3.tzinfo is not None)

dt4 = parse_iso_like_datetime("2026-05-22T10:30:00")
_check("T04 naive datetime treated as UTC",
       dt4.tzinfo == timezone.utc)

_expect_error("T05 invalid string raises ValueError",
              lambda: parse_iso_like_datetime("not-a-date"))


# ---------------------------------------------------------------------------
# T06-T08: days_between
# ---------------------------------------------------------------------------

print("T06-T08: days_between")

d1 = days_between("2026-05-15", "2026-05-22")
_check("T06 positive days_between", abs(d1 - 7.0) < 0.001)

d2 = days_between("2026-05-22", "2026-05-15")
_check("T07 negative days_between (later is before earlier)", abs(d2 + 7.0) < 0.001)

d3 = days_between("2026-05-22", "2026-05-22")
_check("T08 same day → 0.0", abs(d3) < 0.001)


# ---------------------------------------------------------------------------
# T09-T10: make_staleness_finding_id
# ---------------------------------------------------------------------------

print("T09-T10: make_staleness_finding_id")

fid_a = make_staleness_finding_id("news", "as_of", "2026-05-15", "2026-05-22")
fid_b = make_staleness_finding_id("news", "as_of", "2026-05-15", "2026-05-22")
_check("T09 same inputs → same finding_id", fid_a == fid_b)

fid_c = make_staleness_finding_id("macro", "as_of", "2026-05-15", "2026-05-22")
_check("T10 different domain → different finding_id", fid_a != fid_c)


# ---------------------------------------------------------------------------
# T11-T13: StalenessPolicy model — requires policy_id
# ---------------------------------------------------------------------------

print("T11-T13: StalenessPolicy")

pol = StalenessPolicy(
    policy_id="test_news_policy",
    domain="news",
    max_age_days=7.0,
)
_check("T11 StalenessPolicy default near_stale_ratio=0.8", pol.near_stale_ratio == 0.8)
_check("T11b StalenessPolicy default severities", pol.stale_severity == "warning")

_expect_error("T12 max_age_days=0 raises error",
              lambda: StalenessPolicy(policy_id="p", domain="news", max_age_days=0.0))

_expect_error("T13 near_stale_ratio > 1.0 raises error",
              lambda: StalenessPolicy(
                  policy_id="p", domain="news", max_age_days=7.0, near_stale_ratio=1.5
              ))


# ---------------------------------------------------------------------------
# T14-T15: StalenessFinding model — uses as_of (renamed from reference_date)
# ---------------------------------------------------------------------------

print("T14-T15: StalenessFinding")

fid = make_staleness_finding_id("news", "as_of", "2026-05-22", "2026-05-22")
finding = StalenessFinding(
    finding_id=fid,
    domain="news",
    status="fresh",
    severity="info",
    timestamp_role="as_of",
    timestamp_value="2026-05-22",
    as_of="2026-05-22",
    age_days=0.0,
    max_age_days=7.0,
    message="Test finding.",
    source_name="news_snapshot",
    object_id="snap_001",
)
_check("T14 StalenessFinding valid construction", finding.status == "fresh")
_check("T14b as_of field populated", finding.as_of == "2026-05-22")

_expect_error("T15 whitespace finding_id raises error",
              lambda: StalenessFinding(
                  finding_id="   ",
                  domain="news", status="fresh", severity="info",
                  timestamp_role="as_of", as_of="2026-05-22",
                  message="msg",
              ))


# ---------------------------------------------------------------------------
# T16-T22: StalenessReport auto-normalisation
# ---------------------------------------------------------------------------

print("T16-T22: StalenessReport auto-normalisation")

report_empty = StalenessReport(report_id="rep_empty", as_of="2026-05-22")
_check("T16 empty findings → status=fresh", report_empty.status == "fresh")
_check("T16b all counts 0", (
    report_empty.fresh_count == 0 and report_empty.stale_count == 0
    and report_empty.expired_count == 0
))

f_expired = _make_finding(domain="option", status="expired", severity="critical",
                          message="Expired option.")
f_stale = _make_finding(domain="news", status="stale", severity="warning",
                        message="Stale news.")
f_near_stale = _make_finding(domain="macro", status="near_stale", severity="info",
                              message="Near stale macro.", object_id="obj_002")
f_unknown = _make_finding(domain="allocation", status="unknown", severity="warning",
                          message="Unknown ts.", object_id="obj_003",
                          timestamp_value=None)
f_fresh = _make_finding(domain="catalyst", status="fresh", severity="info",
                        message="Fresh catalyst.", object_id="obj_004")

rep_expired = StalenessReport(
    report_id="rep_exp", as_of="2026-05-22",
    findings=[f_expired, f_stale, f_near_stale, f_unknown, f_fresh],
)
_check("T17 expired priority highest", rep_expired.status == "expired")

rep_stale = StalenessReport(
    report_id="rep_stale", as_of="2026-05-22",
    findings=[f_stale, f_near_stale],
)
_check("T18 stale overrides near_stale", rep_stale.status == "stale")

rep_near_stale = StalenessReport(
    report_id="rep_ns", as_of="2026-05-22",
    findings=[f_near_stale, f_unknown],
)
_check("T19 near_stale overrides unknown", rep_near_stale.status == "near_stale")

rep_counts = StalenessReport(
    report_id="rep_cnt", as_of="2026-05-22",
    findings=[f_expired, f_stale, f_near_stale, f_unknown, f_fresh],
)
_check("T20 counts correct", (
    rep_counts.expired_count == 1
    and rep_counts.stale_count == 1
    and rep_counts.near_stale_count == 1
    and rep_counts.unknown_count == 1
    and rep_counts.fresh_count == 1
))

rep_override = StalenessReport(
    report_id="rep_ovr", as_of="2026-05-22",
    findings=[f_stale],
    stale_count=99,   # should be overridden
    status="fresh",   # should be overridden
)
_check("T21 manual wrong counts overridden by normalisation",
       rep_override.stale_count == 1 and rep_override.status == "stale")

_expect_error("T22 whitespace report_id raises error",
              lambda: StalenessReport(report_id="   ", as_of="2026-05-22"))


# ---------------------------------------------------------------------------
# T23-T28: evaluate_timestamp_staleness — policy requires policy_id
# ---------------------------------------------------------------------------

print("T23-T28: evaluate_timestamp_staleness")

pol_news = StalenessPolicy(
    policy_id="test_news_pol",
    domain="news",
    max_age_days=7.0,
    near_stale_ratio=0.8,
)

# 1 day old vs 7-day max → fresh
st, age, sev = evaluate_timestamp_staleness("2026-05-21", "2026-05-22", pol_news)
_check("T23 fresh: age=1d < 7d threshold", st == "fresh" and abs(age - 1.0) < 0.001)

# 6 days old vs 7-day max → near_stale (6 >= 7*0.8=5.6)
st, age, sev = evaluate_timestamp_staleness("2026-05-16", "2026-05-22", pol_news)
_check("T24 near_stale: age=6d >= 5.6d threshold", st == "near_stale" and sev == "info")

# 8 days old vs 7-day max → stale
st, age, sev = evaluate_timestamp_staleness("2026-05-14", "2026-05-22", pol_news)
_check("T25 stale: age=8d >= 7d max", st == "stale" and sev == "warning")

st, age, sev = evaluate_timestamp_staleness(None, "2026-05-22", pol_news)
_check("T26 None timestamp → unknown", st == "unknown" and age is None)

st, age, sev = evaluate_timestamp_staleness("not-a-date", "2026-05-22", pol_news)
_check("T27 unparseable → unknown", st == "unknown" and age is None)

# Future timestamp (3 days ahead) → fresh; age is None (normalised from negative)
st, age, sev = evaluate_timestamp_staleness("2026-05-25", "2026-05-22", pol_news)
_check("T28 future timestamp → fresh and age is None", st == "fresh" and age is None)


# ---------------------------------------------------------------------------
# T29-T31: evaluate_expiration_status — returns StalenessFinding (not tuple)
# ---------------------------------------------------------------------------

print("T29-T31: evaluate_expiration_status")

exp_finding29 = evaluate_expiration_status("2026-05-01", "2026-05-22")
_check("T29 expired: past date → status=expired",
       exp_finding29.status == "expired")
_check("T29b expired: age_days > 0",
       exp_finding29.age_days is not None and exp_finding29.age_days > 0)
_check("T29c expired: severity=critical", exp_finding29.severity == "critical")
_check("T29d expired: timestamp_role=expiration",
       exp_finding29.timestamp_role == "expiration")
_check("T29e expired: returns StalenessFinding",
       isinstance(exp_finding29, StalenessFinding))

exp_finding30 = evaluate_expiration_status("2026-06-01", "2026-05-22")
_check("T30 fresh: future date → status=fresh", exp_finding30.status == "fresh")
_check("T30b fresh: severity=info", exp_finding30.severity == "info")
_check("T30c fresh: age_days is None", exp_finding30.age_days is None)

exp_finding31 = evaluate_expiration_status(None, "2026-05-22")
_check("T31 None expiration → unknown", exp_finding31.status == "unknown")
_check("T31b None expiration → warning (allow_unknown=True default)",
       exp_finding31.severity == "warning")


# ---------------------------------------------------------------------------
# T32-T33: aggregate_staleness_findings
# ---------------------------------------------------------------------------

print("T32-T33: aggregate_staleness_findings")

report32 = aggregate_staleness_findings(
    "rep_32", "2026-05-22",
    [f_stale, f_near_stale],
    target="AAPL",
)
_check("T32 basic aggregation status=stale", report32.status == "stale")
_check("T32b target stored", report32.target == "AAPL")
_check("T32c stale_count=1", report32.stale_count == 1)

report33 = aggregate_staleness_findings("rep_33", "2026-05-22", [])
_check("T33 empty findings → status=fresh", report33.status == "fresh")
_check("T33b all counts 0", report33.stale_count == 0 and report33.expired_count == 0)


# ---------------------------------------------------------------------------
# T34-T37: default_staleness_policy_for_domain
# ---------------------------------------------------------------------------

print("T34-T37: default_staleness_policy_for_domain")

pol_news_def = default_staleness_policy_for_domain("news")
_check("T34 news default max_age_days=7.0", pol_news_def.max_age_days == 7.0)

pol_option = default_staleness_policy_for_domain("option")
_check("T35 option default max_age_days=1.0", pol_option.max_age_days == 1.0)

pol_macro = default_staleness_policy_for_domain("macro")
_check("T36 macro default max_age_days=30.0", pol_macro.max_age_days == 30.0)

_check("T37 all defaults use near_stale_ratio=0.8", all(
    default_staleness_policy_for_domain(d).near_stale_ratio == 0.8
    for d in ["news", "macro", "option", "allocation", "catalyst",
              "earnings", "estimate_revision", "tool_result", "generic"]
))


# ---------------------------------------------------------------------------
# T38-T39: check_tool_result_staleness
# ---------------------------------------------------------------------------

print("T38-T39: check_tool_result_staleness")

from lib.reliability.schemas import ToolResult as _ToolResult

ctx = create_run_context()
from lib.reliability.adapters import make_evidence_id as _mei

_fresh_eid = _mei(
    run_id=ctx.run_id, tool_name="fresh_tool", target="T",
    metric_group="m", payload={},
)
tr_fresh = _ToolResult(
    evidence_id=_fresh_eid,
    tool_name="fresh_tool",
    run_id=ctx.run_id,
    outputs={"as_of": "2026-05-22"},
)
# Patch created_at to be recent
object.__setattr__(tr_fresh, "created_at", "2026-05-22T00:00:00+00:00")

report38 = check_tool_result_staleness(tr_fresh, "2026-05-22")
_check("T38 fresh tool result → status=fresh", report38.status == "fresh")
_check("T38b two findings (created_at + outputs.as_of)", len(report38.findings) == 2)

_stale_eid = _mei(
    run_id=ctx.run_id, tool_name="stale_tool", target="T",
    metric_group="m", payload={},
)
tr_stale = _ToolResult(
    evidence_id=_stale_eid,
    tool_name="stale_tool",
    run_id=ctx.run_id,
    outputs={},
)
object.__setattr__(tr_stale, "created_at", "2026-04-01T00:00:00+00:00")  # 51 days old

report39 = check_tool_result_staleness(tr_stale, "2026-05-22")
_check("T39 stale created_at → report is stale",
       report39.status in ("stale", "expired") and report39.stale_count >= 1)


# ---------------------------------------------------------------------------
# T40-T41: check_news_snapshot_staleness
# ---------------------------------------------------------------------------

print("T40-T41: check_news_snapshot_staleness")


class _FakeEvent:
    def __init__(self, event_id, published_at):
        self.event_id = event_id
        self.published_at = published_at


class _FakeNewsSnapshot:
    def __init__(self, snapshot_id, as_of, events=None):
        self.snapshot_id = snapshot_id
        self.as_of = as_of
        self.events = events or []


snap_stale = _FakeNewsSnapshot("snap_001", "2026-05-05", [])  # 17 days old > 7d max
report40 = check_news_snapshot_staleness(snap_stale, "2026-05-22")
_check("T40 stale snapshot as_of → status=stale", report40.status == "stale")

snap_with_events = _FakeNewsSnapshot(
    "snap_002", "2026-05-20",  # fresh
    [_FakeEvent("ev_001", "2026-05-10")],  # 12 days old > 7d → stale event
)
report41 = check_news_snapshot_staleness(snap_with_events, "2026-05-22")
_check("T41 event published_at checked separately",
       len(report41.findings) == 2)  # snapshot as_of + 1 event
_check("T41b stale event makes report stale", report41.status == "stale")


# ---------------------------------------------------------------------------
# T42: check_macro_snapshot_staleness
# ---------------------------------------------------------------------------

print("T42: check_macro_snapshot_staleness")


class _FakeMacroIndicator:
    def __init__(self, name, as_of):
        self.name = name
        self.as_of = as_of


class _FakeMacroSnapshot:
    def __init__(self, snapshot_id, as_of, indicators=None):
        self.snapshot_id = snapshot_id
        self.as_of = as_of
        self.indicators = indicators or []


snap_macro = _FakeMacroSnapshot(
    "macro_001", "2026-05-22",
    [_FakeMacroIndicator("GDP", "2026-04-01")],  # 51 days > 30d max → stale
)
report42 = check_macro_snapshot_staleness(snap_macro, "2026-05-22")
_check("T42 indicator as_of checked and stale indicator makes report stale",
       report42.stale_count >= 1 and len(report42.findings) == 2)


# ---------------------------------------------------------------------------
# T43: check_allocation_decision_set_staleness
# ---------------------------------------------------------------------------

print("T43: check_allocation_decision_set_staleness")


class _FakeAllocDS:
    def __init__(self, ticker, as_of):
        self.ticker = ticker
        self.as_of = as_of


alloc_fresh = _FakeAllocDS("AAPL", "2026-05-20")  # 2 days old < 7d max → fresh
report43 = check_allocation_decision_set_staleness(alloc_fresh, "2026-05-22")
_check("T43 fresh allocation → status=fresh", report43.status == "fresh")
_check("T43b allocation policy max_age=7d", report43.findings[0].max_age_days == 7.0)


# ---------------------------------------------------------------------------
# T44: check_option_decision_set_staleness
# ---------------------------------------------------------------------------

print("T44: check_option_decision_set_staleness")


class _FakeChain:
    def __init__(self, as_of, expirations=None, contracts=None):
        self.as_of = as_of
        self.expirations = expirations or []
        self.contracts = contracts or []


class _FakeOptionDS:
    def __init__(self, ticker, as_of, chain_snapshot=None):
        self.ticker = ticker
        self.as_of = as_of
        self.chain_snapshot = chain_snapshot


chain = _FakeChain(
    "2026-05-22",
    expirations=["2026-05-01", "2026-06-20"],  # first expired, second active
)
opt_ds = _FakeOptionDS("NVDA", "2026-05-22", chain)
report44 = check_option_decision_set_staleness(opt_ds, "2026-05-22")
_check("T44 expired chain expiry → report status=expired",
       report44.status == "expired")
_check("T44b chain as_of and expirations both checked",
       len(report44.findings) >= 3)  # ds.as_of + chain.as_of + 2 expirations


# ---------------------------------------------------------------------------
# T45: check_catalyst_snapshot_staleness
# ---------------------------------------------------------------------------

print("T45: check_catalyst_snapshot_staleness")


class _FakeRevision:
    def __init__(self, revision_id, revision_date):
        self.revision_id = revision_id
        self.revision_date = revision_date


class _FakeCatalystSnapshot:
    def __init__(self, snapshot_id, as_of, catalysts=None,
                 estimate_revisions=None, earnings_events=None):
        self.snapshot_id = snapshot_id
        self.as_of = as_of
        self.catalysts = catalysts or []
        self.estimate_revisions = estimate_revisions or []
        self.earnings_events = earnings_events or []


rev_stale = _FakeRevision("rev_001", "2026-04-01")  # 51d > 30d → stale
cat_snap = _FakeCatalystSnapshot(
    "cat_001", "2026-05-22",
    estimate_revisions=[rev_stale],
)
report45 = check_catalyst_snapshot_staleness(cat_snap, "2026-05-22")
_check("T45 stale revision_date makes report stale", report45.status == "stale")
_check("T45b estimate_revision domain present",
       "estimate_revision" in report45.domains_present)


# ---------------------------------------------------------------------------
# T46-T48: staleness_findings_to_validation_items
# ---------------------------------------------------------------------------

print("T46-T48: staleness_findings_to_validation_items")

items_from_fresh = staleness_findings_to_validation_items([f_fresh])
_check("T46 fresh findings are skipped", len(items_from_fresh) == 0)

items_from_stale = staleness_findings_to_validation_items([f_stale])
_check("T47 stale finding converted to AggregatedValidationItem",
       len(items_from_stale) == 1)
_check("T47b item_type=stale_data", items_from_stale[0].item_type == "stale_data")
_check("T47c severity=warning (from stale finding)", items_from_stale[0].severity == "warning")
_check("T47d blocking=False for warning", not items_from_stale[0].blocking)

items_from_expired = staleness_findings_to_validation_items([f_expired])
_check("T48 expired finding → critical severity", items_from_expired[0].severity == "critical")
_check("T48b expired → blocking=True", items_from_expired[0].blocking)
_check("T48c item_type=stale_data", items_from_expired[0].item_type == "stale_data")


# ---------------------------------------------------------------------------
# T49: staleness_report_tool_result_from_report + summarize_staleness_report
# ---------------------------------------------------------------------------

print("T49: staleness_report_tool_result_from_report + summarize_staleness_report")

rep49 = aggregate_staleness_findings(
    "rep_49", "2026-05-22", [f_stale, f_near_stale],
    target="NVDA",
)
tr49 = staleness_report_tool_result_from_report("run_2i_001", rep49)
_check("T49 tool_name=staleness_report", tr49.tool_name == "staleness_report")
_check("T49b evidence_id is non-empty", bool(tr49.evidence_id))
_check("T49c inputs has report_id", tr49.inputs.get("report_id") == "rep_49")
_check("T49d inputs has target='staleness'", tr49.inputs.get("target") == "staleness")
_check("T49e custom target stored",
       staleness_report_tool_result_from_report(
           "run_2i_001", rep49, target="NVDA"
       ).inputs.get("target") == "NVDA")

summary49 = summarize_staleness_report(rep49)
_check("T49f summary has status", "status" in summary49)
_check("T49g summary has stale_count", summary49.get("stale_count") == 1)
_check("T49h summary has top_messages", isinstance(summary49.get("top_messages"), list))
_check("T49i summary domains_present list", isinstance(summary49.get("domains_present"), list))


# ===========================================================================
# NEW TESTS (T50+): Full Phase 2I contract coverage
# ===========================================================================

# ---------------------------------------------------------------------------
# T50-T55: StalenessPolicy — new fields: policy_id, expiration_grace_days,
#           allow_unknown, metadata, unknown_severity property
# ---------------------------------------------------------------------------

print("T50-T55: StalenessPolicy new fields")

pol50 = StalenessPolicy(
    policy_id="my_policy",
    domain="news",
    max_age_days=7.0,
    expiration_grace_days=2.0,
    allow_unknown=False,
    metadata={"custom_key": "custom_val"},
)
_check("T50 policy_id accepted", pol50.policy_id == "my_policy")
_check("T50b expiration_grace_days accepted", pol50.expiration_grace_days == 2.0)
_check("T50c allow_unknown=False accepted", pol50.allow_unknown is False)
_check("T50d metadata accepted", pol50.metadata.get("custom_key") == "custom_val")

_expect_error("T51 whitespace-only policy_id rejected",
              lambda: StalenessPolicy(
                  policy_id="   ", domain="news", max_age_days=7.0,
              ))

_check("T52 allow_unknown=True → unknown_severity='warning'",
       StalenessPolicy(policy_id="p", domain="news", max_age_days=7.0,
                       allow_unknown=True).unknown_severity == "warning")

_check("T53 allow_unknown=False → unknown_severity='critical'",
       StalenessPolicy(policy_id="p", domain="news", max_age_days=7.0,
                       allow_unknown=False).unknown_severity == "critical")

_check("T54 expiration_grace_days=0.0 accepted",
       StalenessPolicy(policy_id="p", domain="option", max_age_days=1.0,
                       expiration_grace_days=0.0).expiration_grace_days == 0.0)

# max_age_days=None means no age limit
pol55 = StalenessPolicy(policy_id="no_limit_pol", domain="generic", max_age_days=None)
_check("T55 max_age_days=None is valid", pol55.max_age_days is None)
# Evaluating against a policy with no age limit → always fresh
st55, age55, sev55 = evaluate_timestamp_staleness("2020-01-01", "2026-05-22", pol55)
_check("T55b no age limit → always fresh", st55 == "fresh")

_expect_error("T55c negative expiration_grace_days rejected",
              lambda: StalenessPolicy(
                  policy_id="p", domain="option", max_age_days=1.0,
                  expiration_grace_days=-1.0,
              ))


# ---------------------------------------------------------------------------
# T56-T62: StalenessFinding — new fields: as_of, field_path, evidence_id;
#           constraints: negative age_days, non-positive max_age_days
# ---------------------------------------------------------------------------

print("T56-T62: StalenessFinding new fields and constraints")

fid56 = make_staleness_finding_id("news", "as_of", "2026-05-15", "2026-05-22")
finding56 = StalenessFinding(
    finding_id=fid56,
    domain="news",
    status="stale",
    severity="warning",
    as_of="2026-05-22",
    message="Stale.",
    field_path="snapshot.as_of",
    evidence_id="ev_abc123",
    age_days=7.0,
    max_age_days=7.0,
)
_check("T56 as_of field accepted", finding56.as_of == "2026-05-22")
_check("T57 field_path accepted", finding56.field_path == "snapshot.as_of")
_check("T58 evidence_id accepted", finding56.evidence_id == "ev_abc123")

_expect_error("T59 empty as_of rejected",
              lambda: StalenessFinding(
                  finding_id=fid56, domain="news", status="fresh", severity="info",
                  as_of="", message="msg",
              ))

_expect_error("T60 negative age_days rejected",
              lambda: StalenessFinding(
                  finding_id=fid56, domain="news", status="fresh", severity="info",
                  as_of="2026-05-22", message="msg", age_days=-1.0,
              ))

_expect_error("T61 max_age_days=0.0 rejected",
              lambda: StalenessFinding(
                  finding_id=fid56, domain="news", status="fresh", severity="info",
                  as_of="2026-05-22", message="msg", max_age_days=0.0,
              ))

_expect_error("T62 negative max_age_days rejected",
              lambda: StalenessFinding(
                  finding_id=fid56, domain="news", status="fresh", severity="info",
                  as_of="2026-05-22", message="msg", max_age_days=-5.0,
              ))


# ---------------------------------------------------------------------------
# T63-T66: evaluate_timestamp_staleness — allow_unknown, max_age_days=None,
#           field_path/evidence_id params
# ---------------------------------------------------------------------------

print("T63-T66: evaluate_timestamp_staleness extended")

pol_strict = StalenessPolicy(
    policy_id="strict_pol", domain="news", max_age_days=7.0, allow_unknown=False
)
st63, age63, sev63 = evaluate_timestamp_staleness(None, "2026-05-22", pol_strict)
_check("T63 allow_unknown=False → critical severity for unknown",
       st63 == "unknown" and sev63 == "critical")

pol_lenient = StalenessPolicy(
    policy_id="lenient_pol", domain="news", max_age_days=7.0, allow_unknown=True
)
st64, age64, sev64 = evaluate_timestamp_staleness(None, "2026-05-22", pol_lenient)
_check("T64 allow_unknown=True → warning severity for unknown",
       st64 == "unknown" and sev64 == "warning")

pol_no_limit = StalenessPolicy(
    policy_id="no_limit", domain="generic", max_age_days=None
)
st65, age65, sev65 = evaluate_timestamp_staleness("2010-01-01", "2026-05-22", pol_no_limit)
_check("T65 max_age_days=None → always fresh regardless of age", st65 == "fresh")

# field_path and evidence_id are accepted without error (informational params)
try:
    st66, age66, sev66 = evaluate_timestamp_staleness(
        "2026-05-20", "2026-05-22", pol_news,
        field_path="snapshot.as_of", evidence_id="ev_001",
    )
    _check("T66 field_path/evidence_id params accepted", True)
except Exception as e:
    _check(f"T66 field_path/evidence_id params accepted: {e}", False)


# ---------------------------------------------------------------------------
# T67-T74: evaluate_expiration_status — grace period, allow_unknown,
#           field_path, StalenessFinding return type
# ---------------------------------------------------------------------------

print("T67-T74: evaluate_expiration_status extended")

_check("T67 evaluate_expiration_status returns StalenessFinding",
       isinstance(evaluate_expiration_status("2026-06-01", "2026-05-22"), StalenessFinding))

finding68 = evaluate_expiration_status("2026-06-01", "2026-05-22")
_check("T68 future expiration → fresh", finding68.status == "fresh")
_check("T68b fresh severity=info", finding68.severity == "info")
_check("T68c age_days is None for fresh", finding68.age_days is None)

# Grace period: expired 1 day ago, grace=5 days → near_stale
pol_grace = StalenessPolicy(
    policy_id="grace_pol", domain="option", max_age_days=1.0,
    expiration_grace_days=5.0,
)
finding69 = evaluate_expiration_status("2026-05-21", "2026-05-22", policy=pol_grace)
_check("T69 1d past, 5d grace → near_stale",
       finding69.status == "near_stale")
_check("T69b near_stale severity=warning", finding69.severity == "warning")
_check("T69c age_days > 0", finding69.age_days is not None and finding69.age_days > 0)
_check("T69d metadata has days_past_expiration",
       "days_past_expiration" in finding69.metadata)

# Beyond grace: expired 10 days ago, grace=5 days → expired
finding70 = evaluate_expiration_status("2026-05-12", "2026-05-22", policy=pol_grace)
_check("T70 10d past, 5d grace → expired", finding70.status == "expired")
_check("T70b expired severity=critical", finding70.severity == "critical")

# Missing expiration with allow_unknown=True → unknown warning
pol71 = StalenessPolicy(
    policy_id="p71", domain="option", max_age_days=1.0, allow_unknown=True
)
finding71 = evaluate_expiration_status(None, "2026-05-22", policy=pol71)
_check("T71 missing expiration allow_unknown=True → unknown warning",
       finding71.status == "unknown" and finding71.severity == "warning")

# Missing expiration with allow_unknown=False → unknown critical
pol72 = StalenessPolicy(
    policy_id="p72", domain="option", max_age_days=1.0, allow_unknown=False
)
finding72 = evaluate_expiration_status(None, "2026-05-22", policy=pol72)
_check("T72 missing expiration allow_unknown=False → unknown critical",
       finding72.status == "unknown" and finding72.severity == "critical")

# field_path propagated
finding73 = evaluate_expiration_status(
    "2026-05-01", "2026-05-22",
    field_path="chain_snapshot.contracts.0.expiration",
)
_check("T73 field_path propagated in finding",
       finding73.field_path == "chain_snapshot.contracts.0.expiration")

# timestamp_role is always "expiration"
finding74 = evaluate_expiration_status("2026-05-01", "2026-05-22")
_check("T74 timestamp_role=expiration", finding74.timestamp_role == "expiration")


# ---------------------------------------------------------------------------
# T75-T77: aggregate_staleness_findings — deduplication
# ---------------------------------------------------------------------------

print("T75-T77: aggregate_staleness_findings deduplication")

# Create two findings with the same finding_id
f_dup_a = _make_finding(
    domain="news", status="stale", severity="warning",
    message="Stale message A.", object_id="dup_obj",
)
# Create an identical copy with same inputs → same finding_id
f_dup_b = _make_finding(
    domain="news", status="stale", severity="warning",
    message="Stale message A.", object_id="dup_obj",
)
_check("T75 dup findings have same finding_id", f_dup_a.finding_id == f_dup_b.finding_id)

input_list = [f_dup_a, f_dup_b, f_near_stale]
report75 = aggregate_staleness_findings("rep_75", "2026-05-22", input_list)
_check("T75b duplicate finding_id deduped — 2 unique findings",
       len(report75.findings) == 2)
_check("T75c first occurrence preserved",
       report75.findings[0].finding_id == f_dup_a.finding_id)

_check("T76 counts computed from deduped list — stale_count=1",
       report75.stale_count == 1)

# Verify input list not mutated
_check("T77 input list not mutated", len(input_list) == 3)


# ---------------------------------------------------------------------------
# T78-T80: check_news_snapshot_staleness — field_path provenance
# ---------------------------------------------------------------------------

print("T78-T80: check_news field_path")

snap78 = _FakeNewsSnapshot(
    "snap78", "2026-05-22",
    [_FakeEvent("ev_abc", "2026-05-10")],
)
report78 = check_news_snapshot_staleness(snap78, "2026-05-22")

# Find snapshot.as_of finding
snap_finding = next((f for f in report78.findings if f.timestamp_role == "as_of"
                     and f.source_name == "news_snapshot"), None)
_check("T78 snapshot.as_of finding has field_path='as_of'",
       snap_finding is not None and snap_finding.field_path == "as_of")

# Find event finding
ev_finding = next((f for f in report78.findings if f.timestamp_role == "published_at"), None)
_check("T79 event published_at has field_path='events.0.published_at'",
       ev_finding is not None and ev_finding.field_path == "events.0.published_at")

_check("T80 object_id set to event_id",
       ev_finding is not None and ev_finding.object_id == "ev_abc")


# ---------------------------------------------------------------------------
# T81-T84: check_catalyst_snapshot_staleness — field_path, domains
# ---------------------------------------------------------------------------

print("T81-T84: check_catalyst field_path")


class _FakeCatalystEvent:
    def __init__(self, catalyst_id, event_date):
        self.catalyst_id = catalyst_id
        self.event_date = event_date


class _FakeEarningsEvent:
    def __init__(self, earnings_id, report_date):
        self.earnings_id = earnings_id
        self.report_date = report_date


cat81_snap = _FakeCatalystSnapshot(
    "cat81", "2026-05-22",
    catalysts=[_FakeCatalystEvent("cat_001", "2026-05-10")],
    estimate_revisions=[_FakeRevision("rev_001", "2026-04-01")],
    earnings_events=[_FakeEarningsEvent("earn_001", "2026-04-01")],
)
report81 = check_catalyst_snapshot_staleness(cat81_snap, "2026-05-22")

cat_ev_finding = next(
    (f for f in report81.findings if f.timestamp_role == "event_date"), None
)
_check("T81 catalyst event_date has field_path='catalysts.0.event_date'",
       cat_ev_finding is not None
       and cat_ev_finding.field_path == "catalysts.0.event_date")
_check("T81b domain=catalyst for event_date finding",
       cat_ev_finding is not None and cat_ev_finding.domain == "catalyst")

earn_finding = next(
    (f for f in report81.findings if f.timestamp_role == "report_date"), None
)
_check("T82 earnings report_date has field_path='earnings_events.0.report_date'",
       earn_finding is not None
       and earn_finding.field_path == "earnings_events.0.report_date")

rev_finding = next(
    (f for f in report81.findings if f.timestamp_role == "revision_date"), None
)
_check("T83 revision revision_date has field_path='estimate_revisions.0.revision_date'",
       rev_finding is not None
       and rev_finding.field_path == "estimate_revisions.0.revision_date")

_check("T84 domains include catalyst, earnings, estimate_revision",
       all(d in report81.domains_present
           for d in ["catalyst", "earnings", "estimate_revision"]))


# ---------------------------------------------------------------------------
# T85-T88: check_allocation_decision_set_staleness — portfolio, position
# ---------------------------------------------------------------------------

print("T85-T88: check_allocation portfolio/position")


class _FakePosition:
    def __init__(self, ticker, as_of):
        self.ticker = ticker
        self.as_of = as_of


class _FakePortfolio:
    def __init__(self, portfolio_id, as_of, positions=None):
        self.portfolio_id = portfolio_id
        self.as_of = as_of
        self.positions = positions or []


class _FakeAllocDSWithPortfolio:
    def __init__(self, portfolio_id, as_of, portfolio=None):
        self.portfolio_id = portfolio_id
        self.as_of = as_of
        self.portfolio = portfolio


port85 = _FakePortfolio(
    "port_001", "2026-05-20",
    positions=[_FakePosition("AAPL", "2026-05-19")],
)
alloc85 = _FakeAllocDSWithPortfolio("port_001", "2026-05-20", portfolio=port85)
report85 = check_allocation_decision_set_staleness(alloc85, "2026-05-22")

ds_finding85 = next(
    (f for f in report85.findings
     if f.source_name == "allocation_decision_set"), None
)
_check("T85 decision_set.as_of checked with field_path='as_of'",
       ds_finding85 is not None and ds_finding85.field_path == "as_of")

port_finding85 = next(
    (f for f in report85.findings
     if f.source_name == "portfolio_snapshot"), None
)
_check("T86 portfolio.as_of checked with field_path='portfolio.as_of'",
       port_finding85 is not None and port_finding85.field_path == "portfolio.as_of")

pos_finding85 = next(
    (f for f in report85.findings
     if f.source_name == "position_snapshot"), None
)
_check("T87 position.as_of checked with field_path='portfolio.positions.0.as_of'",
       pos_finding85 is not None
       and pos_finding85.field_path == "portfolio.positions.0.as_of")

# Without portfolio: only decision_set.as_of
alloc88 = _FakeAllocDS("GOOG", "2026-05-22")
report88 = check_allocation_decision_set_staleness(alloc88, "2026-05-22")
_check("T88 no portfolio → only decision_set.as_of finding",
       len(report88.findings) == 1)


# ---------------------------------------------------------------------------
# T89-T91: check_option_decision_set_staleness — contracts, grace period
# ---------------------------------------------------------------------------

print("T89-T91: check_option contracts / grace period")


class _FakeContract:
    def __init__(self, expiration, as_of="2026-05-22"):
        self.expiration = expiration
        self.as_of = as_of


pol_grace_opt = StalenessPolicy(
    policy_id="grace_opt_pol", domain="option", max_age_days=1.0,
    expiration_grace_days=5.0,
)

# Contracts preferred over expirations
chain89 = _FakeChain(
    "2026-05-22",
    expirations=["2026-05-01"],       # should be ignored
    contracts=[_FakeContract("2026-05-22"), _FakeContract("2026-06-20")],
)
opt89 = _FakeOptionDS("SPY", "2026-05-22", chain89)
report89 = check_option_decision_set_staleness(opt89, "2026-05-22", policy=pol_grace_opt)

# Find contract expiration findings
contract_findings = [
    f for f in report89.findings if f.timestamp_role == "expiration"
]
_check("T89 contracts preferred over expirations — 2 contract findings",
       len(contract_findings) == 2)

# Check field_path for first contract
fp89 = next(
    (f.field_path for f in contract_findings
     if "contracts.0" in (f.field_path or "")), None
)
_check("T89b field_path for contract.0 is 'chain_snapshot.contracts.0.expiration'",
       fp89 == "chain_snapshot.contracts.0.expiration")

# Grace period: expired 1d ago with 5d grace → near_stale
chain90 = _FakeChain(
    "2026-05-22",
    contracts=[_FakeContract("2026-05-21")],  # 1 day past, within 5d grace
)
opt90 = _FakeOptionDS("TSLA", "2026-05-22", chain90)
report90 = check_option_decision_set_staleness(opt90, "2026-05-22", policy=pol_grace_opt)
exp_findings90 = [f for f in report90.findings if f.timestamp_role == "expiration"]
_check("T90 1d past expiration within 5d grace → near_stale",
       len(exp_findings90) > 0 and exp_findings90[0].status == "near_stale")

# When contracts list is empty, falls back to expirations
chain91 = _FakeChain("2026-05-22", expirations=["2026-05-01"], contracts=[])
opt91 = _FakeOptionDS("MSFT", "2026-05-22", chain91)
report91 = check_option_decision_set_staleness(opt91, "2026-05-22")
exp_findings91 = [f for f in report91.findings if f.timestamp_role == "expiration"]
_check("T91 empty contracts falls back to expirations list",
       len(exp_findings91) == 1)


# ---------------------------------------------------------------------------
# T92-T93: check_macro_snapshot_staleness — minimal object, graceful
# ---------------------------------------------------------------------------

print("T92-T93: check_macro graceful handling")


class _MinimalObject:
    """Object with no as_of or indicators attribute."""
    pass


try:
    report92 = check_macro_snapshot_staleness(_MinimalObject(), "2026-05-22")
    _check("T92 minimal object does not crash", True)
    # Should produce an unknown finding since as_of is None
    _check("T92b minimal object produces unknown finding",
           report92.unknown_count >= 1)
except Exception as e:
    _check(f"T92 minimal object crashed: {e}", False)
    _check("T92b minimal object unknown finding (skipped due to crash)", False)

report93 = check_macro_snapshot_staleness(
    _FakeMacroSnapshot("m_001", "2026-05-22"), "2026-05-22"
)
_check("T93 checks as_of if present", len(report93.findings) >= 1)
snap_finding93 = next(
    (f for f in report93.findings if f.field_path == "as_of"), None
)
_check("T93b as_of finding has field_path='as_of'", snap_finding93 is not None)


# ---------------------------------------------------------------------------
# T94-T99: staleness_findings_to_validation_items — provenance preservation
# ---------------------------------------------------------------------------

print("T94-T99: staleness_findings_to_validation_items provenance")

f_with_prov = _make_finding(
    domain="news", status="stale", severity="warning",
    message="Stale with provenance.",
    field_path="events.0.published_at",
    evidence_id="ev_prov_001",
    object_id="ev_123",
)
items94 = staleness_findings_to_validation_items([f_with_prov])
_check("T94 field_path preserved in validation item",
       len(items94) == 1 and items94[0].field_path == "events.0.published_at")

_check("T95 evidence_id preserved in validation item",
       items94[0].evidence_id == "ev_prov_001")

_check("T96 object_id preserved in validation item",
       items94[0].object_id == "ev_123")

# unknown status → provenance item_type
f_unknown97 = _make_finding(
    domain="news", status="unknown", severity="warning",
    message="Unknown timestamp.",
    timestamp_value=None,
)
items97 = staleness_findings_to_validation_items([f_unknown97])
_check("T97 unknown status → item_type='provenance'",
       len(items97) == 1 and items97[0].item_type == "provenance")

# near_stale → stale_data
f_near98 = _make_finding(
    domain="macro", status="near_stale", severity="info",
    message="Near stale macro.", object_id="m001",
)
items98 = staleness_findings_to_validation_items([f_near98])
_check("T98 near_stale → item_type='stale_data'",
       len(items98) == 1 and items98[0].item_type == "stale_data")

# metadata has staleness_status
_check("T99 metadata contains staleness_status",
       items94[0].metadata.get("staleness_status") == "stale")


# ---------------------------------------------------------------------------
# T100-T103: default_staleness_policy_for_domain — policy_id, grace, allow_unknown
# ---------------------------------------------------------------------------

print("T100-T103: default policy fields")

for _dom in ["news", "macro", "option", "allocation", "catalyst",
             "earnings", "estimate_revision", "validation", "tool_result", "generic"]:
    _pol = default_staleness_policy_for_domain(_dom)
    _check(
        f"T100 {_dom}: policy_id='default_{_dom}_staleness_policy'",
        _pol.policy_id == f"default_{_dom}_staleness_policy",
    )

_check("T101 expiration_grace_days=0.0 in all default policies", all(
    default_staleness_policy_for_domain(d).expiration_grace_days == 0.0
    for d in ["news", "macro", "option", "allocation", "catalyst",
              "earnings", "estimate_revision", "validation", "tool_result", "generic"]
))

_check("T102 allow_unknown=True in all default policies", all(
    default_staleness_policy_for_domain(d).allow_unknown is True
    for d in ["news", "macro", "option", "allocation", "catalyst",
              "earnings", "estimate_revision", "validation", "tool_result", "generic"]
))

_check("T103 validation domain max_age=7.0",
       default_staleness_policy_for_domain("validation").max_age_days == 7.0)


# ---------------------------------------------------------------------------
# T104: staleness_report_tool_result_from_report — ToolResult validity
# ---------------------------------------------------------------------------

print("T104: staleness_report_tool_result_from_report ToolResult")

from lib.reliability.schemas import ToolResult as _TR104
rep104 = aggregate_staleness_findings("rep_104", "2026-05-22", [f_stale])
tr104 = staleness_report_tool_result_from_report("run_104", rep104, target="AAPL")
_check("T104 returns valid ToolResult instance", isinstance(tr104, _TR104))
_check("T104b tool_name is stable='staleness_report'",
       tr104.tool_name == "staleness_report")
_check("T104c target in inputs", tr104.inputs.get("target") == "AAPL")
_check("T104d evidence_id is deterministic (same inputs → same id)", (
    staleness_report_tool_result_from_report("run_104", rep104, target="AAPL").evidence_id
    == tr104.evidence_id
))
_check("T104e outputs contains status",
       tr104.outputs.get("status") == rep104.status)
_check("T104f calculation_version in outputs",
       "calculation_version" in tr104.outputs)


# ---------------------------------------------------------------------------
# Module isolation: no live app modules imported
# ---------------------------------------------------------------------------

print("Module isolation check")

_LIVE_MODULES = [
    "app", "pages", "lib.llm_orchestrator", "lib.data_fetcher",
    "lib.workflow_state", "streamlit",
]
for mod_name in _LIVE_MODULES:
    loaded = any(
        m == mod_name or m.startswith(mod_name + ".")
        for m in sys.modules
    )
    _check(f"live module not imported: {mod_name}", not loaded)


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print()
total = _PASS + _FAIL
print(f"Results: {_PASS}/{total} passed, {_FAIL} failed.")
if _FAIL > 0:
    sys.exit(1)
