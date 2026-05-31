"""
CRM terminal display — all Rich-based views.
Nothing here touches the database; it only renders data passed to it.
"""

import json as _json
from datetime import date, datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box

from .models import STATUS_CONFIG, STATUS_ORDER, TIER_CONFIG, METHOD_CONFIG, OUTCOME_CONFIG

console = Console()


def _today() -> str:
    return date.today().isoformat()


def _fu_display(fu_date: str | None) -> str:
    """Colorize a follow-up date string."""
    if not fu_date:
        return "[dim]—[/dim]"
    today = _today()
    if fu_date < today:
        days = (date.today() - date.fromisoformat(fu_date)).days
        return f"[red]{fu_date} ({days}d ago)[/red]"
    if fu_date == today:
        return f"[bold yellow]{fu_date} TODAY[/bold yellow]"
    return f"[dim]{fu_date}[/dim]"


def _parse_json_field(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return _json.loads(value or "null") or fallback
    except Exception:
        return fallback


# ── Dashboard ─────────────────────────────────────────────────────────────────

def print_crm_dashboard(stats: dict, follow_ups: list) -> None:
    console.rule("[bold cyan]LeadSystem CRM[/bold cyan]")
    console.print()

    # Status count row
    panels = []
    for status in STATUS_ORDER:
        cfg = STATUS_CONFIG[status]
        count = stats["by_status"].get(status, 0)
        panels.append(Panel(
            f"[bold {cfg['color']}]{count}[/bold {cfg['color']}]\n[dim]{cfg['emoji']} {cfg['label']}[/dim]",
            width=14,
        ))
    console.print(Columns(panels))
    console.print()

    # Financial summary line
    closed_str   = f"[bold green]${stats['closed_total']:,.0f}[/bold green]"
    pipeline_str = f"[bold yellow]${stats['pipeline_total']:,.0f}[/bold yellow]"
    console.print(
        f"  Revenue closed: {closed_str} ({stats['closed_count']} deals)   "
        f"Pipeline: {pipeline_str} ({stats['pipeline_count']} deals)   "
        f"Close rate: [bold]{stats['close_rate']}%[/bold]   "
        f"Total leads: [bold]{stats['total']}[/bold]"
    )
    console.print()

    # Follow-ups
    today = _today()
    overdue  = [f for f in follow_ups if f.get("follow_up_date", "") < today]
    due_today = [f for f in follow_ups if f.get("follow_up_date", "") == today]

    if overdue:
        console.print(f"[bold red]  🚨 OVERDUE FOLLOW-UPS ({len(overdue)})[/bold red]")
        for lead in overdue[:5]:
            days = (date.today() - date.fromisoformat(lead["follow_up_date"])).days
            console.print(
                f"    [red]#{lead['id']}[/red]  [bold]{lead['name'][:32]}[/bold]"
                f"  {lead.get('phone','') or '—'}  [red]{days}d overdue[/red]"
            )
        if len(overdue) > 5:
            console.print(f"    [dim]...and {len(overdue)-5} more. Run: python main.py crm follow-ups[/dim]")
        console.print()

    if due_today:
        console.print(f"[bold yellow]  📅 DUE TODAY ({len(due_today)})[/bold yellow]")
        for lead in due_today:
            console.print(
                f"    [yellow]#{lead['id']}[/yellow]  [bold]{lead['name'][:32]}[/bold]"
                f"  {lead.get('phone','') or '—'}"
            )
        console.print()

    # Quick command reference
    console.print(
        "[dim]  Commands: [/dim]"
        "[cyan]crm pipeline[/cyan]  ·  "
        "[cyan]crm lead <id>[/cyan]  ·  "
        "[cyan]crm update <id>[/cyan]  ·  "
        "[cyan]crm log <id>[/cyan]  ·  "
        "[cyan]crm follow-ups[/cyan]  ·  "
        "[cyan]crm stats[/cyan]"
    )
    console.rule()


# ── Pipeline table ─────────────────────────────────────────────────────────────

def print_pipeline(leads: list, title: str = "Lead Pipeline") -> None:
    table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold white",
        title_style="bold cyan",
        border_style="bright_black",
        show_lines=False,
    )

    table.add_column("ID",       width=5,  justify="right", style="dim")
    table.add_column("Status",   width=16)
    table.add_column("T",        width=3,  justify="center")
    table.add_column("Score",    width=6,  justify="center")
    table.add_column("Business", min_width=24)
    table.add_column("Phone",    width=16)
    table.add_column("City",     width=13)
    table.add_column("Follow-up",width=18)
    table.add_column("Value",    width=10, justify="right")
    table.add_column("Notes",    min_width=22)

    for lead in leads:
        status = lead.get("status", "new")
        scfg   = STATUS_CONFIG.get(status, STATUS_CONFIG["new"])
        tier   = lead.get("tier", 4)
        tcfg   = TIER_CONFIG.get(tier, TIER_CONFIG[4])
        score  = lead.get("warmth_score", 0)
        sc     = "red" if score >= 75 else ("yellow" if score >= 50 else "blue")

        deal   = lead.get("deal_value") or 0
        val_str = f"[green]${deal:,.0f}[/green]" if deal else "[dim]—[/dim]"
        notes  = (lead.get("notes") or "")
        if "\n" in notes:
            notes = notes.split("\n")[-1]
        notes = notes[:24]

        table.add_row(
            str(lead["id"]),
            f"[{scfg['color']}]{scfg['emoji']} {scfg['label']}[/{scfg['color']}]",
            f"[{tcfg['color']}]{tcfg['emoji']}[/{tcfg['color']}]",
            f"[{sc}]{score}[/{sc}]",
            f"[bold]{lead.get('name','')[:24]}[/bold]",
            lead.get("phone","") or "[dim]—[/dim]",
            lead.get("city","").replace(", FL","")[:13],
            _fu_display(lead.get("follow_up_date")),
            val_str,
            f"[dim]{notes}[/dim]" if notes else "[dim]—[/dim]",
        )

    console.print(table)


