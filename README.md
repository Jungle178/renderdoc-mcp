# renderdoc-mcp

Language: [English](#en) | [简体中文](#zh-cn)

<a id="en"></a>
<details open>
<summary><strong>English</strong></summary>

## English

`renderdoc-mcp` is a local stdio MCP server for inspecting existing RenderDoc `.rdc` captures on Windows.

It launches `qrenderdoc.exe`, installs a bundled RenderDoc Python extension into `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`, and bridges MCP tool calls to RenderDoc's embedded Python API over a localhost socket.

Each call to `renderdoc_open_capture` creates a new capture session and returns a `capture_id`. Subsequent tools reuse that session through `capture_id` until you close it or it is evicted by the idle timeout.

## Version support

- Minimum supported RenderDoc version: `1.43`
- Verified baseline: `1.43`
- Newer RenderDoc builds are supported on a best-effort forward-compatible basis with API fallbacks where practical

## Features

- `renderdoc_open_capture`
- `renderdoc_close_capture`
- `renderdoc_get_capture_summary`
- `renderdoc_analyze_frame`
- `renderdoc_get_action_tree`
- `renderdoc_list_actions`
- `renderdoc_list_passes`
- `renderdoc_get_pass_details`
- `renderdoc_get_timing_data`
- `renderdoc_get_performance_hotspots`
- `renderdoc_get_action_details`
- `renderdoc_get_pipeline_state`
- `renderdoc_get_api_pipeline_state`
- `renderdoc_get_shader_code`
- `renderdoc_list_resources`
- `renderdoc_get_pixel_history`
- `renderdoc_debug_pixel`
- `renderdoc_get_texture_data`
- `renderdoc_get_buffer_data`
- `renderdoc_save_texture_to_file`
- `renderdoc://recent-captures`
- `renderdoc://capture/{capture_id}/summary`

## Quick start

Open a capture first:

```powershell
renderdoc_open_capture(capture_path="C:\\captures\\frame.rdc")
```

The response includes `capture_id`, `capture_path`, and `meta.renderdoc_version` when the bridge reports it.

Use that `capture_id` for all follow-up tools:

```powershell
renderdoc_get_capture_summary(capture_id="<capture_id>")
```

```powershell
renderdoc_analyze_frame(capture_id="<capture_id>")
```

When you are done:

```powershell
renderdoc_close_capture(capture_id="<capture_id>")
```

## Frame analysis

For a quick pass summary:

```powershell
renderdoc_analyze_frame(capture_id="<capture_id>")
```

The result includes:

- ordered top-level passes
- `pass_id`, category, confidence, reasons, and event ranges
- draw-heavy and compute-heavy pass rankings
- the tail chain leading into UI and presentation

To include a top-level pass timing summary when GPU duration counters are available:

```powershell
renderdoc_analyze_frame(
  capture_id="<capture_id>",
  include_timing_summary=true
)
```

To drill into a specific pass:

1. Call `renderdoc_list_passes(capture_id=..., limit=100)`.
2. Pick a `pass_id`.
3. Call `renderdoc_get_pass_details(capture_id=..., pass_id=...)`.

To add timing data to a pass:

```powershell
renderdoc_get_timing_data(capture_id="<capture_id>", pass_id="pass:100-250")
```

For frame-level hotspots:

```powershell
renderdoc_get_performance_hotspots(capture_id="<capture_id>")
```

If the replay device exposes `GPUCounter.EventGPUDuration`, hotspots are ranked by real GPU time. Otherwise the tool falls back to draw, dispatch, copy, and clear heuristics.

For quick pass triage, `renderdoc_list_passes` can sort by GPU time or structural metrics:

```powershell
renderdoc_list_passes(
  capture_id="<capture_id>",
  sort_by="gpu_time",
  threshold_ms=0.5,
  limit=20
)
```

If GPU timing is unavailable, `sort_by="gpu_time"` falls back to event order and reports that in the result.

## Actions and pipeline state

`renderdoc_get_action_tree` returns a tree preview of the action hierarchy:

```powershell
renderdoc_get_action_tree(capture_id="<capture_id>", max_depth=2)
```

To page through the full action list:

```powershell
renderdoc_list_actions(capture_id="<capture_id>", cursor=0, limit=100)
```

To fetch API-agnostic pipeline details:

```powershell
renderdoc_get_pipeline_state(capture_id="<capture_id>", event_id=1234)
```

To fetch API-specific pipeline details when implemented for the capture API:

```powershell
renderdoc_get_api_pipeline_state(capture_id="<capture_id>", event_id=1234)
```

On D3D12 this can include descriptor heap and root signature details. On Vulkan it can include pipeline, descriptor set or descriptor buffer, and current render pass information. If the active RenderDoc build does not expose a compatible API-specific accessor, the response reports `available: false` instead of failing the whole tool call.

To fetch shader disassembly for a specific event and stage:

```powershell
renderdoc_get_shader_code(capture_id="<capture_id>", event_id=1234, stage="pixel")
```

If a newer RenderDoc build changes the shader disassembly API surface, the response keeps the shader metadata and reports the disassembly as unavailable instead of failing the request where possible.

## Resources and pixel inspection

Start by listing resources:

```powershell
renderdoc_list_resources(capture_id="<capture_id>", kind="all")
```

Use the returned resource IDs for content inspection:

```powershell
renderdoc_get_texture_data(
  capture_id="<capture_id>",
  texture_id="1234567890",
  mip_level=0,
  x=0,
  y=0,
  width=4,
  height=4
)
```

```powershell
renderdoc_get_buffer_data(
  capture_id="<capture_id>",
  buffer_id="9876543210",
  offset=0,
  size=64
)
```

To export a texture to disk:

```powershell
renderdoc_save_texture_to_file(
  capture_id="<capture_id>",
  texture_id="1234567890",
  output_path="C:\\captures\\albedo.png"
)
```

For pixel history against a specific texture and subresource:

```powershell
renderdoc_get_pixel_history(
  capture_id="<capture_id>",
  texture_id="1234567890",
  x=512,
  y=384
)
```

To collapse that history into a draw-centric impact summary:

```powershell
renderdoc_debug_pixel(
  capture_id="<capture_id>",
  texture_id="1234567890",
  x=512,
  y=384
)
```

## Install

```powershell
uv sync --group dev
uv run renderdoc-install-extension
```

The installer always copies the bundled extension into `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`.

By default it also ensures that `%APPDATA%\qrenderdoc\UI.config` contains `renderdoc_mcp_bridge` inside `AlwaysLoad_Extensions`.

Behavior details:

- The installer only changes the `AlwaysLoad_Extensions` key.
- If `renderdoc_mcp_bridge` is already present, it leaves `UI.config` untouched.
- It does not rewrite unrelated keys.

To install the extension without modifying `UI.config`:

```powershell
uv run renderdoc-install-extension --no-always-load
```

You can also disable the `UI.config` update for both manual installs and automatic startup installs:

```powershell
$env:RENDERDOC_INSTALL_ALWAYS_LOAD = "0"
```

## Run

```powershell
uv run renderdoc-mcp
```

Optional environment variables:

- `RENDERDOC_QRENDERDOC_PATH`: absolute path to `qrenderdoc.exe`
- `RENDERDOC_BRIDGE_TIMEOUT_SECONDS`: handshake timeout, default `30`
- `RENDERDOC_CAPTURE_SESSION_IDLE_SECONDS`: idle timeout in seconds for per-capture sessions, default `300`; set to `0` or a negative value to disable idle eviction
- `RENDERDOC_INSTALL_ALWAYS_LOAD`: `0/false/no/off` to skip editing `UI.config` during extension installation

## Claude Desktop example

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to-renderdoc-mcp>", "renderdoc-mcp"]
    }
  }
}
```

Replace `<path-to-renderdoc-mcp>` with your local checkout path.

## Tests

```powershell
uv run pytest
uv run pytest -m integration
```

</details>

<a id="zh-cn"></a>
<details>
<summary><strong>简体中文</strong></summary>

## 简体中文

`renderdoc-mcp` 是一个运行在 Windows 上、通过 stdio 提供服务的本地 MCP Server，用于检查现有的 RenderDoc `.rdc` capture。

它会启动 `qrenderdoc.exe`，把随仓库提供的 RenderDoc Python 扩展安装到 `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`，然后通过 localhost socket 将 MCP 工具调用桥接到 RenderDoc 内嵌 Python API。

每次调用 `renderdoc_open_capture` 都会创建一个新的 capture session，并返回一个 `capture_id`。后续工具会通过 `capture_id` 复用这个 session，直到你主动关闭它，或它因空闲超时被驱逐。

## 版本支持

- 最低支持的 RenderDoc 版本：`1.43`
- 已验证基线版本：`1.43`
- 对更新版本的 RenderDoc 采用尽力而为的前向兼容策略，并在可行处提供 API 降级处理

## 功能

- `renderdoc_open_capture`
- `renderdoc_close_capture`
- `renderdoc_get_capture_summary`
- `renderdoc_analyze_frame`
- `renderdoc_get_action_tree`
- `renderdoc_list_actions`
- `renderdoc_list_passes`
- `renderdoc_get_pass_details`
- `renderdoc_get_timing_data`
- `renderdoc_get_performance_hotspots`
- `renderdoc_get_action_details`
- `renderdoc_get_pipeline_state`
- `renderdoc_get_api_pipeline_state`
- `renderdoc_get_shader_code`
- `renderdoc_list_resources`
- `renderdoc_get_pixel_history`
- `renderdoc_debug_pixel`
- `renderdoc_get_texture_data`
- `renderdoc_get_buffer_data`
- `renderdoc_save_texture_to_file`
- `renderdoc://recent-captures`
- `renderdoc://capture/{capture_id}/summary`

