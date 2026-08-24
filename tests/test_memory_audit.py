"""Unit tests for the memory runner's stop-at-first-hit logic and resume/config plumbing.

These cover the pure decision helpers -- the full run_memory loop is exercised by the smoke run,
not a unit test, because it needs eval_set.
"""

from alignment_auditor.petri.memory_audit import (
    MemoryConfig,
    _mark_done,
    _resume_point,
    _should_stop,
    parse_memory_config,
)
from alignment_auditor.petri.playbook import Playbook


def test_memory_config_stops_at_first_hit_by_default():
    assert MemoryConfig().stop_at_first_hit is True


def test_parse_memory_config_reads_stop_at_first_hit():
    mem = parse_memory_config({"wave_size": 8, "generations": 16, "stop_at_first_hit": False})
    assert mem.stop_at_first_hit is False


def test_stops_on_first_hit_when_enabled():
    stop, reason = _should_stop(n_valid_hits=1, gen=0, generations=4, stop_at_first_hit=True)
    assert stop is True and reason == "hit"


def test_does_not_stop_midway_when_no_hit_and_not_last_generation():
    stop, reason = _should_stop(n_valid_hits=0, gen=1, generations=4, stop_at_first_hit=True)
    assert stop is False and reason is None


def test_always_stops_at_the_generation_cap():
    stop, reason = _should_stop(n_valid_hits=0, gen=3, generations=4, stop_at_first_hit=True)
    assert stop is True and reason == "cap"


def test_does_not_stop_on_a_hit_when_disabled():
    # Full-generations diagnostic mode: a hit does not end the run early.
    stop, reason = _should_stop(n_valid_hits=2, gen=1, generations=4, stop_at_first_hit=False)
    assert stop is False and reason is None


def test_resume_point_skips_a_replicate_marked_done(tmp_path):
    mem = tmp_path / "memory"
    mem.mkdir()
    # A replicate that hit at gen 1 and stopped: snapshots for 0,1 plus a done marker.
    from alignment_auditor.petri.memory_audit import _write_snapshot
    _write_snapshot(mem, 0, Playbook.empty())
    _write_snapshot(mem, 1, Playbook.empty())
    _mark_done(mem, final_gen=1, reason="hit")
    start_gen, _pb, done = _resume_point(mem, generations=4)
    assert done is True


def test_resume_point_continues_an_unfinished_replicate(tmp_path):
    mem = tmp_path / "memory"
    mem.mkdir()
    from alignment_auditor.petri.memory_audit import _write_snapshot
    _write_snapshot(mem, 0, Playbook.empty())
    start_gen, _pb, done = _resume_point(mem, generations=4)
    assert done is False and start_gen == 1


from alignment_auditor.petri.memory_audit import _replicate_indices


def test_replicate_indices_all_by_default():
    assert _replicate_indices(8, None) == [0, 1, 2, 3, 4, 5, 6, 7]


def test_replicate_indices_single_when_only_rep_given():
    assert _replicate_indices(8, 3) == [3]


def test_replicate_indices_rejects_out_of_range():
    import pytest
    with pytest.raises(SystemExit):
        _replicate_indices(8, 8)
    with pytest.raises(SystemExit):
        _replicate_indices(8, -1)
