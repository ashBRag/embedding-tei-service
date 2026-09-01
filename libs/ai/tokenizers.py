"""Per-model tokenizers and published API limits for Voyage AI models.

Voyage publishes a HuggingFace tokenizer repo per model
(https://huggingface.co/voyageai). Each entry below pins an exact revision -
tokenizers are loaded once per process (`get_tokenizer` is cached) and reused
for every `count_tokens` call, so a silent tokenizer change upstream can't
change token counts (and therefore rate-limit behavior) under a fixed
service deployment.

VOYAGE_MODEL_LIMITS holds each model's published request/rate limits (see
https://docs.voyageai.com/docs/rate-limits and the model's own API reference
page). These are facts about Voyage's API, not deployment config, so they're
hardcoded here rather than read from the environment - they only change when
Voyage changes its published limits, which should be a code change (and a
version bump / changelog entry), not something an operator can accidentally
misconfigure per-deployment.

Only models with entries in *both* VOYAGE_MODEL_LIMITS and
VOYAGE_TOKENIZER_REPOS get rate-limited, token-aware batching in
app/integrations/voyage.py - add a new model by adding both entries.
"""

from dataclasses import dataclass
from functools import cache

from transformers import AutoTokenizer, PreTrainedTokenizerBase

__all__ = ["VOYAGE_MODEL_LIMITS", "VOYAGE_TOKENIZER_REPOS", "VoyageModelLimits", "count_tokens", "get_tokenizer"]


@dataclass(frozen=True)
class VoyageModelLimits:
    """One Voyage model's published per-request caps and rolling rate limit.

    max_texts_per_request / max_tokens_per_request / max_tokens_per_text:
        hard ceilings on the shape of a single API call - enforced by
        app.integrations.base.plan_token_aware_batches.
    tpm / rpm: the rolling per-minute rate limit across requests - enforced
        by libs.ai.rate_limit.RateLimiter. Independent of the per-request
        caps above: a request can be small enough to be legal on its own
        while still needing to wait if recent requests already used up this
        minute's tpm/rpm budget.
    """

    max_texts_per_request: int
    max_tokens_per_request: int
    max_tokens_per_text: int
    tpm: int
    rpm: int


# model name (as used in settings.VOYAGE_MODEL) -> its published limits.
VOYAGE_MODEL_LIMITS: dict[str, VoyageModelLimits] = {
    "voyage-4-lite": VoyageModelLimits(
        max_texts_per_request=1_000,
        max_tokens_per_request=1_000_000,
        max_tokens_per_text=32_000,
        tpm=16_000_000,
        rpm=2_000,
    ),
}

# model name (as used in settings.VOYAGE_MODEL) -> (HF repo id, pinned revision).
VOYAGE_TOKENIZER_REPOS: dict[str, tuple[str, str]] = {
    "voyage-4-lite": ("voyageai/voyage-4-lite", "0335ddf7698395712e3220733b4079006951cfef"),
}


@cache
def get_tokenizer(model: str) -> PreTrainedTokenizerBase:
    """Load (and cache) the HuggingFace tokenizer pinned for `model`.

    Raises:
        KeyError: If `model` has no entry in VOYAGE_TOKENIZER_REPOS.
    """
    repo_id, revision = VOYAGE_TOKENIZER_REPOS[model]
    return AutoTokenizer.from_pretrained(repo_id, revision=revision)


def count_tokens(model: str, text: str) -> int:
    """Return the number of tokens `text` encodes to under `model`'s tokenizer."""
    return len(get_tokenizer(model).encode(text))