# ── Lead detail ────────────────────────────────────────────────────────────────

def print_lead_detail(lead: dict, contact_log: list) -> None:
    status = lead.get("status","new")
    scfg   = STATUS_CONFIG.get(status, STATUS_CONFIG["new"])
    tier   = lead.get("tier", 4)
    tcfg   = TIER_CONFIG.get(tier, TIER_CONFIG[4])

    console.rule(f"[bold]#{lead['id']} — {lead.get('name')}[/bold]")
    console.print()

    # Identity
    console.print(f"  [dim]Status :[/dim]  [{scfg['color']}]{scfg['emoji']} {scfg['label']}[/{scfg['color']}]")
    console.print(f"  [dim]Score  :[/dim]  [{tcfg['color']}]{tcfg['emoji']} {lead.get('warmth_score')}/100[/{tcfg['color']}]  ({lead.get('tier_label','')})")
    console.print(f"  [dim]Phone  :[/dim]  [bold]{lead.get('phone') or 'Not listed'}[/bold]")
    console.print(f"  [dim]Address:[/dim]  {lead.get('address','')}")
    console.print(f"  [dim]Website:[/dim]  {lead.get('website') or '[red]No website[/red]'}")
    console.print(f"  [dim]Reviews:[/dim]  {lead.get('review_count',0)} Google reviews  ·  {lead.get('rating',0)}★")
    console.print(f"  [dim]Niche  :[/dim]  {lead.get('niche_key','').replace('_',' ').title()}")
    if lead.get("google_maps_url"):
        console.print(f"  [dim]Maps   :[/dim]  {lead['google_maps_url']}")
    console.print()

    # CRM state
    if lead.get("notes"):
        console.print("  [bold]Notes:[/bold]")
        for line in (lead["notes"] or "").split("\n"):
            if line.strip():
                console.print(f"    {line}")
        console.print()

    if lead.get("follow_up_date"):
        console.print(f"  [bold]Follow-up:[/bold] {_fu_display(lead['follow_up_date'])}")
        console.print()

    if lead.get("deal_value"):
        console.print(f"  [bold green]Deal value: ${lead['deal_value']:,.0f}[/bold green]")
        console.print()

    # Score breakdown
    breakdown = _parse_json_field(lead.get("score_breakdown"), {})
    if breakdown:
        console.print("  [bold]Score breakdown:[/bold]")
        for reason, pts in breakdown.items():
            console.print(f"    [green]+{pts:2d}[/green]  {reason}")
        console.print()

    # Website issues
    issues = _parse_json_field(lead.get("website_issues"), [])
    if issues:
        console.print("  [bold]Website issues found:[/bold]")
        for issue in issues[:6]:
            console.print(f"    [red]✗[/red] {issue}")
        console.print()

    # Contact history
    if contact_log:
        console.print(f"  [bold]Contact history ({len(contact_log)}):[/bold]")
        for entry in contact_log:
            mcfg = METHOD_CONFIG.get(entry["method"], {"emoji":"","label":entry["method"]})
            ocfg = OUTCOME_CONFIG.get(entry["outcome"], {"emoji":"","color":"white","label":entry["outcome"]})
            logged = entry["logged_at"][:10]
            note_part = f"  [dim italic]{entry['notes']}[/dim italic]" if entry.get("notes") else ""
            console.print(
                f"    [dim]{logged}[/dim]  "
                f"{mcfg['emoji']} {mcfg['label']}  →  "
                f"[{ocfg['color']}]{ocfg['emoji']} {ocfg['label']}[/{ocfg['color']}]"
                + note_part
            )
        console.print()

    console.rule()


