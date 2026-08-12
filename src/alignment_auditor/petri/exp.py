"""Run a Petri experiment defined by a YAML file.

    uv run exp experiments/auditor_judge.yaml --dry-run   # plan only, no API calls
    uv run exp experiments/auditor_judge.yaml             # run it

Paths in the config (and the logs/ output dir) are resolved relative to the
current directory, so run this from the repo root.

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
from inspect_ai.model import GenerateConfig, Model, ModelConfig, get_model
from inspect_petri import audit, audit_judge
from inspect_petri._seeds.dataset import seeds_dataset

# Search upward from the cwd, so `exp` works from anywhere under the repo.
load_dotenv()

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


ROLES = ("auditor", "target", "judge")


def resolve(name: str) -> str:
    """Expand a short alias to a provider/model string."""
    return ALIASES.get(name, name)


# Custom seeds ship with the package, so a config names a set ("trial_suppression")
# rather than carrying a path into src/. An actual path still works, for a seed
# directory kept outside the repo.
SEEDS_DIR = Path(__file__).parent / "seeds"


def resolve_seeds_dir(value: str) -> Path:
    packaged = SEEDS_DIR / value
    return packaged if packaged.is_dir() else Path(value)


def reasoning_config(model: str, settings: dict[str, str]) -> GenerateConfig:
    """Build a GenerateConfig, dropping settings the model's provider does not implement.

    `mode` (standard | pro) is OpenAI GPT-5.6+ only; the Anthropic provider never reads it, so
    passing it through would be harmless at request time. It is filtered anyway because these
    settings are also written into the log's `model_roles` as the record of what ran, and a log
    claiming an Anthropic model used `mode=standard` is a false provenance record -- in exactly
    the field the analysis scripts read to recover a run's configuration.

    This matters because a role can hold models from more than one provider: in the gradient
    experiment's arm B the judges are `gpt-5.6-sol` (inline) and `opus5` (rescore), and reasoning
    is configured per role rather than per model.
    """
    is_openai = model.startswith("openai/")
    return GenerateConfig(
        reasoning_effort=settings.get("effort"),
        reasoning_mode=settings.get("mode") if is_openai else None,
    )


def role_model(name: str, role: str, reasoning: dict[str, dict[str, str]]) -> str | Model:
    """Resolve a role's model, attaching reasoning settings if the experiment sets them.

    Left unset, each provider applies its own default, and those differ: Claude 4.7+ (Sonnet 5,
    Opus 5) run adaptive thinking server-side whether or not we ask, while the OpenAI provider
    sends no `reasoning` block at all unless asked. So "no config" is not a neutral baseline --
    it silently gives Anthropic models a larger reasoning budget than OpenAI ones, and any
    cross-family comparison inherits that. Verified from logged request/response pairs:

        anthropic/claude-opus-5    adaptive thinking on, API default effort (documented `high`)
        anthropic/claude-sonnet-5  same
        openai/gpt-5.6-*           effort=medium, mode=standard  (server-echoed)
        openai/gpt-4o              no reasoning (not a reasoning model)

    Set them explicitly rather than relying on those defaults: the levels are then recorded in
    the config instead of inferred, and a provider changing its default cannot silently change
    the experiment.

    `effort` is provider-neutral (Anthropic maps it to adaptive thinking plus
    `output_config.effort`, OpenAI to `reasoning.effort`), but the LABELS ARE NOT CALIBRATED --
    Anthropic `high` and OpenAI `high` are internal names, not equal compute. Setting both to
    the same string equalises the setting, not the reasoning.

    `mode` (standard | pro) is OpenAI GPT-5.6+ only and is ignored elsewhere; `pro` does more
    model work per turn.

    eval_set types model_roles as `dict[str, str | Model]`, so a ModelConfig cannot be passed
    directly -- get_model() returns a Model carrying the config, which can.
    """
    resolved = resolve(name)
    settings = reasoning.get(role) or {}
    if not settings:
        return resolved
    return get_model(resolved, config=reasoning_config(resolved, settings))


class Experiment:
    def __init__(self, config: dict, name: str):
        # Name comes from the filename (YYMMDD_slug) so logs are traceable to
        # the config that produced them and can't drift out of sync with it.
        self.name = name
        self.targets = config["targets"]
        self.auditors = config["auditors"]
        self.judges = config["judges"]
        # Either built-in seed ids, or a directory of custom .md seed files.
        seeds_dir = config.get("seeds_dir")
        self.seeds_dir = resolve_seeds_dir(seeds_dir) if seeds_dir else None
        self.seeds = config.get("seeds", [])
        self.max_turns = config.get("max_turns", 30)
        self.epochs = config.get("epochs", 1)
        # Per-role reasoning settings, e.g. {target: {effort: medium, mode: standard}}.
        # See role_model() for what each key means and why leaving them unset is not neutral.
        self.reasoning: dict[str, dict[str, str]] = config.get("reasoning") or {}
        unknown = set(self.reasoning) - set(ROLES)
        if unknown:
            sys.exit(f"unknown reasoning role(s): {sorted(unknown)}; expected {ROLES}")
        for role, settings in self.reasoning.items():
            if not isinstance(settings, dict):
                sys.exit(f"reasoning.{role} must be a mapping, e.g. {{effort: high}}")
            bad = set(settings) - {"effort", "mode"}
            if bad:
                sys.exit(f"unknown reasoning.{role} key(s): {sorted(bad)}; expected effort, mode")
        self.root = Path("logs") / self.name

    @property
    def seed_selector(self) -> str:
        # A directory of custom .md seed files, or built-in seeds by id.
        # For ids: one string, not a list -- Petri reads a list of strings as
        # *literal* auditor instructions rather than seed IDs.
        if self.seeds_dir:
            return str(self.seeds_dir)
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
        # Bundled sets print as their name; an external directory prints in full.
        bundled = SEEDS_DIR in exp.seeds_dir.parents
        where = exp.seeds_dir.name if bundled else exp.seeds_dir
        found = sorted(p.stem for p in exp.seeds_dir.glob("*.md"))
        for f in found:
            print(f"    ok      {f}  (from {where})")
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
        print(f"  ({len(available)} seeds available; see petri/seeds/README.md for custom ones)")
    return not missing


def plan(exp: Experiment) -> None:
    convs = exp.conversations()
    scorings = exp.scorings()
    todo_c = [c for c in convs if not exp.conv_dir(*c).exists()]
    todo_s = [s for s in scorings if not exp.scored_path(*s).exists()]

    print(f"\nexperiment: {exp.name}")
    n_seeds = len(list(exp.seeds_dir.glob("*.md"))) if exp.seeds_dir else len(exp.seeds)
    print(f"  seeds ({n_seeds}), max_turns={exp.max_turns}, epochs={exp.epochs}:")
    # Print every role, not just the configured ones: "provider default" is the load-bearing
    # case, and it means different things for Anthropic and OpenAI (see role_model()).
    # Resolve every role through the same code path `run` uses. This is the only part of the
    # plan that touches role_model(), and it is here on purpose: without it a dry run cannot
    # catch a bad reasoning block or a broken role resolution, and the failure surfaces only
    # after `run` has been invoked for real.
    print("  reasoning:")
    for r in ROLES:
        s = exp.reasoning.get(r) or {}
        names = {"auditor": exp.auditors, "target": exp.targets, "judge": exp.judges}[r]
        for name in names:
            resolved = resolve(name)
            # Report the config as it will actually be sent, not as the YAML requests it:
            # reasoning_config drops provider-inapplicable keys, so a role-level `mode` set for
            # an OpenAI model is not applied to an Anthropic one in the same role.
            role_model(name, r, exp.reasoning)  # exercise the run() path; surfaces errors here
            if not s:
                desc = "PROVIDER DEFAULT"
            else:
                cfg = reasoning_config(resolved, s)
                applied = {"effort": cfg.reasoning_effort, "mode": cfg.reasoning_mode}
                desc = ", ".join(f"{k}={v}" for k, v in applied.items() if v is not None)
                dropped = sorted(set(s) - {k for k, v in applied.items() if v is not None})
                if dropped:
                    desc += f"   ({', '.join(dropped)} n/a for this provider)"
            print(f"    {r:<8} {resolved:<28} {desc}")
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
                "auditor": role_model(auditor, "auditor", exp.reasoning),
                "target": role_model(target, "target", exp.reasoning),
                "judge": role_model(first_judge, "judge", exp.reasoning),
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
                audit_judge(model=role_model(judge, "judge", exp.reasoning)),
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
            "judge": ModelConfig(
                model=resolve(judge),
                config=reasoning_config(resolve(judge), exp.reasoning.get("judge") or {}),
            )
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
