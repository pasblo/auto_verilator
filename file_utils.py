from pathlib import Path


def path_contains_any(path: str, folders: list[str]) -> bool:
    """
    Return True if any item in `folders` is one path segment in `path`.
    Matching is case-insensitive.
    """
    segments = {segment.lower() for segment in Path(path).parts}
    targets = {folder.strip("\\/").lower() for folder in folders if folder}
    return any(folder in segments for folder in targets)
