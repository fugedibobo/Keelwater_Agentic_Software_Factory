"""Typed contracts: one model per table and stage output of architecture section 7. Change additively only."""

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .config import bucket_ids


def _e(name, values):
    return StrEnum(name, {v.replace("-", "_"): v for v in values.split()})


Source = _e("Source", "gong intercom fireflies fullstory hubspot shortcut notion")
Route = _e("Route", "sales support onboarding account_management sessions")
AccountStatus = _e("AccountStatus", "resolved unresolved ambiguous")
Profile = _e("Profile", "replay demo aws self-hosted")
Batch = _e("Batch", "all sep oct")
Decision = _e("Decision", "keep drop low_confidence untriaged")
SignalType = _e("SignalType", "bug feature_gap usability_friction workflow_blocker praise churn_risk question")
QuoteMatch = _e("QuoteMatch", "exact normalised failed")
Status = _e("Status", "new proposed accepted merged rejected parked intent_drafted in_factory shipped enabled measured")
Tag = _e("Tag", "none shipped on_roadmap")
TagState = _e("TagState", "proposed confirmed removed")
CheckStatus = _e("CheckStatus", "passed failed_checks")
Judge = _e("Judge", "faithfulness signal duplicate")  # coherence is reserved, not built in v1
Verdict = _e("Verdict", "pass fail")
JudgeState = _e("JudgeState", "uncalibrated calibrating trusted revoked")
AnnotationAction = _e("AnnotationAction", "accept merge split reject park reassign edit undo confirm_tag remove_tag")
ReasonCode = _e("ReasonCode", "not_product_signal already_shipped already_on_roadmap evidence_wrong mixed_problems low_value other")
LabelOrigin = _e("LabelOrigin", "real_pm synthetic_seed live_reviewer")
LabelSplit = _e("LabelSplit", "dev held_out")
HandoffStatus = _e("HandoffStatus", "drafted approved sent rejected_by_factory superseded cancelled")
OuttakeKind = _e("OuttakeKind", "release_note help_article change_notice followup_brief")
OuttakeStatus = _e("OuttakeStatus", "draft accepted rejected")
ActorKind = _e("ActorKind", "system person")
TargetType = _e("TargetType", "brief opportunity")
RunStatus = _e("RunStatus", "running done failed")

# Status machine (architecture section 7). Human gates need actor_kind person.
TRANSITIONS = {
    "new": {"proposed"},
    "proposed": {"accepted", "merged", "rejected", "parked"},
    "accepted": {"intent_drafted"},
    "intent_drafted": {"in_factory"},
    "in_factory": {"shipped", "accepted"},
    "shipped": {"enabled"},
    "enabled": {"measured"},
    "parked": {"proposed"},
}
HUMAN_GATES = {("proposed", s) for s in ("accepted", "merged", "rejected", "parked")} | {("parked", "proposed")}


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _bucket(v):
    if v is not None and v not in bucket_ids():
        raise ValueError(f"bucket {v!r} not in config/taxonomy.yaml")
    return v


def _quote(v):
    if v is not None and not 5 <= len(v.split()) <= 60:
        raise ValueError("quote must be 5-60 words")
    return v



class _Checked(Row):
    @field_validator("bucket", check_fields=False)
    @classmethod
    def _b(cls, v):
        return _bucket(v)

    @field_validator("quote", check_fields=False)
    @classmethod
    def _q(cls, v):
        return _quote(v)

    @field_validator("severity", check_fields=False)
    @classmethod
    def _s(cls, v):
        if v is not None and not 1 <= v <= 4:
            raise ValueError("severity must be 1-4")
        return v

    @model_validator(mode="after")
    def _probs(self):
        for name in ("is_signal_p", "is_product_signal", "bucket_conf", "bucket_confidence", "similarity"):
            v = getattr(self, name, None)
            if v is not None and not 0 <= v <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        return self


# ---- tables -------------------------------------------------------------------------------------------

class Run(_Checked):
    run_id: str
    started_at: str
    as_of: date
    profile: Profile
    seed: int
    batch: Batch
    data_hash: str
    config_hash: str
    prompt_versions: dict[str, str]
    model_ids: dict[str, str]
    output_hash: str | None = None
    cost_usd: float = 0.0
    status: RunStatus = RunStatus.running
    manifest_json: dict[str, Any] | None = None


class Account(_Checked):
    account_id: str
    name: str
    arr_gbp: float | None = None
    tier: str | None = None
    renewal_date: date | None = None


class RawRecord(_Checked):
    raw_id: str
    source: Source
    route: Route | None = None
    source_id: str
    account_id: str | None = None
    account_status: AccountStatus | None = None
    occurred_at: str | None = None
    payload_json: Any


