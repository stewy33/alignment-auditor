"""Run a Petri experiment defined by a YAML file.

    uv run exp.py experiments/auditor_judge.yaml --dry-run   # plan only, no API calls
    uv run exp.py experiments/auditor_judge.yaml             # run it

The matrix is auditors x targets x judges, but the axes are priced differently:
a conversation must be run for each (auditor, target) pair, while judges only
rescore transcripts that already exist. So N judges cost N scoring passes, not
N full runs.

Everything is resumable. Conversations use Inspect's `eval_set`, which skips
work already completed in its log dir; scoring is skipped when the output file
is already present. Re-running after adding a judge (or after a crash) only
does the missing work.

Layout under logs/<name>/:
    conv/<auditor>__<target>/              conversations (scored by judges[0])
    scored/<auditor>__<target>__<judge>.eval   one file per judge
"""

import argparse
import sys
from datetime import datetime, timedelta
from difflib import get_close_matches
from pathlib import Path

import yaml
from dotenv import load_dotenv
from shortuuid import uuid as shortuuid
from inspect_ai import eval_set, score
from inspect_ai.log import list_eval_logs, read_eval_log, write_eval_log
from inspect_ai.model import ModelConfig
from inspect_petri import audit, audit_judge
from inspect_petri._seeds.dataset import seeds_dataset

load_dotenv(".env")

# Short names so config files stay readable.
ALIASES = {
    "opus5": "anthropic/claude-opus-5",
    "sonnet5": "anthropic/claude-sonnet-5",
    "haiku45": "anthropic/claude-haiku-4-5",
    "sonnet46": "anthropic/claude-sonnet-4-6",
    "opus46": "anthropic/claude-opus-4-6",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
}


def resolve(name: str) -> str:
    """Expand a short alias to a provider/model string."""
    return ALIASES.get(name, name)


class Experiment:
    def __init__(self, config: dict, name: str):
        # Name comes from the filename (YYMMDD_slug) so logs are traceable to
        # the config that produced them and can't drift out of sync with it.
        self.name = name
        self.targets = config["targets"]
        self.auditors = config["auditors"]
        self.judges = config["judges"]
        # Either built-in seed ids, or a directory of custom .md seed files.
        self.seeds_dir = config.get("seeds_dir")
        self.seeds = config.get("seeds", [])
        self.max_turns = config.get("max_turns", 30)
        self.epochs = config.get("epochs", 1)
        self.root = Path("logs") / self.name

    @property
    def seed_selector(self) -> str:
        # A directory of custom .md seed files, or built-in seeds by id.
        # For ids: one string, not a list -- Petri reads a list of strings as
        # *literal* auditor instructions rather than seed IDs.
        if self.seeds_dir:
            return self.seeds_dir
        return "id:" + ",".join(self.seeds)

    def conv_dir(self, auditor: str, target: str) -> Path:
        return self.root / "conv" / f"{auditor}__{target}"

    def scored_path(self, auditor: str, target: str, judge: str) -> Path:
        return self.root / "scored" / f"{auditor}__{target}__{judge}.eval"

    def conversations(self) -> list[tuple[str, str]]:
        return [(a, t) for a in self.auditors for t in self.targets]

    def scorings(self) -> list[tuple[str, str, str]]:
        return [(a, t, j) for a, t in self.conversations() for j in self.judges]


def verify_seeds(exp: Experiment) -> bool:
    """Resolve seeds before spending anything."""
    if exp.seeds_dir:
        found = sorted(p.stem for p in Path(exp.seeds_dir).glob("*.md"))
        for f in found:
            print(f"    ok      {f}  (from {exp.seeds_dir})")
        if not found:
            print(f"\n  ERROR: no .md seed files in {exp.seeds_dir}")
        return bool(found)
    available = {s.id for s in seeds_dataset(None)}
    missing = [s for s in exp.seeds if s not in available]
    for s in exp.seeds:
        print(f"    {'ok     ' if s not in missing else 'MISSING'} {s}")
    for s in missing:
        close = get_close_matches(s, available, n=3, cutoff=0.5)
        hint = f" did you mean: {', '.join(close)}?" if close else ""
        print(f"\n  ERROR: no built-in seed '{s}'.{hint}")
    if missing:
        print(f"  ({len(available)} seeds available; see seeds/README.md for custom ones)")
    return not missing


