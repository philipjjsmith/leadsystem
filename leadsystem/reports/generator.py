"""
Report generator.
Produces two outputs per scan run:
  1. Individual HTML reports per lead (the "audit" you send the business)
  2. A master leads.csv with all results ranked by warmth score
"""

import os
import csv
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, BaseLoader
from config import REPORTS_DIR, LEADS_DIR


# ─── Individual Business Report HTML ──────────────────────────────────────────

REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Website Audit — {{ lead.name }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f9fa; color: #1a1a1a; line-height: 1.6; }
  .container { max-width: 760px; margin: 0 auto; padding: 2rem 1rem; }
  .header { background: #0f172a; color: white; border-radius: 12px; padding: 2rem; margin-bottom: 1.5rem; }
  .header h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 0.25rem; }
  .header .subtitle { color: #94a3b8; font-size: 0.9rem; }
  .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .tier-1 { background: #fee2e2; color: #991b1b; }
  .tier-2 { background: #fef3c7; color: #92400e; }
  .tier-3 { background: #dbeafe; color: #1e40af; }
  .card { background: white; border-radius: 10px; border: 1px solid #e2e8f0; padding: 1.5rem; margin-bottom: 1.25rem; }
  .card h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #0f172a; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.75rem; }
  .score-row { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #f8f9fa; }
  .score-row:last-child { border-bottom: none; }
  .score-label { color: #475569; font-size: 0.9rem; }
  .score-value { font-weight: 600; font-size: 0.9rem; }
  .score-good { color: #16a34a; }
  .score-warn { color: #d97706; }
  .score-bad { color: #dc2626; }
  .issue-list { list-style: none; }
  .issue-list li { padding: 0.5rem 0; color: #475569; font-size: 0.9rem; padding-left: 1.25rem; position: relative; border-bottom: 1px solid #f8f9fa; }
  .issue-list li:before { content: "✗"; position: absolute; left: 0; color: #ef4444; }
  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  .info-item label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; display: block; margin-bottom: 2px; }
  .info-item span { font-size: 0.9rem; font-weight: 500; }
  .big-score { font-size: 3rem; font-weight: 800; }
  .score-bar { height: 8px; background: #f1f5f9; border-radius: 4px; margin-top: 6px; }
  .score-fill { height: 100%; border-radius: 4px; }
  .cta-box { background: linear-gradient(135deg, #0f172a, #1e3a5f); color: white; border-radius: 12px; padding: 2rem; text-align: center; margin-top: 1.5rem; }
  .cta-box h3 { font-size: 1.3rem; margin-bottom: 0.5rem; }
  .cta-box p { color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }
  .cta-phone { font-size: 1.5rem; font-weight: 700; color: #60a5fa; }
  .opportunity { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 1rem; }
  .opportunity p { color: #166534; font-size: 0.9rem; }
  .breakdown-item { display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.85rem; }
  .breakdown-pts { color: #16a34a; font-weight: 600; }
  a { color: #2563eb; }
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
      <div>
        <h1>{{ lead.name }}</h1>
        <div class="subtitle">{{ lead.address }}</div>
        <div style="margin-top:0.75rem">
          <span class="badge tier-{{ lead.tier }}">{{ lead.tier_label }}</span>
          {% if lead.phone %}
          <span style="color:#64748b; font-size:0.85rem; margin-left:1rem">📞 {{ lead.phone }}</span>
          {% endif %}
        </div>
      </div>
      <div style="text-align:right">
        <div style="color:#94a3b8; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em;">Warmth Score</div>
        <div class="big-score" style="color:{% if lead.warmth_score >= 75 %}#f87171{% elif lead.warmth_score >= 50 %}#fbbf24{% else %}#60a5fa{% endif %}">{{ lead.warmth_score }}</div>
        <div style="color:#64748b; font-size:0.75rem;">/100</div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Business Overview</h2>
    <div class="info-grid">
      <div class="info-item"><label>Google Rating</label><span>{% if lead.rating %}{{ lead.rating }}★{% else %}No rating yet{% endif %}</span></div>
      <div class="info-item"><label>Reviews</label><span>{{ lead.review_count }} Google reviews</span></div>
      <div class="info-item"><label>Website</label><span>{% if lead.website %}<a href="{{ lead.website }}">{{ lead.website[:40] }}{% if lead.website|length > 40 %}...{% endif %}</a>{% else %}❌ No website{% endif %}</span></div>
      <div class="info-item"><label>Business Status</label><span>{{ lead.business_status }}</span></div>
      <div class="info-item"><label>Facebook</label><span>{% if lead.has_facebook %}<a href="{{ lead.facebook_url }}">Found ✓</a>{% else %}Not found{% endif %}</span></div>
      <div class="info-item"><label>Instagram</label><span>{% if lead.has_instagram %}<a href="{{ lead.instagram_url }}">Found ✓</a>{% else %}Not found{% endif %}</span></div>
      <div class="info-item"><label>Niche</label><span>{{ lead.niche_key | replace('_',' ') | title }}</span></div>
      <div class="info-item"><label>City</label><span>{{ lead.city }}</span></div>
    </div>
  </div>

  {% if not lead.has_website %}
  <div class="card">
    <h2>⚠️ No Website Found</h2>
    <div class="opportunity">
      <p><strong>This business has no website.</strong> Every customer who searches for them on Google hits a dead end. They are actively losing leads to competitors every single day. This is your opening — they need one, they just haven't found the right person to build it yet.</p>
    </div>
    {% if lead.review_count >= 20 %}
    <p style="margin-top:1rem; color:#475569; font-size:0.9rem">With {{ lead.review_count }} Google reviews and a {{ lead.rating }}★ rating, this is clearly an active, legitimate business that customers trust. A professional website would immediately convert those searchers into booked customers.</p>
    {% endif %}
  </div>
  {% endif %}

  {% if lead.has_website and lead.website_issues %}
  <div class="card">
    <h2>🔍 Website Audit Results</h2>
    {% if lead.website_score %}
    <div style="display:grid; grid-template-columns: repeat(2, 1fr); gap:1rem; margin-bottom:1.25rem;">
      {% for label, key in [('Mobile Performance', 'mobile_performance'), ('Desktop Performance', 'desktop_performance'), ('SEO Score', 'seo'), ('Accessibility', 'accessibility')] %}
      {% set val = lead.website_score.get(key, 0) %}
      <div>
        <div style="display:flex; justify-content:space-between;">
          <span style="font-size:0.8rem; color:#64748b;">{{ label }}</span>
          <span style="font-size:0.8rem; font-weight:600; color:{% if val >= 75 %}#16a34a{% elif val >= 50 %}#d97706{% else %}#dc2626{% endif %}">{{ val }}/100</span>
        </div>
        <div class="score-bar"><div class="score-fill" style="width:{{ val }}%; background:{% if val >= 75 %}#16a34a{% elif val >= 50 %}#d97706{% else %}#dc2626{% endif %};"></div></div>
      </div>
      {% endfor %}
    </div>
    {% endif %}
    <ul class="issue-list">
      {% for issue in lead.website_issues %}
      <li>{{ issue }}</li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}

  <div class="card">
    <h2>📊 Lead Score Breakdown</h2>
    {% for reason, pts in lead.score_breakdown.items() %}
    <div class="breakdown-item">
      <span style="color:#475569;">{{ reason }}</span>
      <span class="breakdown-pts">+{{ pts }} pts</span>
    </div>
    {% endfor %}
    <div style="border-top:2px solid #0f172a; margin-top:0.75rem; padding-top:0.75rem; display:flex; justify-content:space-between;">
      <strong>Total warmth score</strong>
      <strong>{{ lead.warmth_score }}/100</strong>
    </div>
  </div>

  {% if lead.reviews %}
  <div class="card">
    <h2>💬 Recent Customer Reviews</h2>
    {% for review in lead.reviews[:3] %}
    <div style="padding:0.75rem 0; border-bottom: 1px solid #f1f5f9;">
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <strong style="font-size:0.9rem;">{{ review.author_name }}</strong>
        <span style="font-size:0.85rem; color:#d97706;">{{ '★' * review.rating }}</span>
      </div>
      <p style="font-size:0.85rem; color:#475569;">{{ review.text[:200] }}{% if review.text|length > 200 %}...{% endif %}</p>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="card">
    <h2>💰 Suggested Approach</h2>
    <p style="color:#475569; font-size:0.9rem; margin-bottom:1rem;">{{ pitch_angle }}</p>
    <div style="background:#f8fafc; border-radius:8px; padding:1rem;">
      <div style="font-size:0.8rem; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em;">Suggested Project Price</div>
      <div style="font-size:1.5rem; font-weight:700; color:#0f172a; margin-top:4px;">{{ suggested_price }}</div>
      <div style="font-size:0.8rem; color:#94a3b8; margin-top:2px;">Collect 50% upfront (~{{ deposit }})</div>
    </div>
  </div>

  <div class="cta-box">
    <h3>Ready to get online?</h3>
    <p>Fast turnaround · Flat rate · Local Florida developer</p>
    <div class="cta-phone">{{ contact_phone }}</div>
    <div style="color:#64748b; font-size:0.85rem; margin-top:0.5rem;">{{ contact_name }}</div>
  </div>

  <div style="text-align:center; color:#94a3b8; font-size:0.8rem; margin-top:1.5rem;">
    Generated {{ generated_date }} · {{ lead.google_maps_url and '<a href="' + lead.google_maps_url + '" style="color:#94a3b8">View on Google Maps</a>' or '' }}
  </div>

</div>
</body>
</html>"""


def generate_lead_report(lead: dict, contact_name: str = "Philip Smith", contact_phone: str = "") -> str:
    """Generate an individual HTML report for a single lead. Returns HTML string."""
    from scoring.lead_scorer import get_suggested_price, get_pitch_angle

    suggested_price = get_suggested_price(lead)
    pitch_angle = get_pitch_angle(lead)

    # Extract deposit from price string
    try:
        price_nums = [int(s.replace(",", "")) for s in suggested_price.replace("$", "").split("–")[0].split() if s.replace(",", "").isdigit()]
        deposit = f"${price_nums[0] // 2:,}" if price_nums else "~$250"
    except Exception:
        deposit = "~$250"

    env = Environment(loader=BaseLoader())
    template = env.from_string(REPORT_TEMPLATE)
    return template.render(
        lead=lead,
        pitch_angle=pitch_angle,
        suggested_price=suggested_price,
        deposit=deposit,
        contact_name=contact_name,
        contact_phone=contact_phone,
        generated_date=datetime.now().strftime("%B %d, %Y"),
    )


def save_lead_report(lead: dict, output_dir: str = REPORTS_DIR, **kwargs) -> str:
    """Save HTML report to disk. Returns file path."""
    os.makedirs(output_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "- " else "_" for c in lead.get("name", "lead"))
    safe_name = safe_name.replace(" ", "_")[:40]
    filename = f"{safe_name}_{lead.get('warmth_score', 0)}.html"
    filepath = os.path.join(output_dir, filename)

    html = generate_lead_report(lead, **kwargs)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return filepath


def export_leads_csv(leads: list[dict], filepath: str = None) -> str:
    """Export all leads to a ranked CSV file."""
    if not filepath:
        os.makedirs(LEADS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(LEADS_DIR, f"leads_{timestamp}.csv")

    sorted_leads = sorted(leads, key=lambda x: x.get("warmth_score", 0), reverse=True)

    fieldnames = [
        "tier", "warmth_score", "name", "city", "phone", "website", "rating",
        "review_count", "has_website", "has_facebook", "has_instagram",
        "niche_key", "budget_tier", "address", "google_maps_url",
        "mobile_performance", "pitch_angle",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in sorted_leads:
            from scoring.lead_scorer import get_pitch_angle
            row = {k: lead.get(k, "") for k in fieldnames}
            row["mobile_performance"] = (lead.get("website_score") or {}).get("mobile_performance", "N/A")
            row["pitch_angle"] = get_pitch_angle(lead)
            writer.writerow(row)

    return filepath


def save_leads_json(leads: list[dict], filepath: str = None) -> str:
    """Save full lead data as JSON for later processing."""
    if not filepath:
        os.makedirs(LEADS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(LEADS_DIR, f"leads_{timestamp}.json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, default=str)

    return filepath
