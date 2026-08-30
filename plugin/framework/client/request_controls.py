# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Low-level pacing and retry policy helpers for outbound LLM requests.

Concurrency: ``RequestPacer`` (minimum gap between sends) and
``LocalHttpsCertificateFallback`` (which local hosts retried without TLS
verify) are fields on one transport. They are not locked: each
``LlmClient`` has its own transport and typically one in-flight stream.
Chat and grammar do not share a pacer. Adding a lock here would not
protect a connection you must not share in the first place.

Backoff helpers port OpenClaw ``packages/retry`` delay math (jitter,
Retry-After floor, delay cap) without the RetrySupervisor / retryAsync
runner. Callers keep the existing one-retry loops.
"""

import datetime
import email.utils
import logging
import math
import random
import time
from typing import Callable, Literal

from .ssl_helpers import _is_certificate_verify_error
from .provider_detection import is_local_host

log = logging.getLogger(__name__)

# Minimum wall time between consecutive HTTP sends on one client. Grammar queue
# workers also use this value to stagger parallel drains so they do not burst.
LLM_MIN_REQUEST_INTERVAL_SEC = 0.05

# OpenClaw packages/retry defaults (ms) expressed in seconds.
RETRY_MIN_DELAY_SEC = 0.3
RETRY_MAX_DELAY_SEC = 30.0
RETRY_WAIT_CHUNK_SEC = 0.05
RETRYABLE_HTTP_STATUS = frozenset({429, 503})


def parse_retry_after(header: str | None) -> float | None:
    """Parse Retry-After as delta-seconds or HTTP-date. Invalid/missing -> None."""
    if not header:
        return None
    text = header.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    delay = parsed.timestamp() - time.time()
    if not math.isfinite(delay):
        return None
    return delay


def _apply_jitter_ms(delay_ms: float, jitter: float | Literal["full"], mode: Literal["symmetric", "positive"], rng: Callable[[], float]) -> float:
    # OpenClaw packages/retry applyJitter: Retry-After is a lower bound, so
    # positive jitter ceils. Over-cap hints spread downward to avoid lockstep.
    if jitter == "full":
        if mode == "symmetric":
            return max(0.0, round(delay_ms * (0.5 + rng() * 0.5)))
        return max(0.0, math.ceil(delay_ms * (1.0 + rng())))
    if jitter <= 0:
        return math.ceil(delay_ms) if mode == "positive" else delay_ms
    fraction = rng()
    offset = fraction * jitter if mode == "positive" else (fraction * 2.0 - 1.0) * jitter
    raw = delay_ms * (1.0 + offset)
    return max(0.0, math.ceil(raw) if mode == "positive" else round(raw))


def backoff_delay_sec(
    *,
    attempt: int = 1,
    retry_after_sec: float | None = None,
    min_delay: float = RETRY_MIN_DELAY_SEC,
    max_delay: float = RETRY_MAX_DELAY_SEC,
    jitter: float | Literal["full"] = "full",
    random: Callable[[], float] = random.random,
) -> float:
    """Jittered delay before the next attempt. ``attempt`` is 1-based (first retry)."""
    retry_after_value = retry_after_sec if retry_after_sec is not None and math.isfinite(retry_after_sec) else None
    if retry_after_value is not None:
        base = max(retry_after_value, min_delay)
    else:
        base = min_delay * (2 ** max(attempt - 1, 0))
    delay_cap = max_delay
    delay = min(base, delay_cap)
    can_honor = retry_after_value is not None and retry_after_value <= delay_cap
    has_retry_after = retry_after_value is not None
    wants_positive = (not has_retry_after or can_honor) if jitter == "full" else can_honor
    delay_ms = delay * 1000.0
    delay_ms = _apply_jitter_ms(delay_ms, jitter, "positive" if wants_positive else "symmetric", random)
    delay = min(max(delay_ms / 1000.0, min_delay), delay_cap)
    return delay


def wait_abortable(
    delay_sec: float,
    stop_checker: Callable[[], bool] | None = None,
    *,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    chunk_sec: float = RETRY_WAIT_CHUNK_SEC,
) -> bool:
    """Sleep ``delay_sec`` in small chunks so Stop aborts the wait. False if stopped."""
    sleeper = sleep or time.sleep
    now = monotonic or time.monotonic
    if stop_checker and stop_checker():
        return False
    if not math.isfinite(delay_sec) or delay_sec <= 0:
        return not (stop_checker and stop_checker())
    deadline = now() + delay_sec
    while True:
        if stop_checker and stop_checker():
            return False
        remaining = deadline - now()
        if remaining <= 0:
            return not (stop_checker and stop_checker())
        sleeper(min(chunk_sec, remaining))


class RequestPacer:
    """Sleep before rapid repeat sends on the same client."""

    def __init__(self, min_interval_sec: float = LLM_MIN_REQUEST_INTERVAL_SEC, *, monotonic: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None) -> None:
        self.min_interval_sec = min_interval_sec
        self._monotonic = monotonic
        self._sleep = sleep
        self.last_sent_monotonic = 0.0

    def _now(self) -> float:
        return (self._monotonic or time.monotonic)()

    def wait_before_send(self) -> None:
        """Sleep if needed so consecutive sends are not back-to-back."""
        wait = self.min_interval_sec - (self._now() - self.last_sent_monotonic)
        if wait > 0:
            (self._sleep or time.sleep)(wait)

    def mark_sent(self) -> None:
        self.last_sent_monotonic = self._now()


class LocalHttpsCertificateFallback:
    """Track local HTTPS hosts that should retry with certificate verification disabled."""

    def __init__(self) -> None:
        self._fallback_hosts: set[str] = set()

    def ssl_mode_for(self, scheme: str, host: str) -> str:
        """Return ``verified``, ``unverified``, or ``plain`` for the next connection.

        Public HTTPS is always verified. Local HTTPS starts verified and
        switches to unverified only after ``enable_if_applicable`` records a
        certificate failure (self-signed Ollama/LM Studio). Previously this
        returned ``unverified`` for every non-local host, which silently
        disabled TLS checks for OpenAI, Anthropic, OpenRouter, and similar.
        """
        if scheme != "https":
            return "plain"
        if is_local_host(host) and host in self._fallback_hosts:
            return "unverified"
        return "verified"

    def enable_if_applicable(self, host: str, err: BaseException) -> bool:
        """Enable unverified retry for a local host after certificate validation fails."""
        if not host or not is_local_host(host) or not _is_certificate_verify_error(err):
            return False
        if host in self._fallback_hosts:
            return False
        self._fallback_hosts.add(host)
        log.error("Local HTTPS certificate verification failed for %s; retrying unverified." % host)
        return True

    def has_fallback(self, host: str) -> bool:
        return host in self._fallback_hosts
