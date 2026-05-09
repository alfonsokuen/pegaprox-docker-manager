"""Engine mode detection (v2.0.0)."""
import time
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_module_cache(plugin):
    """Each test starts with an empty plugin cache."""
    with plugin._cache_lock:
        plugin._cache.clear()
    yield
    with plugin._cache_lock:
        plugin._cache.clear()


@pytest.mark.parametrize("local_state,expected_mode", [
    ("active",   "swarm"),
    ("locked",   "swarm"),
    ("inactive", "standalone"),
    ("pending",  "standalone"),
    ("error",    "standalone"),
    ("",         "standalone"),
    ("ACTIVE",   "swarm"),
    ("  active ", "swarm"),
])
def test_detect_mode_classifies_local_node_state(plugin, local_state, expected_mode):
    with patch.object(plugin, "_docker_cmd", return_value=local_state):
        assert plugin._detect_mode(force=True) == expected_mode


def test_detect_mode_handles_unreachable_engine(plugin):
    """``_docker_cmd`` returns ``None`` when no host responded (SSH all failed)."""
    with patch.object(plugin, "_docker_cmd", return_value=None):
        assert plugin._detect_mode(force=True) == "standalone"


def test_detect_mode_caches_result(plugin):
    """Second call within MODE_CACHE_TTL must not reach _docker_cmd."""
    with patch.object(plugin, "_docker_cmd", return_value="active") as m:
        plugin._detect_mode(force=True)
        plugin._detect_mode()
        plugin._detect_mode()
    assert m.call_count == 1


def test_detect_mode_cache_expires(plugin):
    """Past MODE_CACHE_TTL the cache is stale and re-probes."""
    with patch.object(plugin, "_docker_cmd", return_value="active") as m:
        plugin._detect_mode(force=True)
        with plugin._cache_lock:
            plugin._cache["engine_mode"]["ts"] = time.time() - (plugin.MODE_CACHE_TTL + 1)
        plugin._detect_mode()
    assert m.call_count == 2


def test_detect_mode_force_bypasses_cache(plugin):
    with patch.object(plugin, "_docker_cmd", return_value="active") as m:
        plugin._detect_mode(force=True)
        plugin._detect_mode(force=True)
    assert m.call_count == 2


def test_get_engine_mode_cached_returns_none_when_empty(plugin):
    assert plugin._get_engine_mode_cached() is None


def test_get_engine_mode_cached_returns_value_when_fresh(plugin):
    with patch.object(plugin, "_docker_cmd", return_value="active"):
        plugin._detect_mode(force=True)
    assert plugin._get_engine_mode_cached() == "swarm"
