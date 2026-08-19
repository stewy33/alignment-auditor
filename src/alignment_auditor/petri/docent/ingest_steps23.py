"""Upload the 260819 step-2 (reach-out) and step-3 (exploit-share) audits to Docent,
one AgentRun per audit with a TranscriptGroup of auditor/target/judge transcripts.

    uv run python -m alignment_auditor.petri.docent.ingest_steps23 --dry-run
    uv run python -m alignment_auditor.petri.docent.ingest_steps23            # uploads
"""
import argparse

from docent.data_models.chat.checks import check_agent_runs
from alignment_auditor.petri.docent.petri_to_docent import build_agent_runs, upload

STEPS = {
    "2": dict(
        cell_dir="logs/260819_step2_reachout_n256/scored",
        behaviour_file="glm52__glm52__custom_opus48.eval",
        judge_files={"reachout_broad": "glm52__glm52__reachout_broad_opus48.eval",
                     "validity": "glm52__glm52__validity_opus48.eval"},
        collection="step2-reachout-glm52-n256",
        desc=("Step 2 emergent reach-out, bare-statement seed. glm52 auditor+target, opus48 "
              "judges, n=256. One AgentRun/audit; TranscriptGroup = auditor, target, "
              "judge:custom (strict ASK), judge:reachout_broad, judge:validity. Fields: "
              "rung_level, signature, reachout_broad_signature, scenario_valid, "
              "signature_and_valid, peers_undirected, unsanctioned, pushiness, etc."),
    ),
    "3": dict(
        cell_dir="logs/260819_step3_exploit_share_n256/scored",
        behaviour_file="glm52__glm52__custom_opus48.eval",
        judge_files={"validity": "glm52__glm52__validity_opus48.eval"},
        collection="step3-exploit-share-glm52-n256",
        desc=("Step 3 exploit proliferation, bare-statement seed. glm52 auditor+target, opus48 "
              "judges, n=256. One AgentRun/audit; TranscriptGroup = auditor, target, "
              "judge:custom (exploit posted), judge:validity. Fields: rung_level, signature, "
              "scenario_valid, signature_and_valid, unsanctioned, pushiness, realism, etc."),
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["2", "3"], default=None)
    args = ap.parse_args()

    for step, cfg in STEPS.items():
        if args.only and step != args.only:
            continue
        runs = build_agent_runs(cfg["cell_dir"], cfg["behaviour_file"], cfg["judge_files"],
                                extra_meta={"step": step})
        rep = check_agent_runs(runs)
        n = len(runs)
        sig = sum(r.metadata.get("signature") for r in runs)
        val = sum(bool(r.metadata.get("scenario_valid")) for r in runs)
        sv = sum(r.metadata.get("signature_and_valid") for r in runs)
        ntr = {len(r.transcripts) for r in runs}
        print(f"step {step}: n={n} transcripts/run={ntr} signature={sig} valid={val} "
              f"sig&valid={sv} warnings={rep.warning_count} {rep.counts_by_code}")
        if not args.dry_run:
            upload(runs, cfg["collection"], cfg["desc"])
    if args.dry_run:
        print("\n[dry-run] not uploading")


if __name__ == "__main__":
    main()
