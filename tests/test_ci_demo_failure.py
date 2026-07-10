"""TEMPORARY CI demo — deliberately failing test.

Exists only to prove the CI gate turns red when a test fails on a PR. This file
is reverted immediately after the demonstration; it should never reach main.
"""


def test_ci_gate_catches_failures():
    assert 1 == 2, "intentional failure to demonstrate the CI gate"
