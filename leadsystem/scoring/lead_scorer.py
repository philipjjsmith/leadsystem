"""
Lead warmth scoring engine.
Takes a raw lead dict and assigns a 0-100 warmth score + tier 1-4.
Higher score = more likely to need and buy a website quickly.
"""

from config import SCORING, TIERS


def score_lead(lead: dict) -> dict:
    """
    Score a lead 0-100 and assign a tier.
    Returns the lead dict with warmth_score, tier, tier_label, score_breakdown added.
    """
    score = 0
    breakdown = {}

    # ── Website status (highest weight) ───────────────────────────────────────
    has_website = lead.get("has_website", False)
    mobile_score = lead.get("website_score", {}).get("mobile_performance") if lead.get("website_score") else None
    website_issues = lead.get("website_issues", [])

    if not has_website:
        points = SCORING["no_website"]
        score += points
        breakdown["No website"] = points
    else:
        if mobile_score is not None and mobile_score < 50:
            points = SCORING["bad_website_mobile"]
            score += points
            breakdown[f"Very poor mobile score ({mobile_score}/100)"] = points
        elif mobile_score is not None and mobile_score < 75:
            points = SCORING["bad_website_overall"]
            score += points
            breakdown[f"Poor mobile score ({mobile_score}/100)"] = points

    # ── Review volume (signals established, active business) ──────────────────
    review_count = lead.get("review_count", 0)
    if review_count >= 100:
        points = SCORING["reviews_100_plus"]
        score += points
        breakdown[f"{review_count} Google reviews (100+)"] = points
    elif review_count >= 50:
        points = SCORING["reviews_50_to_99"]
        score += points
        breakdown[f"{review_count} Google reviews (50-99)"] = points
    elif review_count >= 10:
        points = SCORING["reviews_10_to_49"]
        score += points
        breakdown[f"{review_count} Google reviews (10-49)"] = points

    # ── Rating quality ─────────────────────────────────────────────────────────
    rating = lead.get("rating", 0)
    if rating >= 4.0:
        points = SCORING["rating_4_plus"]
        score += points
        breakdown[f"Strong rating ({rating}★)"] = points
    elif rating >= 3.5:
        points = SCORING["rating_3_5_to_4"]
        score += points
        breakdown[f"Decent rating ({rating}★)"] = points

    # ── Contact info available ─────────────────────────────────────────────────
    if lead.get("phone"):
        points = SCORING["has_phone"]
        score += points
        breakdown["Phone number available"] = points

    # ── Social media present but no website (tech-willing) ───────────────────
    if not has_website and (lead.get("has_facebook") or lead.get("has_instagram")):
        points = SCORING["has_facebook_no_website"]
        score += points
        breakdown["Has social media but no website"] = points

    # ── Photos uploaded (cares about presentation) ────────────────────────────
    if lead.get("has_photos"):
        points = SCORING["has_photos"]
        score += points
        breakdown["Has Google photos"] = points

    # ── Niche budget tier bonus ────────────────────────────────────────────────
    budget_tier = lead.get("budget_tier", "")
    if budget_tier == "high":
        points = SCORING["high_budget_niche"]
        score += points
        breakdown[f"High-budget niche ({lead.get('niche_key', '')})"] = points
    elif budget_tier == "mid":
        points = SCORING["mid_budget_niche"]
        score += points
        breakdown[f"Mid-budget niche ({lead.get('niche_key', '')})"] = points

    # ── Active business bonus ──────────────────────────────────────────────────
    if lead.get("business_status") == "OPERATIONAL" and lead.get("is_open"):
        points = SCORING["business_open_active"]
        score += points
        breakdown["Currently operational"] = points

    # ── Cap at 100 ─────────────────────────────────────────────────────────────
    score = min(score, 100)

    # ── Assign tier ────────────────────────────────────────────────────────────
    tier = 4
    for t_num in [1, 2, 3, 4]:
        if score >= TIERS[t_num]["min_score"]:
            tier = t_num
            break

    lead["warmth_score"] = score
    lead["tier"] = tier
    lead["tier_label"] = f"{TIERS[tier]['emoji']} {TIERS[tier]['label']}"
    lead["score_breakdown"] = breakdown

    return lead


