from __future__ import annotations

from renderdoc_mcp.qrenderdoc_extension.renderdoc_mcp_bridge.client import BridgeClient


class FakeMiniQt:
    def InvokeOntoUIThread(self, callback):
        callback()


class FakeExtensions:
    def GetMiniQtHelper(self):
        return FakeMiniQt()


class FakeContext:
    def Extensions(self):
        return FakeExtensions()


def test_bridge_client_registers_handler_registry() -> None:
    client = BridgeClient(FakeContext())

    assert {
        "get_action_tree",
        "get_pipeline_state",
        "get_api_pipeline_state",
        "close_capture",
    }.issubset(set(client.handlers))
