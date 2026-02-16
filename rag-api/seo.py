"""
SEO Audit Module — rule-based HTML analysis for common SEO issues.

Uses BeautifulSoup to parse HTML and check against a set of SEO best practices.
No LLM needed — pure deterministic checks.
"""

import re

from bs4 import BeautifulSoup


def audit_html(html: str) -> dict:
    """
    Audit HTML for common SEO issues.

    Args:
        html: Raw HTML string to audit.

    Returns:
        Dict with keys: score (0-100), issues (list), passed (list).
    """
    soup = BeautifulSoup(html, "html.parser")
    issues = []
    passed = []

    # ── 1. Title tag ─────────────────────────────────────────────────────
    title_tag = soup.find("title")
    if not title_tag or not title_tag.string:
        issues.append({
            "severity": "error",
            "rule": "missing_title",
            "message": "Page is missing a <title> tag",
        })
    else:
        title_text = title_tag.string.strip()
        if len(title_text) < 30:
            issues.append({
                "severity": "warning",
                "rule": "title_too_short",
                "message": f"Title is too short ({len(title_text)} chars). Aim for 30-60 characters",
            })
        elif len(title_text) > 60:
            issues.append({
                "severity": "warning",
                "rule": "title_too_long",
                "message": f"Title is too long ({len(title_text)} chars). Aim for 30-60 characters",
            })
        else:
            passed.append({
                "rule": "has_title",
                "message": f"Title tag present ({len(title_text)} chars)",
            })

    # ── 2. Meta description ──────────────────────────────────────────────
    meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if not meta_desc or not meta_desc.get("content"):
        issues.append({
            "severity": "error",
            "rule": "missing_meta_description",
            "message": "Page is missing <meta name=\"description\">",
        })
    else:
        desc_text = meta_desc["content"].strip()
        if len(desc_text) < 120:
            issues.append({
                "severity": "warning",
                "rule": "meta_description_short",
                "message": f"Meta description is short ({len(desc_text)} chars). Aim for 120-160",
            })
        elif len(desc_text) > 160:
            issues.append({
                "severity": "warning",
                "rule": "meta_description_long",
                "message": f"Meta description is long ({len(desc_text)} chars). Aim for 120-160",
            })
        else:
            passed.append({
                "rule": "has_meta_description",
                "message": f"Meta description present ({len(desc_text)} chars)",
            })

    # ── 3. H1 tag ────────────────────────────────────────────────────────
    h1_tags = soup.find_all("h1")
    if len(h1_tags) == 0:
        issues.append({
            "severity": "error",
            "rule": "missing_h1",
            "message": "Page has no <h1> tag",
        })
    elif len(h1_tags) > 1:
        issues.append({
            "severity": "warning",
            "rule": "multiple_h1",
            "message": f"Page has {len(h1_tags)} <h1> tags. Use exactly one",
        })
    else:
        passed.append({
            "rule": "has_h1",
            "message": "Page has exactly one <h1> tag",
        })

    # ── 4. HTML lang attribute ───────────────────────────────────────────
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        passed.append({
            "rule": "has_lang",
            "message": f"HTML lang attribute set to \"{html_tag['lang']}\"",
        })
    else:
        issues.append({
            "severity": "warning",
            "rule": "missing_lang",
            "message": "Missing <html lang=\"...\"> attribute",
        })

    # ── 5. Charset ───────────────────────────────────────────────────────
    meta_charset = soup.find("meta", attrs={"charset": True})
    meta_content_type = soup.find("meta", attrs={"http-equiv": re.compile(r"Content-Type", re.I)})
    if meta_charset or meta_content_type:
        passed.append({
            "rule": "has_charset",
            "message": "Character encoding declared",
        })
    else:
        issues.append({
            "severity": "warning",
            "rule": "missing_charset",
            "message": "Missing charset declaration (<meta charset=\"UTF-8\">)",
        })

    # ── 6. Viewport meta ────────────────────────────────────────────────
    meta_viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    if meta_viewport:
        passed.append({
            "rule": "has_viewport",
            "message": "Viewport meta tag present (mobile-friendly)",
        })
    else:
        issues.append({
            "severity": "error",
            "rule": "missing_viewport",
            "message": "Missing <meta name=\"viewport\"> — page won't be mobile-friendly",
        })

    # ── 7. Image alt attributes ──────────────────────────────────────────
    images = soup.find_all("img")
    images_without_alt = [img for img in images if not img.get("alt")]
    if images and not images_without_alt:
        passed.append({
            "rule": "images_have_alt",
            "message": f"All {len(images)} images have alt text",
        })
    elif images_without_alt:
        issues.append({
            "severity": "warning",
            "rule": "images_missing_alt",
            "message": f"{len(images_without_alt)} of {len(images)} images are missing alt text",
        })

    # ── 8. Heading hierarchy ─────────────────────────────────────────────
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    if headings:
        levels = [int(h.name[1]) for h in headings]
        skips = []
        for i in range(1, len(levels)):
            if levels[i] > levels[i - 1] + 1:
                skips.append(f"h{levels[i-1]} -> h{levels[i]}")
        if skips:
            issues.append({
                "severity": "warning",
                "rule": "heading_hierarchy_skip",
                "message": f"Heading hierarchy skips levels: {', '.join(skips)}",
            })
        else:
            passed.append({
                "rule": "heading_hierarchy_ok",
                "message": "Heading hierarchy is correct (no skipped levels)",
            })

    # ── 9. Open Graph tags ───────────────────────────────────────────────
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_title and og_desc:
        passed.append({
            "rule": "has_og_tags",
            "message": "Open Graph tags present (og:title, og:description)",
        })
    else:
        missing = []
        if not og_title:
            missing.append("og:title")
        if not og_desc:
            missing.append("og:description")
        issues.append({
            "severity": "warning",
            "rule": "missing_og_tags",
            "message": f"Missing Open Graph tags: {', '.join(missing)}",
        })

    # ── 10. Canonical URL ────────────────────────────────────────────────
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        passed.append({
            "rule": "has_canonical",
            "message": "Canonical URL tag present",
        })
    else:
        issues.append({
            "severity": "warning",
            "rule": "missing_canonical",
            "message": "Missing <link rel=\"canonical\" href=\"...\">",
        })

    # ── 11. Empty links ──────────────────────────────────────────────────
    links = soup.find_all("a")
    empty_links = [a for a in links if not a.get("href") or a["href"].strip() in ("", "#")]
    if empty_links:
        issues.append({
            "severity": "warning",
            "rule": "empty_links",
            "message": f"{len(empty_links)} links have empty or '#' href attributes",
        })

    # ── Calculate score ──────────────────────────────────────────────────
    total_checks = len(issues) + len(passed)
    if total_checks == 0:
        score = 0
    else:
        # Errors cost 10 points, warnings cost 5
        error_count = sum(1 for i in issues if i["severity"] == "error")
        warning_count = sum(1 for i in issues if i["severity"] == "warning")
        deductions = (error_count * 10) + (warning_count * 5)
        score = max(0, 100 - deductions)

    return {
        "score": score,
        "total_checks": total_checks,
        "errors": sum(1 for i in issues if i["severity"] == "error"),
        "warnings": sum(1 for i in issues if i["severity"] == "warning"),
        "passed_count": len(passed),
        "issues": issues,
        "passed": passed,
    }
