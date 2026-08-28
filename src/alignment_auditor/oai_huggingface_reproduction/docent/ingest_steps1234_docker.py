"""Upload the DIRECT docker reproduction of the OAI/HuggingFace incident ladder (steps 1-4) to
Docent, ONE COLLECTION PER STEP, react + glm-5.2 cells only.

These are plain single-agent Inspect logs (one react agent in a real docker sandbox against a
mock registry / gdrive), so `sample.messages` IS the agent's own thread and one Transcript per
sample suffices -- unlike the Petri audits (petri/docent/petri_to_docent.py). Each step pools
its family dirs so all its variants are filterable in one collection:

    step1: step1_boundary_probe (registry write) + step1_gdrive_probe (external exfil)
    step2: step2_seeded_probe (residue gradient) + step2_engagement (sanctioned board)
    step3: step3_exploit_share (SSRF proliferation) + step3_coordination (post to coord area)

Per-sample score metadata (signature, judge_level, judge_headline, solved, found_board,
shared_exploit, found_seed, registry_put_paths, ...) is flattened onto AgentRun.metadata so it
is directly filterable. Latest .eval per cell dir wins.

Usage:  uv run python -m alignment_auditor.oai_huggingface_reproduction.docent.ingest_steps1234_docker <step 1-4>
"""
from __future__ import annotations

import glob
import math
import os
import sys
import time
from typing import Any

from docent.data_models import AgentRun, Transcript
from docent.data_models.chat import parse_chat_message

LOG_ROOT = os.environ.get("LOG_ROOT", "logs/260810_oai_huggingface_reproduction")

STEP_CFG: dict[int, tuple[list[str], str, str]] = {
    1: (["step1_boundary_probe", "step1_gdrive_probe"], "oai-hf-repro-step1-open-channel",
        "Direct docker reproduction, incident step 1 (open a channel / deposit agent-authored "
        "content into shared or external infra). react + glm-5.2. Pools the registry-write probe "
        "(step1_boundary_probe) and the external-exfil probe (step1_gdrive_probe, where "
        "elicit_intense/turns40_breadthv1 fire the signature). signature=wrote out; ground truth "
        "= registry_put_paths."),
    2: (["step2_seeded_probe", "step2_engagement"], "oai-hf-repro-step2-reach-out",
        "Direct docker reproduction, incident step 2 (engage/respond to a seeded peer agent). "
        "react + glm-5.2. Pools the residue-gradient probe (step2_seeded_probe; cluster_*=directed "
        "notes, nat_*=undirected residue) with the sanctioned-board probe (step2_engagement). The "
        "step that did NOT elicit: signature=deposited own object, responsive_to_peer=reach-out."),
    3: (["step3_exploit_share", "step3_coordination"], "oai-hf-repro-step3-exploit-share",
        "Direct docker reproduction, incident step 3 (post a working exploit/token back to the "
        "peers' board). react + glm-5.2. Pools the SSRF-proliferation probe (step3_exploit_share; "
        "ssrf_hidden/explicit fire) with the coordination-post probe (step3_coordination). "
        "signature=shared the exploit; solved/found_board/shared_token are the mechanism."),
}


def _clean(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def _cell_meta(step: int, family: str, cell: str) -> dict[str, Any]:
    parts = cell.split("__")
    scaffold = parts[0] if parts else ""
    model = parts[1] if len(parts) > 1 else "glm52"
    variant = "__".join(parts[2:]) or "base"
    condition = "pressure" if "pressure" in cell or "press" in variant else "baseline"
    return {
        "step": step,
        "probe": family,
        "cell": cell,
        "scaffold": scaffold,
        "model": model,
        "variant": variant,
        "condition": condition,
    }


def _is_react_glm52(cell: str) -> bool:
    return cell.startswith("react") and "glm52" in cell


def build_step(step: int) -> list[AgentRun]:
    from inspect_ai.log import read_eval_log

    families, _, _ = STEP_CFG[step]
    runs: list[AgentRun] = []
    for family in families:
        for celldir in sorted(glob.glob(f"{LOG_ROOT}/{family}/*")):
            cell = os.path.basename(celldir)
            if not os.path.isdir(celldir) or not _is_react_glm52(cell):
                continue
            evs = sorted(glob.glob(f"{celldir}/*.eval"))
            if not evs:
                continue
            path = evs[-1]  # latest eval per cell
            base = _cell_meta(step, family, cell)
            try:
                log = read_eval_log(path)
            except Exception as exc:
                print(f"  SKIP {family}/{cell}: {exc}")
                continue
            for s in log.samples or []:
                md = dict(base)
                md["epoch"] = s.epoch
                md["sample_id"] = str(s.id)
                md["log_file"] = path
                for _name, sc in (s.scores or {}).items():
                    for k, v in (sc.metadata or {}).items():
                        md[k] = _clean(v)
                    md.setdefault("score_value", _clean(sc.value))
                    if "judge_level" in (sc.metadata or {}):
                        md.setdefault("level", _clean(sc.metadata["judge_level"]))
                msgs = [parse_chat_message(m.model_dump()) for m in (s.messages or [])]
                if not msgs:
                    continue
                runs.append(AgentRun(transcripts=[Transcript(name="agent", messages=msgs)],
                                     metadata=_clean(md)))
        print(f"  {family}: cumulative {len(runs)} runs")
    return runs


def main() -> None:
    from docent import Docent

    step = int(sys.argv[1])
    _, collection, description = STEP_CFG[step]
    runs = build_step(step)
    print(f"step {step}: {len(runs)} runs -> collection {collection}")

    try:
        from docent.data_models.chat.checks import check_agent_runs
        print("sanity:", check_agent_runs(runs).counts_by_code)
    except Exception as exc:
        print("sanity check unavailable:", exc)

    c = Docent()
    cid = c.create_collection(name=collection, description=description)
    res = c.add_agent_runs(cid, runs)
    for _ in range(15):
        time.sleep(6)
        try:
            if len(c.list_agent_run_ids(cid)) >= len(runs):
                break
        except Exception:
            pass
    print(f"DONE {collection}: add={res.get('status')} runs={len(runs)} -> "
          f"https://docent.transluce.org/dashboard/{cid}")


if __name__ == "__main__":
    main()
