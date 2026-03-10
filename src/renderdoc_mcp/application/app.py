from __future__ import annotations

from renderdoc_mcp.application.context import ApplicationContext
from renderdoc_mcp.application.handlers import ActionHandlers, CaptureHandlers, ResourceHandlers
from renderdoc_mcp.session_pool import CaptureSessionPool


class RenderDocApplication:
    def __init__(self, session_pool: CaptureSessionPool | None = None) -> None:
        self.context = ApplicationContext(session_pool=session_pool)
        self.captures = CaptureHandlers(self.context)
        self.actions = ActionHandlers(self.context)
        self.resources = ResourceHandlers(self.context)
