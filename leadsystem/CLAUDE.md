# LeadSystem — Claude Code Handoff

## What this project does

LeadSystem is a Florida-focused web design lead generation engine.
It scrapes Google Maps / Places API for local businesses with no website
or a poor website, scores them by "warmth" (likelihood to buy a web design
service), and generates personalized HTML audit reports you can send to
each business.

**Goal:** Find 2-3 paying clients for a $400-$1,000 web design project
in under 2 weeks. Fully remote. No bidding platforms.

---

## Setup (do this first)

```bash
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env`:
```
GOOGLE_PLACES_API_KEY=your_key_here
PAGESPEED_API_KEY=your_key_here   # same key works for both
```

**Getting a Google API key (5 minutes, free $200/month credit):**
1. Go to https://console.cloud.google.com
2. Create a project
3. Enable: "Places API" + "Geocoding API" + "PageSpeed Insights API"
4. Create credentials → API Key → copy into .env

---

## How to run

### Quick start — scan Clearwater for HVAC leads:
```bash
python main.py scan --city "Clearwater, FL" --niche hvac --contact-phone "727-555-0100"
```

### Scan multiple niches for one city:
```bash
python main.py scan --city "Tampa, FL" --all-niches --contact-phone "727-555-0100"
```

### Florida blitz — all cities, key niches:
```bash
python main.py scan --florida-blitz --niches "hvac,plumbing,roofing,salon,auto_repair" --contact-phone "727-555-0100"
```

### Only show Tier 1 leads (hottest):
```bash
python main.py scan --city "Clearwater, FL" --niche hvac --tier1-only
```

### View saved results:
```bash
python main.py dashboard --input output/leads/latest.json
python main.py dashboard --input output/leads/latest.json --detail 3   # detail view for lead #3
```

### Generate HTML reports from saved data:
```bash
python main.py report --input output/leads/latest.json --contact-phone "727-555-0100"
```

### List all available niches:
```bash
python main.py list-niches
```

---

## Output files

After a scan:
- `output/leads/latest.json` — full data for all leads (for reprocessing)
- `output/leads/latest.csv` — ranked spreadsheet (open in Excel/Sheets)
- `output/reports/BusinessName_Score.html` — individual business audit reports

**The HTML reports are what you send to prospects.** They show:
- The business's warmth score and tier
- What's missing (no website / bad mobile score / slow load)
- Their Google reviews and rating
- Your pitch angle and suggested price
- Your contact info at the bottom

---

## Lead scoring system

| Factor | Points |
|--------|--------|
| No website | +40 |
| Bad mobile score (<50) | +25 |
| Poor mobile (50-75) | +15 |
| 100+ Google reviews | +15 |
| 50-99 reviews | +10 |
| 10-49 reviews | +5 |
| Rating 4.0+ | +10 |
| Phone listed | +5 |
| Social media but no website | +10 |
| Has Google photos | +5 |
| High-budget niche (HVAC, law, medical) | +10 |
| Mid-budget niche | +5 |
| Active/operational | +3 |

**Tier 1 (75-100) 🔥** — Contact within 48 hours. No website, active, reviews.
**Tier 2 (50-74) ⚡** — High priority. Bad website or growing business.
**Tier 3 (25-49) 📊** — Worth reaching. Some gaps.
**Tier 4 (0-24) 📋** — Skip.

---

## High-value niches (Florida)

Best niches for fast closes (high budget, often no/bad website):
- `hvac` — HVAC / AC repair (Florida gold — every home needs AC)
- `plumbing` — Plumbing services
- `roofing` — Roofing contractors
- `electrician` — Electricians
- `auto_repair` — Auto mechanics
- `pest_control` — Pest control (Florida = bugs everywhere)
- `insurance_agent` — Insurance agents (Philip's network)
- `pool_service` — Pool service (Florida = pools everywhere)

---

## Project structure

```
leadsystem/
├── main.py                    # CLI — all commands
├── config.py                  # Niches, cities, scoring weights
├── requirements.txt
├── .env                       # Your API keys (not committed)
├── scraper/
│   ├── places_client.py       # Google Places API — finds businesses
│   ├── website_auditor.py     # PageSpeed Insights + website checks
│   └── social_checker.py      # Facebook / Instagram / Yelp detection
├── scoring/
│   └── lead_scorer.py         # Warmth scoring algorithm (0-100)
├── reports/
│   └── generator.py           # HTML reports + CSV export
├── dashboard/
│   └── display.py             # Rich terminal dashboard
└── output/                    # Generated files (gitignored)
    ├── leads/
    └── reports/
```

---

## Extending this project

Things Claude Code can help you add:

1. **Email automation** — Auto-draft outreach emails using lead data + AI
2. **SMS integration** — Twilio integration to text leads directly from CLI
3. **Competitor comparison** — Pull 3 competitors per lead who DO have websites
4. **Scheduled scanning** — Cron job to rescan weekly and alert on new leads
5. **Web dashboard** — Flask/FastAPI frontend to view leads in browser
6. **CRM export** — Push leads directly to HubSpot or Pipedrive
7. **Lead deduplication** — Prevent scanning the same business twice
8. **Outreach tracker** — Track which leads have been contacted and their responses

---

## Common Claude Code prompts for this project

```
"Run the scanner for Tampa, FL with all niches and show me the results"
"Add email drafting to the report — generate a personalized cold email for each lead"
"Build a simple web dashboard I can open in a browser to browse leads"
"Add a --deduplicate flag that skips businesses already in a previous scan"
"Generate a batch of outreach SMS messages for all Tier 1 leads"
"Add Twilio SMS sending so I can text a lead directly from the CLI"
```

---

## Notes

- Google Places API free tier: $200/month credit = ~6,000 place detail requests free
- PageSpeed Insights API: 100% free, no quota for normal use
- Social checks use Google search scraping — no paid APIs needed
- For Florida blitz, budget ~2-4 hours of scan time
- Tier 1 leads are the only ones worth contacting cold — Tier 2 needs a warm intro
