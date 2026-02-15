"""
AST-aware chunking — splits code files by semantic boundaries.

The key insight: naive character-count splitting destroys context.
A React component split in the middle of a JSX return is useless for RAG.

Strategy per file type:
- HTML:  Split by top-level semantic elements (<header>, <section>, <footer>, etc.)
- CSS:   Split by rule blocks or @media queries
- JSX/TSX/JS/TS: Split by export/function/class boundaries
- Vue:   Split <template>, <script>, <style> blocks
- Astro: Split frontmatter, template, style blocks
- Svelte: Split <script>, markup, <style> blocks

Fallback: if AST splitting produces chunks that are too large,
          apply line-based splitting with overlap.
"""

import logging
import re
from dataclasses import dataclass

from .config import IndexerConfig

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A semantic chunk of code with metadata."""
    text: str
    chunk_index: int
    total_chunks: int
    section_type: str  # e.g., "header", "section", "component", "styles", "script"
    start_line: int
    end_line: int


class Chunker:
    """AST-aware code chunker for design files."""

    def __init__(self, config: IndexerConfig):
        self.config = config

    def chunk(self, content: str, extension: str) -> list[Chunk]:
        """
        Chunk file content based on extension.

        Returns a list of Chunk objects, each containing a semantically
        meaningful section of the file.
        """
        if not content or not content.strip():
            return []

        # Route to the appropriate chunker
        chunker_map = {
            ".html": self._chunk_html,
            ".htm": self._chunk_html,
            ".css": self._chunk_css,
            ".scss": self._chunk_css,
            ".sass": self._chunk_css,
            ".jsx": self._chunk_jsx_tsx,
            ".tsx": self._chunk_jsx_tsx,
            ".js": self._chunk_js_ts,
            ".ts": self._chunk_js_ts,
            ".vue": self._chunk_vue,
            ".astro": self._chunk_astro,
            ".svelte": self._chunk_svelte,
        }

        chunker_fn = chunker_map.get(extension, self._chunk_fallback)
        chunks = chunker_fn(content)

        # Post-process: split oversized chunks, drop tiny ones
        final_chunks = []
        for chunk in chunks:
            if len(chunk.text) < self.config.chunk_min_chars:
                continue
            if len(chunk.text) > self.config.chunk_max_chars:
                sub_chunks = self._split_oversized(chunk)
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)

        # Re-number chunks
        for i, chunk in enumerate(final_chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(final_chunks)

        return final_chunks

    # ── HTML Chunker ───────────────────────────────────────────────────

    def _chunk_html(self, content: str) -> list[Chunk]:
        """Split HTML by semantic sections."""
        chunks = []

        # First, try to extract <head> as its own chunk (SEO-relevant)
        head_match = re.search(r"<head[^>]*>(.*?)</head>", content, re.DOTALL | re.IGNORECASE)
        if head_match:
            chunks.append(Chunk(
                text=head_match.group(0),
                chunk_index=0, total_chunks=0,
                section_type="head-meta",
                start_line=content[:head_match.start()].count("\n") + 1,
                end_line=content[:head_match.end()].count("\n") + 1,
            ))

        # Split <body> by semantic HTML5 elements
        body_match = re.search(r"<body[^>]*>(.*?)</body>", content, re.DOTALL | re.IGNORECASE)
        body_content = body_match.group(1) if body_match else content

        # Pattern: match top-level semantic elements
        semantic_tags = r"(<(?:header|nav|main|section|article|aside|footer|div\s+(?:id|class)=)[^>]*>.*?</(?:header|nav|main|section|article|aside|footer|div)>)"
        sections = re.split(semantic_tags, body_content, flags=re.DOTALL | re.IGNORECASE)

        for section in sections:
            section = section.strip()
            if not section or len(section) < self.config.chunk_min_chars:
                continue

            # Detect section type from tag
            section_type = "section"
            tag_match = re.match(r"<(\w+)", section)
            if tag_match:
                tag = tag_match.group(1).lower()
                if tag in ("header", "nav", "main", "section", "article", "aside", "footer"):
                    section_type = tag

            line_offset = content.find(section)
            start_line = content[:line_offset].count("\n") + 1 if line_offset >= 0 else 0

            chunks.append(Chunk(
                text=section,
                chunk_index=0, total_chunks=0,
                section_type=section_type,
                start_line=start_line,
                end_line=start_line + section.count("\n"),
            ))

        # If no semantic sections found (only head or nothing), extract
        # <body> content as a "component" chunk instead of falling back to
        # _chunk_fallback which would chunk the entire file including <head>.
        # This fixes HyperUI-style files where <body> contains only a <div>
        # without <header>/<section>/<main> wrappers.
        if len(chunks) <= 1:
            if body_match and body_match.group(1).strip():
                body_text = body_match.group(0)  # full <body>...</body>
                body_start = content[:body_match.start()].count("\n") + 1
                chunks.append(Chunk(
                    text=body_text,
                    chunk_index=0, total_chunks=0,
                    section_type="component",
                    start_line=body_start,
                    end_line=body_start + body_text.count("\n"),
                ))
            else:
                return self._chunk_fallback(content)

        return chunks

    # ── CSS Chunker ────────────────────────────────────────────────────

    def _chunk_css(self, content: str) -> list[Chunk]:
        """Split CSS by top-level rule blocks and @media queries."""
        chunks = []

        # Split by @media queries and top-level comment blocks
        # This regex finds @media blocks (including nested braces) and
        # sequences of regular rules between them
        current_chunk_lines: list[str] = []
        current_section = "rules"
        brace_depth = 0
        start_line = 1

        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()

            # Detect @media or @keyframes start
            if brace_depth == 0 and re.match(r"@(media|keyframes|supports|layer|font-face)", stripped):
                # Flush current chunk
                if current_chunk_lines:
                    text = "\n".join(current_chunk_lines)
                    if text.strip():
                        chunks.append(Chunk(
                            text=text, chunk_index=0, total_chunks=0,
                            section_type=current_section,
                            start_line=start_line, end_line=i - 1,
                        ))
                current_chunk_lines = [line]
                current_section = "media-query" if "@media" in stripped else "at-rule"
                start_line = i

            # Detect large comment blocks (component separators)
            elif brace_depth == 0 and stripped.startswith("/*") and (
                "===" in stripped or "---" in stripped or "SECTION" in stripped.upper()
            ):
                if current_chunk_lines:
                    text = "\n".join(current_chunk_lines)
                    if text.strip():
                        chunks.append(Chunk(
                            text=text, chunk_index=0, total_chunks=0,
                            section_type=current_section,
                            start_line=start_line, end_line=i - 1,
                        ))
                current_chunk_lines = [line]
                current_section = "rules"
                start_line = i
            else:
                current_chunk_lines.append(line)

            brace_depth += line.count("{") - line.count("}")

            # End of an @-block
            if brace_depth == 0 and current_section in ("media-query", "at-rule") and "}" in line:
                text = "\n".join(current_chunk_lines)
                if text.strip():
                    chunks.append(Chunk(
                        text=text, chunk_index=0, total_chunks=0,
                        section_type=current_section,
                        start_line=start_line, end_line=i,
                    ))
                current_chunk_lines = []
                current_section = "rules"
                start_line = i + 1

        # Flush remaining
        if current_chunk_lines:
            text = "\n".join(current_chunk_lines)
            if text.strip():
                chunks.append(Chunk(
                    text=text, chunk_index=0, total_chunks=0,
                    section_type=current_section,
                    start_line=start_line, end_line=start_line + len(current_chunk_lines),
                ))

        return chunks if chunks else self._chunk_fallback(content)

    # ── JSX / TSX Chunker ──────────────────────────────────────────────

    def _chunk_jsx_tsx(self, content: str) -> list[Chunk]:
        """Split React files by component/function boundaries."""
        return self._chunk_by_export_boundaries(content, "component")

    # ── JS / TS Chunker ────────────────────────────────────────────────

    def _chunk_js_ts(self, content: str) -> list[Chunk]:
        """Split JS/TS files by function/class/export boundaries."""
        return self._chunk_by_export_boundaries(content, "function")

    def _chunk_by_export_boundaries(self, content: str, default_section: str) -> list[Chunk]:
        """
        Split JS/TS/JSX/TSX by top-level declarations.

        Detects: export default, export const, function, class, const Component.
        """
        lines = content.split("\n")
        boundaries: list[int] = [0]  # Always start at line 0

        # Patterns that indicate a new semantic boundary
        boundary_patterns = [
            r"^export\s+default\s+",
            r"^export\s+(const|function|class|let|var|interface|type)\s+",
            r"^(const|let|var)\s+\w+\s*=\s*(\(|function|class)",
            r"^function\s+\w+",
            r"^class\s+\w+",
            r"^interface\s+\w+",
            r"^type\s+\w+",
            r"^/\*\*",  # JSDoc comments (often precede components)
        ]
        combined_pattern = re.compile("|".join(f"({p})" for p in boundary_patterns))

        brace_depth = 0
        for i, line in enumerate(lines):
            stripped = line.strip()

            # Only detect boundaries at top-level (brace depth 0)
            if brace_depth == 0 and i > 0 and combined_pattern.match(stripped):
                boundaries.append(i)

            brace_depth += stripped.count("{") - stripped.count("}")
            # Handle template literals and JSX
            brace_depth = max(0, brace_depth)

        boundaries.append(len(lines))

        # Build chunks from boundary ranges
        chunks = []
        for idx in range(len(boundaries) - 1):
            start = boundaries[idx]
            end = boundaries[idx + 1]
            text = "\n".join(lines[start:end]).strip()
            if not text:
                continue

            # Detect section type
            section_type = default_section
            if re.match(r"(export\s+default|export\s+const\s+\w+\s*=)", text):
                section_type = "component"
            elif re.match(r"^import\s", text):
                section_type = "imports"
            elif text.startswith("/*") or text.startswith("//"):
                section_type = "comments"

            chunks.append(Chunk(
                text=text, chunk_index=0, total_chunks=0,
                section_type=section_type,
                start_line=start + 1, end_line=end,
            ))

        # Merge tiny adjacent import chunks
        chunks = self._merge_small_chunks(chunks)

        return chunks if chunks else self._chunk_fallback(content)

    # ── Vue SFC Chunker ────────────────────────────────────────────────

    def _chunk_vue(self, content: str) -> list[Chunk]:
        """Split Vue Single File Components by <template>, <script>, <style>."""
        return self._chunk_sfc_blocks(
            content,
            block_tags=["template", "script", "style"],
        )

    # ── Astro Chunker ──────────────────────────────────────────────────

    def _chunk_astro(self, content: str) -> list[Chunk]:
        """Split Astro files by frontmatter (---) and template sections."""
        chunks = []

        # Astro frontmatter is between --- fences
        frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if frontmatter_match:
            chunks.append(Chunk(
                text=frontmatter_match.group(0),
                chunk_index=0, total_chunks=0,
                section_type="frontmatter",
                start_line=1,
                end_line=frontmatter_match.group(0).count("\n") + 1,
            ))
            template_content = content[frontmatter_match.end():]
        else:
            template_content = content

        # Split the template part like HTML
        template_chunks = self._chunk_html(template_content)
        for tc in template_chunks:
            tc.section_type = f"astro-{tc.section_type}"
        chunks.extend(template_chunks)

        # Also extract <style> blocks
        style_blocks = re.findall(r"(<style[^>]*>.*?</style>)", content, re.DOTALL)
        for style in style_blocks:
            chunks.append(Chunk(
                text=style, chunk_index=0, total_chunks=0,
                section_type="style",
                start_line=0, end_line=0,
            ))

        return chunks if chunks else self._chunk_fallback(content)

    # ── Svelte Chunker ─────────────────────────────────────────────────

    def _chunk_svelte(self, content: str) -> list[Chunk]:
        """Split Svelte files by <script>, markup, <style>."""
        return self._chunk_sfc_blocks(
            content,
            block_tags=["script", "style"],
        )

    # ── Shared Helpers ─────────────────────────────────────────────────

    def _chunk_sfc_blocks(self, content: str, block_tags: list[str]) -> list[Chunk]:
        """Generic SFC block splitter for Vue/Svelte."""
        chunks = []
        remaining = content

        for tag in block_tags:
            pattern = rf"(<{tag}[^>]*>.*?</{tag}>)"
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                offset = content.find(match)
                chunks.append(Chunk(
                    text=match, chunk_index=0, total_chunks=0,
                    section_type=tag,
                    start_line=content[:offset].count("\n") + 1,
                    end_line=content[:offset + len(match)].count("\n") + 1,
                ))
                remaining = remaining.replace(match, "", 1)

        # Whatever's left is the template/markup
        remaining = remaining.strip()
        if remaining and len(remaining) >= self.config.chunk_min_chars:
            # Split the template portion like HTML
            html_chunks = self._chunk_html(remaining)
            for hc in html_chunks:
                hc.section_type = f"template-{hc.section_type}"
            chunks.extend(html_chunks)

        return chunks if chunks else self._chunk_fallback(content)

    def _chunk_fallback(self, content: str) -> list[Chunk]:
        """
        Line-based chunking with overlap.
        Used when AST-aware chunking fails or for unknown file types.
        """
        lines = content.split("\n")
        chunks = []
        target_lines = max(10, self.config.chunk_target_chars // 60)  # ~60 chars per line avg
        overlap_lines = max(2, target_lines // 10)  # Reduced from 20% to 10% for Pi performance

        i = 0
        while i < len(lines):
            end = min(i + target_lines, len(lines))
            text = "\n".join(lines[i:end])

            chunks.append(Chunk(
                text=text, chunk_index=0, total_chunks=0,
                section_type="fragment",
                start_line=i + 1, end_line=end,
            ))
            i = end - overlap_lines if end < len(lines) else end

        return chunks

    def _split_oversized(self, chunk: Chunk) -> list[Chunk]:
        """Split a chunk that exceeds max_chars into smaller pieces."""
        sub_chunks = self._chunk_fallback(chunk.text)
        for sc in sub_chunks:
            sc.section_type = f"{chunk.section_type}-part"
            sc.start_line += chunk.start_line - 1
            sc.end_line += chunk.start_line - 1
        return sub_chunks

    def _merge_small_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Merge adjacent small chunks (e.g., consecutive import lines)."""
        if not chunks:
            return chunks

        merged = [chunks[0]]
        for chunk in chunks[1:]:
            prev = merged[-1]
            combined_len = len(prev.text) + len(chunk.text)
            # Merge if both are small and same section type, or if prev is imports
            if (combined_len < self.config.chunk_target_chars and
                    (prev.section_type == chunk.section_type or prev.section_type == "imports")):
                merged[-1] = Chunk(
                    text=prev.text + "\n\n" + chunk.text,
                    chunk_index=prev.chunk_index,
                    total_chunks=0,
                    section_type=prev.section_type if prev.section_type == chunk.section_type else chunk.section_type,
                    start_line=prev.start_line,
                    end_line=chunk.end_line,
                )
            else:
                merged.append(chunk)

        return merged
