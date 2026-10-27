"""The experiment framework's shapes. Times: event (it happened), publish (it became public), acquired (WE got it); derived objects add derivation time."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

#: The independently versioned parts of how an intelligence is constructed. A protocol is a composition of one version of each it uses.
POLICY_KINDS = ("attention", "extraction", "memory", "interpretation", "hypothesis", "evidence", "investigation", "prediction", "learning", "model", "prompts", "tools")
Mode = Literal["controlled", "independent"]


class Evidence(BaseModel):
    """L1: an original record with its acquisition history. The body is never altered; a revised source is a new record."""

    id: str
    kind: str = ""
    source: str = ""                    # who/what it came from (product/kind, outlet)
    title: str = ""
    body: str = ""
    event_time: str = ""                # when the thing described happened ("" = unknown)
    publish_time: str = ""              # when it became public
    acquired_at: str = ""               # when we first held it ("" = unknown: a historical replay then relies on publish_time alone and says so)
    origin_chain: list[str] = Field(default_factory=list)   # ids of records this one repeats or cites: common origins are one chain, not many voices
    url: str = ""                       # where it was published, when known (origin chains match on the canonical URL)
    content_hash: str = ""


class Observation(BaseModel):
    """L2 / L3: something DERIVED. It always names its sources and the method (and version) that produced it."""

    id: str
    source_ids: list[str]
    method: str
    method_version: str
    text: str
    derived_at: str                     # wall-clock derivation time
    as_of: str = ""                     # the information time the producer worked under (a branch's own notes are stamped with their run's cutoff)
    branch: str = ""                    # "" = shared L2; otherwise private to that branch (L3)
    revision: int = 1


class PolicyVersion(BaseModel):
    kind: str
    name: str
    version: int
    params: dict[str, Any] = Field(default_factory=dict)    # everything the policy needs, captured as-is (prompt text, model settings, thresholds)
    impl_sha: str = ""                  # hash of the code that interprets it, when that is code (detects a changed implementation under an old version)
    digest: str = ""

    @property
    def ref(self) -> str:
        return f"{self.kind}/{self.name}@{self.version}"


class Protocol(BaseModel):
    """A composition of policy versions. Immutable: its id is the digest of the composition."""

    id: str
    name: str
    policies: dict[str, PolicyVersion]
    parent: str = ""                    # the protocol this was derived from


class Branch(BaseModel):
    """Isolated mutable state for one protocol: its private memory namespace. Forkable; the fork starts from a copy and the parent is untouched."""

    id: str
    name: str
    protocol_id: str
    parent: str = ""
    forked_memory_digest: str = ""
    created_at: str = ""


class Question(BaseModel):
    id: str
    text: str
    rules: str = ""
    cutoff: str                         # the information cutoff: nothing published, acquired or derived after it may be seen
    closes_at: str = ""
    source: str = ""                    # e.g. market:<id>: where the resolution is read from
    category: Literal["historical", "live", "synthetic"] = "historical"
    common_set: bool = False            # part of the mandatory common question set (independent mode)
    hints: dict[str, Any] = Field(default_factory=dict)      # what production's research is also told about a question: {"countries": [...], "theaters": [...]}
    reference: dict[str, Any] = Field(default_factory=dict)  # comparison values the protocols never see: market_p at the cutoff, base_rate


class Resolution(BaseModel):
    question_id: str
    outcome: Literal["yes", "no", "void"]
    rule: str
    resolved_at: str = ""
    recorded_at: str = ""


class RunRecord(BaseModel):
    run_id: str
    question_id: str
    protocol_id: str
    branch_id: str
    mode: Mode = "controlled"
    snapshot: str
    manifest_digest: str
    prompt_digest: str
    output_digest: str
    p: float | None                     # None = the protocol abstained (stored and evaluated, never dropped)
    usd: float = 0.0
    live: bool = False
    started_at: str = ""
    impl_shas: dict[str, str] = Field(default_factory=dict)
