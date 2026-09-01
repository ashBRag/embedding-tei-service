"""Per-model tokenizers for Voyage AI models, used for rate-limit token counting.

Voyage publishes a HuggingFace tokenizer repo per model
(https://huggingface.co/voyageai). Each entry below pins an exact revision -
tokenizers are loaded once per process (`get_tokenizer` is cached) and reused
for every `count_tokens` call, so a silent tokenizer change upstream can't
change token counts (and therefore rate-limit behavior) under a fixed
service deployment.

Only models with an entry here can be used for the Voyage provider's
rate-limited batching (see libs/ai/rate_limit.py) - add a new model by
adding its (repo_id, revision) pair to VOYAGE_TOKENIZER_REPOS.
"""

from functools import cache

from transformers import AutoTokenizer, PreTrainedTokenizerBase

__all__ = ["VOYAGE_TOKENIZER_REPOS", "count_tokens", "get_tokenizer"]

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
