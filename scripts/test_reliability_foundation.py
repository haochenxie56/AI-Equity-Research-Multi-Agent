"""
Smoke test for the Phase 0.1 reliability foundation.

Run from repo root:
    python scripts/test_reliability_foundation.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.reliability import (
    AgentConfidence,
    AgentResult,
    EvidenceRef,
    EvidenceStore,
    Finding,
    ToolResult,
    create_run_context,
    validate_agent_result,
)


def main() -> None:
    # 1. Run context
    ctx = create_run_context(ticker="ORCL", task="Test reliability foundation")
    print(f"Run ID  : {ctx.run_id}")
    print(f"Run dir : {ctx.run_dir}")

    # 2. Evidence store (fresh run_dir — nothing to load from disk)
    store = EvidenceStore(run_dir=ctx.run_dir)

    # 3. Sample valuation ToolResult
    valuation_result = ToolResult(
        evidence_id="valuation_ORCL_001",
        tool_name="DCFValuation",
        run_id=ctx.run_id,
        ticker="ORCL",
        inputs={"wacc": 0.09, "terminal_growth": 0.03, "forecast_years": 5},
        outputs={"intrinsic_value_per_share": 142.50, "upside_pct": 12.3},
        description="DCF valuation for ORCL based on 5-year FCF forecast",
    )
    store.add_tool_result(valuation_result)

    # 4. AgentResult with strong evidence binding (tool_name + metric set on EvidenceRef)
    agent_result = AgentResult(
        agent_name="FinancialAgent",
        ticker="ORCL",
        run_id=ctx.run_id,
        findings=[
            Finding(
                text=(
                    "DCF analysis indicates an intrinsic value of $142.50 per share, "
                    "representing approximately 12.3% upside from the current price."
                ),
                evidence=[
                    EvidenceRef(
                        evidence_id="valuation_ORCL_001",
                        excerpt="intrinsic_value_per_share=142.50, upside_pct=12.3",
                        tool_name="DCFValuation",
                        metric="intrinsic_value_per_share",
                    )
                ],
            )
        ],
        confidence=AgentConfidence(
            level="medium",
            rationale="Single DCF scenario; results are sensitive to WACC assumptions.",
            score=0.6,
        ),
    )

    # 5. Validate
    report = validate_agent_result(agent_result, store)

    # 6. Persist manifest (tool_results.jsonl already written by add_tool_result)
    store.save_manifest()

    # 7. Report
    print(f"Validation passed: {report.passed}")
    print("ValidationReport JSON:")
    print(report.model_dump_json(indent=2))

    if report.issues:
        print(f"\nWarnings/issues ({len(report.issues)}):")
        for iss in report.issues:
            print(f"  [{iss.severity}] {iss.code} @ {iss.location}: {iss.message}")

    if not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
