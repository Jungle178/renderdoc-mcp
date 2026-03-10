from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from renderdoc_mcp.application.context import ApplicationContext
from renderdoc_mcp.application.response import attach_capture, ensure_meta
from renderdoc_mcp.errors import ReplayFailureError

SUPPORTED_RESOURCE_KINDS = {"all", "textures", "buffers"}
MAX_BUFFER_READ_SIZE = 65536
MAX_TEXTURE_PREVIEW_DIMENSION = 64
MAX_TEXTURE_PREVIEW_PIXELS = 1024
SUPPORTED_TEXTURE_EXPORT_TYPES = {
    ".dds": "DDS",
    ".hdr": "HDR",
    ".jpeg": "JPG",
    ".jpg": "JPG",
    ".png": "PNG",
}


class ResourceHandlers:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def renderdoc_list_resources(
        self,
        capture_id: str,
        kind: str = "all",
        name_filter: str | None = None,
    ) -> dict[str, Any]:
        normalized_kind = self.context.normalize_optional_string(kind) or "all"
        normalized_name_filter = self.context.normalize_optional_string(name_filter)

        if normalized_kind not in SUPPORTED_RESOURCE_KINDS:
            raise ReplayFailureError(
                "kind must be one of 'all', 'textures', or 'buffers'.",
                {"kind": normalized_kind},
            )

        params: dict[str, Any] = {"kind": normalized_kind}
        if normalized_name_filter:
            params["name_filter"] = normalized_name_filter

        session, result = self.context.capture_tool(capture_id, "list_resources", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_pixel_history(
        self,
        capture_id: str,
        texture_id: str,
        x: int,
        y: int,
        mip_level: int | None = 0,
        array_slice: int | None = 0,
        sample: int | None = 0,
    ) -> dict[str, Any]:
        params = self._normalize_pixel_params(texture_id, x, y, mip_level, array_slice, sample)
        session, result = self.context.capture_tool(capture_id, "get_pixel_history", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_debug_pixel(
        self,
        capture_id: str,
        texture_id: str,
        x: int,
        y: int,
        mip_level: int | None = 0,
        array_slice: int | None = 0,
        sample: int | None = 0,
    ) -> dict[str, Any]:
        params = self._normalize_pixel_params(texture_id, x, y, mip_level, array_slice, sample)
        session, result = self.context.capture_tool(capture_id, "debug_pixel", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_texture_data(
        self,
        capture_id: str,
        texture_id: str,
        mip_level: int,
        x: int,
        y: int,
        width: int,
        height: int,
        array_slice: int = 0,
        sample: int = 0,
    ) -> dict[str, Any]:
        params = {
            "texture_id": self.context.normalize_required_string(texture_id, "texture_id"),
            "mip_level": self.context.normalize_non_negative_int(mip_level, "mip_level"),
            "x": self.context.normalize_non_negative_int(x, "x"),
            "y": self.context.normalize_non_negative_int(y, "y"),
            "width": self.context.normalize_positive_int(width, "width"),
            "height": self.context.normalize_positive_int(height, "height"),
            "array_slice": self.context.normalize_non_negative_int(array_slice, "array_slice"),
            "sample": self.context.normalize_non_negative_int(sample, "sample"),
        }

        if params["width"] > MAX_TEXTURE_PREVIEW_DIMENSION:
            raise ReplayFailureError(
                f"width must be less than or equal to {MAX_TEXTURE_PREVIEW_DIMENSION}.",
                {"width": params["width"]},
            )
        if params["height"] > MAX_TEXTURE_PREVIEW_DIMENSION:
            raise ReplayFailureError(
                f"height must be less than or equal to {MAX_TEXTURE_PREVIEW_DIMENSION}.",
                {"height": params["height"]},
            )
        if params["width"] * params["height"] > MAX_TEXTURE_PREVIEW_PIXELS:
            raise ReplayFailureError(
                f"width * height must be less than or equal to {MAX_TEXTURE_PREVIEW_PIXELS}.",
                {"width": params["width"], "height": params["height"]},
            )

        session, result = self.context.capture_tool(capture_id, "get_texture_data", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_buffer_data(
        self,
        capture_id: str,
        buffer_id: str,
        offset: int,
        size: int,
    ) -> dict[str, Any]:
        params = {
            "buffer_id": self.context.normalize_required_string(buffer_id, "buffer_id"),
            "offset": self.context.normalize_non_negative_int(offset, "offset"),
            "size": self.context.normalize_positive_int(size, "size"),
        }

        if params["size"] > MAX_BUFFER_READ_SIZE:
            raise ReplayFailureError(
                f"size must be less than or equal to {MAX_BUFFER_READ_SIZE}.",
                {"size": params["size"]},
            )

        session, result = self.context.capture_tool(capture_id, "get_buffer_data", params)
        if "data_hex_preview" not in result and result.get("data_base64"):
            try:
                decoded = base64.b64decode(str(result["data_base64"]), validate=False)
            except Exception:
                decoded = b""
            result["data_hex_preview"] = decoded[:64].hex(" ")
        return attach_capture(ensure_meta(result), session)

    def renderdoc_save_texture_to_file(
        self,
        capture_id: str,
        texture_id: str,
        output_path: str,
        mip_level: int = 0,
        array_slice: int = 0,
    ) -> dict[str, Any]:
        normalized_output_path = self.context.normalize_required_string(output_path, "output_path")
        params = {
            "texture_id": self.context.normalize_required_string(texture_id, "texture_id"),
            "output_path": normalized_output_path,
            "mip_level": self.context.normalize_non_negative_int(mip_level, "mip_level"),
            "array_slice": self.context.normalize_non_negative_int(array_slice, "array_slice"),
        }

        extension = Path(normalized_output_path).suffix.lower()
        if extension not in SUPPORTED_TEXTURE_EXPORT_TYPES:
            raise ReplayFailureError(
                "output_path must end in one of: .dds, .hdr, .jpeg, .jpg, .png.",
                {"output_path": normalized_output_path},
            )

        session, result = self.context.capture_tool(capture_id, "save_texture_to_file", params)
        return attach_capture(ensure_meta(result), session)

    def _normalize_pixel_params(
        self,
        texture_id: str,
        x: int,
        y: int,
        mip_level: int | None,
        array_slice: int | None,
        sample: int | None,
    ) -> dict[str, Any]:
        return {
            "texture_id": self.context.normalize_required_string(texture_id, "texture_id"),
            "x": self.context.normalize_non_negative_int(x, "x"),
            "y": self.context.normalize_non_negative_int(y, "y"),
            "mip_level": self.context.normalize_non_negative_int(mip_level, "mip_level"),
            "array_slice": self.context.normalize_non_negative_int(array_slice, "array_slice"),
            "sample": self.context.normalize_non_negative_int(sample, "sample"),
        }
