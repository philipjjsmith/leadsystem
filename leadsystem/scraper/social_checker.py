"""
Social media presence checker.
Checks if a business has a Facebook page, Instagram, or Yelp listing.
Uses lightweight HTTP checks — no paid APIs needed.
"""

import requests
import urllib.parse
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def check_facebook(business_name: str, city: str) -> dict:
    """
    Search for a Facebook business page by name + city.
    Returns presence indicator + likely URL.
    """
    result = {"has_facebook": False, "facebook_url": "", "confidence": "low"}
    try:
        # Search Google for Facebook page
        query = f'site:facebook.com "{business_name}" "{city.split(",")[0]}"'
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        resp = requests.get(search_url, headers=HEADERS, timeout=8)

        if resp.status_code == 200 and "facebook.com" in resp.text:
            # Extract Facebook URL from results
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "facebook.com" in href and "/search?" not in href:
                    # Clean the URL
                    if "url?q=" in href:
                        fb_url = href.split("url?q=")[1].split("&")[0]
                        fb_url = urllib.parse.unquote(fb_url)
                    elif href.startswith("https://www.facebook.com"):
                        fb_url = href
                    else:
                        continue
                    if "/pages/" in fb_url or "/p/" in fb_url or fb_url.count("/") <= 4:
                        result["has_facebook"] = True
                        result["facebook_url"] = fb_url
                        result["confidence"] = "medium"
                        break
    except Exception:
        pass
    return result


def check_yelp(business_name: str, city: str) -> dict:
    """
    Check for a Yelp listing — gives us additional review/rating data.
    """
    result = {"has_yelp": False, "yelp_url": "", "yelp_rating": None, "yelp_review_count": None}
    try:
        query = f'site:yelp.com "{business_name}" "{city.split(",")[0]}"'
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        resp = requests.get(search_url, headers=HEADERS, timeout=8)

        if resp.status_code == 200 and "yelp.com/biz/" in resp.text:
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "yelp.com/biz/" in href:
                    if "url?q=" in href:
                        yelp_url = href.split("url?q=")[1].split("&")[0]
                        yelp_url = urllib.parse.unquote(yelp_url)
                    elif href.startswith("https://www.yelp.com"):
                        yelp_url = href
                    else:
                        continue
                    result["has_yelp"] = True
                    result["yelp_url"] = yelp_url
                    break
    except Exception:
        pass
    return result


def check_instagram(business_name: str) -> dict:
    """
    Check if a business has an Instagram account.
    """
    result = {"has_instagram": False, "instagram_url": ""}
    try:
        clean_name = business_name.lower().replace(" ", "").replace("'", "").replace("-", "")[:20]
        query = f'site:instagram.com "{business_name}"'
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        resp = requests.get(search_url, headers=HEADERS, timeout=8)

        if resp.status_code == 200 and "instagram.com" in resp.text:
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "instagram.com" in href and "/p/" not in href:
                    if "url?q=" in href:
                        ig_url = href.split("url?q=")[1].split("&")[0]
                        ig_url = urllib.parse.unquote(ig_url)
                        if "instagram.com" in ig_url:
                            result["has_instagram"] = True
                            result["instagram_url"] = ig_url
                            break
    except Exception:
        pass
    return result


def enrich_with_social(lead: dict) -> dict:
    """
    Run all social checks for a lead and merge results in-place.
    """
    business_name = lead.get("name", "")
    city = lead.get("city", "Florida")

    fb = check_facebook(business_name, city)
    yelp = check_yelp(business_name, city)
    ig = check_instagram(business_name)

    lead["has_facebook"] = fb["has_facebook"]
    lead["facebook_url"] = fb["facebook_url"]
    lead["has_yelp"] = yelp["has_yelp"]
    lead["yelp_url"] = yelp["yelp_url"]
    lead["has_instagram"] = ig["has_instagram"]
    lead["instagram_url"] = ig["instagram_url"]

    return lead
