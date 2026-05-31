"""
Website auditor — runs PageSpeed Insights API on existing websites
and performs basic checks (mobile, SSL, load time, tech stack detection).
The PageSpeed Insights API is completely FREE with an API key.
"""

import requests
import httpx
from urllib.parse import urlparse
from config import PAGESPEED_API_KEY

PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def run_pagespeed_audit(url: str) -> dict:
    """
    Run PageSpeed Insights on a URL.
    Returns scores (0-100) for performance, accessibility, SEO, best-practices.
    Also returns specific issues found.
    """
    if not url:
        return {}

    results = {}

    for strategy in ("mobile", "desktop"):
        params = {
            "url": url,
            "strategy": strategy,
            "key": PAGESPEED_API_KEY,
            "category": ["performance", "accessibility", "seo", "best-practices"],
        }
        try:
            resp = requests.get(PAGESPEED_API_URL, params=params, timeout=30)
            data = resp.json()

            categories = data.get("lighthouseResult", {}).get("categories", {})
            audits = data.get("lighthouseResult", {}).get("audits", {})

            scores = {
                "performance": round((categories.get("performance", {}).get("score", 0) or 0) * 100),
                "accessibility": round((categories.get("accessibility", {}).get("score", 0) or 0) * 100),
                "seo": round((categories.get("seo", {}).get("score", 0) or 0) * 100),
                "best_practices": round((categories.get("best-practices", {}).get("score", 0) or 0) * 100),
            }

            # Pull specific failing audits
            issues = []
            critical_audits = [
                "uses-responsive-images",
                "render-blocking-resources",
                "unused-javascript",
                "uses-optimized-images",
                "time-to-first-byte",
                "cumulative-layout-shift",
                "largest-contentful-paint",
                "viewport",
                "uses-rel-noopener",
                "meta-description",
                "document-title",
                "image-alt",
            ]
            for audit_key in critical_audits:
                audit = audits.get(audit_key, {})
                score = audit.get("score")
                if score is not None and score < 0.9:
                    issues.append({
                        "id": audit_key,
                        "title": audit.get("title", audit_key),
                        "description": audit.get("description", ""),
                        "score": score,
                    })

            results[strategy] = {
                "scores": scores,
                "issues": issues,
                "lcp": audits.get("largest-contentful-paint", {}).get("displayValue", ""),
                "fid": audits.get("total-blocking-time", {}).get("displayValue", ""),
                "cls": audits.get("cumulative-layout-shift", {}).get("displayValue", ""),
            }
        except Exception as e:
            results[strategy] = {"scores": {}, "issues": [], "error": str(e)}

    return results


def check_website_basics(url: str) -> dict:
    """
    Quick checks on a website — does it load, is it SSL, what tech is it on?
    """
    if not url:
        return {"reachable": False}

    result = {
        "url": url,
        "reachable": False,
        "has_ssl": url.startswith("https"),
        "redirects_to_mobile": False,
        "tech_hints": [],
        "status_code": None,
        "load_time_ms": None,
    }

    try:
        import time
        start = time.time()
        resp = httpx.get(url, follow_redirects=True, timeout=10)
        result["load_time_ms"] = round((time.time() - start) * 1000)
        result["reachable"] = True
        result["status_code"] = resp.status_code

        # Tech detection from headers / HTML
        server = resp.headers.get("server", "").lower()
        powered_by = resp.headers.get("x-powered-by", "").lower()
        content = resp.text.lower()

        if "wordpress" in content or "wp-content" in content:
            result["tech_hints"].append("WordPress")
        if "wix.com" in content:
            result["tech_hints"].append("Wix")
        if "squarespace" in content:
            result["tech_hints"].append("Squarespace")
        if "shopify" in content:
            result["tech_hints"].append("Shopify")
        if "weebly" in content:
            result["tech_hints"].append("Weebly")
        if "godaddy" in content or "godaddy" in server:
            result["tech_hints"].append("GoDaddy Website Builder")
        if "bootstrap" in content:
            result["tech_hints"].append("Bootstrap")
        if "jquery" in content:
            result["tech_hints"].append("jQuery")

        # Check for copyright year to estimate age
        import re
        years = re.findall(r"copyright.*?(\d{4})", content[:5000])
        if years:
            oldest = min(int(y) for y in years if 2000 <= int(y) <= 2026)
            result["copyright_year"] = oldest
            if oldest < 2020:
                result["tech_hints"].append(f"Site appears old (copyright {oldest})")

        # Check viewport meta tag (mobile responsiveness indicator)
        if 'name="viewport"' not in content and "name='viewport'" not in content:
            result["no_viewport"] = True
            result["tech_hints"].append("No viewport meta tag — not mobile optimized")

    except Exception as e:
        result["error"] = str(e)

    return result


def audit_website(url: str) -> tuple[dict, list[str]]:
    """
    Full website audit combining PageSpeed + basics.
    Returns (scores_dict, issues_list).
    """
    if not url:
        return {}, ["No website — this is your opportunity"]

    basics = check_website_basics(url)
    pagespeed = run_pagespeed_audit(url)

    mobile_perf = pagespeed.get("mobile", {}).get("scores", {}).get("performance", 0)
    desktop_perf = pagespeed.get("desktop", {}).get("scores", {}).get("performance", 0)
    mobile_seo = pagespeed.get("mobile", {}).get("scores", {}).get("seo", 0)

    scores = {
        "mobile_performance": mobile_perf,
        "desktop_performance": desktop_perf,
        "seo": mobile_seo,
        "accessibility": pagespeed.get("mobile", {}).get("scores", {}).get("accessibility", 0),
    }

    issues = []
    if not basics.get("reachable"):
        issues.append("Website is unreachable or broken")
    if not basics.get("has_ssl"):
        issues.append("No HTTPS/SSL — Google penalizes this and Chrome shows 'Not Secure'")
    if basics.get("no_viewport"):
        issues.append("Not mobile-friendly — no viewport meta tag")
    if mobile_perf < 50:
        issues.append(f"Mobile performance score: {mobile_perf}/100 — very slow on phones")
    elif mobile_perf < 75:
        issues.append(f"Mobile performance score: {mobile_perf}/100 — needs improvement")
    if mobile_seo < 70:
        issues.append(f"SEO score: {mobile_seo}/100 — not ranking well in Google")
    if basics.get("load_time_ms", 0) > 3000:
        issues.append(f"Slow load time: {basics['load_time_ms']}ms — users bounce after 3s")
    if "Wix" in basics.get("tech_hints", []) or "GoDaddy Website Builder" in basics.get("tech_hints", []):
        issues.append(f"Built on {basics['tech_hints'][0]} — template builder, hard to customize and slow")

    all_psi_issues = pagespeed.get("mobile", {}).get("issues", []) + pagespeed.get("desktop", {}).get("issues", [])
    seen = set()
    for issue in all_psi_issues:
        if issue["title"] not in seen:
            issues.append(issue["title"])
            seen.add(issue["title"])

    return scores, issues
