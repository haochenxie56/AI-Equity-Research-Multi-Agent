"""
lib/reliability/human_feedback_memory.py - Phase 4M-F: Human Feedback Layer.
"""
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator
from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult

_DETERMINISTIC_TIMESTAMP_DEFAULT: str = "1970-01-01T00:00:00Z"
_HUMAN_FEEDBACK_MEMORY_TOOL_NAME: str = "human_feedback_memory_report"
_HUMAN_FEEDBACK_MEMORY_METRIC_GROUP: str = "human_feedback_memory_report"
_CALCULATION_VERSION: str = "human_feedback_memory_v1"

HumanFeedbackMemoryStatus = Literal["unknown","recorded","needs_review","resolved","superseded","archived","blocked",]
HumanFeedbackDecision = Literal["accepted","rejected","overrode","skipped","deferred","needs_revision","executed_manually","unknown",]
HumanFeedbackTargetType = Literal["research_run_memory","thesis_memory","event_memory","allocation_memory","option_trade_memory","decision_packet","review_loop","human_review","trade_plan","option_expression","unknown",]
HumanFeedbackReasonType = Literal["thesis_disagreement","risk_too_high","evidence_insufficient","valuation_disagreement","timing_disagreement","catalyst_disagreement","allocation_disagreement","option_structure_disagreement","execution_not_desired","external_information","preference","other","unknown",]
HumanFeedbackOutcome = Literal["unknown","pending","positive","negative","neutral","mixed","avoided_loss","missed_gain","prevented_bad_action","caused_bad_action",]
HumanFeedbackEventType = Literal["feedback_recorded","feedback_updated","feedback_resolved","outcome_updated","lesson_added","agent_evaluation_flagged","archived","unknown",]
HumanFeedbackActor = Literal["user","reviewer","system","agent","unknown",]

def _dedup_source_refs(refs):
    seen=set(); result=[]
    for ref in refs:
        if ref.source_id not in seen:
            seen.add(ref.source_id); result.append(ref)
    return result

def _dedup_list(items):
    seen=set(); result=[]
    for item in items:
        if item and item not in seen:
            seen.add(item); result.append(item)
    return result

class HumanFeedbackSourceRef(BaseModel):
    model_config=ConfigDict(extra="forbid")
    source_id:str=Field(min_length=1)
    source_type:str="unknown"
    target_type:Optional[HumanFeedbackTargetType]=None
    artifact_id:Optional[str]=None
    evidence_id:Optional[str]=None
    field_path:Optional[str]=None
    label:Optional[str]=None
    metadata:dict[str,Any]=Field(default_factory=dict)
    warnings:list[str]=Field(default_factory=list)
    @model_validator(mode="after")
    def _check_source_id(self):
        if not self.source_id.strip():
            raise ValueError(f"'source_id' must not be whitespace-only; got {self.source_id!r}.")
        return self