## 快速开始

先打开一个 capture：

```powershell
renderdoc_open_capture(capture_path="C:\\captures\\frame.rdc")
```

返回结果里会包含 `capture_id`、`capture_path`，以及 bridge 上报时带回的 `meta.renderdoc_version`。

后续所有工具都使用这个 `capture_id`：

```powershell
renderdoc_get_capture_summary(capture_id="<capture_id>")
```

```powershell
renderdoc_analyze_frame(capture_id="<capture_id>")
```

完成后关闭 session：

```powershell
renderdoc_close_capture(capture_id="<capture_id>")
```

## 帧分析

快速查看 pass 摘要：

```powershell
renderdoc_analyze_frame(capture_id="<capture_id>")
```

返回结果包括：

- 按顺序排列的顶层 pass
- `pass_id`、分类、置信度、判定原因和事件范围
- draw 密集型和 compute 密集型 pass 排名
- 指向 UI 和 present 的尾部调用链

如果 replay 设备支持 GPU duration counter，也可以附带顶层 pass 的 timing 摘要：

```powershell
renderdoc_analyze_frame(
  capture_id="<capture_id>",
  include_timing_summary=true
)
```

查看某个具体 pass 的方式：

1. 调用 `renderdoc_list_passes(capture_id=..., limit=100)`。
2. 选一个 `pass_id`。
3. 调用 `renderdoc_get_pass_details(capture_id=..., pass_id=...)`。