def get_outreach_scripts(lead: dict) -> dict:
    """
    Generate personalized phone, SMS, and email outreach scripts.
    Adapts to: no website / builder site (Wix/GoDaddy) / bad mobile / generic issues.
    """
    import json as _json

    name      = lead.get("name", "your business")
    city      = (lead.get("city") or "Florida").split(",")[0].strip()
    niche_raw = lead.get("niche_key", "")
    niche     = niche_raw.replace("_", " ")
    rating    = lead.get("rating") or 0
    reviews   = lead.get("review_count") or 0
    has_web   = bool(lead.get("has_website"))

    # Mobile score: stored as int in DB (mobile_score col) or nested in website_score dict.
    # Use explicit None check — 0 is a valid (terrible) score, not "missing".
    # -1 = audit didn't run (no website / skipped). None and -1 both mean "not measured".
    _raw_ms = lead.get("mobile_score")
    if _raw_ms is None or _raw_ms == -1:
        ws = lead.get("website_score") or {}
        if isinstance(ws, str):
            try: ws = _json.loads(ws)
            except Exception: ws = {}
        ms_val = ws.get("mobile_performance")
        mobile_score = ms_val if isinstance(ms_val, int) else None
    else:
        mobile_score = _raw_ms

    # Issues list
    issues = lead.get("website_issues") or []
    if isinstance(issues, str):
        try: issues = _json.loads(issues)
        except Exception: issues = []

    issues_text = " ".join(str(i) for i in issues).lower()
    has_wix     = "wix" in issues_text
    has_godaddy = "godaddy" in issues_text
    builder     = "Wix" if has_wix else ("GoDaddy Website Builder" if has_godaddy else None)

    urgency_map = {
        "hvac": "AC repair calls", "plumbing": "plumbing calls",
        "roofing": "roofing jobs", "electrician": "electrical jobs",
        "pressure_washing": "power washing jobs", "landscaping": "lawn care clients",
        "cleaning_service": "cleaning clients", "auto_repair": "car repair customers",
        "auto_detailing": "detailing appointments", "salon": "new clients",
        "pool_service": "pool service clients", "pest_control": "pest control calls",
        "painting": "painting jobs", "flooring": "flooring projects",
        "insurance_agent": "insurance clients", "dentist": "new patients",
        "chiropractic": "new patients", "law_firm": "new clients",
        "real_estate": "new clients", "restaurant": "new customers",
    }
    urgency  = urgency_map.get(niche_raw, "new customers")
    rev_line = f"{reviews} Google reviews and a {rating}★ rating — " if reviews >= 10 else ""

    # ── A: No website ──────────────────────────────────────────────────────────
    if not has_web:
        phone_script = (
            f"Hey, is this {name}?\n\n"
            f"My name's Philip — I'm a local web designer based in the Tampa Bay area.\n\n"
            f"I was searching for {niche} in {city} and found your Google listing. {rev_line}"
            f"but I couldn't find a website for you.\n\n"
            f"Right now, every customer who searches \"{niche} near me\" in {city} and finds your "
            f"listing clicks — and hits a dead end. No website means they call your competitor instead.\n\n"
            f"I build clean, fast websites for {niche} businesses — flat rate, no monthly fees, "
            f"usually live within 1-2 weeks.\n\n"
            f"Would you have 5 minutes this week to talk? I can even mock up what your site could "
            f"look like before you commit to anything."
        )
        sms = (
            f"Hey, this is Philip — local web designer. Found {name} on Google"
            f"{f' ({reviews} reviews, {rating}★)' if reviews >= 10 else ''} but no website. "
            f"You're missing {urgency} every day. I build fast sites for {niche} businesses, "
            f"flat rate. 5-min call this week? — Philip"
        )
        subj = f"Quick question about {name}'s online presence"
        body = (
            f"Hi there,\n\n"
            f"My name is Philip Smith and I'm a local web designer in the Tampa Bay area.\n\n"
            f"I came across {name} on Google while searching for {niche} in {city} — {rev_line}"
            f"but I noticed there's no website.\n\n"
            f"Here's what that's costing you right now: when someone in {city} searches "
            f"\"{niche} near me\" and your listing comes up, they click — and hit a dead end. "
            f"Most move straight to the first competitor who has a site.\n\n"
            f"I build clean, mobile-friendly websites specifically for {niche} businesses. "
            f"Flat rate. No monthly fees. I handle everything from design to launch.\n\n"
            f"I'd love to put together a free mock-up of what your site could look like. "
            f"No commitment whatsoever.\n\n"
            f"Would you be open to a quick 5-minute call this week?\n\n"
            f"Best,\nPhilip Smith\nLocal Web Designer — Tampa Bay Area"
        )

    # ── B: Builder site (Wix / GoDaddy) ───────────────────────────────────────
    elif builder:
        phone_script = (
            f"Hey, is this {name}?\n\n"
            f"My name's Philip — local web designer, Tampa Bay area. I looked at your website "
            f"and noticed it's built on {builder}. Wanted to give you a quick heads-up.\n\n"
            f"Those template builders load really slow on phones — and most people searching for "
            f"{niche} in {city} are on their phones. A slow site means Google ranks you lower "
            f"and customers bounce before they ever call you.\n\n"
            f"I specialize in converting {builder} sites to fast, custom websites — same content "
            f"you already have, dramatically better performance.\n\n"
            f"Would you have 5 minutes this week? I can pull up your exact speed data while we talk."
        )
        sms = (
            f"Hey, this is Philip — local web designer. {name}'s site is on {builder} which loads "
            f"slow on phones — hurting your Google ranking and losing you {urgency}. "
            f"I convert these to fast custom sites. Worth a quick look? — Philip"
        )
        subj = f"Your {builder} site is hurting your Google ranking — {name}"
        body = (
            f"Hi there,\n\n"
            f"My name is Philip and I'm a local web designer in the Tampa Bay area.\n\n"
            f"I came across {name} online and noticed your website is built on {builder}. "
            f"I wanted to flag something that's likely costing you {urgency}:\n\n"
            f"{builder} sites are known for slow mobile load times. Here's why that matters:\n\n"
            f"  - Google's ranking algorithm penalizes slow-loading sites\n"
            f"  - Over 60% of searches for {niche} happen on mobile phones\n"
            f"  - Slow sites see higher bounce rates — customers leave before they see your number\n\n"
            f"I help {niche} businesses migrate off {builder} to fast, custom websites that perform. "
            f"I keep all your existing content — just dramatically faster.\n\n"
            f"Happy to run a free speed comparison on your current site. No commitment.\n\n"
            f"Worth a quick call?\n\nBest,\nPhilip Smith\nLocal Web Designer — Tampa Bay Area"
        )

    # ── C: Bad mobile score ────────────────────────────────────────────────────
    elif mobile_score is not None and mobile_score < 75:
        grade = "critically slow" if mobile_score < 40 else "below Google's passing grade"
        phone_script = (
            f"Hey, is this {name}?\n\n"
            f"My name's Philip — local web designer, Tampa Bay area.\n\n"
            f"I ran a free Google performance check on your website — it's scoring {mobile_score} "
            f"out of 100 on mobile speed. Google's passing grade is 75. That puts it in the "
            f"{grade} range.\n\n"
            f"What that means practically: customers finding you on their phone are hitting a slow "
            f"site and bouncing — and Google is ranking you lower because of it.\n\n"
            f"I fix this for {niche} businesses. Quick turnaround, flat rate. "
            f"Would you have 5 minutes this week?"
        )
        sms = (
            f"Hey, this is Philip — quick heads-up: {name}'s website scores {mobile_score}/100 "
            f"on mobile speed (Google wants 75+). You're losing {urgency} to faster competitors. "
            f"I fix this fast — free audit? — Philip"
        )
        subj = f"{name}'s website scored {mobile_score}/100 on mobile — here's what that means"
        body = (
            f"Hi there,\n\n"
            f"My name is Philip and I'm a local web designer in the Tampa Bay area.\n\n"
            f"I ran a Google PageSpeed audit on {name}'s website:\n\n"
            f"  Mobile Performance Score: {mobile_score}/100\n"
            f"  Google's passing grade: 75+\n\n"
            f"Here's what that score means for your business:\n\n"
            f"  - Google actively demotes slow sites in local search rankings\n"
            f"  - 53% of mobile users leave if a page takes more than 3 seconds to load\n"
            f"  - Most people searching for {niche} in {city} are on their phone\n\n"
            f"This is very fixable. I work specifically with {niche} businesses to improve mobile "
            f"performance — most clients see measurable improvement in Google visibility within "
            f"30-60 days.\n\n"
            f"I can walk you through exactly what's causing the slowness — no cost, no commitment.\n\n"
            f"Worth a quick 5-minute call?\n\nBest,\nPhilip Smith\nLocal Web Designer — Tampa Bay Area"
        )

    # ── D: Generic — website exists, other issues ──────────────────────────────
    else:
        issue_count = len(issues) if issues else "a few"
        top_issue   = str(issues[0]).lower() if issues else "some technical gaps"
        phone_script = (
            f"Hey, is this {name}?\n\n"
            f"My name's Philip — local web designer, Tampa Bay area. I came across your business "
            f"while researching {niche} companies in {city} and ran a quick audit on your website.\n\n"
            f"I found {issue_count} issues that are likely affecting your Google ranking and costing "
            f"you {urgency}. The biggest one: {top_issue}.\n\n"
            f"I work specifically with {niche} businesses on quick, targeted fixes. Would you have "
            f"5 minutes this week? I can share my screen and show you exactly what I'm seeing."
        )
        sms = (
            f"Hey, this is Philip — local web designer. I audited {name}'s website and found "
            f"{issue_count} issues affecting your Google ranking and {urgency}. "
            f"Worth a quick look? — Philip"
        )
        subj = f"Website audit for {name} — {issue_count} issues found"
        body = (
            f"Hi there,\n\n"
            f"My name is Philip and I'm a local web designer in the Tampa Bay area.\n\n"
            f"I ran a free website audit on {name} and found some things worth flagging:\n\n"
            + "\n".join(f"  - {i}" for i in (issues[:5] if issues else ["Several optimization opportunities"]))
            + f"\n\nThese affect how Google ranks your site in {city} searches and can cost you "
            f"{urgency} every day they go unresolved.\n\n"
            f"I work specifically with {niche} businesses on fast, focused fixes — and I'd be "
            f"happy to walk you through the full audit at no cost.\n\n"
            f"Would you be open to a quick call this week?\n\n"
            f"Best,\nPhilip Smith\nLocal Web Designer — Tampa Bay Area"
        )

    return {
        "phone":         phone_script.strip(),
        "sms":           sms.strip(),
        "email_subject": subj,
        "email_body":    body.strip(),
    }


