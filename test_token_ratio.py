#!/usr/bin/env python3
"""
Quick script to test character-to-token ratio for your content.
Run this on sample files from your design library.
"""

import sys
from pathlib import Path


def estimate_tokens(text, ratio=3.0):
    """Estimate tokens using char-to-token ratio."""
    return len(text) / ratio


def analyze_file(filepath):
    """Analyze a file's token usage."""
    path = Path(filepath)

    if not path.exists():
        print(f"File not found: {filepath}")
        return

    # Determine content type
    ext = path.suffix.lower()
    content_type_ratios = {
        '.html': 3.0,
        '.htm': 3.0,
        '.css': 3.5,
        '.scss': 3.0,
        '.js': 2.5,
        '.jsx': 2.5,
        '.ts': 2.5,
        '.tsx': 2.5,
    }

    ratio = content_type_ratios.get(ext, 3.0)
    content = path.read_text(encoding='utf-8', errors='ignore')

    chars = len(content)
    estimated_tokens = estimate_tokens(content, ratio)

    print(f"\n{'='*60}")
    print(f"File: {path.name}")
    print(f"Type: {ext}")
    print(f"{'='*60}")
    print(f"Characters: {chars:,}")
    print(f"Estimated tokens: {estimated_tokens:,.0f} (ratio: {ratio})")
    print(f"Chars per token: {chars / estimated_tokens:.2f}")
    print(f"\nWith current chunking (1000 chars):")
    print(f"  Chunks needed: ~{chars / 1000:.0f}")
    print(f"  Tokens per chunk: ~{estimate_tokens('x' * 1000, ratio):.0f}")
    print(f"\nWith balanced chunking (1500 chars):")
    print(f"  Chunks needed: ~{chars / 1500:.0f}")
    print(f"  Tokens per chunk: ~{estimate_tokens('x' * 1500, ratio):.0f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_token_ratio.py <file_path>")
        print("\nExample:")
        print("  python test_token_ratio.py /mnt/design-library/example-websites/html-css/sample.html")
        sys.exit(1)

    analyze_file(sys.argv[1])
