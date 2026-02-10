"""File discovery — walk codebase, filter by language, compute hashes."""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from ..models import FileInfo, ImageFileInfo

log = logging.getLogger("ollqd.discovery")

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".go": "go",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".rs": "rust",
    ".java": "java", ".kt": "kotlin", ".scala": "scala",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql",
    ".r": "r", ".R": "r",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".json": "json",
    ".md": "markdown", ".rst": "restructuredtext",
    ".tf": "terraform", ".hcl": "hcl",
    ".dockerfile": "dockerfile",
    ".proto": "protobuf",
    ".graphql": "graphql", ".gql": "graphql",
}

SKIP_DIRS: set[str] = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", ".venv", "venv", "env", ".env",
    "dist", "build", "target", "out", "bin", "obj",
    ".next", ".nuxt", ".output",
    "vendor", "third_party",
    ".idea", ".vscode",
    "coverage", ".coverage",
}

SKIP_FILES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.sum", "Cargo.lock", "poetry.lock", "uv.lock",
    "Pipfile.lock", "composer.lock", "Gemfile.lock",
}


def discover_files(
    root: Path,
    max_file_size_kb: int = 512,
    extra_skip_dirs: Optional[set[str]] = None,
) -> list[FileInfo]:
    """Walk the codebase and collect indexable files."""
    skip = SKIP_DIRS | (extra_skip_dirs or set())
    files: list[FileInfo] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]

        for fname in filenames:
            if fname in SKIP_FILES:
                continue

            ext = Path(fname).suffix.lower()
            if fname.lower() == "dockerfile":
                ext = ".dockerfile"

            if ext not in LANGUAGE_MAP:
                continue

            full = Path(dirpath) / fname
            try:
                stat = full.stat()
            except OSError:
                continue

            if stat.st_size > max_file_size_kb * 1024:
                continue

            try:
                content = full.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()
            except (OSError, PermissionError):
                continue

            files.append(FileInfo(
                path=str(full.relative_to(root)),
                abs_path=str(full),
                language=LANGUAGE_MAP[ext],
                size_bytes=stat.st_size,
                content_hash=content_hash,
            ))

    log.info("Discovered %d indexable files", len(files))
    return files


IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}


def discover_images(
    root: Path,
    max_image_size_kb: int = 10240,
    extra_skip_dirs: Optional[set[str]] = None,
) -> list[ImageFileInfo]:
    """Walk directory tree and collect image files."""
    skip = SKIP_DIRS | (extra_skip_dirs or set())
    images: list[ImageFileInfo] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue

            full = Path(dirpath) / fname
            try:
                stat = full.stat()
            except OSError:
                continue

            if stat.st_size > max_image_size_kb * 1024:
                continue

            try:
                content = full.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()
            except (OSError, PermissionError):
                continue

            width, height = None, None
            try:
                from PIL import Image
                with Image.open(full) as img:
                    width, height = img.size
            except Exception:
                pass

            images.append(ImageFileInfo(
                path=str(full.relative_to(root)),
                abs_path=str(full),
                extension=ext,
                size_bytes=stat.st_size,
                content_hash=content_hash,
                width=width,
                height=height,
            ))

    log.info("Discovered %d image files", len(images))
    return images
