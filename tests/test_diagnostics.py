from __future__ import annotations

import logging
import threading

from sql_obfuscator.diagnostics import capture_sqlglot_warnings


def test_sqlglot_warning_capture_is_isolated_for_overlapping_requests():
    logger = logging.getLogger("sqlglot")
    barrier = threading.Barrier(2)
    results: dict[str, list[str]] = {}

    def capture_request(label: str) -> None:
        with capture_sqlglot_warnings() as messages:
            barrier.wait(timeout=5)
            logger.warning(label)
            barrier.wait(timeout=5)
            results[label] = list(messages)

    threads = [
        threading.Thread(target=capture_request, args=("request-a",)),
        threading.Thread(target=capture_request, args=("request-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert results == {
        "request-a": ["request-a"],
        "request-b": ["request-b"],
    }
