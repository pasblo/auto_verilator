from __future__ import annotations

from pathlib import Path


def path_contains_any(path: str, folders: list[str]) -> bool:
    """Return True if any item in ``folders`` matches one path segment in
    ``path``. Matching is case-insensitive."""
    segments = {segment.lower() for segment in Path(path).parts}
    targets = {folder.strip("\\/").lower() for folder in folders if folder}
    return any(folder in segments for folder in targets)


def resolve_user_path(path_value: str) -> Path:
    """Resolve a user-supplied path: expand ``~`` and anchor relative paths
    at the current working directory."""
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path
