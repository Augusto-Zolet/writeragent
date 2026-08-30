import datetime
import email.utils
import ssl

from plugin.framework.client.request_controls import (
    LocalHttpsCertificateFallback,
    RequestPacer,
    backoff_delay_sec,
    parse_retry_after,
    wait_abortable,
)


def test_request_pacer_sleeps_for_back_to_back_sends():
    sleeps: list[float] = []
    times = iter([1000.0, 1000.0, 1000.0])
    pacer = RequestPacer(monotonic=lambda: next(times), sleep=sleeps.append)

    pacer.wait_before_send()
    pacer.mark_sent()
    pacer.wait_before_send()

    assert sleeps == [0.05]


def test_local_https_certificate_fallback_only_enables_for_local_cert_errors():
    fallback = LocalHttpsCertificateFallback()

    assert fallback.ssl_mode_for("https", "localhost") == "verified"
    assert fallback.ssl_mode_for("https", "api.openai.com") == "verified"
    assert fallback.enable_if_applicable("localhost", ssl.SSLCertVerificationError("self-signed certificate")) is True
    assert fallback.ssl_mode_for("https", "localhost") == "unverified"
    assert fallback.ssl_mode_for("https", "api.openai.com") == "verified"

    assert fallback.enable_if_applicable("api.openai.com", ssl.SSLCertVerificationError("self-signed certificate")) is False
    assert fallback.enable_if_applicable("localhost", OSError("connection reset")) is False
    assert fallback.ssl_mode_for("http", "localhost") == "plain"


def test_parse_retry_after_seconds_and_http_date():
    assert parse_retry_after("2") == 2.0
    assert parse_retry_after(" 1.5 ") == 1.5
    assert parse_retry_after(None) is None
    assert parse_retry_after("not-a-date") is None

    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=8)
    header = email.utils.format_datetime(future, usegmt=True)
    delay = parse_retry_after(header)
    assert delay is not None
    assert 6.0 < delay < 10.0


def test_backoff_honors_retry_after_floor_with_zero_jitter():
    # OpenClaw: 1.4ms Retry-After with jitter=0 ceils to 2ms, never undercuts the hint.
    delay = backoff_delay_sec(
        attempt=1,
        retry_after_sec=0.0014,
        min_delay=0.0,
        max_delay=0.01,
        jitter=0,
        random=lambda: 0.0,
    )
    assert delay == 0.002


def test_backoff_over_cap_retry_after_spreads_downward():
    delay = backoff_delay_sec(
        attempt=1,
        retry_after_sec=100.0,
        min_delay=0.3,
        max_delay=30.0,
        jitter="full",
        random=lambda: 0.0,
    )
    assert delay == 15.0


def test_wait_abortable_stops_without_sleeping_remainder():
    sleeps: list[float] = []
    calls = {"n": 0}

    def stop_checker() -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    times = iter([0.0, 0.0, 0.0, 0.0])
    ok = wait_abortable(
        10.0,
        stop_checker,
        sleep=sleeps.append,
        monotonic=lambda: next(times),
        chunk_sec=0.05,
    )
    assert ok is False
    assert sleeps == [0.05]
