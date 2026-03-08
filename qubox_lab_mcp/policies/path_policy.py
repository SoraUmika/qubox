"""Central path allowlist policy."""
from __future__ import annotations

from pathlib import Path

from ..config import ServerConfig
from ..errors import PathAccessError


class PathPolicy:
    """Resolve user-supplied paths under configured roots only."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.allowed_roots = [root.resolve() for root in config.allowed_roots]

    def resolve_path(
        self,
        user_path: str,
        *,
        must_exist: bool = True,
        allow_directory: bool = True,
    ) -> Path:
        raw = (user_path or "").strip()
        if not raw:
            raise PathAccessError("Path must not be empty")

        candidate = Path(raw).expanduser()
        resolved: Path | None = None

        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
            self._ensure_allowed(resolved)
        else:
            existing_candidates = []
            for root in self.allowed_roots:
                test_path = (root / candidate).resolve(strict=False)
                try:
                    self._ensure_allowed(test_path)
                except PathAccessError:
                    continue
                if test_path.exists():
                    existing_candidates.append(test_path)
            resolved = existing_candidates[0] if existing_candidates else (self.allowed_roots[0] / candidate).resolve(strict=False)
            self._ensure_allowed(resolved)

        if must_exist and not resolved.exists():
            raise PathAccessError("Path does not exist", path=str(resolved))
        if resolved.exists() and resolved.is_dir() and not allow_directory:
            raise PathAccessError("Expected a file path, got a directory", path=str(resolved))
        if resolved.exists() and not allow_directory and not resolved.is_file():
            raise PathAccessError("Expected a regular file", path=str(resolved))
        self._reject_excluded(resolved)
        return resolved

    def display_path(self, path: Path) -> str:
        resolved = path.resolve(strict=False)
        for root in self.allowed_roots:
            try:
                return resolved.relative_to(root).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()

    def _ensure_allowed(self, path: Path) -> None:
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return
            except ValueError:
                continue
        raise PathAccessError("Path is outside allowed roots", path=str(path), allowed_roots=[str(root) for root in self.allowed_roots])

    def _reject_excluded(self, path: Path) -> None:
        excluded = self.config.excluded_names
        for part in path.parts:
            if part in excluded:
                raise PathAccessError("Path points to an excluded location", path=str(path), excluded=part)