class Snippet(_Checked):
    snippet_id: str
    raw_id: str
    speaker_email: str | None = None
    text: str
    context_text: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


class Triage(_Checked):
    snippet_id: str
    run_id: str
    call_id: str | None = None
    backend: str
    is_signal_p: float | None = None
    bucket: str | None = None
    bucket_conf: float | None = None
    severity: int | None = None
    signal_type: SignalType | None = None
    decision: Decision
    latency_ms: float | None = None
    audit_weight: float | None = None


class Insight(_Checked):
    insight_id: str
    snippet_id: str
    run_id: str
    call_id: str | None = None
    problem: str
    quote: str
    quote_match: QuoteMatch
    quote_span_start: int | None = None
    quote_span_end: int | None = None
    workflow: str | None = None
    desired_outcome: str | None = None
    severity: int
    account_id: str | None = None
    account_status: AccountStatus | None = None
    embedding: list[float] | None = None


class Opportunity(_Checked):
    opportunity_id: str
    title: str
    problem_statement: str
    bucket: str
    status: Status = Status.new
    squad: str | None = None
    first_seen_as_of: date
    centroid: list[float] | None = None
    merged_into: str | None = None
    tag: Tag = Tag.none
    tag_ref: str | None = None
    tag_state: TagState | None = None


class OpportunityInsight(_Checked):
    opportunity_id: str
    insight_id: str
    similarity: float
    post_ship: bool = False


class Score(_Checked):
    opportunity_id: str
    run_id: str
    total: float
    breadth: float
    severity: float
    value: float
    corroboration: float
    recency: float
    renewal: float
    roadmap: float
    unresolved_insights: int = 0


class Brief(_Checked):
    brief_id: str
    opportunity_id: str
    run_id: str
    call_id: str | None = None
    body_md: str
    citations_json: list[str]
    check_status: CheckStatus
    check_failures_json: list[Any] = []
    prompt_version: str
    model: str


class JudgeVersion(_Checked):
    judge_version_id: str  # <judge>@<prompt version>+<model id>
    judge: Judge
    prompt_version: str
    model: str
    state: JudgeState = JudgeState.uncalibrated
    n_pass: int = 0
    n_fail: int = 0
    tpr: float | None = None
    tnr: float | None = None
    tpr_lower: float | None = None
    tnr_lower: float | None = None
    state_changed_at: str | None = None


class Judgement(_Checked):
    judgement_id: str
    run_id: str
    call_id: str | None = None
    judge_version_id: str
    judge: Judge
    target_type: TargetType
    target_id: str
    verdict: Verdict
    critique: str


class Annotation(_Checked):
    annotation_id: str
    target_type: str
    target_id: str
    actor: str
    action: AnnotationAction
    reason_code: ReasonCode | None = None
    note: str | None = None
    undo_of: str | None = None
    created_at: str

    @model_validator(mode="after")
    def _other_needs_note(self):
        if self.reason_code == ReasonCode.other and not self.note:
            raise ValueError("reason_code other needs a note")
        return self


class Label(_Checked):
    label_id: str
    judge: Judge
    target_type: str  # brief or a noise-audit item
    target_id: str
    verdict: Verdict
    critique: str | None = None
    origin: LabelOrigin
    blind: bool
    split: LabelSplit
    weight: float = 1.0
    actor: str
    created_at: str


class Handoff(_Checked):
    handoff_id: str
    opportunity_id: str
    intent_doc_md: str | None = None
    factory_job_json: dict[str, Any] | None = None
    evidence_snapshot: list[str] = []
    manifest_hash: str | None = None
    status: HandoffStatus = HandoffStatus.drafted
    factory_reason: str | None = None
    errors_json: list[Any] = []


class Outtake(_Checked):
    outtake_id: str
    story_ref: str
    call_id: str | None = None
    kind: OuttakeKind
    body_md: str
    status: OuttakeStatus = OuttakeStatus.draft


class ModelCall(_Checked):
    call_id: str
    run_id: str | None = None
    stage: str
    target_type: str
    target_id: str
    model: str
    profile: Profile
    endpoint: str | None = None
    prompt_version: str | None = None
    input_hash: str
    output_hash: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False


class AuditEvent(_Checked):
    event_id: str
    at: str
    actor: str
    actor_kind: ActorKind
    action: str
    target_type: str
    target_id: str
    details_json: dict[str, Any]
    prev_hash: str
    hash: str


TABLES = {
    "run": Run, "account": Account, "raw_record": RawRecord, "snippet": Snippet, "triage": Triage,
    "insight": Insight, "opportunity": Opportunity, "opportunity_insight": OpportunityInsight,
    "score": Score, "brief": Brief, "judge_version": JudgeVersion, "judgement": Judgement,
    "annotation": Annotation, "label": Label, "handoff": Handoff, "outtake": Outtake,
    "model_call": ModelCall, "audit_event": AuditEvent,
}