# ── Stats ──────────────────────────────────────────────────────────────────────

def print_stats(stats: dict) -> None:
    console.rule("[bold cyan]Revenue & Pipeline Stats[/bold cyan]")
    console.print()

    panels = [
        Panel(f"[bold green]${stats['closed_total']:,.2f}[/bold green]\n[dim]Revenue closed[/dim]", width=22),
        Panel(f"[bold yellow]${stats['pipeline_total']:,.2f}[/bold yellow]\n[dim]In pipeline[/dim]", width=20),
        Panel(f"[bold]{stats['close_rate']}%[/bold]\n[dim]Close rate[/dim]", width=14),
        Panel(f"[bold]${stats['avg_deal']:,.0f}[/bold]\n[dim]Avg deal size[/dim]", width=16),
        Panel(f"[bold]{stats['total']}[/bold]\n[dim]Total leads[/dim]", width=14),
    ]
    console.print(Columns(panels))
    console.print()

    table = Table(box=box.SIMPLE, header_style="bold", show_edge=False, show_header=False)
    table.add_column(width=20)
    table.add_column(width=8, justify="right")

    for status in STATUS_ORDER:
        cfg   = STATUS_CONFIG[status]
        count = stats["by_status"].get(status, 0)
        table.add_row(
            f"[{cfg['color']}]{cfg['emoji']} {cfg['label']}[/{cfg['color']}]",
            f"[{cfg['color']}]{count}[/{cfg['color']}]",
        )

    console.print(table)
    console.rule()


# ── Follow-ups ─────────────────────────────────────────────────────────────────

def print_follow_up_list(leads: list) -> None:
    if not leads:
        console.print("[dim]No follow-ups scheduled.[/dim]")
        return

    table = Table(
        title="Scheduled Follow-ups",
        box=box.ROUNDED,
        header_style="bold white",
        title_style="bold cyan",
        border_style="bright_black",
    )
    table.add_column("ID",       width=5,  justify="right")
    table.add_column("Due",      width=22)
    table.add_column("Status",   width=16)
    table.add_column("Business", min_width=26)
    table.add_column("Phone",    width=16)
    table.add_column("Notes",    min_width=24)

    for lead in leads:
        status = lead.get("status","new")
        scfg   = STATUS_CONFIG.get(status, STATUS_CONFIG["new"])
        notes  = (lead.get("notes") or "")
        if "\n" in notes:
            notes = notes.split("\n")[-1]
        notes = notes[:26]

        table.add_row(
            str(lead["id"]),
            _fu_display(lead.get("follow_up_date")),
            f"[{scfg['color']}]{scfg['emoji']} {scfg['label']}[/{scfg['color']}]",
            lead.get("name","")[:26],
            lead.get("phone","") or "[dim]—[/dim]",
            f"[dim]{notes}[/dim]" if notes else "[dim]—[/dim]",
        )

    console.print(table)
