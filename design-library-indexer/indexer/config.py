"""
Indexer configuration — all tunable settings in one place.
"""

from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class IndexerConfig:
    """Central configuration for the design library indexer."""

    # ── Paths ──────────────────────────────────────────────────────────
    library_root: Path = Path("/mnt/design-library")
    index_metadata_dir: Path = Path("/mnt/design-library/.index")
    chroma_persist_dir: Path = Path("/home/rpi/ai-engine/chroma_data")
    chroma_collection_name: str = "design_library"

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
    # We aim for ~1500 chars (~375 tokens) per chunk for granularity.
    chunk_target_chars: int = 1000
    chunk_max_chars: int = 2000
    chunk_min_chars: int = 100  # skip tiny fragments

    # ── Indexing Behavior ──────────────────────────────────────────────
    batch_size: int = 100  # ChromaDB upsert batch size (increased for Pi)
    max_file_size_bytes: int = 500_000  # 500KB — skip huge files
    hash_algorithm: str = "sha256"
    log_every_n_files: int = 25  # Log more frequently for progress tracking

    # ── Directories to index (relative to library_root) ────────────────
    index_paths: list = field(default_factory=lambda: [
        "example-websites",
        "components",
        "seo-configs",
        "style-guides",
    ])
