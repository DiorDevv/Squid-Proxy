"""Regression test for the tailer -> ring buffer -> WS broadcast wiring in
main.py: a prior bug discarded RingBuffer.append()'s return value and passed
the raw ParsedEvent to the WS broadcaster, which expects a StoredEvent and
silently failed on every single event (masked by the polling fallback)."""

from app.main import _handle_new_event
from app.services.event_store import RingBuffer, StoredEvent
from app.services.log_parser import parse_line


class _FakeState:
    def __init__(self, ring_buffer):
        self.ring_buffer = ring_buffer
        self.broadcast_calls = []

    def broadcast_nowait(self, stored):
        self.broadcast_calls.append(stored)


class _FakeApp:
    def __init__(self, ring_buffer):
        self.state = _FakeState(ring_buffer)
        self.state.ws_manager = self.state


def test_handle_new_event_broadcasts_the_stored_event_not_the_raw_event():
    ring_buffer = RingBuffer(max_events=10)
    app = _FakeApp(ring_buffer)

    line = "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    event = parse_line(line)
    assert event is not None

    _handle_new_event(app, event)

    assert len(ring_buffer) == 1
    assert len(app.state.broadcast_calls) == 1
    broadcasted = app.state.broadcast_calls[0]
    assert isinstance(broadcasted, StoredEvent)
    assert broadcasted.id == 1
    assert broadcasted.event is event