def plan(exp: Experiment) -> None:
    convs = exp.conversations()
    scorings = exp.scorings()
    todo_c = [c for c in convs if not exp.conv_dir(*c).exists()]
    todo_s = [s for s in scorings if not exp.scored_path(*s).exists()]

    print(f"\nexperiment: {exp.name}")
    n_seeds = len(list(Path(exp.seeds_dir).glob("*.md"))) if exp.seeds_dir else len(exp.seeds)
    print(f"  seeds ({n_seeds}), max_turns={exp.max_turns}, epochs={exp.epochs}:")
    seeds_ok = verify_seeds(exp)

    print(f"\n  conversations: {len(convs)} total, {len(todo_c)} to run")
    for a, t in convs:
        mark = "TODO" if (a, t) in todo_c else "done"
        print(f"    [{mark}] auditor={a:10} target={t}")

    print(f"\n  scorings: {len(scorings)} total, {len(todo_s)} to run")
    for a, t, j in scorings:
        mark = "TODO" if (a, t, j) in todo_s else "done"
        print(f"    [{mark}] {a:10} x {t:15} judged by {j}")

    audits = len(todo_c) * n_seeds * exp.epochs
    print(f"\n  outstanding: {audits} audits ({exp.max_turns} turns max) + {len(todo_s)} scoring passes")
    if not seeds_ok:
        print("\n  >>> fix the seeds before running <<<")


def inline_judge_of(log) -> str | None:
    """Which judge (if any) already scored this conversation log in-run."""
    role = (log.eval.model_roles or {}).get("judge")
    return getattr(role, "model", None) if role else None


def run(exp: Experiment) -> None:
    if not verify_seeds(exp):
        sys.exit("aborting: unresolved seeds")

    # The first judge runs inline, inside eval_set's parallel sample execution,
    # so it costs no extra wall-clock. Remaining judges rescore afterwards. The
    # judge reads only the serialized transcript (see _judge/judge.py: it
    # flattens the target timeline and renders numbered messages), so inline and
    # rescored judging see identical input -- the split is purely about timing.
    first_judge = exp.judges[0]

    for auditor, target in exp.conversations():
        log_dir = exp.conv_dir(auditor, target)
        print(f"\n=== conversations: auditor={auditor} target={target} -> {log_dir}")
        success, _ = eval_set(
            audit(seed_instructions=exp.seed_selector, max_turns=exp.max_turns),
            log_dir=str(log_dir),
            model_roles={
                "auditor": resolve(auditor),
                "target": resolve(target),
                "judge": resolve(first_judge),
            },
            epochs=exp.epochs,
            metadata={"experiment": exp.name, "auditor": auditor, "target": target},
            display="plain",
        )
        if not success:
            print(f"  !! incomplete for {auditor}/{target}; re-run to resume")

    # Every judge ends up as its own scored/ file, so analysis sees one shape.
    # The inline judge is extracted from the conversation log for free; the rest
    # are rescored. A judges[0] changed after a run won't match the log's inline
    # judge, so it correctly falls through to rescoring rather than going stale.
    for auditor, target, judge in exp.scorings():
        judge_index = exp.judges.index(judge)
        out = exp.scored_path(auditor, target, judge)
        if out.exists():
            print(f"  skip (exists): {out.name}")
            continue
        logs = list_eval_logs(str(exp.conv_dir(auditor, target)))
        if not logs:
            print(f"  !! no conversation log for {auditor}/{target}; skipping judge {judge}")
            continue

        conv = read_eval_log(logs[0].name)
        if inline_judge_of(conv) == resolve(judge) and conv.results:
            print(f"\n=== extracting inline scores: {auditor}/{target} judge={judge}")
            scored = conv
        else:
            print(f"\n=== scoring {auditor}/{target} with judge={judge}")
            scored = score(
                conv,
                audit_judge(model=resolve(judge)),
                action="overwrite",
                display="plain",
            )
        # score() copies the source log wholesale, identity included, so every
        # judge's file for a cell would share an eval_id, task_id and created
        # stamp. The viewer treats those as the same run and collapses them,
        # showing one judge per cell. Give each scored log its own identity, and
        # a display name so the viewer's list is readable without filenames.
        scored.eval.eval_id = shortuuid()
        scored.eval.run_id = shortuuid()
        scored.eval.task_id = shortuuid()
        scored.eval.task_display_name = f"{auditor} x {target} | judge={judge}"
        scored.eval.created = (
            datetime.fromisoformat(scored.eval.created) + timedelta(seconds=judge_index)
        ).isoformat()
        # A rescored log inherits model_roles from the conversation, so its
        # "judge" entry would still name the *inline* judge -- actively wrong
        # for every judge after the first. Point it at the judge that produced
        # these scores.
        scored.eval.model_roles = (scored.eval.model_roles or {}) | {
            "judge": ModelConfig(model=resolve(judge))
        }
        # Record the cell in the log itself; the filename alone loses provenance
        # if the file is ever moved or renamed.
        scored.eval.metadata = (scored.eval.metadata or {}) | {
            "experiment": exp.name,
            "auditor": auditor,
            "target": target,
            "judge": judge,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        write_eval_log(scored, str(out))
        print(f"  wrote {out}")

    print(f"\ndone. results: uv run inspect view --log-dir {exp.root}/scored")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("config", type=Path, help="path to experiment YAML")
    p.add_argument("--dry-run", action="store_true", help="print the plan, spend nothing")
    args = p.parse_args()

    exp = Experiment(yaml.safe_load(args.config.read_text()), name=args.config.stem)
    if args.dry_run:
        plan(exp)
    else:
        plan(exp)
        run(exp)


if __name__ == "__main__":
    main()
