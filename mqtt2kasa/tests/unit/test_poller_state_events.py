"""Regression tests for spurious state events out of handle_kasa_poller.

Recovering from a failed poll is not a state change. The poller used to decide
whether to emit an event with `if kasa.curr_state != new_state or fails:`, so
the first successful poll after any failure re-emitted the unchanged state. Every
subscriber saw that as a second transition, and on a topic published with retain
it also rewrote the retained value.

These tests drive the poller with a scripted fake device: no broker, no network.
They are written with asyncio.run() rather than pytest-asyncio on purpose, since
CI installs plain pytest.
"""

import asyncio

from mqtt2kasa import kasa_wrapper
from mqtt2kasa.kasa_wrapper import handle_kasa_poller


class _StopPolling(Exception):
    """Raised by the fake device once its scripted poll results run out."""


class FakeKasa:
    """Just enough of Kasa for the poller: scripted is_on/brightness results."""

    def __init__(self, states, brightnesses=None, dimmable=False):
        self.name = "fake"
        self.host = "192.0.2.1"
        self.poll_interval = 0
        self.curr_state = None
        self.curr_brightness = None
        self._states = list(states)
        self._brightnesses = list(brightnesses or [])
        self._dimmable = dimmable

    @property
    async def is_on(self):
        if not self._states:
            raise _StopPolling
        return self._states.pop(0)

    @property
    async def is_dimmable(self):
        return self._dimmable

    @property
    async def brightness(self):
        if not self._brightnesses:
            raise _StopPolling
        return self._brightnesses.pop(0)


def _run_poller(kasa):
    """Poll until the fake runs out of results; return the events emitted."""

    async def _no_sleep(_interval):
        return

    async def go():
        q = asyncio.Queue()
        try:
            await handle_kasa_poller(kasa, q)
        except _StopPolling:
            pass
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        return events

    original_sleep = kasa_wrapper._sleep_with_jitter
    kasa_wrapper._sleep_with_jitter = _no_sleep
    try:
        return asyncio.run(go())
    finally:
        kasa_wrapper._sleep_with_jitter = original_sleep


def test_recovered_poll_does_not_republish_unchanged_state():
    """off, a failed poll, then off again -> one event, not two."""
    events = _run_poller(FakeKasa([False, None, False]))
    assert [e.state for e in events] == [False]


def test_many_failures_then_recovery_still_publishes_nothing_new():
    events = _run_poller(FakeKasa([True, None, None, None, True]))
    assert [e.state for e in events] == [True]


def test_genuine_changes_are_still_published():
    events = _run_poller(FakeKasa([False, True, True, False]))
    assert [e.state for e in events] == [False, True, False]


def test_change_detected_across_a_failed_poll():
    """A failure must not swallow a change that happened during it."""
    events = _run_poller(FakeKasa([False, None, True]))
    assert [e.state for e in events] == [False, True]


def test_first_event_is_marked_by_a_null_old_state():
    events = _run_poller(FakeKasa([True, False]))
    assert events[0].old_state is None
    assert events[1].old_state is True


def test_brightness_failure_does_not_republish_state():
    """A dimmable device whose first brightness read fails still reports its
    state exactly once."""
    kasa = FakeKasa([False, False], brightnesses=[None, 50], dimmable=True)
    events = _run_poller(kasa)
    assert [e.event for e in events] == ["KasaStateEvent", "KasaBrightnessEvent"]
    assert [e.state for e in events if e.event == "KasaStateEvent"] == [False]


def test_recovered_brightness_poll_does_not_republish_unchanged_brightness():
    """Also covers the shared failure counter: the state poller ran first and
    `or fails` saw the *brightness* failure, so an unchanged state was
    republished on the next cycle."""
    kasa = FakeKasa([False, False, False], brightnesses=[50, None, 50], dimmable=True)
    events = _run_poller(kasa)
    assert [e.event for e in events] == ["KasaStateEvent", "KasaBrightnessEvent"]
    assert [e.brightness for e in events if e.event == "KasaBrightnessEvent"] == [50]


def test_brightness_is_not_polled_on_a_plain_switch():
    kasa = FakeKasa([False, True], brightnesses=[], dimmable=False)
    events = _run_poller(kasa)
    assert [e.event for e in events] == ["KasaStateEvent", "KasaStateEvent"]