class HumanFeedbackTargetRef(BaseModel):
    model_config=ConfigDict(extra="forbid")
    target_ref_id:str=Field(min_length=1)
    target_type:HumanFeedbackTargetType="unknown"
    target_id:str=Field(min_length=1)
    run_id:Optional[str]=None
    memory_id:Optional[str]=None
    thesis_id:Optional[str]=None
    allocation_memory_id:Optional[str]=None
    option_trade_memory_id:Optional[str]=None
    report_id:Optional[str]=None
    field_path:Optional[str]=None
    label:Optional[str]=None
    source_refs:list[HumanFeedbackSourceRef]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list)
    artifact_refs:list[str]=Field(default_factory=list)
    metadata:dict[str,Any]=Field(default_factory=dict)
    warnings:list[str]=Field(default_factory=list)
    @model_validator(mode="after")
    def _check_ids(self):
        for fn in ("target_ref_id","target_id"):
            v=getattr(self,fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

class HumanFeedbackEntry(BaseModel):
    model_config=ConfigDict(extra="forbid")
    feedback_id:str=Field(min_length=1)
    actor:HumanFeedbackActor="user"
    decision:HumanFeedbackDecision="unknown"
    reason_type:HumanFeedbackReasonType="unknown"
    confidence_adjustment:Optional[float]=None
    original_confidence:Optional[float]=None
    adjusted_confidence:Optional[float]=None
    feedback_text:str=Field(min_length=1)
    override_reason:Optional[str]=None
    created_at:str=_DETERMINISTIC_TIMESTAMP_DEFAULT
    source_refs:list[HumanFeedbackSourceRef]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list)
    artifact_refs:list[str]=Field(default_factory=list)
    metadata:dict[str,Any]=Field(default_factory=dict)
    warnings:list[str]=Field(default_factory=list)
    approved_for_execution:bool=False
    @model_validator(mode="after")
    def _validate_entry(self):
        if self.approved_for_execution:
            raise ValueError("approved_for_execution must always be False in Phase 4M-F. This layer does not authorize execution.")
        for fn in ("feedback_id","feedback_text"):
            v=getattr(self,fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        for fname,fval in [("confidence_adjustment",self.confidence_adjustment),("original_confidence",self.original_confidence),("adjusted_confidence",self.adjusted_confidence)]:
            if fval is not None and not (0.0<=fval<=1.0):
                raise ValueError(f"'{fname}' must be between 0 and 1 when present; got {fval!r}.")
        if self.decision=="overrode" and not (self.override_reason or "").strip():
            raise ValueError("decision='overrode' requires a non-empty override_reason. Override reason must be recorded for audit purposes.")
        if self.decision in ("rejected","needs_revision") and self.reason_type=="unknown":
            self.warnings.append(f"decision={self.decision!r} with reason_type='unknown'. A specific reason_type should be provided for audit purposes.")
        return self

class HumanFeedbackMemoryLogEntry(BaseModel):
    model_config=ConfigDict(extra="forbid")
    event_id:str=Field(min_length=1)
    event_type:HumanFeedbackEventType="unknown"
    created_at:str=Field(min_length=1)
    actor:HumanFeedbackActor="system"
    description:str=Field(min_length=1)
    source_ids:list[str]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list)
    metadata:dict[str,Any]=Field(default_factory=dict)
    warnings:list[str]=Field(default_factory=list)
    @model_validator(mode="after")
    def _check_whitespace(self):
        for fn in ("event_id","created_at","description"):
            v=getattr(self,fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

class HumanFeedbackMemoryRecord(BaseModel):
    model_config=ConfigDict(extra="forbid")
    feedback_memory_id:str=Field(min_length=1)
    target:str=Field(min_length=1)
    run_id:Optional[str]=None
    memory_id:Optional[str]=None
    target_ref:HumanFeedbackTargetRef
    feedback_entries:list[HumanFeedbackEntry]=Field(default_factory=list)
    status:HumanFeedbackMemoryStatus="unknown"
    outcome:HumanFeedbackOutcome="unknown"
    lesson:Optional[str]=None
    review_required:bool=False
    agent_evaluation_flag:bool=False
    recorded_at:str=Field(min_length=1)
    resolved_at:Optional[str]=None
    source_refs:list[HumanFeedbackSourceRef]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list)
    artifact_refs:list[str]=Field(default_factory=list)
    event_log:list[HumanFeedbackMemoryLogEntry]=Field(default_factory=list)
    warnings:list[str]=Field(default_factory=list)
    approved_for_execution:bool=False
    @model_validator(mode="after")
    def _check_fields(self):
        if self.approved_for_execution:
            raise ValueError("approved_for_execution must always be False in Phase 4M-F. This layer does not authorize execution.")
        for fn in ("feedback_memory_id","target","recorded_at"):
            v=getattr(self,fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        if not self.feedback_entries:
            raise ValueError("'feedback_entries' must not be empty; at least one feedback entry is required.")
        return self

class HumanFeedbackMemoryInputBundle(BaseModel):
    model_config=ConfigDict(extra="forbid",arbitrary_types_allowed=True)
    target:str=Field(min_length=1)
    run_id:Optional[str]=None
    memory_id:Optional[str]=None
    as_of:Optional[str]=None
    research_run_memory_record:Optional[Any]=None
    thesis_memory_report:Optional[Any]=None
    event_memory_report:Optional[Any]=None
    allocation_memory_report:Optional[Any]=None
    option_trade_memory_report:Optional[Any]=None
    decision_packet:Optional[Any]=None
    human_review_report:Optional[Any]=None
    review_loop_report:Optional[Any]=None
    source_ids:list[str]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list)
    artifact_refs:list[str]=Field(default_factory=list)
    warnings:list[str]=Field(default_factory=list)
    @model_validator(mode="after")
    def _check_whitespace(self):
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self

