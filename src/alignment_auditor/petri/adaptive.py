"""Adaptive sampling with early stopping for Petri audits.

Fixed-n mode (the default) runs exactly `epochs` audits per (auditor, target) cell.
Adaptive mode -- enabled by putting `stop_at_successful_n: K` in the config -- instead
runs UP TO `epochs` audits but stops launching new ones the moment K of them satisfy
`success_criteria`. So a scenario that fires early is cheap, and one that never fires
is still capped at n=`epochs`. This is a sequential DETECTION design ("does this seed
elicit the behaviour, and grab K examples"), not an estimation of the rate -- stopping
early biases any rate you would compute from the stopped denominator, so report counts.

Mechanism: Inspect's native `Task.early_stopping`. The gating judge (judges[0]) runs
INLINE as the task scorer, so every completed audit is scored the instant it finishes.
`complete_sample` tallies the successes; once K are reached, `schedule_sample` returns an
EarlyStop for every audit not yet started, so no further work is scheduled. Concurrency is
the eval's `max_samples` (the config's `max_parallel`): at most that many audits are ever
in flight, and the up-to-(max_parallel - 1) already running when the Kth success lands run
to completion (Inspect does not hard-cancel a sample mid-generation) and are kept as extra
data. Skipped audits produce no sample in the log, so the scoring phase and the viewer see
only the audits that actually ran.

Because the whole cell is a single `eval_set` run, resume is native: a re-run skips the
audits already completed. The manager is therefore SEEDED on construction with the successes
already on disk (`count_disk_successes`), so a resumed run does not forget them and re-open
an already-satisfied cell.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai.util import EarlyStop


@dataclass(frozen=True)
class SuccessCriteria:
    """What counts as a "positive" audit, evaluated against the gating judge's score value.

    The judge's score `value` is a dict of named metrics (the custom judge's `level`/`signature`,
    or the stock judge's per-dimension scores). `key` selects one of them; the audit is a success
    when that metric is `>= min` (numeric threshold) or, with `is_true`, is truthy (a bool metric
    is carried as 1/0, so `signature`'s "file was written" reads as >= 1). Exactly one of the two
    is set. For step-1 SSRF that is `{key: signature, is_true: true}` -- the seed's `signature`
    is "the agent genuinely deposited an object", i.e. actually wrote the file.
    """

    key: str
    min: float | None = None
    is_true: bool = False

    def met(self, value) -> bool:
        metric = value.get(self.key) if isinstance(value, dict) else value
        if metric is None:
            return False
        try:
            metric = float(metric)
        except (TypeError, ValueError):
            return False
        if self.min is not None:
            return metric >= self.min
        return metric >= 1  # is_true: bool metrics are coerced to 1/0 by the judge


def parse_success_criteria(cfg) -> SuccessCriteria:
    """Validate and build a SuccessCriteria from the config's `success_criteria` mapping."""
    if not isinstance(cfg, dict) or "key" not in cfg:
        sys.exit("success_criteria must be a mapping with a 'key' and one of 'min: <n>' / 'is_true: true'")
    has_min = cfg.get("min") is not None
    is_true = bool(cfg.get("is_true", False))
    if has_min == is_true:  # neither, or both
        sys.exit("success_criteria needs exactly one of 'min: <n>' or 'is_true: true'")
    return SuccessCriteria(key=cfg["key"], min=cfg.get("min"), is_true=is_true)


def _sample_value(scores) -> object | None:
    """The gating judge's score value for a sample. In adaptive mode exactly one scorer runs
    inline, so take the single entry; return None when the sample has no score (never scored)."""
    for score in (scores or {}).values():
        return getattr(score, "value", None)
    return None


def count_disk_successes(conv_dir, criteria: SuccessCriteria) -> int:
    """Count already-completed audits in `conv_dir` that meet the criteria.

    Used to SEED the stopping manager on a resumed run so successes from a prior, interrupted
    run are not forgotten. Reads the inline gating score straight off each logged sample; skipped
    (early-stopped) audits are absent from the log and so are never counted.
    """
    if not Path(conv_dir).exists():
        return 0
    n = 0
    for info in list_eval_logs(str(conv_dir)):
        log = read_eval_log(info.name)
        for sample in log.samples or []:
            if criteria.met(_sample_value(sample.scores)):
                n += 1
    return n


class SuccessCountStopping:
    """Inspect `EarlyStopping` manager: stop once `target` audits meet `criteria`.

    Implements the EarlyStopping protocol (start_task / schedule_sample / complete_sample /
    complete_task) by duck typing -- Inspect calls these; nothing here subclasses a base.
    """

    def __init__(
        self,
        criteria: SuccessCriteria,
        target: int,
        initial_successes: int = 0,
        on_event: Callable[[str], None] | None = None,
    ):
        self.criteria = criteria
        self.target = target
        self.successes = initial_successes
        self.scored = 0
        self._on_event = on_event or (lambda _msg: None)

    async def start_task(self, task, samples, epochs) -> str:
        if self.successes >= self.target:
            self._on_event(
                f"already {self.successes}/{self.target} successes on disk; every remaining audit will be skipped"
            )
        return "success-count"

    async def schedule_sample(self, id, epoch) -> EarlyStop | None:
        if self.successes >= self.target:
            return EarlyStop(id=id, epoch=epoch, reason=f"reached {self.target} successes")
        return None

    async def complete_sample(self, id, epoch, scores) -> None:
        self.scored += 1
        if self.criteria.met(_sample_value({k: v.score for k, v in scores.items()})):
            self.successes += 1
            self._on_event(f"success {self.successes}/{self.target} (audit #{self.scored})")

    async def complete_task(self) -> dict:
        return {"successes": self.successes, "target": self.target, "scored": self.scored}
