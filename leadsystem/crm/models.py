"""
CRM display config — status labels, colors, emojis.
Single source of truth for all CRM state representations.
"""

STATUS_CONFIG = {
    "new":        {"emoji": "🆕", "color": "cyan",    "label": "New"},
    "called":     {"emoji": "📞", "color": "blue",    "label": "Called"},
    "interested": {"emoji": "⚡", "color": "yellow",  "label": "Interested"},
    "proposal":   {"emoji": "📋", "color": "magenta", "label": "Proposal Sent"},
    "closed":     {"emoji": "✅", "color": "green",   "label": "Closed"},
    "lost":       {"emoji": "❌", "color": "red",     "label": "Lost"},
}

STATUS_ORDER = ["new", "called", "interested", "proposal", "closed", "lost"]

METHOD_CONFIG = {
    "call":      {"emoji": "📞", "label": "Phone Call"},
    "email":     {"emoji": "📧", "label": "Email"},
    "sms":       {"emoji": "💬", "label": "SMS"},
    "in-person": {"emoji": "🤝", "label": "In Person"},
    "other":     {"emoji": "📝", "label": "Other"},
}

OUTCOME_CONFIG = {
    "no-answer":      {"emoji": "🔇", "color": "dim",     "label": "No Answer"},
    "left-vm":        {"emoji": "📨", "color": "blue",    "label": "Left Voicemail"},
    "not-interested": {"emoji": "❌", "color": "red",     "label": "Not Interested"},
    "interested":     {"emoji": "⚡", "color": "yellow",  "label": "Interested"},
    "proposal-sent":  {"emoji": "📋", "color": "magenta", "label": "Proposal Sent"},
    "closed":         {"emoji": "✅", "color": "green",   "label": "Closed Deal"},
}

TIER_CONFIG = {
    1: {"emoji": "🔥", "color": "red",    "label": "Tier 1"},
    2: {"emoji": "⚡", "color": "yellow", "label": "Tier 2"},
    3: {"emoji": "📊", "color": "blue",   "label": "Tier 3"},
    4: {"emoji": "📋", "color": "dim",    "label": "Tier 4"},
}