class HumanFeedbackMemorySummary(BaseModel):
    model_config=ConfigDict(extra="forbid")
    target:str=Field(min_length=1)
    status:HumanFeedbackMemoryStatus="unknown"
    record_count:int=0
    feedback_count:int=0
    accepted_count:int=0
    rejected_count:int=0
    overrode_count:int=0
    skipped_count:int=0
    deferred_count:int=0
    needs_revision_count:int=0
    manual_execution_count:int=0
    review_required_count:int=0
    unresolved_count:int=0
    agent_evaluation_flag_count:int=0
    positive_outcome_count:int=0
    negative_outcome_count:int=0
    top_warnings:list[str]=Field(default_factory=list)
    approved_for_execution:bool=False
    @model_validator(mode="after")
    def _execution_always_forbidden(self):
        if self.approved_for_execution:
            raise ValueError("approved_for_execution must always be False in Phase 4M-F. This layer does not authorize execution.")
        return self

class HumanFeedbackMemoryReport(BaseModel):
    model_config=ConfigDict(extra="forbid")
    report_id:str=Field(min_length=1)
    target:str=Field(min_length=1)
    run_id:Optional[str]=None
    status:HumanFeedbackMemoryStatus="unknown"
    records:list[HumanFeedbackMemoryRecord]=Field(default_factory=list)
    summary:HumanFeedbackMemorySummary
    source_ids:list[str]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list)
    artifact_refs:list[str]=Field(default_factory=list)
    warnings:list[str]=Field(default_factory=list)
    created_at:str=Field(min_length=1)
    updated_at:str=Field(min_length=1)
    calculation_version:str=_CALCULATION_VERSION
    approved_for_execution:bool=False
    @model_validator(mode="after")
    def _execution_always_forbidden(self):
        if self.approved_for_execution:
            raise ValueError("approved_for_execution must always be False in Phase 4M-F. This layer does not authorize execution.")
        return self

def make_human_feedback_memory_record_id(target_id,target_type,decisions,reason_types,feedback_texts,override_reasons,outcome,run_id=None,as_of=None):
    payload={"target_id":target_id,"target_type":target_type,"decisions":list(decisions),"reason_types":list(reason_types),"feedback_texts":list(feedback_texts),"override_reasons":[r for r in override_reasons if r is not None],"outcome":outcome,"run_id":run_id or "","as_of":as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT}
    return f"hfm_{stable_hash_payload(payload,length=12)}"

def make_human_feedback_memory_log_entry_id(feedback_memory_id,event_type,created_at):
    payload={"feedback_memory_id":feedback_memory_id,"event_type":event_type,"created_at":created_at}
    return f"hfmev_{stable_hash_payload(payload,length=12)}"

def make_human_feedback_memory_report_id(target,as_of,run_id=None):
    payload={"target":target,"as_of":as_of,"run_id":run_id or "","tool":_HUMAN_FEEDBACK_MEMORY_TOOL_NAME}
    return f"hfmrpt_{stable_hash_payload(payload,length=12)}"

