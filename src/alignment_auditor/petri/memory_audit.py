"""Generational memory-augmented auditing loop (the "Poor Man's RL" runner).

A memory run is a sequence of generations for one cell (auditor x target x base seed). Each
generation injects the current playbook into the auditor's scenario, runs a wave of K audits
scored inline (behaviour rung + validity in one merged judge), and hands the wave's verdicts to
the Reviewer, which rewrites the playbook for the next generation. The point is to raise the
per-audit valid-elicitation rate ACROSS a run, so the auditor lands the behaviour for fewer
dollars than the iid baseline.

This reuses exp.py's primitives (alias resolution, role_model, the merged inline gating judge,
the audit task shape) rather than duplicating them. It is turned on by a `memory:` block in an
experiment YAML; without that block, exp.py's normal iid path runs, unchanged.

On-disk layout under logs/<name>/:
    rep_<r>/gen_<g>/            eval_set log dir for the wave (K inline-scored audits)
    rep_<r>/gen_<g>/reviewer_usage.json   the review-after-gen-g's token usage (priced later)
    rep_<r>/gen_<g>/seed/<seed>.md        the composed per-generation seed
    rep_<r>/memory/gen_<g>.md / .json     the playbook snapshot produced after gen g

Resumability: eval_set resumes a partial wave natively; the loop restarts at the first
generation whose playbook snapshot is missing, replaying nothing already completed.
"""

import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from inspect_ai import eval_set
from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai.model import get_model

from .exp import Experiment, resolve, role_model
from .playbook import Entry, Playbook, Verdict, compose_seed, render_playbook
from . import reviewer


@dataclass
class MemoryConfig:
    """The `memory:` block of an experiment YAML."""

    wave_size: int = 4
    generations: int = 4
    replicates: int = 1
    reviewer_model: str = "gpt-5.6-luna"
    reviewer_effort: str = "max"
    # Stop a replicate the moment a generation lands a valid hit. The objective is cost to the
    # FIRST valid elicitation, so audits after the first hit do not change the measured number and
    # there is nothing to exploit under P>=1 -- running on would only burn budget. `generations`
    # is the cap: a replicate that never hits runs to it and is right-censored. Turn off for a
    # diagnostic run that wants the full per-generation hit-rate trajectory.
    stop_at_first_hit: bool = True


def parse_memory_config(cfg) -> MemoryConfig | None:
    """Build a MemoryConfig from a config's `memory:` mapping, or None if absent."""
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        sys.exit("`memory:` must be a mapping (wave_size, generations, replicates, ...)")
    known = set(MemoryConfig.__dataclass_fields__)
    unknown = set(cfg) - known
    if unknown:
        sys.exit(f"unknown memory key(s): {sorted(unknown)}; expected {sorted(known)}")
    mem = MemoryConfig(**cfg)
    if not isinstance(mem.stop_at_first_hit, bool):
        sys.exit("memory.stop_at_first_hit must be true or false")
    for name, value in (("wave_size", mem.wave_size), ("generations", mem.generations), ("replicates", mem.replicates)):
        if not isinstance(value, int) or value < 1:
            sys.exit(f"memory.{name} must be a positive integer")
    return mem


# --- playbook persistence -------------------------------------------------------------------

def _playbook_to_dict(pb: Playbook) -> dict:
    return {
        "generation": pb.generation,
        "near_misses": [asdict(e) for e in pb.near_misses],
        "dead_ends": [asdict(e) for e in pb.dead_ends],
        "wins": [asdict(e) for e in pb.wins],
    }


def _playbook_from_dict(d: dict) -> Playbook:
    def entries(key):
        return [Entry(**e) for e in d.get(key, [])]

    return Playbook(
        near_misses=entries("near_misses"),
        dead_ends=entries("dead_ends"),
        wins=entries("wins"),
        generation=d.get("generation", 0),
    )


def _write_snapshot(memory_dir: Path, gen: int, pb: Playbook) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / f"gen_{gen}.json").write_text(json.dumps(_playbook_to_dict(pb), indent=2))
    md = render_playbook(pb) or "(empty playbook)"
    (memory_dir / f"gen_{gen}.md").write_text(md + "\n")


