from __future__ import annotations

from pathlib import Path

from renderdoc_mcp.native_helper import _iter_dll_search_dirs


def test_iter_dll_search_dirs_discovers_embedded_python_runtime(tmp_path: Path) -> None:
    repo_root = tmp_path / "renderdoc"
    module_dir = repo_root / "x64" / "Development" / "pymodules"
    dll_dir = repo_root / "x64" / "Development"
    python_dir = repo_root / "qrenderdoc" / "3rdparty" / "python" / "x64"
    module_dir.mkdir(parents=True)
    dll_dir.mkdir(parents=True, exist_ok=True)
    python_dir.mkdir(parents=True)
    (python_dir / "python36.dll").write_bytes(b"")

    search_dirs = _iter_dll_search_dirs(str(module_dir), str(dll_dir))

    assert search_dirs == [
        str(module_dir.resolve()),
        str(dll_dir.resolve()),
        str(python_dir.resolve()),
    ]


def test_iter_dll_search_dirs_de_duplicates_candidates(tmp_path: Path) -> None:
    module_dir = tmp_path / "pymodules"
    module_dir.mkdir()

    search_dirs = _iter_dll_search_dirs(str(module_dir), str(module_dir))

    assert search_dirs == [str(module_dir.resolve())]