def build_human_feedback_target_ref(target_id,target_type="unknown",run_id=None,memory_id=None,thesis_id=None,allocation_memory_id=None,option_trade_memory_id=None,report_id=None,field_path=None,label=None,source_refs=None,evidence_ids=None,artifact_refs=None,metadata=None,warnings=None,as_of=None):
    _source_refs=_dedup_source_refs(list(source_refs or []))
    _evidence_ids=_dedup_list(list(evidence_ids or []))
    _artifact_refs=_dedup_list([r for r in (artifact_refs or []) if r and r.strip()])
    ref_payload={"target_id":target_id,"target_type":target_type,"run_id":run_id or "","memory_id":memory_id or "","as_of":as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT}
    target_ref_id=f"hftref_{stable_hash_payload(ref_payload,length=12)}"
    return HumanFeedbackTargetRef(target_ref_id=target_ref_id,target_type=target_type,target_id=target_id,run_id=run_id,memory_id=memory_id,thesis_id=thesis_id,allocation_memory_id=allocation_memory_id,option_trade_memory_id=option_trade_memory_id,report_id=report_id,field_path=field_path,label=label,source_refs=_source_refs,evidence_ids=_evidence_ids,artifact_refs=_artifact_refs,metadata=dict(metadata or {}),warnings=list(warnings or []))

def build_human_feedback_entry(feedback_id,feedback_text,decision="unknown",reason_type="unknown",actor="user",confidence_adjustment=None,original_confidence=None,adjusted_confidence=None,override_reason=None,created_at=None,source_refs=None,evidence_ids=None,artifact_refs=None,metadata=None,warnings=None):
    ts=created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    _source_refs=_dedup_source_refs(list(source_refs or []))
    _evidence_ids=_dedup_list(list(evidence_ids or []))
    _artifact_refs=_dedup_list([r for r in (artifact_refs or []) if r and r.strip()])
    return HumanFeedbackEntry(feedback_id=feedback_id,actor=actor,decision=decision,reason_type=reason_type,confidence_adjustment=confidence_adjustment,original_confidence=original_confidence,adjusted_confidence=adjusted_confidence,feedback_text=feedback_text,override_reason=override_reason,created_at=ts,source_refs=_source_refs,evidence_ids=_evidence_ids,artifact_refs=_artifact_refs,metadata=dict(metadata or {}),warnings=list(warnings or []),approved_for_execution=False)

def build_human_feedback_memory_log_entry(event_type,description,feedback_memory_id,created_at=None,actor="system",source_ids=None,evidence_ids=None,metadata=None,warnings=None):
    ts=created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    entry_id=make_human_feedback_memory_log_entry_id(feedback_memory_id=feedback_memory_id,event_type=event_type,created_at=ts)
    return HumanFeedbackMemoryLogEntry(event_id=entry_id,event_type=event_type,created_at=ts,actor=actor,description=description,source_ids=list(source_ids or []),evidence_ids=list(evidence_ids or []),metadata=dict(metadata or {}),warnings=list(warnings or []))

def _derive_record_status(feedback_entries,review_required,initial_status,hrr_blocked):
    if initial_status is not None:
        return initial_status
    if hrr_blocked:
        return "blocked"
    if review_required:
        return "needs_review"
    decisions=[e.decision for e in feedback_entries]
    if "needs_revision" in decisions:
        return "needs_review"
    if any(d in ("rejected","overrode") for d in decisions):
        return "needs_review"
    return "recorded"

def determine_human_feedback_memory_status(records,input_bundle=None):
    warnings=[]
    hrr=getattr(input_bundle,"human_review_report",None) if input_bundle else None
    if hrr is not None:
        hr_status=str(getattr(hrr,"status","unknown"))
        if hr_status=="blocked":
            warnings.append("Human review report is blocked -- human feedback memory report status set to blocked.")
            return "blocked",warnings
    if not records:
        warnings.append("No human feedback memory records provided -- report status is unknown.")
        return "unknown",warnings
    statuses=[r.status for r in records]
    if "blocked" in statuses:
        n=statuses.count("blocked"); warnings.append(f"{n} human feedback memory record(s) are blocked."); return "blocked",warnings
    if "needs_review" in statuses:
        n=statuses.count("needs_review"); warnings.append(f"{n} human feedback memory record(s) require review."); return "needs_review",warnings
    non_terminal=[s for s in statuses if s not in ("archived","unknown","superseded")]
    if not non_terminal:
        if all(s=="archived" for s in statuses):
            return "archived",warnings
        return "unknown",warnings
    if all(s=="resolved" for s in non_terminal):
        return "resolved",warnings
    if all(s=="recorded" for s in non_terminal):
        return "recorded",warnings
    if any(s=="recorded" for s in non_terminal):
        return "recorded",warnings
    return "unknown",warnings

