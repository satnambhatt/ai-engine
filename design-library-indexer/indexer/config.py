"""
Indexer configuration — all tunable settings in one place.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

_EXTERNAL_BASE = Path("/mnt/design-library")
_LOCAL_BASE = Path("/home/rpi/ai-engine")


def _use_external_drive() -> bool:
    """Read USE_EXTERNAL_DRIVE from env. Defaults to True (external drive)."""
    return os.environ.get("USE_EXTERNAL_DRIVE", "true").lower() not in ("false", "0", "no")


@dataclass
class IndexerConfig:
    """Central configuration for the design library indexer."""

    # ── Storage mode ───────────────────────────────────────────────────
    # Set USE_EXTERNAL_DRIVE=false in /home/rpi/ai-engine/.env (or env)
    # to store everything under /home/rpi/ai-engine/ instead.
    use_external_drive: bool = field(default_factory=_use_external_drive)

    # ── Paths — computed in __post_init__ based on use_external_drive ──
    # Can be overridden after construction (e.g. config.library_root = Path(...))
    library_root: Path = field(default=None)
    index_metadata_dir: Path = field(default=None)
    chroma_persist_dir: Path = field(default=None)
    chroma_collection_name: str = "design_library"

    def __post_init__(self):
        if self.library_root is None:
            self.library_root = (
                _EXTERNAL_BASE if self.use_external_drive
                else _LOCAL_BASE / "design-library"
            )
        if self.index_metadata_dir is None:
            self.index_metadata_dir = self.library_root / ".index"
        if self.chroma_persist_dir is None:
            self.chroma_persist_dir = (
                _EXTERNAL_BASE / "chroma_data" if self.use_external_drive
                else _LOCAL_BASE / "chroma_data"
            )

    # ── Ollama ─────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    # nomic-embed-text max input is 8192 tokens (~6000 words).
    # High quality embeddings but slower on Pi hardware.
    # Our chunk sizes (1000-2000 chars) are well below this limit.

    # ── File Discovery ─────────────────────────────────────────────────
    # Extensions that get chunked, embedded, and stored
    code_extensions: frozenset = frozenset({
        ".html", ".htm", ".css", ".scss", ".sass",
        ".js", ".jsx", ".tsx", ".ts",
        ".vue", ".svelte", ".astro",
    })

    # Extensions indexed as metadata only (not chunked)
    config_extensions: frozenset = frozenset({
        ".json", ".yaml", ".yml", ".toml",
    })

    # Config filenames we specifically care about
    config_filenames: frozenset = frozenset({
        "package.json", "tailwind.config.js", "tailwind.config.ts",
        "tailwind.config.mjs", "next.config.js", "next.config.mjs",
        "next.config.ts", "astro.config.mjs", "astro.config.ts",
        "vite.config.js", "vite.config.ts", "nuxt.config.ts",
        "svelte.config.js", "tsconfig.json",
    })

    # ── Skip Patterns ──────────────────────────────────────────────────
    skip_directories: frozenset = frozenset({
        "node_modules", ".git", ".github", ".vscode", ".idea",
        "dist", "build", ".next", ".output", ".nuxt", ".svelte-kit",
        ".astro", "__pycache__", ".cache", ".turbo", ".vercel",
        "coverage", ".nyc_output", "storybook-static",
        ".index",  # our own metadata directory
    })

    skip_extensions: frozenset = frozenset({
        # Minified
        ".min.js", ".min.css",
        # Source maps
        ".map",
        # Images
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
        ".bmp", ".tiff", ".avif",
        # Fonts
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
        # Media
        ".mp4", ".webm", ".mp3", ".ogg", ".wav",
        # Archives
        ".zip", ".tar", ".gz", ".br",
        # Lock files
        ".lock",
        # Misc binary
        ".pdf", ".doc", ".docx", ".psd", ".ai", ".sketch", ".fig",
    })

    skip_filenames: frozenset = frozenset({
        "LICENSE", "LICENSE.md", "LICENSE.txt",
        "CHANGELOG.md", "CHANGELOG.txt",
        "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
        ".gitignore", ".gitattributes",
        ".eslintrc", ".eslintrc.js", ".eslintrc.json",
        ".prettierrc", ".prettierrc.js", ".prettierrc.json",
        ".editorconfig", ".npmrc", ".nvmrc",
        "yarn.lock", "package-lock.json", "pnpm-lock.yaml",
        "bun.lockb",
        ".env", ".env.local", ".env.example",
    })

    # ── Chunking ───────────────────────────────────────────────────────
    # Target chunk size in characters (not tokens).
    # nomic-embed-text handles ~8192 tokens. 1 token ≈ 4 chars.
    # We aim for ~2000 chars (~500 tokens) per chunk — halves embedding API calls.
    chunk_target_chars: int = 2000
    chunk_max_chars: int = 4000
    chunk_min_chars: int = 200  # skip tiny fragments

    # ── Indexing Behavior ──────────────────────────────────────────────
    batch_size: int = 200  # ChromaDB upsert batch size
    max_file_size_bytes: int = 500_000  # 500KB — skip huge files
    hash_algorithm: str = "sha256"
    log_every_n_files: int = 1  # Log progress after every file

    # ── Directories to index (relative to library_root) ────────────────
    index_paths: list = field(default_factory=lambda: [
        "example-websites",
        "components",
        "seo-configs",
        "style-guides",
    ])
