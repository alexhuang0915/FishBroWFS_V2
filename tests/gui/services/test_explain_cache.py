from gui.services.explain_cache import ExplainCache


class DummyClient:
    def __init__(self):
        self.call_count = 0

    def get_job_explain(self, job_id: str) -> dict:
        self.call_count += 1
        return {"summary": f"s_{job_id}"}


def test_explain_cache_within_ttl(monkeypatch):
    client = DummyClient()
    cache = ExplainCache(client=client, ttl_seconds=5.0)

    time_values = [100.0]

    def fake_monotonic():
        return time_values[0]

    monkeypatch.setattr("gui.services.explain_cache.time.monotonic", fake_monotonic)

    first = cache.get("job-1")
    assert first["summary"] == "s_job-1"
    assert client.call_count == 1

    # Same timestamp -> cache hit
    second = cache.get("job-1")
    assert second == first
    assert client.call_count == 1

    # Advance time beyond TTL
    time_values[0] += 10.0
    third = cache.get("job-1")
    assert third["summary"] == "s_job-1"
    assert client.call_count == 2