# Rows the output hash covers (N1); columns that vary between runs are dropped before hashing.
OUTPUT_TABLES = ("insight", "opportunity", "opportunity_insight", "score", "brief", "judgement", "handoff")
OUTPUT_HASH_EXCLUDE = {"run_id", "brief_id", "latency_ms", "cost_usd", "cached", "started_at", "created_at", "at", "state_changed_at"}


# ---- stage outputs (what a model returns; the gateway validates into these) ---------------------------------

class TriageOutput(_Checked):
    is_product_signal: float
    bucket: str
    bucket_confidence: float
    severity: int
    signal_type: SignalType


class ExtractOutput(_Checked):
    problem: str
    quote: str
    workflow: str
    desired_outcome: str


class ClusterLabelOutput(Row):
    title: str
    problem_statement: str


class BriefOutput(Row):
    body_md: str
    citations: list[str]


class JudgeOutput(Row):
    verdict: Verdict
    critique: str


class AcceptanceCriterion(Row):
    given: str
    when: str
    then: str


class HandoffOutput(Row):
    intent_doc_md: str
    problem_statement: str
    acceptance_criteria: list[AcceptanceCriterion]
    non_goals: list[str]
    constraints: list[str]
    metric_name: str
    metric_definition: str


class OuttakeOutput(Row):
    body_md: str


class GenerateOutput(Row):
    text: str


# Model stages that send a JSON schema; triage (decision model) and embed have none.
STAGE_OUTPUT = {
    "triage_fallback": TriageOutput, "extract": ExtractOutput, "cluster_label": ClusterLabelOutput,
    "brief": BriefOutput, "judge": JudgeOutput, "handoff": HandoffOutput, "outtake": OuttakeOutput,
    "generate": GenerateOutput,
}


# ---- manifest and reports -----------------------------------------------------------------------------------

class RunManifest(Row):
    profile: Profile
    seed: int
    batch: Batch
    as_of: date
    data_hash: str
    config_hash: str
    config_files: dict[str, str]
    prompt_versions: dict[str, str]
    model_ids: dict[str, str]
    model_swaps: dict[str, str] = {}
    cache_keys: list[str] = []


class RunReport(Row):
    run_id: str
    manifest: RunManifest
    output_hash: str
    stages: dict[str, str]
    cost_usd: float


class SuiteReport(Row):
    suite: str
    run_id: str
    seed: int | None = None
    passed: bool
    metrics: dict[str, float | int | bool | None] = {}
    gates: dict[str, bool] = {}
    cache_keys: list[str] = []


class GroundTruthReport(SuiteReport):
    suite: Literal["ground-truth"] = "ground-truth"


class JudgesReport(SuiteReport):
    suite: Literal["judges"] = "judges"


class HoldoutReport(SuiteReport):
    suite: Literal["holdout"] = "holdout"


class StabilityReport(SuiteReport):
    suite: Literal["stability"] = "stability"


# ---- board request bodies (docs/signal-board.md section 9) --------------------------------------------------

class AcceptBody(Row):
    confirmed: bool


class MergeBody(Row):
    target_id: str


class RejectBody(Row):
    reason_code: ReasonCode
    note: str | None = None

    @model_validator(mode="after")
    def _note(self):
        if self.reason_code == ReasonCode.other and not self.note:
            raise ValueError("reason_code other needs a note")
        return self


class ParkBody(Row):
    note: str | None = None


class ReassignBody(Row):
    squad: str


class EditBody(Row):
    title: str
    problem_statement: str


class ConfirmTagBody(Row):
    pass


class RemoveTagBody(Row):
    note: str | None = None


class SplitBody(Row):
    insight_ids: list[str]


class UndoBody(Row):
    audit_event_id: str


class LabelBody(Row):
    target_type: str
    target_id: str
    judge: Judge
    verdict: Verdict
    critique: str | None = None


class OuttakeDecisionBody(Row):
    decision: Literal["accepted", "rejected"]
    note: str | None = None


ALL_MODELS = [m for m in list(TABLES.values()) + [
    TriageOutput, ExtractOutput, ClusterLabelOutput, BriefOutput, JudgeOutput, AcceptanceCriterion, HandoffOutput, OuttakeOutput,
    GenerateOutput, RunManifest, RunReport, SuiteReport, GroundTruthReport, JudgesReport, HoldoutReport,
    StabilityReport, AcceptBody, MergeBody, RejectBody, ParkBody, ReassignBody, EditBody, ConfirmTagBody,
    RemoveTagBody, SplitBody, UndoBody, LabelBody, OuttakeDecisionBody]]