为某个 pass 拉取 timing 数据：

```powershell
renderdoc_get_timing_data(capture_id="<capture_id>", pass_id="pass:100-250")
```

查看整帧热点：

```powershell
renderdoc_get_performance_hotspots(capture_id="<capture_id>")
```

如果 replay 设备暴露了 `GPUCounter.EventGPUDuration`，热点会按真实 GPU 时间排序。否则工具会退回到 draw、dispatch、copy 和 clear 等启发式规则。

快速筛查 pass 时，`renderdoc_list_passes` 支持按 GPU 时间或结构化指标排序：

```powershell
renderdoc_list_passes(
  capture_id="<capture_id>",
  sort_by="gpu_time",
  threshold_ms=0.5,
  limit=20
)
```

如果 GPU timing 不可用，`sort_by="gpu_time"` 会自动回退到事件顺序，并在返回结果中说明这一点。

## Action 与 Pipeline State

`renderdoc_get_action_tree` 会返回 action 层级树的预览：

```powershell
renderdoc_get_action_tree(capture_id="<capture_id>", max_depth=2)
```

如需按页遍历完整 action 列表：

```powershell
renderdoc_list_actions(capture_id="<capture_id>", cursor=0, limit=100)
```

获取与 API 无关的 pipeline 详情：

```powershell
renderdoc_get_pipeline_state(capture_id="<capture_id>", event_id=1234)
```