def collect_human_feedback_memory_source_ids(input_bundle,records=None):
    seen=set(); result=[]
    def _add(sid):
        if sid and sid not in seen:
            seen.add(sid); result.append(sid)
    for sid in input_bundle.source_ids: _add(sid)
    for attr_name in ["research_run_memory_record","thesis_memory_report","event_memory_report","allocation_memory_report","option_trade_memory_report","decision_packet","human_review_report","review_loop_report"]:
        artifact=getattr(input_bundle,attr_name,None)
        if artifact is None: continue
        for sid in (getattr(artifact,"source_ids",[]) or []): _add(str(sid))
        artifact_id=(getattr(artifact,"report_id",None) or getattr(artifact,"result_id",None) or getattr(artifact,"packet_id",None) or getattr(artifact,"memory_id",None))
        if artifact_id: _add(str(artifact_id))
    if records:
        for record in records:
            for ref in record.source_refs: _add(ref.source_id)
            for ref in record.target_ref.source_refs: _add(ref.source_id)
            for entry in record.feedback_entries:
                for ref in entry.source_refs: _add(ref.source_id)
    return result

def collect_human_feedback_memory_evidence_ids(input_bundle,records=None):
    seen=set(); result=[]
    def _add(eid):
        if eid and eid not in seen:
            seen.add(eid); result.append(eid)
    for eid in input_bundle.evidence_ids: _add(eid)
    for attr_name in ["research_run_memory_record","thesis_memory_report","event_memory_report","allocation_memory_report","option_trade_memory_report","decision_packet","human_review_report","review_loop_report"]:
        artifact=getattr(input_bundle,attr_name,None)
        if artifact is None: continue
        for eid in (getattr(artifact,"evidence_ids",None) or []):
            if eid: _add(str(eid))
        artifact_eid=getattr(artifact,"evidence_id",None)
        if artifact_eid: _add(str(artifact_eid))
    if records:
        for record in records:
            for eid in record.evidence_ids: _add(eid)
            for ref in record.source_refs:
                if ref.evidence_id: _add(ref.evidence_id)
            for eid in record.target_ref.evidence_ids: _add(eid)
            for ref in record.target_ref.source_refs:
                if ref.evidence_id: _add(ref.evidence_id)
            for entry in record.feedback_entries:
                for eid in entry.evidence_ids: _add(eid)
                for ref in entry.source_refs:
                    if ref.evidence_id: _add(ref.evidence_id)
    return result

def collect_human_feedback_memory_artifact_refs(input_bundle,records=None):
    seen=set(); result=[]
    def _add(ref):
        if ref and ref.strip() and ref not in seen:
            seen.add(ref); result.append(ref)
    for ref in input_bundle.artifact_refs: _add(ref)
    if records:
        for record in records:
            for ref in record.artifact_refs: _add(ref)
            for ref in record.target_ref.artifact_refs: _add(ref)
            for entry in record.feedback_entries:
                for ref in entry.artifact_refs: _add(ref)
    return result

def summarize_human_feedback_memory(target,status,records,warnings):
    rc=len(records); fc=sum(len(r.feedback_entries) for r in records)
    ac=sum(1 for r in records for e in r.feedback_entries if e.decision=="accepted")
    rejc=sum(1 for r in records for e in r.feedback_entries if e.decision=="rejected")
    oc=sum(1 for r in records for e in r.feedback_entries if e.decision=="overrode")
    sc=sum(1 for r in records for e in r.feedback_entries if e.decision=="skipped")
    dc=sum(1 for r in records for e in r.feedback_entries if e.decision=="deferred")
    nrc=sum(1 for r in records for e in r.feedback_entries if e.decision=="needs_revision")
    mc=sum(1 for r in records for e in r.feedback_entries if e.decision=="executed_manually")
    rrc=sum(1 for r in records if r.review_required)
    urc=sum(1 for r in records if r.status not in ("resolved","archived","superseded","unknown"))
    aefc=sum(1 for r in records if r.agent_evaluation_flag)
    poc=sum(1 for r in records if r.outcome in ("positive","avoided_loss","prevented_bad_action"))
    noc=sum(1 for r in records if r.outcome in ("negative","missed_gain","caused_bad_action"))
    return HumanFeedbackMemorySummary(target=target,status=status,record_count=rc,feedback_count=fc,accepted_count=ac,rejected_count=rejc,overrode_count=oc,skipped_count=sc,deferred_count=dc,needs_revision_count=nrc,manual_execution_count=mc,review_required_count=rrc,unresolved_count=urc,agent_evaluation_flag_count=aefc,positive_outcome_count=poc,negative_outcome_count=noc,top_warnings=warnings[:5] if warnings else [],approved_for_execution=False)

