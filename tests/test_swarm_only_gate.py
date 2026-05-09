"""Swarm-only route guard (v2.0.0)."""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_module_cache(plugin):
    with plugin._cache_lock:
        plugin._cache.clear()
    yield
    with plugin._cache_lock:
        plugin._cache.clear()


def test_require_swarm_passes_in_swarm_mode(plugin):
    with patch.object(plugin, "_docker_cmd", return_value="active"):
        plugin._detect_mode(force=True)
        assert plugin._require_swarm() is None


def test_require_swarm_blocks_standalone_with_422(plugin):
    with patch.object(plugin, "_docker_cmd", return_value="inactive"):
        plugin._detect_mode(force=True)
        result = plugin._require_swarm()
    assert isinstance(result, tuple)
    body, status = result
    assert status == 422
    assert body["error"] == "swarm-only endpoint"
    assert body["mode"] == "standalone"
    assert "Swarm" in body["hint"]


def test_swarm_only_wrap_short_circuits_in_standalone(plugin):
    """Wrapped handler must NOT execute when engine is standalone."""
    calls = []
    def handler():
        calls.append(1)
        return {"ok": True}
    wrapped = plugin._swarm_only_wrap(handler)
    with patch.object(plugin, "_docker_cmd", return_value="inactive"):
        plugin._detect_mode(force=True)
        body, status = wrapped()
    assert calls == []
    assert status == 422


def test_swarm_only_wrap_calls_handler_in_swarm(plugin):
    def handler():
        return {"data": 42}
    wrapped = plugin._swarm_only_wrap(handler)
    with patch.object(plugin, "_docker_cmd", return_value="active"):
        plugin._detect_mode(force=True)
        result = wrapped()
    assert result == {"data": 42}


def test_swarm_only_wrap_marks_handler(plugin):
    def handler():
        return None
    wrapped = plugin._swarm_only_wrap(handler)
    assert getattr(wrapped, "__swarm_only__", False) is True


def test_swarm_only_routes_set_covers_swarm_endpoints(plugin):
    """Whitelist hygiene — every documented swarm-only path must be in the set
    so future refactors don't accidentally drop one."""
    must_include = {
        "overview", "nodes", "node-stats", "node-action",
        "services", "service-detail", "service-logs", "service-scale",
        "service-restart", "service-rollback", "service-update", "service-remove",
        "stacks", "stack-detail", "stack-compose", "stack-logs",
        "stack-stop", "stack-start", "stack-deploy", "stack-remove",
        "tasks", "topology",
        "load-balance", "rebalance-service",
        "balance/insights", "balance/rebalance-all", "balance/rebalance-status",
        "metrics/history", "metrics/trends",
        "policy/audit", "policy/checks", "policy/apply", "policy/appliers",
        "webhooks", "webhook-create", "webhook-revoke", "webhook/trigger",
    }
    assert must_include.issubset(plugin._SWARM_ONLY_ROUTES)


def test_standalone_safe_routes_not_in_set(plugin):
    """Routes that work on a plain Docker engine must NOT be flagged
    swarm-only — otherwise standalone users lose access to them."""
    standalone_safe = {
        "ui", "config", "config/save", "test-connection", "refresh", "host-mode",
        "containers", "container-logs", "container-action",
        "networks", "network-remove",
        "volumes", "volume-remove",
        "images", "image-pull", "image-remove",
        "disk/prune", "disk/settings", "disk/auto-prune/run",
    }
    overlap = standalone_safe & plugin._SWARM_ONLY_ROUTES
    assert not overlap, f"these routes wrongly marked swarm-only: {overlap}"
