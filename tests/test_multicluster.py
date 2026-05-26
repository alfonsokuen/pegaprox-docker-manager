"""Multi-cluster support (v2.1.0): config normalization, active-cluster
routing, and per-cluster cache isolation."""
import pytest


@pytest.fixture(autouse=True)
def _reset(plugin):
    with plugin._cache_lock:
        plugin._cache.clear()
    # Default thread has no bound cluster between tests.
    if hasattr(plugin._active, "cluster_id"):
        plugin._active.cluster_id = None
    yield
    with plugin._cache_lock:
        plugin._cache.clear()
    if hasattr(plugin._active, "cluster_id"):
        plugin._active.cluster_id = None


def test_legacy_swarm_hosts_becomes_default_cluster(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_load_config",
                        lambda: {"swarm_hosts": [{"host": "10.0.0.1"}], "poll_interval": 30})
    clusters = plugin._get_clusters()
    assert len(clusters) == 1
    assert clusters[0]["id"] == "default"
    assert clusters[0]["hosts"] == [{"host": "10.0.0.1"}]
    assert plugin._default_cluster_id() == "default"


def test_clusters_config_is_normalized(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_load_config", lambda: {
        "clusters": [
            {"id": "prod", "name": "Prod", "hosts": [{"host": "1.1.1.1"}]},
            {"id": "qa", "name": "QA", "hosts": [{"host": "2.2.2.2"}, {"host": "3.3.3.3"}]},
        ],
        "poll_interval": 30,
    })
    clusters = plugin._get_clusters()
    assert [c["id"] for c in clusters] == ["prod", "qa"]
    assert plugin._default_cluster_id() == "prod"


def test_active_hosts_follow_bound_cluster(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_load_config", lambda: {
        "clusters": [
            {"id": "prod", "name": "Prod", "hosts": [{"host": "1.1.1.1"}]},
            {"id": "qa", "name": "QA", "hosts": [{"host": "2.2.2.2"}]},
        ],
    })
    assert plugin._run_in_cluster("prod", lambda: plugin._active_hosts()) == [{"host": "1.1.1.1"}]
    assert plugin._run_in_cluster("qa", lambda: plugin._active_hosts()) == [{"host": "2.2.2.2"}]
    # Unknown id falls back to first cluster's hosts.
    assert plugin._run_in_cluster("ghost", lambda: plugin._active_hosts()) == [{"host": "1.1.1.1"}]


def test_cache_is_isolated_per_cluster(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_load_config", lambda: {
        "clusters": [
            {"id": "prod", "name": "Prod", "hosts": [{"host": "1.1.1.1"}]},
            {"id": "qa", "name": "QA", "hosts": [{"host": "2.2.2.2"}]},
        ],
    })
    plugin._run_in_cluster("prod", lambda: plugin._cache_set("services", ["prod-svc"]))
    plugin._run_in_cluster("qa", lambda: plugin._cache_set("services", ["qa-svc"]))
    assert plugin._run_in_cluster("prod", lambda: plugin._cache_get("services")) == ["prod-svc"]
    assert plugin._run_in_cluster("qa", lambda: plugin._cache_get("services")) == ["qa-svc"]
    # Invalidating one cluster leaves the other intact.
    plugin._run_in_cluster("prod", lambda: plugin._invalidate("services"))
    assert plugin._run_in_cluster("prod", lambda: plugin._cache_get("services")) is None
    assert plugin._run_in_cluster("qa", lambda: plugin._cache_get("services")) == ["qa-svc"]