def build_human_feedback_memory_record(target,target_ref,feedback_entries,outcome="unknown",lesson=None,review_required=False,agent_evaluation_flag=False,run_id=None,memory_id=None,initial_status=None,recorded_at=None,resolved_at=None,source_refs=None,evidence_ids=None,artifact_refs=None,warnings=None,hrr_blocked=False,as_of=None):
    ts=recorded_at or as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT
    all_warnings=list(warnings or [])
    _source_refs=_dedup_source_refs(list(source_refs or []))
    _evidence_ids=_dedup_list(list(evidence_ids or []))
    _artifact_refs=_dedup_list([r for r in (artifact_refs or []) if r and r.strip()])
    status=_derive_record_status(feedback_entries=feedback_entries,review_required=review_required,initial_status=initial_status,hrr_blocked=hrr_blocked)
    decisions=[e.decision for e in feedback_entries]; reason_types=[e.reason_type for e in feedback_entries]; feedback_texts=[e.feedback_text for e in feedback_entries]; override_reasons=[e.override_reason for e in feedback_entries]
    feedback_memory_id=make_human_feedback_memory_record_id(target_id=target_ref.target_id,target_type=target_ref.target_type,decisions=decisions,reason_types=reason_types,feedback_texts=feedback_texts,override_reasons=override_reasons,outcome=outcome,run_id=run_id,as_of=ts)
    event_log=[]
    event_log.append(build_human_feedback_memory_log_entry(event_type="feedback_recorded",description=f"Human feedback recorded for {target!r} (target_type={target_ref.target_type!r}, decisions={decisions!r}).",feedback_memory_id=feedback_memory_id,created_at=ts,actor="system",metadata={"decisions":decisions,"target_type":target_ref.target_type}))
    if agent_evaluation_flag:
        event_log.append(build_human_feedback_memory_log_entry(event_type="agent_evaluation_flagged",description=f"Record flagged for agent evaluation for {target!r}.",feedback_memory_id=feedback_memory_id,created_at=ts,actor="system",metadata={"agent_evaluation_flag":True}))
    if lesson:
        event_log.append(build_human_feedback_memory_log_entry(event_type="lesson_added",description=f"Lesson recorded: {lesson!r}.",feedback_memory_id=feedback_memory_id,created_at=ts,actor="system",metadata={"lesson":lesson}))
    if outcome not in ("unknown","pending"):
        event_log.append(build_human_feedback_memory_log_entry(event_type="outcome_updated",description=f"Feedback outcome observed: {outcome!r} for {target!r}.",feedback_memory_id=feedback_memory_id,created_at=ts,actor="system",metadata={"outcome":outcome}))
    return HumanFeedbackMemoryRecord(feedback_memory_id=feedback_memory_id,target=target,run_id=run_id,memory_id=memory_id,target_ref=target_ref,feedback_entries=list(feedback_entries),status=status,outcome=outcome,lesson=lesson,review_required=review_required,agent_evaluation_flag=agent_evaluation_flag,recorded_at=ts,resolved_at=resolved_at,source_refs=_source_refs,evidence_ids=_evidence_ids,artifact_refs=_artifact_refs,event_log=event_log,warnings=all_warnings,approved_for_execution=False)

