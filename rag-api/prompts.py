"""
Prompt Engineering Layer — system prompts, design rules, and context injection.

Each task type (hero, page, component, seo_rewrite) has a tailored system prompt.
Design rules are injected into every prompt to ensure high-quality output.
RAG context from ChromaDB is injected as reference examples.
"""

# ── Design Rules ─────────────────────────────────────────────────────────────
# These are injected into every generation prompt to maintain quality.

DESIGN_RULES = """\
Design rules you MUST follow:
- Use semantic HTML5 elements (<header>, <nav>, <main>, <section>, <article>, <footer>)
- Write clean, minimal markup — no unnecessary wrapper divs
- Mobile-first responsive design using CSS media queries or clamp()
- Use CSS custom properties (--color-primary, --font-body, etc.) for theming
- Prefer system font stacks or well-known web fonts (Inter, DM Sans, etc.)
- No inline styles — use <style> blocks or CSS classes
- Accessible: proper alt text on images, ARIA labels where needed, sufficient contrast
- Avoid generic AI aesthetics:
  - No excessive rainbow gradients
  - No "Lorem ipsum" placeholder text — use realistic sample content
  - No stock-photo placeholder URLs — use solid color backgrounds or CSS patterns instead
  - No rounded-everything bubbly designs unless specifically requested
- Use subtle, intentional animations (prefer CSS transitions over JS)
- Include :hover and :focus states for interactive elements
- Structure CSS with logical grouping: layout, typography, colors, components
"""

# ── Task-Specific System Prompts ─────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "hero": """\
You are an expert front-end developer specializing in hero sections.

Generate a complete, production-ready hero section based on the user's brief.
Output ONLY the HTML and CSS code — no explanations, no markdown fences.

The hero section should:
- Be visually striking but not generic
- Include a clear headline, subheadline, and call-to-action
- Be fully responsive (mobile-first)
- Use the design patterns from the reference examples provided

{design_rules}
""",

    "page": """\
You are an expert front-end developer who builds complete web pages.

Generate a full, production-ready HTML page based on the user's brief.
Output ONLY the complete HTML document (<!DOCTYPE html> to </html>) — no explanations, no markdown fences.

The page should:
- Include proper <head> with meta tags, title, and embedded <style>
- Have a clear visual hierarchy with header, main content, and footer
- Be fully responsive (mobile-first)
- Use the design patterns from the reference examples provided

{design_rules}
""",

    "component": """\
You are an expert front-end developer who builds reusable UI components.

Generate a clean, production-ready HTML/CSS component based on the user's brief.
Output ONLY the HTML and CSS code — no explanations, no markdown fences.

The component should:
- Be self-contained (no external dependencies)
- Be reusable and configurable via CSS custom properties
- Include proper states (hover, focus, active, disabled if applicable)
- Use the design patterns from the reference examples provided

{design_rules}
""",

    "seo_rewrite": """\
You are an SEO specialist and front-end developer.

The user will provide HTML code that has SEO issues. Rewrite it to fix the issues while
preserving the visual design. Output ONLY the corrected HTML — no explanations, no markdown fences.

Fix these common SEO problems:
- Add or improve <title> tag (30-60 characters, keyword-rich)
- Add or improve <meta name="description"> (120-160 characters)
- Ensure exactly one <h1> tag with the primary keyword
- Add <html lang="en"> if missing
- Add <meta name="viewport"> if missing
- Add alt text to images
- Fix heading hierarchy (h1 → h2 → h3, no skipping)
- Add Open Graph meta tags (og:title, og:description, og:type)
- Add canonical URL tag

{design_rules}
""",
}


def build_prompt(
    task: str,
    brief: str,
    context_chunks: list[dict],
) -> tuple[str, str]:
    """
    Build the (system_prompt, user_prompt) pair for a generation task.

    Args:
        task: One of "hero", "page", "component", "seo_rewrite".
        brief: The user's description of what they want.
        context_chunks: List of dicts with keys: text, file_path, similarity.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    # Get task-specific system prompt
    system_template = SYSTEM_PROMPTS.get(task, SYSTEM_PROMPTS["component"])
    system_prompt = system_template.format(design_rules=DESIGN_RULES)

    # Build user prompt with context injection
    parts = []

    # Inject RAG context as reference examples
    if context_chunks:
        parts.append("Here are reference examples from a design library for inspiration:\n")
        for i, chunk in enumerate(context_chunks, 1):
            file_path = chunk.get("file_path", "unknown")
            similarity = chunk.get("similarity", 0)
            text = chunk.get("text", "")
            parts.append(
                f"--- Reference {i} (from {file_path}, relevance: {similarity:.0%}) ---\n"
                f"{text}\n"
            )
        parts.append("--- End of references ---\n\n")
        parts.append(
            "Use the above examples as inspiration for style and structure, "
            "but create something original based on the brief below.\n\n"
        )

    # Add the actual brief
    parts.append(f"Brief: {brief}")

    user_prompt = "\n".join(parts)

    return system_prompt, user_prompt
