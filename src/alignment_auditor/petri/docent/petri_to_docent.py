"""Convert Petri audit .eval logs into Docent AgentRuns with a TranscriptGroup per sample.

REPO CONVENTION (see .claude/skills/petri-to-docent): every Petri audit becomes ONE AgentRun
whose single TranscriptGroup holds one transcript per PARTICIPANT:

    auditor   -- the model that role-played the environment
    target    -- the agent under test (its full agentic conversation)
    judge:<label> -- one transcript per judge that scored the audit (custom, validity, and any
                     extra behaviour block such as reachout_broad)

A Petri "cell" (one seeds_dir run) is scored by several judges, each writing its own
scored/*.eval; those files re-score the SAME audit, so auditor+target are read once from the
behaviour file and each judge's single model call is pulled from its own file and joined by
(sample_id, epoch). Judge verdicts (level/signature/scenario_valid + headline/rationale) and the
validity sub-fields are flattened onto AgentRun.metadata for filtering.

Key gotchas baked in here (learned the hard way):
  * All judge blocks share the inspect scorer name `seed_custom_judge`; the block identity is in
    the FILENAME, not the scorer name.
  * ModelEvents carry `.role` ('auditor'/'target'); the judge call has role None + the judge model.
  * Attachments must be resolved (`resolve_sample_attachments`) or reasoning shows as
    'attachment://...'.
  * scoring_metadata holds inspect Score OBJECTS whose .value is NaN on judge parse-failure ->
    drop it (a plain recursive float-clean does not reach into objects) or the upload 400s.
  * Docent collection reads are eventually-consistent; poll counts after add_agent_runs.

Usage:
    from alignment_auditor.petri.docent.petri_to_docent import build_agent_runs, upload
    runs = build_agent_runs(cell_dir="logs/<run>/scored", behaviour_file="...__custom_opus48.eval",
                            extra_meta={"step": "2"})
    upload(runs, collection_name="...", description="...")   # prints URL, verifies count
"""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from inspect_ai.log import read_eval_log, resolve_sample_attachments
from docent.data_models.agent_run import AgentRun
from docent.data_models.transcript import Transcript, TranscriptGroup
from docent.data_models.chat import parse_chat_message


def _clean(obj: Any) -> Any:
    """Recursively replace non-finite floats (NaN/Inf) with None -- invalid JSON."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _msgs(inspect_messages) -> list:
    return [parse_chat_message(m.model_dump()) for m in inspect_messages]


def _judge_label(filename: str) -> str:
    """`glm52__glm52__validity_opus48.eval` -> `validity`; `...__custom_opus48` -> `custom`."""
    stem = Path(filename).stem
    tail = stem.split("__")[-1]              # e.g. validity_opus48
    return tail.rsplit("_", 1)[0] if "_" in tail else tail


def _last_role_event(events, role: str):
    evs = [e for e in events if type(e).__name__ == "ModelEvent" and getattr(e, "role", None) == role]
    return evs[-1] if evs else None


def _judge_event(events):
    """The judge model call: a ModelEvent with role None (scored separately from auditor/target)."""
    evs = [e for e in events if type(e).__name__ == "ModelEvent" and getattr(e, "role", None) is None]
    return evs[-1] if evs else None


def _event_transcript(event, name: str, group_id: str) -> Transcript | None:
    """Build a Transcript from a ModelEvent's input history plus its output message."""
    if event is None:
        return None
    msgs = list(event.input)
    out = event.output
    om = out.message if hasattr(out, "message") and out.message is not None else (
        out.choices[0].message if getattr(out, "choices", None) else None)
    if om is not None:
        msgs = msgs + [om]
    return Transcript(name=name, transcript_group_id=group_id, messages=_msgs(msgs), metadata={})


# validity sub-fields differ by step; we surface whatever the judge emitted.
_VALIDITY_BOOLS = ["scenario_valid", "honest_path_available", "peers_undirected", "unsanctioned"]
_VALIDITY_INTS = ["pushiness", "realism", "persona_pressure"]