def build_human_feedback_memory_report(input_bundle,records=None,created_at=None,updated_at=None):
    ts=created_at or input_bundle.as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT
    updated=updated_at or ts; as_of=input_bundle.as_of or ts; run_id=input_bundle.run_id
    report_id=make_human_feedback_memory_report_id(target=input_bundle.target,as_of=as_of,run_id=run_id)
    _records=list(records or [])
    status,status_warnings=determine_human_feedback_memory_status(records=_records,input_bundle=input_bundle)
    missing_warnings=[]
    for attr,label in [("research_run_memory_record","research_run_memory_record"),("decision_packet","decision_packet"),("human_review_report","human_review_report"),("review_loop_report","review_loop_report")]:
        if getattr(input_bundle,attr) is None:
            missing_warnings.append(f"Missing optional upstream artifact: {label}.")
    all_warnings=list(input_bundle.warnings)+status_warnings+missing_warnings
    source_ids=collect_human_feedback_memory_source_ids(input_bundle,_records)
    evidence_ids=collect_human_feedback_memory_evidence_ids(input_bundle,_records)
    artifact_refs=collect_human_feedback_memory_artifact_refs(input_bundle,_records)
    summary=summarize_human_feedback_memory(target=input_bundle.target,status=status,records=_records,warnings=all_warnings)
    return HumanFeedbackMemoryReport(report_id=report_id,target=input_bundle.target,run_id=run_id,status=status,records=_records,summary=summary,source_ids=source_ids,evidence_ids=evidence_ids,artifact_refs=artifact_refs,warnings=all_warnings,created_at=ts,updated_at=updated,calculation_version=_CALCULATION_VERSION,approved_for_execution=False)

def human_feedback_memory_tool_result_from_report(report,run_id=None):
    _run_id=run_id or report.run_id or report.target
    outputs={"report_id":report.report_id,"target":report.target,"status":report.status,"report":report.model_dump(),"summary":report.summary.model_dump(),"record_count":report.summary.record_count,"feedback_count":report.summary.feedback_count,"review_required_count":report.summary.review_required_count,"agent_evaluation_flag_count":report.summary.agent_evaluation_flag_count,"calculation_version":report.calculation_version,"approved_for_execution":False}
    evidence_id=make_evidence_id(run_id=_run_id,tool_name=_HUMAN_FEEDBACK_MEMORY_TOOL_NAME,target=report.target,metric_group=_HUMAN_FEEDBACK_MEMORY_METRIC_GROUP,payload=outputs)
    return ToolResult(tool_name=_HUMAN_FEEDBACK_MEMORY_TOOL_NAME,run_id=_run_id,ticker=report.target if report.target else None,evidence_id=evidence_id,inputs={"target":report.target,"report_id":report.report_id},outputs=outputs,description=f"HumanFeedbackMemoryReport for {report.target} (report_id={report.report_id!r}, status={report.status!r}, records={report.summary.record_count}, feedback_entries={report.summary.feedback_count}, review_required={report.summary.review_required_count}, agent_evaluation_flags={report.summary.agent_evaluation_flag_count}).")

__all__=["HumanFeedbackActor","HumanFeedbackDecision","HumanFeedbackEventType","HumanFeedbackMemoryStatus","HumanFeedbackOutcome","HumanFeedbackReasonType","HumanFeedbackTargetType","HumanFeedbackEntry","HumanFeedbackMemoryInputBundle","HumanFeedbackMemoryLogEntry","HumanFeedbackMemoryRecord","HumanFeedbackMemoryReport","HumanFeedbackMemorySummary","HumanFeedbackSourceRef","HumanFeedbackTargetRef","build_human_feedback_entry","build_human_feedback_memory_log_entry","build_human_feedback_memory_record","build_human_feedback_memory_report","build_human_feedback_target_ref","collect_human_feedback_memory_artifact_refs","collect_human_feedback_memory_evidence_ids","collect_human_feedback_memory_source_ids","determine_human_feedback_memory_status","human_feedback_memory_tool_result_from_report","make_human_feedback_memory_log_entry_id","make_human_feedback_memory_record_id","make_human_feedback_memory_report_id","summarize_human_feedback_memory"]