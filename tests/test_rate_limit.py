"""Tests for libs.ai.rate_limit.RateLimiter and app.integrations.base's token-aware batching."""

import asyncio

import pytest

from app.integrations.base import embed_in_rate_limited_batches, plan_token_aware_batches
from libs.ai.rate_limit import ModelLimits, RateLimiter


def _count_chars(text: str) -> int:
    return len(text)


def test_plan_empty_texts_returns_no_batches():
    assert plan_token_aware_batches([], max_batch_size=10, max_tokens_per_batch=100, count_tokens=_count_chars) == []


def test_plan_splits_on_max_batch_size():
    texts = ["a", "b", "c"]
    batches = plan_token_aware_batches(texts, max_batch_size=2, max_tokens_per_batch=1000, count_tokens=_count_chars)
    assert batches == [["a", "b"], ["c"]]


def test_plan_splits_on_token_budget():
    texts = ["aaaa", "bbbb", "cccc"]  # 4 tokens each
    batches = plan_token_aware_batches(texts, max_batch_size=10, max_tokens_per_batch=8, count_tokens=_count_chars)
    assert batches == [["aaaa", "bbbb"], ["cccc"]]


def test_plan_oversized_single_text_gets_own_batch():
    texts = ["short", "x" * 100]
    batches = plan_token_aware_batches(texts, max_batch_size=10, max_tokens_per_batch=8, count_tokens=_count_chars)
    assert batches == [["short"], ["x" * 100]]


def test_plan_preserves_order():
    texts = [str(i) for i in range(10)]
    batches = plan_token_aware_batches(texts, max_batch_size=3, max_tokens_per_batch=1000, count_tokens=_count_chars)
    assert [t for batch in batches for t in batch] == texts


async def test_acquire_within_budget_does_not_block():
    limiter = RateLimiter(ModelLimits(tpm=1000, rpm=10, max_batch_size=100))
    await asyncio.wait_for(limiter.acquire(100), timeout=1)
    tokens_used, requests_used = limiter._usage()
    assert tokens_used == 100
    assert requests_used == 1


async def test_acquire_over_rpm_blocks_until_window_frees():
    limiter = RateLimiter(ModelLimits(tpm=1_000_000, rpm=1, max_batch_size=100))
    await limiter.acquire(1)

    acquired = False

    async def second_acquire():
        nonlocal acquired
        await limiter.acquire(1)
        acquired = True

    task = asyncio.create_task(second_acquire())
    await asyncio.sleep(0.05)
    assert not acquired  # still blocked, RPM budget of 1 is exhausted

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_acquire_over_tpm_blocks():
    limiter = RateLimiter(ModelLimits(tpm=100, rpm=1000, max_batch_size=1000))
    await limiter.acquire(90)

    acquired = False

    async def second_acquire():
        nonlocal acquired
        await limiter.acquire(50)  # 90 + 50 > 100 tpm
        acquired = True

    task = asyncio.create_task(second_acquire())
    await asyncio.sleep(0.05)
    assert not acquired

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_embed_in_rate_limited_batches_empty_texts_returns_empty_without_calling_embed():
    limiter = RateLimiter(ModelLimits(tpm=1000, rpm=10, max_batch_size=10))
    calls = []

    async def embed_batch(batch):
        calls.append(batch)
        return [[0.0]] * len(batch)

    result = await embed_in_rate_limited_batches(
        [],
        max_batch_size=10,
        max_tokens_per_batch=100,
        count_tokens=_count_chars,
        rate_limiter=limiter,
        embed_batch=embed_batch,
        validate=lambda batch, vectors: None,
        on_error=lambda batch, exc: None,
    )
    assert result == []
    assert calls == []


async def test_embed_in_rate_limited_batches_batches_and_embeds_in_order():
    limiter = RateLimiter(ModelLimits(tpm=1000, rpm=10, max_batch_size=10))
    texts = ["hello", "world", "foo"]
    calls = []

    async def embed_batch(batch):
        calls.append(list(batch))
        return [[float(len(t))] for t in batch]

    result = await embed_in_rate_limited_batches(
        texts,
        max_batch_size=2,
        max_tokens_per_batch=1000,
        count_tokens=_count_chars,
        rate_limiter=limiter,
        embed_batch=embed_batch,
        validate=lambda batch, vectors: None,
        on_error=lambda batch, exc: None,
    )
    assert calls == [["hello", "world"], ["foo"]]
    assert result == [[5.0], [5.0], [3.0]]


async def test_embed_in_rate_limited_batches_error_calls_on_error_and_reraises():
    limiter = RateLimiter(ModelLimits(tpm=1000, rpm=10, max_batch_size=10))
    errors = []

    async def embed_batch(batch):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await embed_in_rate_limited_batches(
            ["hi"],
            max_batch_size=10,
            max_tokens_per_batch=100,
            count_tokens=_count_chars,
            rate_limiter=limiter,
            embed_batch=embed_batch,
            validate=lambda batch, vectors: None,
            on_error=lambda batch, exc: errors.append((batch, exc)),
        )
    assert len(errors) == 1
    assert errors[0][0] == ["hi"]
