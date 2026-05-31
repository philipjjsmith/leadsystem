"""
Terminal dashboard using Rich.
Displays ranked leads with tier indicators, scores, and key info.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box
from config import TIERS


console = Console()


def print_lead_table(leads: list[dict], title: str = "Lead Pipeline") -> None:
    """Print a ranked table of all leads."""
    sorted_leads = sorted(leads, key=lambda x: x.get("warmth_score", 0), reverse=True)

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        title_style="bold cyan",
        border_style="bright_black",
    )

    table.add_column("Rank", style="dim", width=5, justify="right")
    table.add_column("Tier", width=4, justify="center")
    table.add_column("Score", width=7, justify="center")
    table.add_column("Business", min_width=22)
    table.add_column("City", width=14)
    table.add_column("Phone", width=15)
    table.add_column("Reviews", width=8, justify="right")
    table.add_column("Rating", width=7, justify="center")
    table.add_column("Website", width=10, justify="center")
    table.add_column("Niche", width=14)

    tier_colors = {1: "red", 2: "yellow", 3: "blue", 4: "white"}
    score_colors = lambda s: "red" if s >= 75 else ("yellow" if s >= 50 else ("blue" if s >= 25 else "dim"))

    for i, lead in enumerate(sorted_leads, 1):
        tier = lead.get("tier", 4)
        score = lead.get("warmth_score", 0)
        color = tier_colors.get(tier, "white")
        emoji = TIERS[tier]["emoji"]

        website_text = Text("✓", style="green") if lead.get("has_website") else Text("✗ NONE", style="bold red")
        rating_text = f"{lead.get('rating', 0)}★" if lead.get("rating") else "—"

        table.add_row(
            str(i),
            f"[{color}]{emoji}[/{color}]",
            f"[{score_colors(score)}]{score}[/{score_colors(score)}]",
            f"[bold]{lead.get('name', '')[:22]}[/bold]",
            lead.get("city", "").replace(", FL", "")[:14],
            lead.get("phone", "")[:15] or "[dim]No phone[/dim]",
            str(lead.get("review_count", 0)),
            rating_text,
            website_text,
            lead.get("niche_key", "").replace("_", " ")[:14],
        )

    console.print(table)


def print_summary_stats(leads: list[dict]) -> None:
    """Print summary statistics panel."""
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    total_with_phone = 0
    no_website = 0
    avg_score = 0

    for lead in leads:
        tier_counts[lead.get("tier", 4)] += 1
        if lead.get("phone"):
            total_with_phone += 1
        if not lead.get("has_website"):
            no_website += 1
        avg_score += lead.get("warmth_score", 0)

    avg_score = round(avg_score / len(leads)) if leads else 0

    stats = [
        Panel(f"[bold]{len(leads)}[/bold]\n[dim]total leads[/dim]", style="cyan", width=16),
        Panel(f"[bold red]{tier_counts[1]}[/bold red]\n[dim]🔥 Tier 1[/dim]", style="red", width=16),
        Panel(f"[bold yellow]{tier_counts[2]}[/bold yellow]\n[dim]⚡ Tier 2[/dim]", style="yellow", width=16),
        Panel(f"[bold red]{no_website}[/bold red]\n[dim]no website[/dim]", style="white", width=16),
        Panel(f"[bold]{total_with_phone}[/bold]\n[dim]have phone[/dim]", style="green", width=16),
        Panel(f"[bold]{avg_score}[/bold]\n[dim]avg score[/dim]", style="blue", width=16),
    ]
    console.print(Columns(stats))


def print_lead_detail(lead: dict) -> None:
    """Print detailed view of a single lead."""
    from scoring.lead_scorer import get_suggested_price, get_pitch_angle

    tier = lead.get("tier", 4)
    tier_color = {1: "red", 2: "yellow", 3: "blue", 4: "white"}.get(tier, "white")

    console.rule(f"[bold {tier_color}]{TIERS[tier]['emoji']} {lead.get('name')}[/bold {tier_color}]")
    console.print(f"  [dim]Score:[/dim] [bold]{lead.get('warmth_score')}/100[/bold]  |  [dim]Tier:[/dim] {lead.get('tier_label')}")
    console.print(f"  [dim]Address:[/dim] {lead.get('address')}")
    console.print(f"  [dim]Phone:[/dim] {lead.get('phone') or 'Not listed'}")
    console.print(f"  [dim]Website:[/dim] {lead.get('website') or '❌ No website'}")
    console.print(f"  [dim]Google:[/dim] {lead.get('rating')}★ — {lead.get('review_count')} reviews")

    if lead.get("score_breakdown"):
        console.print("\n  [bold]Score breakdown:[/bold]")
        for reason, pts in lead["score_breakdown"].items():
            console.print(f"    [green]+{pts:2d}[/green]  {reason}")

    if lead.get("website_issues"):
        console.print("\n  [bold]Website issues:[/bold]")
        for issue in lead["website_issues"][:5]:
            console.print(f"    [red]✗[/red] {issue}")

    console.print(f"\n  [bold]Pitch angle:[/bold]")
    console.print(f"  [italic]{get_pitch_angle(lead)}[/italic]")

    console.print(f"\n  [bold]Suggested price:[/bold] [green]{get_suggested_price(lead)}[/green]")
    console.rule()


def print_scan_progress(city: str, niche: str, found: int, tier1: int, tier2: int) -> None:
    console.print(
        f"  [cyan]✓[/cyan] [bold]{city}[/bold] / {niche}: "
        f"[white]{found}[/white] leads — "
        f"[red]{tier1} 🔥[/red]  [yellow]{tier2} ⚡[/yellow]"
    )
