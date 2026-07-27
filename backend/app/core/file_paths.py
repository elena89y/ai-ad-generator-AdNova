from pathlib import Path


def resolve_existing_file(file_path: str | Path | None, root_dir: str | Path) -> Path | None:
    """Return an existing file only when it is contained by root_dir."""
    if not file_path:
        return None
    root = Path(root_dir).resolve()
    candidate = Path(file_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def delete_file_within(file_path: str | Path | None, root_dir: str | Path) -> bool:
    candidate = resolve_existing_file(file_path, root_dir)
    if candidate is None:
        return False
    try:
        candidate.unlink()
    except OSError:
        return False
    return True
