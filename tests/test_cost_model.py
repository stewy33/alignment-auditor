"""Unit tests for the cost-model extension: the Reviewer as a 4th cost component.

The Reviewer runs once per generation on the separate OpenAI account (gpt-5.6-luna by default);
its cost is amortised across the K audits of the generation it informed, so it shows up on the
memory arm's x-axis and the arm pays its own overhead.
"""

from alignment_auditor.petri.analysis import cost_model


def test_luna_and_terra_are_priced():
    assert "openai/gpt-5.6-luna" in cost_model.PRICES
    assert "openai/gpt-5.6-terra" in cost_model.PRICES
    luna = cost_model.PRICES["openai/gpt-5.6-luna"]
    assert (luna.inp, luna.out) == (0.20, 1.20)
    terra = cost_model.PRICES["openai/gpt-5.6-terra"]
    assert (terra.inp, terra.out) == (2.0, 12.0)


def test_reviewer_usage_is_priced_at_the_models_rate():
    # 1,000,000 input + 1,000,000 output tokens of Luna = $0.20 + $1.20 = $1.40.
    usage = {
        "model": "openai/gpt-5.6-luna",
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "input_tokens_cache_read": 0,
        "input_tokens_cache_write": 0,
    }
    assert cost_model.reviewer_usage_cost(usage) == 1.40


def test_reviewer_cost_amortises_evenly_across_the_generations_audits():
    usage = {"model": "openai/gpt-5.6-luna", "input_tokens": 500_000, "output_tokens": 0}
    # $0.10 of input spread over 4 audits -> $0.025 each.
    assert cost_model.amortised_reviewer_share(usage, n_audits=4) == 0.10 / 4


def test_amortised_share_is_zero_when_there_are_no_audits():
    usage = {"model": "openai/gpt-5.6-luna", "input_tokens": 500_000, "output_tokens": 0}
    assert cost_model.amortised_reviewer_share(usage, n_audits=0) == 0.0


def test_unknown_reviewer_model_costs_zero():
    assert cost_model.reviewer_usage_cost({"model": "openai/mystery", "input_tokens": 1_000_000}) == 0.0