def build_agent_runs(cell_dir: str, behaviour_file: str, judge_files: dict[str, str] | None = None,
                     extra_meta: dict[str, Any] | None = None) -> list[AgentRun]:
    """One AgentRun per audit in `behaviour_file`, TranscriptGroup = auditor/target/judge:*.

    cell_dir       directory holding the scored .eval files
    behaviour_file the behaviour judge's .eval (carries auditor+target events; its judge = the
                   primary rung ladder). Its label becomes judge:<label> and drives rung_level.
    judge_files    optional {label: filename} of OTHER judges to add as transcripts + metadata
                   (validity is detected automatically by 'validity' in its label).
    extra_meta     merged onto every run's metadata (e.g. {"step": "2"}).
    """
    root = Path(cell_dir)
    beh_label = _judge_label(behaviour_file)
    judge_files = dict(judge_files or {})

    # Pre-read every judge file's per-epoch judge event + verdict metadata.
    def read_judge(path: Path):
        log = read_eval_log(str(path))
        ev, md = {}, {}
        for s in log.samples or []:
            s = resolve_sample_attachments(s)
            ev[s.epoch] = _judge_event(s.events)
            for sc in (s.scores or {}).values():
                if isinstance(getattr(sc, "metadata", None), dict):
                    md[s.epoch] = sc.metadata
        return ev, md

    beh_events, beh_md = read_judge(root / behaviour_file)
    others = {lab: read_judge(root / fn) for lab, fn in judge_files.items()}

    log = read_eval_log(str(root / behaviour_file))
    runs: list[AgentRun] = []
    for s in log.samples or []:
        s = resolve_sample_attachments(s)
        ep = s.epoch
        grp = TranscriptGroup(name="audit")
        transcripts = [
            Transcript(name="target", transcript_group_id=grp.id, messages=_msgs(s.messages), metadata={}),
        ]
        aud = _event_transcript(_last_role_event(s.events, "auditor"), "auditor", grp.id)
        if aud:
            transcripts.append(aud)
        # behaviour judge transcript
        jb = _event_transcript(beh_events.get(ep), f"judge:{beh_label}", grp.id)
        if jb:
            transcripts.append(jb)
        # other judge transcripts
        for lab, (ev, _md) in others.items():
            jt = _event_transcript(ev.get(ep), f"judge:{lab}", grp.id)
            if jt:
                transcripts.append(jt)

        # ---- flat metadata ----
        b = beh_md.get(ep, {})
        m: dict[str, Any] = {"sample_id": str(s.id), "epoch_id": ep}
        m.update(extra_meta or {})
        m["tags"] = (s.metadata or {}).get("tags")
        m["rung_level"] = int(b.get("level", -1))
        m["signature"] = bool(b.get("signature", False))
        m["behavior_headline"] = b.get("headline")
        m["behavior_rationale"] = b.get("rationale")
        val_md = {}
        for lab, (_ev, md) in others.items():
            v = md.get(ep, {})
            if "validity" in lab:
                val_md = v
                for k in _VALIDITY_BOOLS:
                    if k in v:
                        m[k] = bool(v[k])
                for k in _VALIDITY_INTS:
                    if k in v:
                        m[k] = int(v[k])
                m["validity_headline"] = v.get("headline")
                m["validity_rationale"] = v.get("rationale")
            else:  # another behaviour variant (e.g. reachout_broad)
                if "level" in v:
                    m[f"{lab}_level"] = int(v["level"])
                if "signature" in v:
                    m[f"{lab}_signature"] = bool(v["signature"])
                m[f"{lab}_headline"] = v.get("headline")
        m["signature_and_valid"] = m["signature"] and bool(val_md.get("scenario_valid", False))

        runs.append(AgentRun(transcripts=transcripts, transcript_groups=[grp], metadata=_clean(m)))
    return runs


def upload(runs: list[AgentRun], collection_name: str, description: str = "") -> str:
    from docent import Docent
    c = Docent()
    cid = c.create_collection(name=collection_name, description=description)
    res = c.add_agent_runs(cid, runs)
    for _ in range(10):
        time.sleep(6)
        if len(c.list_agent_run_ids(cid)) >= len(runs):
            break
    url = f"https://docent.transluce.org/dashboard/{cid}"
    print(f"{collection_name}: add={res.get('status')} runs={len(runs)} -> {url}")
    return cid
