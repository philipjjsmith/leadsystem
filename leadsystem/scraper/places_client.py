"""
Google Places API client.
Uses Places API text search + place details to find businesses in a city/niche.

Pagination fix: Google page tokens need 2-5s to become valid. We wait 3s then
retry up to 3 times with backoff (2s, 4s, 6s) before giving up on a page.

Dual-query: each niche has a primary + secondary search term. Both run and
results are deduplicated by place_id, giving up to ~80-120 leads per niche/city
instead of the 20-60 from a single query.
"""

import time
import requests
from typing import Optional
from rich.console import Console
from config import GOOGLE_PLACES_API_KEY, REQUEST_DELAY_SECONDS

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAILS_URL     = "https://maps.googleapis.com/maps/api/place/details/json"
GEOCODE_URL            = "https://maps.googleapis.com/maps/api/geocode/json"

console = Console()


def geocode_city(city: str) -> Optional[tuple[float, float]]:
    """Convert a city name to lat/lng coordinates."""
    resp = requests.get(GEOCODE_URL, params={"address": city, "key": GOOGLE_PLACES_API_KEY})
    data = resp.json()
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None


def text_search_businesses(query: str, city: str, next_page_token: str = None) -> dict:
    """
    Run one text search page. Handles page token timing:

    Google docs: "There is a short delay between when a next_page_token is issued
    and when it will become valid. Requesting the next page before it is available
    will return an INVALID_REQUEST response. Retrying the request should resolve it."

    Strategy: wait 3s, then retry up to 3 times with 2/4/6s backoff.
    """
    if next_page_token:
        params = {"pagetoken": next_page_token, "key": GOOGLE_PLACES_API_KEY}
        time.sleep(3)

        last_data = {}
        for attempt in range(3):
            resp = requests.get(PLACES_TEXT_SEARCH_URL, params=params)
            last_data = resp.json()
            if last_data.get("status") != "INVALID_REQUEST":
                return last_data
            wait = 2 + attempt * 2  # 2s, 4s, 6s
            console.print(f"  [dim]  Page token not ready yet, retrying in {wait}s...[/dim]")
            time.sleep(wait)

        return last_data
    else:
        params = {
            "query":  f"{query} in {city}",
            "key":    GOOGLE_PLACES_API_KEY,
            "region": "us",
        }
        resp = requests.get(PLACES_TEXT_SEARCH_URL, params=params)
        return resp.json()


def get_place_details(place_id: str) -> dict:
    """Pull full details for a place_id (website, phone, hours, reviews, etc.)."""
    fields = ",".join([
        "name", "formatted_address", "formatted_phone_number",
        "international_phone_number", "website", "rating",
        "user_ratings_total", "opening_hours", "business_status",
        "photos", "reviews", "price_level", "types", "url",
        "editorial_summary", "geometry", "place_id",
    ])
    resp = requests.get(PLACES_DETAILS_URL, params={
        "place_id": place_id,
        "fields":   fields,
        "key":      GOOGLE_PLACES_API_KEY,
    })
    return resp.json().get("result", {})


def _fetch_all_pages(query: str, city: str, max_pages: int) -> list[dict]:
    """
    Run one text search query, paginating up to max_pages (hard max: 3).
    Returns raw place dicts from search results (not full details yet).
    """
    all_places = []
    next_token = None
    pages_fetched = 0

    console.print(f"  [dim]Query: {query} in {city}[/dim]")

    while pages_fetched < max_pages:
        data = text_search_businesses(query, city, next_token)
        status = data.get("status", "UNKNOWN")

        if status == "ZERO_RESULTS":
            console.print(f"  [dim]  No results for this query.[/dim]")
            break
        if status != "OK":
            console.print(f"  [yellow]  Search stopped: {status} (page {pages_fetched + 1})[/yellow]")
            break

        results = data.get("results", [])
        all_places.extend(results)
        pages_fetched += 1
        console.print(f"  [dim]  Page {pages_fetched}: {len(results)} results ({len(all_places)} total)[/dim]")

        next_token = data.get("next_page_token")
        if not next_token:
            break

    return all_places


def collect_leads(niche_query: str, city: str, niche_key: str, budget_tier: str, max_results: int = 60) -> list[dict]:
    """
    Main collection function.
    1. Runs primary query (up to 3 pages = 60 results)
    2. Runs secondary query if defined in config (up to 60 more)
    3. Deduplicates by place_id
    4. Fetches full details for each unique business
    Returns a list of raw lead dicts ready for scoring.
    """
    from config import NICHE_SECONDARY_QUERY

    max_pages = min(max_results // 20, 3)

    # ── Primary query ──────────────────────────────────────────────────────────
    raw_places = _fetch_all_pages(niche_query, city, max_pages)

    # ── Secondary query ────────────────────────────────────────────────────────
    secondary = NICHE_SECONDARY_QUERY.get(niche_key)
    if secondary:
        extra = _fetch_all_pages(secondary, city, max_pages)
        raw_places.extend(extra)

    # ── Deduplicate by place_id ────────────────────────────────────────────────
    seen, unique_places = set(), []
    for place in raw_places:
        pid = place.get("place_id")
        if pid and pid not in seen:
            seen.add(pid)
            unique_places.append(place)

    console.print(f"  [dim]Fetching details for {len(unique_places)} unique businesses...[/dim]")

    # ── Fetch full details for each ────────────────────────────────────────────
    leads = []
    for i, place in enumerate(unique_places):
        place_id = place.get("place_id")
        if not place_id:
            continue

        details = get_place_details(place_id)
        time.sleep(REQUEST_DELAY_SECONDS)

        lead = {
            "place_id":         place_id,
            "name":             details.get("name", place.get("name", "")),
            "address":          details.get("formatted_address", place.get("formatted_address", "")),
            "phone":            details.get("formatted_phone_number", ""),
            "phone_intl":       details.get("international_phone_number", ""),
            "google_maps_url":  details.get("url", ""),
            "website":          details.get("website", ""),
            "has_website":      bool(details.get("website", "")),
            "rating":           details.get("rating", 0),
            "review_count":     details.get("user_ratings_total", 0),
            "reviews":          details.get("reviews", []),
            "price_level":      details.get("price_level", 0),
            "business_status":  details.get("business_status", "UNKNOWN"),
            "types":            details.get("types", []),
            "is_open":          bool(details.get("opening_hours", {}).get("open_now")),
            "hours":            details.get("opening_hours", {}).get("weekday_text", []),
            "description":      details.get("editorial_summary", {}).get("overview", ""),
            "photo_count":      len(details.get("photos", [])),
            "has_photos":       len(details.get("photos", [])) > 0,
            "photo_reference":  (details.get("photos", [{}])[0].get("photo_reference", "") if details.get("photos") else ""),
            "niche_key":        niche_key,
            "budget_tier":      budget_tier,
            "city":             city,
            # Filled by auditor / scorer later
            "website_score":    None,
            "mobile_score":     None,
            "website_issues":   [],
            "has_facebook":     False,
            "has_instagram":    False,
            "facebook_url":     "",
            "instagram_url":    "",
            "warmth_score":     0,
            "tier":             4,
            "tier_label":       "",
            "score_breakdown":  {},
        }
        leads.append(lead)

        if (i + 1) % 10 == 0:
            console.print(f"  [dim]  Processed {i+1}/{len(unique_places)}[/dim]")

    return leads