def get_suggested_price(lead: dict) -> str:
    """Suggest a project price range based on niche + website status."""
    budget_tier = lead.get("budget_tier", "mid")
    has_website = lead.get("has_website", False)

    if not has_website:
        prices = {
            "high": "$650 – $1,200",
            "mid": "$450 – $750",
            "entry": "$350 – $550",
        }
    else:
        prices = {
            "high": "$800 – $1,500 (redesign)",
            "mid": "$550 – $900 (redesign)",
            "entry": "$400 – $650 (redesign)",
        }

    return prices.get(budget_tier, "$450 – $750")


def get_pitch_angle(lead: dict) -> str:
    """
    One-line pitch angle specific to this lead's situation.
    Perfect for personalizing outreach.
    """
    name = lead.get("name", "your business")
    has_website = lead.get("has_website", False)
    review_count = lead.get("review_count", 0)
    rating = lead.get("rating", 0)
    mobile_score = (lead.get("website_score") or {}).get("mobile_performance", None)
    niche = lead.get("niche_key", "")

    if not has_website and review_count >= 50:
        return (
            f"{name} has {review_count} Google reviews and {rating}★ but no website — "
            f"every customer who searches is hitting a dead end."
        )
    elif not has_website:
        return (
            f"{name} has no website. Competitors in {lead.get('city','your area').split(',')[0]} "
            f"with sites are capturing every online search."
        )
    elif mobile_score is not None and mobile_score < 50:
        return (
            f"{name}'s website scores {mobile_score}/100 on mobile — "
            f"the majority of local searches happen on phones."
        )
    elif "hvac" in niche or "plumbing" in niche or "roofing" in niche:
        return (
            f"{name} is in a high-intent search niche — customers Google '{niche.replace('_',' ')} near me' "
            f"in emergencies and click the first professional site they see."
        )
    else:
        return (
            f"{name}'s online presence has clear gaps that are costing them leads every day."
        )
