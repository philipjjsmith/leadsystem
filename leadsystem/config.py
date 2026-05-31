import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", "")

# ─── Florida Cities ────────────────────────────────────────────────────────────
FLORIDA_CITIES = [
    "Clearwater, FL",
    "Tampa, FL",
    "St. Petersburg, FL",
    "Sarasota, FL",
    "Orlando, FL",
    "Fort Lauderdale, FL",
    "Miami, FL",
    "Jacksonville, FL",
    "Naples, FL",
    "Fort Myers, FL",
    "Bradenton, FL",
    "Lakeland, FL",
    "Palm Harbor, FL",
    "Largo, FL",
    "Dunedin, FL",
    "New Port Richey, FL",
    "Wesley Chapel, FL",
    "Brandon, FL",
]

# ─── High-Value Target Niches ──────────────────────────────────────────────────
# Format: (search_query, display_name, budget_tier)
# budget_tier: "high" = likely $600-1200 project, "mid" = $400-700, "entry" = $300-500
NICHES = {
    "hvac": ("HVAC air conditioning repair", "HVAC / AC Repair", "high"),
    "plumbing": ("plumber plumbing service", "Plumbing", "high"),
    "roofing": ("roofing contractor", "Roofing", "high"),
    "electrician": ("electrician electrical contractor", "Electrician", "high"),
    "landscaping": ("landscaping lawn care service", "Landscaping / Lawn Care", "mid"),
    "pool_service": ("pool service repair cleaning", "Pool Service", "mid"),
    "pressure_washing": ("pressure washing power washing", "Pressure Washing", "mid"),
    "auto_repair": ("auto repair mechanic shop", "Auto Repair", "high"),
    "auto_detailing": ("auto detailing car detailing", "Auto Detailing", "mid"),
    "salon": ("hair salon barbershop beauty salon", "Salon / Barbershop", "mid"),
    "restaurant": ("restaurant food local dining", "Restaurant", "mid"),
    "cleaning_service": ("house cleaning maid service", "Cleaning Service", "mid"),
    "pest_control": ("pest control exterminator", "Pest Control", "high"),
    "painting": ("painting contractor house painter", "Painting Contractor", "mid"),
    "flooring": ("flooring installation hardwood tile", "Flooring", "high"),
    "insurance_agent": ("insurance agent broker", "Insurance Agent", "high"),
    "law_firm": ("law firm attorney lawyer", "Law Firm / Attorney", "high"),
    "dentist": ("dentist dental office", "Dentist", "high"),
    "chiropractic": ("chiropractor chiropractic", "Chiropractor", "high"),
    "real_estate": ("real estate agent broker", "Real Estate Agent", "mid"),
}

# ─── Lead Tier Definitions ─────────────────────────────────────────────────────
TIERS = {
    1: {
        "label": "Tier 1 — Immediate Contact",
        "emoji": "🔥",
        "color": "red",
        "min_score": 75,
        "description": "No website, active business, verified reviews. Close within 48 hours.",
    },
    2: {
        "label": "Tier 2 — High Priority",
        "emoji": "⚡",
        "color": "yellow",
        "min_score": 50,
        "description": "Bad/outdated website or high-activity no-website business. Contact this week.",
    },
    3: {
        "label": "Tier 3 — Worth Reaching",
        "emoji": "📊",
        "color": "blue",
        "min_score": 25,
        "description": "Some web presence gaps. Good for follow-up outreach.",
    },
    4: {
        "label": "Tier 4 — Low Priority",
        "emoji": "📋",
        "color": "white",
        "min_score": 0,
        "description": "Decent web presence. Skip unless volume is low.",
    },
}

# ─── Scoring Weights ───────────────────────────────────────────────────────────
SCORING = {
    "no_website": 40,
    "bad_website_mobile": 25,        # mobile score < 50
    "bad_website_overall": 15,       # overall score 50-70
    "reviews_100_plus": 15,
    "reviews_50_to_99": 10,
    "reviews_10_to_49": 5,
    "rating_4_plus": 10,
    "rating_3_5_to_4": 5,
    "has_phone": 5,
    "has_facebook_no_website": 10,
    "has_photos": 5,
    "high_budget_niche": 10,
    "mid_budget_niche": 5,
    "business_open_active": 3,
}

# ─── Secondary Search Queries (doubles lead count per niche via deduplication) ─
# Each niche runs both the primary NICHES query AND this one.
# Results are merged and deduplicated by place_id before scoring.
NICHE_SECONDARY_QUERY = {
    "hvac":             "AC service air conditioning cooling heating",
    "plumbing":         "drain repair water heater plumber",
    "roofing":          "roof repair roofer shingle replacement",
    "electrician":      "electrical repair wiring contractor",
    "landscaping":      "lawn care lawn mowing yard maintenance",
    "pool_service":     "pool cleaning pool maintenance swimming pool",
    "pressure_washing": "power washing exterior cleaning house",
    "auto_repair":      "car repair mechanic auto service shop",
    "auto_detailing":   "car wash auto spa vehicle detailing",
    "salon":            "hair stylist beauty salon nail salon",
    "restaurant":       "local restaurant eatery cafe diner",
    "cleaning_service": "cleaning company maid service home cleaning",
    "pest_control":     "termite control bug exterminator",
    "painting":         "house painter interior exterior painting",
    "flooring":         "floor installation hardwood carpet tile",
    "insurance_agent":  "insurance office broker coverage",
    "law_firm":         "law office legal services attorney",
    "dentist":          "dental care teeth whitening dental clinic",
    "chiropractic":     "back pain spine adjustment chiropractic",
    "real_estate":      "realtor homes for sale real estate office",
}

# ─── Search Settings ───────────────────────────────────────────────────────────
SEARCH_RADIUS_METERS = 25000    # 25km radius per city
MAX_RESULTS_PER_SEARCH = 60     # Google Pages API max (3 pages × 20)
REQUEST_DELAY_SECONDS = 0.5     # Be polite to the API

# ─── Output Paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR = "output"
LEADS_DIR = "output/leads"
REPORTS_DIR = "output/reports"
