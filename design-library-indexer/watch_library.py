#!/usr/bin/env python3
"""
File watcher — monitors the design library for changes and triggers
incremental re-indexing automatically.

Run as a background service via systemd.

Usage:
    python watch_library.py
    python watch_library.py --library-root /mnt/design-library
    python watch_library.py --debounce 60  # wait 60s after last change
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from threading import Timer

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from indexer.config import IndexerConfig
from indexer.engine import IndexerEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class DebouncedIndexHandler(FileSystemEventHandler):
    """
    Watches for file changes and triggers indexing after a debounce period.

    The debounce prevents re-indexing on every single file save during a
    bulk git clone or copy operation. Instead, it waits for changes to
    "settle" before running.
    """

    def __init__(self, config: IndexerConfig, debounce_seconds: int = 30):
        super().__init__()
        self.config = config
        self.debounce_seconds = debounce_seconds
        self._timer: Timer | None = None
        self._pending_changes: set[str] = set()

        # Extensions we care about
        self._watched_extensions = config.code_extensions | config.config_extensions

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Called on any file system event."""
        if event.is_directory:
            return

        # Check if the file is one we index
        path = Path(event.src_path)

        # Skip our own metadata directory
        if ".index" in path.parts:
            return

        # Skip files we don't index
        ext = path.suffix.lower()
        if ext not in self._watched_extensions:
            return

        # Skip ignored directories
        for part in path.parts:
            if part in self.config.skip_directories:
                return

        self._pending_changes.add(str(path))
        logger.debug(f"Change detected: {event.event_type} {path.name} "
                      f"({len(self._pending_changes)} pending)")

        # Reset the debounce timer
        if self._timer is not None:
            self._timer.cancel()

        self._timer = Timer(self.debounce_seconds, self._run_index)
        self._timer.start()

    def _run_index(self) -> None:
        """Execute incremental indexing after debounce period."""
        n_changes = len(self._pending_changes)
        logger.info(f"Debounce complete. {n_changes} files changed. Starting incremental index...")
        self._pending_changes.clear()

        try:
            engine = IndexerEngine(self.config)
            stats = engine.run(full=False)
            logger.info(f"Index update complete. "
                        f"Processed {stats['files_processed']} files, "
                        f"stored {stats['chunks_stored']} chunks.")
        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="Watch design library for changes")
    parser.add_argument("--library-root", type=str, default="/mnt/design-library")
    parser.add_argument("--debounce", type=int, default=30,
                        help="Seconds to wait after last change before indexing")
    parser.add_argument("--chroma-dir", type=str, default=None)
    parser.add_argument("--ollama-url", type=str, default=None)
    args = parser.parse_args()

    config = IndexerConfig()
    config.library_root = Path(args.library_root)
    config.index_metadata_dir = config.library_root / ".index"
    if args.chroma_dir:
        config.chroma_persist_dir = Path(args.chroma_dir)
    if args.ollama_url:
        config.ollama_base_url = args.ollama_url

    if not config.library_root.exists():
        logger.error(f"Library root does not exist: {config.library_root}")
        sys.exit(1)

    handler = DebouncedIndexHandler(config, debounce_seconds=args.debounce)
    observer = Observer()

    # Watch all configured index paths
    for subdir in config.index_paths:
        watch_path = config.library_root / subdir
        if watch_path.exists():
            observer.schedule(handler, str(watch_path), recursive=True)
            logger.info(f"Watching: {watch_path}")
        else:
            logger.warning(f"Path does not exist, skipping: {watch_path}")

    observer.start()
    logger.info(f"File watcher started (debounce: {args.debounce}s). Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down file watcher...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