获取与具体图形 API 相关的 pipeline 详情：

```powershell
renderdoc_get_api_pipeline_state(capture_id="<capture_id>", event_id=1234)
```

在 D3D12 上，这可能包含 descriptor heap 和 root signature 细节。在 Vulkan 上，这可能包含 pipeline、descriptor set 或 descriptor buffer，以及当前 render pass 信息。如果当前 RenderDoc 版本没有暴露兼容的 API-specific accessor，响应会返回 `available: false`，而不是让整条工具调用失败。

查看某个 event 和 shader stage 的反汇编：

```powershell
renderdoc_get_shader_code(capture_id="<capture_id>", event_id=1234, stage="pixel")
```

如果更高版本的 RenderDoc 调整了 shader disassembly 相关 API，响应会尽量保留 shader 元数据，并把 disassembly 标记为 unavailable，而不是直接失败。

## 资源与像素检查

先列出资源：

```powershell
renderdoc_list_resources(capture_id="<capture_id>", kind="all")
```

使用返回的 resource ID 做内容检查：

```powershell
renderdoc_get_texture_data(
  capture_id="<capture_id>",
  texture_id="1234567890",
  mip_level=0,
  x=0,
  y=0,
  width=4,
  height=4
)
```

```powershell
renderdoc_get_buffer_data(
  capture_id="<capture_id>",
  buffer_id="9876543210",
  offset=0,
  size=64
)
```

把 texture 导出到磁盘：

```powershell
renderdoc_save_texture_to_file(
  capture_id="<capture_id>",
  texture_id="1234567890",
  output_path="C:\\captures\\albedo.png"
)
```

查看某个 texture 像素和子资源上的 pixel history：

```powershell
renderdoc_get_pixel_history(
  capture_id="<capture_id>",
  texture_id="1234567890",
  x=512,
  y=384
)
```

把 pixel history 压缩成以 draw 为中心的影响摘要：

```powershell
renderdoc_debug_pixel(
  capture_id="<capture_id>",
  texture_id="1234567890",
  x=512,
  y=384
)
```

## 安装

```powershell
uv sync --group dev
uv run renderdoc-install-extension
```

安装器始终会把随仓库提供的扩展复制到 `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`。

默认情况下，它还会确保 `%APPDATA%\qrenderdoc\UI.config` 的 `AlwaysLoad_Extensions` 中包含 `renderdoc_mcp_bridge`。

具体行为：

- 安装器只会修改 `AlwaysLoad_Extensions` 这一项。
- 如果 `renderdoc_mcp_bridge` 已经存在，就不会改写 `UI.config`。
- 不会重写其他无关键。

如果你只想安装扩展、不修改 `UI.config`：

```powershell
uv run renderdoc-install-extension --no-always-load
```

你也可以通过环境变量同时关闭手动安装和自动启动安装时对 `UI.config` 的修改：

```powershell
$env:RENDERDOC_INSTALL_ALWAYS_LOAD = "0"
```

## 运行

```powershell
uv run renderdoc-mcp
```

可选环境变量：

- `RENDERDOC_QRENDERDOC_PATH`：`qrenderdoc.exe` 的绝对路径
- `RENDERDOC_BRIDGE_TIMEOUT_SECONDS`：握手超时，默认 `30`
- `RENDERDOC_CAPTURE_SESSION_IDLE_SECONDS`：单个 capture session 的空闲超时时间，默认 `300` 秒；设为 `0` 或负数可禁用空闲驱逐
- `RENDERDOC_INSTALL_ALWAYS_LOAD`：设为 `0/false/no/off` 可在安装扩展时跳过 `UI.config` 修改

## Claude Desktop 配置示例

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to-renderdoc-mcp>", "renderdoc-mcp"]
    }
  }
}
```

请把 `<path-to-renderdoc-mcp>` 替换为你的本地仓库路径。

## 测试

```powershell
uv run pytest
uv run pytest -m integration
```

</details>
