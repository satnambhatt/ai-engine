"""
File discovery — walks the design library, filters files, detects changes.

Uses SHA256 hashing to skip files that haven't changed since last index run.
This is critical on a Pi where re-embedding everything takes hours.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .config import IndexerConfig

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredFile:
    """A file discovered in the design library."""
    path: Path
    relative_path: str        # relative to library_root
    extension: str
    size_bytes: int
    sha256: str
    framework: str             # detected framework: html, react, nextjs, astro, vue, svelte, css, config
    repo_name: str             # parent git repo name (if under example-websites/)
    component_category: str    # header, hero, footer, etc. (if under components/)
    file_type: str             # "code" or "config"


class FileDiscovery:
    """Walks the design library and yields files to index."""

    def __init__(self, config: IndexerConfig):
        self.config = config
        self.hash_file = config.index_metadata_dir / "file_hashes.json"
        self._previous_hashes: dict[str, str] = {}
        self._current_hashes: dict[str, str] = {}

    def load_previous_hashes(self) -> None:
        """Load hashes from last indexing run for change detection."""
        if self.hash_file.exists():
            try:
                with open(self.hash_file, "r") as f:
                    self._previous_hashes = json.load(f)
                logger.info(f"Loaded {len(self._previous_hashes)} previous file hashes")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not load previous hashes: {e}")
                self._previous_hashes = {}
        else:
            logger.info("No previous hash file found — full index will run")

    def save_current_hashes(self) -> None:
        """Persist current hashes for next run."""
        self.config.index_metadata_dir.mkdir(parents=True, exist_ok=True)
        with open(self.hash_file, "w") as f:
            json.dump(self._current_hashes, f, indent=2)
        logger.info(f"Saved {len(self._current_hashes)} file hashes")

    def discover(self, incremental: bool = True):
        """
        Walk the library and yield DiscoveredFile objects.

        Args:
            incremental: If True, skip files whose hash hasn't changed.
                         Set False for a full re-index.

        Yields:
            DiscoveredFile for each file that needs indexing.
        """
        if incremental:
            self.load_previous_hashes()

        stats = {"total_walked": 0, "skipped_dir": 0, "skipped_ext": 0,
                 "skipped_name": 0, "skipped_size": 0, "skipped_unchanged": 0,
                 "yielded_code": 0, "yielded_config": 0}

        for index_subdir in self.config.index_paths:
            root_path = self.config.library_root / index_subdir
            if not root_path.exists():
                logger.warning(f"Index path does not exist: {root_path}")
                continue

            for dirpath, dirnames, filenames in os.walk(root_path):
                # Prune skip directories IN-PLACE (prevents os.walk from descending)
                dirnames[:] = [
                    d for d in dirnames
                    if d not in self.config.skip_directories
                ]

                for filename in filenames:
                    stats["total_walked"] += 1
                    filepath = Path(dirpath) / filename

                    # ── Filter: skip by filename ──
                    if filename in self.config.skip_filenames:
                        stats["skipped_name"] += 1
                        continue

                    # ── Filter: skip by extension ──
                    ext = self._get_extension(filename)
                    if ext in self.config.skip_extensions:
                        stats["skipped_ext"] += 1
                        continue

                    # ── Determine file type ──
                    if ext in self.config.code_extensions:
                        file_type = "code"
                    elif ext in self.config.config_extensions and filename in self.config.config_filenames:
                        file_type = "config"
                    elif ext in self.config.code_extensions:
                        file_type = "code"
                    else:
                        # Not a file type we care about
                        stats["skipped_ext"] += 1
                        continue

                    # ── Filter: skip by size ──
                    try:
                        size = filepath.stat().st_size
                    except OSError:
                        continue
                    if size > self.config.max_file_size_bytes:
                        stats["skipped_size"] += 1
                        continue
                    if size == 0:
                        continue

                    # ── Hash for change detection ──
                    file_hash = self._hash_file(filepath)
                    rel_path = str(filepath.relative_to(self.config.library_root))
                    self._current_hashes[rel_path] = file_hash

                    if incremental and self._previous_hashes.get(rel_path) == file_hash:
                        stats["skipped_unchanged"] += 1
                        continue

                    # ── Extract metadata ──
                    framework = self._detect_framework(filepath, ext)
                    repo_name = self._detect_repo_name(filepath)
                    component_category = self._detect_component_category(filepath)

                    discovered = DiscoveredFile(
                        path=filepath,
                        relative_path=rel_path,
                        extension=ext,
                        size_bytes=size,
                        sha256=file_hash,
                        framework=framework,
                        repo_name=repo_name,
                        component_category=component_category,
                        file_type=file_type,
                    )

                    if file_type == "code":
                        stats["yielded_code"] += 1
                    else:
                        stats["yielded_config"] += 1

                    if stats["total_walked"] % self.config.log_every_n_files == 0:
                        logger.info(f"Progress: walked {stats['total_walked']} files...")

                    yield discovered

        logger.info(
            f"Discovery complete: walked={stats['total_walked']}, "
            f"code={stats['yielded_code']}, config={stats['yielded_config']}, "
            f"skipped_unchanged={stats['skipped_unchanged']}, "
            f"skipped_dir={stats['skipped_dir']}, skipped_ext={stats['skipped_ext']}, "
            f"skipped_name={stats['skipped_name']}, skipped_size={stats['skipped_size']}"
        )

    def count_indexable_files(self, incremental: bool = True) -> int:
        """
        Fast pre-count of files that will be indexed.

        Walks the same paths and applies the same filters as discover(),
        but skips hashing to stay fast. For incremental runs, it hashes
        to check against previous hashes (same cost as discover).
        """
        if incremental:
            self.load_previous_hashes()

        count = 0
        for index_subdir in self.config.index_paths:
            root_path = self.config.library_root / index_subdir
            if not root_path.exists():
                continue

            for dirpath, dirnames, filenames in os.walk(root_path):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in self.config.skip_directories
                ]

                for filename in filenames:
                    if filename in self.config.skip_filenames:
                        continue

                    ext = self._get_extension(filename)
                    if ext in self.config.skip_extensions:
                        continue

                    if ext not in self.config.code_extensions:
                        if not (ext in self.config.config_extensions and filename in self.config.config_filenames):
                            continue

                    filepath = Path(dirpath) / filename
                    try:
                        size = filepath.stat().st_size
                    except OSError:
                        continue
                    if size > self.config.max_file_size_bytes or size == 0:
                        continue

                    if incremental:
                        file_hash = self._hash_file(filepath)
                        rel_path = str(filepath.relative_to(self.config.library_root))
                        if self._previous_hashes.get(rel_path) == file_hash:
                            continue

                    count += 1

        return count

    def get_deleted_files(self) -> list[str]:
        """Return relative paths of files that existed last run but are now gone."""
        previous_keys = set(self._previous_hashes.keys())
        current_keys = set(self._current_hashes.keys())
        return list(previous_keys - current_keys)

    # ── Private helpers ────────────────────────────────────────────────

    def _get_extension(self, filename: str) -> str:
        """Get file extension, handling compound extensions like .min.js"""
        if filename.endswith(".min.js"):
            return ".min.js"
        if filename.endswith(".min.css"):
            return ".min.css"
        return Path(filename).suffix.lower()

    def _hash_file(self, filepath: Path) -> str:
        """SHA256 hash of file contents."""
        h = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def _detect_framework(self, filepath: Path, ext: str) -> str:
        """Detect the framework based on file extension and path context."""
        path_str = str(filepath).lower()

        if ext == ".astro":
            return "astro"
        if ext == ".vue":
            return "vue"
        if ext == ".svelte":
            return "svelte"
        if ext in (".jsx", ".tsx"):
            # Distinguish React from Next.js
            if "/pages/" in path_str or "/app/" in path_str:
                if "next.config" in path_str or "/nextjs/" in path_str or "/.next/" in path_str:
                    return "nextjs"
            # Check if parent dirs suggest Next.js
            parts = filepath.parts
            for part in parts:
                if "next" in part.lower():
                    return "nextjs"
            return "react"
        if ext == ".ts":
            return "typescript"
        if ext in (".css", ".scss", ".sass"):
            return "css"
        if ext in (".html", ".htm"):
            return "html"
        if ext == ".js":
            return "javascript"
        return "unknown"

    def _detect_repo_name(self, filepath: Path) -> str:
        """Extract the git repo directory name if under example-websites/."""
        try:
            rel = filepath.relative_to(self.config.library_root / "example-websites")
            # The repo name is the second path component
            # e.g., example-websites/react/shadcn-taxonomy/src/...
            #        parts[0]=react, parts[1]=shadcn-taxonomy
            parts = rel.parts
            if len(parts) >= 2:
                return parts[1]
            elif len(parts) >= 1:
                return parts[0]
        except ValueError:
            pass
        return ""

    def _detect_component_category(self, filepath: Path) -> str:
        """Detect component category from path or filename."""
        path_lower = str(filepath).lower()
        name_lower = filepath.stem.lower()

        categories = {
            "header": ["header", "navbar", "nav-bar", "navigation", "topbar", "top-bar"],
            "hero": ["hero", "banner", "jumbotron", "landing-hero", "above-fold"],
            "footer": ["footer", "bottom-bar", "site-footer"],
            "pricing": ["pricing", "price-table", "price-card", "plan"],
            "testimonial": ["testimonial", "review", "quote", "social-proof"],
            "contact": ["contact", "contact-form", "get-in-touch"],
            "cta": ["cta", "call-to-action", "signup"],
            "feature": ["feature", "features", "benefit", "services"],
            "faq": ["faq", "accordion", "questions"],
            "404": ["404", "not-found", "error-page"],
            "auth": ["login", "signin", "signup", "register", "auth"],
            "sidebar": ["sidebar", "side-nav", "drawer"],
            "card": ["card", "cards", "grid-card"],
            "modal": ["modal", "dialog", "popup"],
            "form": ["form", "input", "field"],
            "table": ["table", "data-table", "grid"],
            "layout": ["layout", "page-layout", "wrapper", "shell"],
        }

        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in name_lower or f"/{keyword}" in path_lower:
                    return category

        return ""