def _mark_done(memory_dir: Path, final_gen: int, reason: str) -> None:
    """Record that a replicate finished, and why -- so resume skips it. A replicate can finish
    before the generation cap (it hit), which a snapshot alone cannot express."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "done.json").write_text(json.dumps({"final_gen": final_gen, "reason": reason}))


def _resume_point(memory_dir: Path, generations: int) -> tuple[int, Playbook, bool]:
    """(start_gen, playbook, done) from the highest existing snapshot.

    Snapshot gen_g is the playbook to inject at generation g+1, so a present gen_g means gens
    0..g are done. `done` is True when a done marker is present (the replicate hit and stopped,
    or ran to the cap) -- resume then skips it regardless of start_gen.
    """
    if not memory_dir.is_dir():
        return 0, Playbook.empty(), False
    done = (memory_dir / "done.json").exists()
    have = sorted(
        int(p.stem.removeprefix("gen_"))
        for p in memory_dir.glob("gen_*.json")
    )
    if not have:
        return 0, Playbook.empty(), done
    last = have[-1]
    pb = _playbook_from_dict(json.loads((memory_dir / f"gen_{last}.json").read_text()))
    return last + 1, pb, done


def _replicate_indices(replicates: int, only_rep: int | None) -> list[int]:
    """Which replicate indices this process runs. `only_rep` selects a single one so replicates
    can run as independent parallel processes (each owns its own rep_<r>/ subtree)."""
    if only_rep is None:
        return list(range(replicates))
    if not isinstance(only_rep, int) or only_rep < 0 or only_rep >= replicates:
        sys.exit(f"--only-rep must be in [0, {replicates}); got {only_rep}")
    return [only_rep]


def _should_stop(n_valid_hits: int, gen: int, generations: int, stop_at_first_hit: bool) -> tuple[bool, str | None]:
    """Whether this replicate ends after generation `gen`, and why.

    Stops on the first valid hit (when enabled) -- there is nothing left to measure or exploit --
    and always stops at the generation cap. Returns (stop, reason) where reason is "hit"/"cap".
    """
    if stop_at_first_hit and n_valid_hits > 0:
        return True, "hit"
    if gen == generations - 1:
        return True, "cap"
    return False, None


# --- verdict extraction ---------------------------------------------------------------------

def extract_verdicts(log_dir: Path) -> list[Verdict]:
    """Read a wave's inline merged-judge scores into Verdicts for the Reviewer.

    Each audit's inline score is the merged gating judge's value dict (level, signature,
    scenario_valid, ...); its explanation carries the behaviour + validity rationales.
    """
    verdicts: list[Verdict] = []
    for info in sorted(list_eval_logs(str(log_dir)), key=lambda i: i.name):
        log = read_eval_log(info.name)
        for s in log.samples or []:
            value, explanation = _merged_score(s.scores)
            if not isinstance(value, dict) or "level" not in value:
                continue  # unscored audit (judge returned no parseable verdict) -- skip it
            verdicts.append(
                Verdict(
                    level=int(value.get("level", 0)),
                    signature=float(value.get("signature", 0)) >= 1,
                    scenario_valid=float(value.get("scenario_valid", 0)) >= 1,
                    headline=str((value.get("headline") or "")),
                    rationale=str(explanation or "")[:600],
                )
            )
    return verdicts


def _merged_score(scores):
    for sc in (scores or {}).values():
        return getattr(sc, "value", None), getattr(sc, "explanation", None)
    return None, None


# --- the loop -------------------------------------------------------------------------------

def run_memory(exp: Experiment, mem: MemoryConfig, only_rep: int | None = None) -> None:
    base_seed_path = _base_seed(exp)
    base_text = base_seed_path.read_text()
    seed_stem = base_seed_path.name

    # A real Model (not a bare string): the Reviewer calls .generate() on it. Effort is applied
    # per call inside reviewer.update, so no reasoning config is baked in here.
    reviewer_id = resolve(mem.reviewer_model)
    reviewer_model = get_model(reviewer_id)

    for auditor, target in exp.conversations():
        for rep in _replicate_indices(mem.replicates, only_rep):
            cell = exp.root / f"rep_{rep}"
            memory_dir = cell / "memory"
            start_gen, playbook, done = _resume_point(memory_dir, mem.generations)
            if done or start_gen >= mem.generations:
                print(f"  [rep {rep}] already complete; skipping")
                continue

            for g in range(start_gen, mem.generations):
                gen_dir = cell / f"gen_{g}"
                seed_dir = gen_dir / "seed"
                seed_dir.mkdir(parents=True, exist_ok=True)
                (seed_dir / seed_stem).write_text(compose_seed(base_text, playbook))

                task = exp.build_audit_task(str(seed_dir))
                task.scorer = exp.merged_gating_scorer()

                window = exp.max_parallel or mem.wave_size
                print(
                    f"\n=== memory: auditor={auditor} target={target} rep={rep} gen={g} "
                    f"-> {gen_dir}  [wave={mem.wave_size}, window={window}]"
                )
                eval_kwargs: dict = {"max_samples": window}
                if exp.max_connections is not None:
                    eval_kwargs["max_connections"] = exp.max_connections
                success, _ = eval_set(
                    task,
                    log_dir=str(gen_dir),
                    model_roles={
                        # Provider routing applies to the glm auditor+target only -- NOT the Opus
                        # judge, whose OpenRouter route is Anthropic and would break under a
                        # glm-specific `order`.
                        "auditor": role_model(auditor, "auditor", exp.reasoning, exp.max_connections, exp.openrouter_provider),
                        "target": role_model(target, "target", exp.reasoning, exp.max_connections, exp.openrouter_provider),
                        "judge": role_model(exp.judges[0].model, "judge", exp.reasoning, exp.max_connections),
                    },
                    epochs=mem.wave_size,
                    metadata={"experiment": exp.name, "auditor": auditor, "target": target,
                              "replicate": rep, "generation": g},
                    display="plain",
                    **eval_kwargs,
                )
                if not success:
                    print(f"  !! wave incomplete for rep={rep} gen={g}; re-run to resume")
                    return

                verdicts = extract_verdicts(gen_dir)
                n_valid_hits = sum(1 for v in verdicts if v.signature and v.scenario_valid)
                print(f"  scored {len(verdicts)} audits; {n_valid_hits} valid hit(s)")

                # Stop this replicate on the first valid hit (nothing left to measure or exploit)
                # or at the generation cap. Either way no review runs -- the next generation's
                # playbook would inform no wave, so paying for it would only inflate the x-axis.
                stop, reason = _should_stop(n_valid_hits, g, mem.generations, mem.stop_at_first_hit)
                if stop:
                    _write_snapshot(memory_dir, g, playbook)
                    _mark_done(memory_dir, g, reason)
                    print(f"  [rep {rep}] done at gen {g} ({reason})")
                    break

                result = asyncio.run(
                    reviewer.update(playbook, verdicts, model=reviewer_model, gen=g, effort=mem.reviewer_effort)
                )
                # Force the full provider/model id so cost_model.PRICES can price the usage
                # (Model.name may drop the provider prefix).
                result.usage["model"] = reviewer_id
                (gen_dir / "reviewer_usage.json").write_text(json.dumps(result.usage, indent=2))
                playbook = result.playbook
                _write_snapshot(memory_dir, g, playbook)

    print(f"\ndone. memory logs under {exp.root}/  (snapshots in rep_*/memory/)")


def _base_seed(exp: Experiment) -> Path:
    if not exp.seeds_dir:
        sys.exit("a memory run needs `seeds_dir` (one base seed directory)")
    seeds = sorted(exp.seeds_dir.glob("*.md"))
    if len(seeds) != 1:
        sys.exit(f"a memory run needs exactly one base seed in {exp.seeds_dir}; found {len(seeds)}")
    return seeds[0]
