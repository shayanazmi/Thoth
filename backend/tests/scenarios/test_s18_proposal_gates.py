"""
S18 · The research proposal (docs/features/08-writing.md).

User-seat criteria encoded here:
  - Writing the proposal needs the researcher's explicit approval (with an estimate); the outline costs nothing heavy.
  - The Writer is given only the research file (trial witnesses as W1.., design, hypothesis, the researcher's
    own "I say") and a section whose material is missing carries a [GAP] marker.
  - The Verifier removes claims a witness does not support (unknown witness, wrong number, does-not-support),
    softens over-reaching ones, flags uncited ones, and lists every removal.
  - A FATAL from the Reviewer triggers at most 2 revision rounds; if it stays, the proposal stays provisional.
  - A thinker's critical concern keeps the proposal provisional until the researcher answers it.
  - References list only witnesses a surviving sentence cites.
  - No export without approval; a provisional export is watermarked.
  - The researcher's edits are never overwritten without their say-so; with no model, nothing is invented.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage

from backend.tests.scenarios.conftest import read_sse as _read_sse

HYP = "Night-shift nurses have higher emotional exhaustion than day-shift nurses because of circadian misalignment."
W1_FINDING = "Night-shift nurses reported higher emotional exhaustion than day-shift nurses"
OUTLINE = [
    {"key": "literature", "title": "Literature review", "purpose": "verdicts per sub-claim"},
    {"key": "methods", "title": "Methods", "purpose": "the chosen design"},
    {"key": "expected_outcomes", "title": "Expected outcomes", "purpose": "each result and its meaning"},
]

LIT = ("## Literature review\n\n"
       f"{W1_FINDING} {{{{w:W1}}}}. "
       "Night shifts cause burnout in all nurses {{w:W1}}. "
       "The ICU survey included n = 999 nurses {{w:W1}}. "
       "A cohort study found the opposite pattern {{w:W7}}. "
       "Prior studies report that 80% of nurses leave within a year. "
       "The trial found the evidence insufficient overall {{file:verdict}}.")
CLEAN_LIT = f"## Literature review\n\n{W1_FINDING} {{{{w:W1}}}}. The trial found the evidence insufficient overall {{{{file:verdict}}}}."
METHODS = "## Methods\n\nThis study will follow nurses for eight weeks using the chosen cohort design {{file:design}}."
OUTCOMES_NO_REFUTE = "## Expected outcomes\n\nIf misalignment predicts exhaustion, the hypothesis gains support."
OUTCOMES = OUTCOMES_NO_REFUTE + " If exhaustion does not differ between shifts, the hypothesis would be refuted."


class Model:
    """One scripted model for every proposal role; answers by role prompt and section."""

    def __init__(self, sections=None, reviewer_fatal=False, writer_up=True):
        self.calls = []
        self.sections = {"Literature review": LIT, "Methods": METHODS, "Expected outcomes": OUTCOMES, **(sections or {})}
        self.reviewer_fatal = reviewer_fatal
        self.writer_up = writer_up

    def bind_tools(self, *a, **k):
        return self

    def invoke(self, messages, **kw):
        system, human = messages[0].content, messages[-1].content
        if "You are Thoth's Writer" in system:
            role = "outline" if "Tailor the purpose" in system else ("revise" if "REVISION" in system else "writer")
        elif "You are Thoth's Verifier" in system:
            role = "verifier"
        elif "You are Thoth's Reviewer" in system:
            role = "reviewer"
        else:
            role = "other"
        self.calls.append((role, system, human))
        if role in ("writer", "revise", "outline") and not self.writer_up:
            raise RuntimeError("writer down")
        if role == "outline":
            return AIMessage(content=json.dumps({"sections": [{"key": "literature", "purpose": "W1's survey and the trial verdict"}]}))
        if role in ("writer", "revise"):
            title = json.loads(re.search(r"<section>(.*?)</section>", human, re.S).group(1))["title"]
            return AIMessage(content=json.dumps({"markdown": self.sections.get(title, f"## {title}\n\nThis study will do it.")}))
        if role == "verifier":
            sentence = re.search(r"<sentence>(.*?)</sentence>", human, re.S).group(1)
            if "cause burnout" in sentence:
                v = {"support": "partially_supports", "problem": "causal_leap", "action": "soften",
                     "softened": "Night-shift nurses reported higher emotional exhaustion in a cross-sectional survey", "why": "association only"}
            elif W1_FINDING in sentence:
                v = {"support": "supports", "problem": "none", "action": "keep", "softened": "", "why": "states it"}
            else:
                v = {"support": "does_not_support", "problem": "predicate_drift", "action": "keep", "softened": "", "why": "different outcome"}
            return AIMessage(content=json.dumps(v))
        if role == "reviewer":
            weak = [{"severity": "FATAL", "section": "Methods", "passage": "follow nurses for eight weeks",
                     "problem": "The design cannot test mediation.", "fix": "Add a mediation analysis."}] if self.reviewer_fatal else []
            weak.append({"severity": "MINOR", "section": "Expected outcomes", "passage": "the hypothesis gains support", "problem": "vague", "fix": "say how much"})
            return AIMessage(content=json.dumps({"summary": "A careful proposal.", "strengths": [], "weaknesses": weak, "questions": [], "revision_plan": []}))
        return AIMessage(content="{}")


class Thinkers:
    def __init__(self, severity="critical"):
        self.severity = severity

    def invoke(self, messages, **kw):
        if "You extract structure from reviews" in messages[0].content:
            return AIMessage(content=json.dumps({"verdict": "objecting", "would_change_mind_if": "a falsifier",
                                                 "concerns": [{"claim": "No falsifier for mediation.", "severity": self.severity, "why": "untestable"}]}))
        return AIMessage(content="I object: nothing here could show the mechanism is wrong.")


def _install(monkeypatch, model, thinkers=None):
    import backend.research.llm as rl
    import backend.thinkers.modes as tm
    monkeypatch.setattr(rl, "_llm", lambda role: model)
    if thinkers:
        monkeypatch.setattr(tm, "_llm", lambda role: thinkers)
        monkeypatch.setattr(tm, "_in_background", lambda coro: coro.close())


def _seed(thread, design=True):
    from backend.memory import conversation_store as nb
    from backend.research import store
    nb.write_section(thread, "hypothesis", HYP, "thoth_accepted")
    nb.write_section(thread, "question", "Do night-shift nurses report more exhaustion?", "thoth_accepted")
    nb.write_section(thread, "resources", json.dumps({"time": "3 months", "budget": "none"}), "user")
    if design:
        nb.write_section(thread, "design", json.dumps({"name": "Prospective cohort", "design_type": "cohort_prospective",
                                                       "summary": "Follow nurses for 8 weeks."}), "user")
    tid = store.create_trial(thread, HYP, [{"id": 1, "claim": "Night nurses are more exhausted."}])
    p1 = store.add_paper(tid, {"title": "Exhaustion in ICU nurses by shift", "year": 2021, "authors": ["Ana Lee", "Bo Kim", "C Ray"],
                               "doi": "10.1000/icu.2021"})
    store.update_paper(p1, status="done", access="full_text", weight=0.45, i_say_user="My reading: the ICU gap is real but small.",
                       record_json={"design": {"value": "cross_sectional"}, "sample_size": {"value": "240"},
                                    "results": [{"finding": W1_FINDING, "numbers": "n = 240", "locator": "Table 2", "provenance": "from_full_text"}]})
    p2 = store.add_paper(tid, {"title": "Uncited sleep paper", "year": 2019, "authors": ["Dee Zed"], "abstract": "Sleep was poorer on nights."})
    store.update_paper(p2, status="done", access="abstract_only", weight=0.2, record_json={})
    store.update_trial(tid, status="complete", verdict_json={"overall": {"verdict": "insufficient_evidence", "reason": "few witnesses"}})


def _write(client, thread, approve=True, **extra):
    with client.stream("POST", "/api/proposal/write", json={"project_id": thread, "approve": approve, "outline": OUTLINE, **extra}) as r:
        if r.status_code != 200:
            return r.status_code, []
        return 200, _read_sse(r, max_events=200, max_seconds=30)


def _state(client, thread):
    return client.get(f"/api/proposal?project_id={thread}").json()


def test_writing_needs_explicit_approval_and_the_outline_writes_nothing(client, monkeypatch):
    model = Model()
    _install(monkeypatch, model)
    _seed("p18a")
    out = client.post("/api/proposal/outline", json={"project_id": "p18a"}).json()
    assert [s["key"] for s in out["outline"]][-1] == "references" and len(out["outline"]) == 10
    assert out["outline"][2]["purpose"] == "W1's survey and the trial verdict" and out["estimate"]["sections"] == 9
    assert out["sections"] == {} and [c[0] for c in model.calls] == ["outline"]
    assert _write(client, "p18a", approve=False)[0] == 403
    assert client.post("/api/proposal/sections/methods/regenerate", json={"project_id": "p18a"}).status_code == 403
    assert _state(client, "p18a")["sections"] == {}
    assert client.post("/api/proposal/outline", json={"project_id": "nohyp"}).status_code == 400


def test_writer_sees_only_the_research_file_and_marks_gaps(client, monkeypatch):
    model = Model(sections={"Expected outcomes": OUTCOMES_NO_REFUTE})
    _install(monkeypatch, model)
    _seed("p18b", design=False)
    status, events = _write(client, "p18b")
    assert status == 200 and [e["event"] for e in events].count("section_done") == 3
    human = next(c[2] for c in model.calls if c[0] == "writer")
    assert '"id": "W1"' in human and "Exhaustion in ICU nurses by shift" in human and "the ICU gap is real but small" in human
    assert "Ana Lee" not in human and "10.1000/icu.2021" not in human, "bibliographic detail is not the Writer's to use"
    secs = _state(client, "p18b")["sections"]
    assert "[GAP: this section needs a chosen study design" in secs["methods"]["draft"]
    assert "[GAP: the result that would refute the hypothesis" in secs["expected_outcomes"]["draft"]
    st = _state(client, "p18b")["status"]
    assert st["status"] == "provisional" and any("[GAP]" in g for g in st["gaps"])


def test_verifier_removes_softens_and_flags(client, monkeypatch):
    _install(monkeypatch, Model())
    _seed("p18c")
    _write(client, "p18c")
    lit = _state(client, "p18c")["sections"]["literature"]["verification"]
    final = lit["final_markdown"]
    assert f"{W1_FINDING} [W1]." in final
    assert "Night-shift nurses reported higher emotional exhaustion in a cross-sectional survey [W1]." in final
    assert "cause burnout" not in final and "n = 999" not in final and "opposite pattern" not in final
    removed = {r["sentence"]: r for r in lit["removed"]}
    assert removed["The ICU survey included n = 999 nurses."]["problem"] == "number_mismatch"
    assert "not a witness" in removed["A cohort study found the opposite pattern."]["why"]
    assert "80% of nurses" in final, "an uncited factual sentence is flagged, not silently kept as verified"
    assert "insufficient overall {{file:verdict}}." in final, "file provenance survives, so an edited section can be re-verified"
    uncited = [s["r"] for s in lit["segments"] if s["t"] == "s" and s["r"]["kind"] == "uncited"]
    assert len(uncited) == 1 and lit["summary"]["uncited"] == 1
    assert lit["summary"]["removed"] == 2 and lit["summary"]["softened"] == 1 and lit["summary"]["kept"] == 1


def test_a_fatal_keeps_the_proposal_provisional_after_two_revision_rounds(client, monkeypatch):
    model = Model(reviewer_fatal=True)
    _install(monkeypatch, model)
    _seed("p18d")
    _, events = _write(client, "p18d")
    roles = [c[0] for c in model.calls]
    assert roles.count("reviewer") == 3 and roles.count("revise") == 2, "two revision rounds, then stop"
    assert [e["event"] for e in events].count("section_revising") == 2
    st = _state(client, "p18d")
    assert st["review"]["counts"]["FATAL"] == 1 and st["review"]["loops"] == 2
    assert st["status"]["status"] == "provisional" and any("FATAL" in g for g in st["status"]["gaps"])
    assert st["sections"]["methods"]["revisions"] == 2

    with client.stream("POST", "/api/proposal/review/stream", json={"project_id": "p18d"}) as r:
        names = [e["event"] for e in _read_sse(r, max_events=100, max_seconds=30)]
    assert names.count("review_done") == 3 and names.count("section_revising") == 2 and "status" in names


def test_thinker_critical_concern_blocks_reviewed_until_answered(client, monkeypatch):
    _install(monkeypatch, Model(sections={"Literature review": CLEAN_LIT}), Thinkers("critical"))
    _seed("p18e")
    _write(client, "p18e")
    st = _state(client, "p18e")["status"]
    assert st["gaps"] == ["No thinker has reviewed this proposal."], st["gaps"]
    out = client.post("/api/proposal/thinkers", json={"project_id": "p18e", "thinker_ids": ["popper"]}).json()
    assert out["status"]["status"] == "provisional" and out["status"]["thinkers"]["open"] == 1
    cid = out["concerns"][0]["id"]
    assert client.post(f"/api/proposal/concerns/{cid}/answer", json={"project_id": "p18e", "reply": ""}).status_code == 400
    ans = client.post(f"/api/proposal/concerns/{cid}/answer", json={"project_id": "p18e", "reply": "Mediation is tested by the lagged model; a null path refutes it."}).json()
    assert ans["status"]["status"] == "reviewed" and ans["status"]["gaps"] == []


def test_references_hold_only_witnesses_a_surviving_sentence_cites(client, monkeypatch):
    _install(monkeypatch, Model())
    _seed("p18f")
    _write(client, "p18f")
    refs = _state(client, "p18f")["references"]
    assert refs["cited"] == ["W1"]
    assert "Exhaustion in ICU nurses by shift" in refs["markdown"] and "10.1000/icu.2021" in refs["markdown"]
    assert "Uncited sleep paper" not in refs["markdown"]


def test_export_needs_approval_and_a_provisional_one_is_watermarked(client, monkeypatch):
    _install(monkeypatch, Model())
    _seed("p18g")
    _write(client, "p18g")
    assert client.post("/api/proposal/export", json={"project_id": "p18g"}).status_code == 403
    assert client.post("/api/proposal/export", json={"project_id": "p18g", "approve": True, "format": "pdf"}).status_code == 501
    out = client.post("/api/proposal/export", json={"project_id": "p18g", "approve": True}).json()
    assert out["watermarked"] is True and out["filename"].startswith("PROVISIONAL-")
    assert out["content"].startswith("> **PROVISIONAL") and "(Lee et al., 2021)" in out["content"] and "## References" in out["content"]
    assert "[W1]" not in out["content"] and "{{" not in out["content"], "readers never see witness ids or markers"


def test_user_edits_are_kept_and_no_model_means_nothing_written(client, monkeypatch):
    model = Model()
    _install(monkeypatch, model)
    _seed("p18h")
    _write(client, "p18h")
    mine = "## Methods\n\nMy own methods text. I will use the cohort design."
    sec = client.put("/api/proposal/sections/methods", json={"project_id": "p18h", "markdown": mine}).json()
    assert sec["user_edited"] is True and sec["verification"] is None
    assert any("not checked" in g for g in _state(client, "p18h")["status"]["gaps"])
    assert client.post("/api/proposal/sections/methods/regenerate", json={"project_id": "p18h"}).status_code == 409
    _, events = _write(client, "p18h", only_missing=False)
    assert {"event": "section_kept", "payload": {"key": "methods", "reason": "has your edits"}} in events
    assert _state(client, "p18h")["sections"]["methods"]["draft"] == mine
    again = client.post("/api/proposal/sections/methods/regenerate", json={"project_id": "p18h", "overwrite": True}).json()
    assert again["section"]["user_edited"] is False

    _install(monkeypatch, Model(writer_up=False))
    _seed("p18i")
    _, events = _write(client, "p18i")
    assert [e["event"] for e in events].count("section_failed") == 3
    assert _state(client, "p18i")["sections"] == {}
