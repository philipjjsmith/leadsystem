"""
LeadSystem CLI
Usage:
  python main.py scan --city "Clearwater, FL" --niche hvac
  python main.py scan --city "Tampa, FL" --all-niches
  python main.py scan --florida-blitz --niches hvac,plumbing,roofing
  python main.py report --input output/leads/leads_20250529.json
  python main.py dashboard --input output/leads/leads_20250529.json
"""

import os
import sys
import time
import click
import json
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import print as rprint

console = Console()


def check_api_key():
    from config import GOOGLE_PLACES_API_KEY
    if not GOOGLE_PLACES_API_KEY:
        console.print("[bold red]ERROR:[/bold red] No Google Places API key found.")
        console.print("  1. Copy .env.example to .env")
        console.print("  2. Add your key: GOOGLE_PLACES_API_KEY=your_key_here")
        console.print("  3. Get a free key at: https://console.cloud.google.com")
        console.print("  4. Enable: Places API + PageSpeed Insights API")
        sys.exit(1)


@click.group()
def cli():
    """LeadSystem — Florida web design lead generation engine."""
    pass


@cli.command()
@click.option("--city", "-c", default=None, help="City to scan, e.g. 'Clearwater, FL'")
@click.option("--niche", "-n", default=None, help="Niche key, e.g. 'hvac' (see config.py for full list)")
@click.option("--all-niches", is_flag=True, help="Scan all niches for the given city")
@click.option("--florida-blitz", is_flag=True, help="Scan all Florida cities with selected niches")
@click.option("--niches", default="hvac,plumbing,roofing,salon,auto_repair", help="Comma-separated niches for blitz mode")
@click.option("--max-results", default=60, help="Max businesses per search (default 60, Google hard max)")
@click.option("--audit-websites", is_flag=True, default=True, help="Run PageSpeed audit on existing websites")
@click.option("--check-social", is_flag=True, default=True, help="Check social media presence")
@click.option("--tier1-only", is_flag=True, help="Only output Tier 1 leads")
@click.option("--no-website-only", "no_website_only", is_flag=True, help="Only keep leads with no website (including dead/broken sites)")
@click.option("--min-score", default=0, help="Minimum warmth score to include")
@click.option("--output-dir", default="output", help="Directory for output files")
@click.option("--contact-name", default="Philip Smith", help="Your name for reports")
@click.option("--contact-phone", default="", help="Your phone for reports")
@click.option("--auto-import", "auto_import", is_flag=True, help="Auto-import results into CRM after scan")
def scan(city, niche, all_niches, florida_blitz, niches, max_results,
         audit_websites, check_social, tier1_only, no_website_only, min_score,
         output_dir, contact_name, contact_phone, auto_import):
    """Scan for businesses with no/bad websites and score them."""

    check_api_key()

    from config import NICHES, FLORIDA_CITIES
    from scraper.places_client import collect_leads
    from scraper.website_auditor import audit_website
    from scraper.social_checker import enrich_with_social
    from scoring.lead_scorer import score_lead
    from reports.generator import export_leads_csv, save_leads_json, save_lead_report
    from dashboard.display import print_lead_table, print_summary_stats, print_scan_progress

    # ── Determine what to scan ─────────────────────────────────────────────────
    scan_targets = []  # list of (city, niche_key)

    if florida_blitz:
        cities_to_scan = FLORIDA_CITIES
        niches_to_scan = [n.strip() for n in niches.split(",") if n.strip() in NICHES]
        for c in cities_to_scan:
            for n in niches_to_scan:
                scan_targets.append((c, n))
    elif all_niches and city:
        for n in NICHES:
            scan_targets.append((city, n))
    elif city and niche:
        if niche not in NICHES:
            console.print(f"[red]Unknown niche: {niche}[/red]")
            console.print(f"Available: {', '.join(NICHES.keys())}")
            sys.exit(1)
        scan_targets.append((city, niche))
    else:
        console.print("[red]Specify --city + --niche, or --city + --all-niches, or --florida-blitz[/red]")
        sys.exit(1)

    all_leads = []
    total_targets = len(scan_targets)

    console.rule("[bold cyan]LeadSystem — Scanning Florida[/bold cyan]")
    console.print(f"  Targets: [bold]{total_targets}[/bold] city/niche combinations")
    console.print(f"  Mode: {'Website audit ✓' if audit_websites else 'Skip audit'} | {'Social check ✓' if check_social else 'Skip social'}")
    console.print()

    # ── Main scan loop ─────────────────────────────────────────────────────────
    for scan_num, (scan_city, niche_key) in enumerate(scan_targets, 1):
        niche_query, niche_display, budget_tier = NICHES[niche_key]
        console.print(f"[bold][{scan_num}/{total_targets}][/bold] {scan_city} — {niche_display}")

        try:
            raw_leads = collect_leads(niche_query, scan_city, niche_key, budget_tier, max_results)
        except Exception as e:
            console.print(f"  [red]Error collecting leads: {e}[/red]")
            continue

        enriched = []
        for lead in raw_leads:
            # ── Website audit ──────────────────────────────────────────────────
            if audit_websites and lead.get("has_website"):
                try:
                    scores, issues = audit_website(lead["website"])
                    lead["website_score"] = scores
                    lead["website_issues"] = issues
                    # Dead website detection: if site is unreachable, treat it
                    # as a no-website lead so it gets the full +40 bonus.
                    if issues and issues[0] == "Website is unreachable or broken":
                        lead["has_website"] = False
                        lead["website"] = ""
                        lead["website_score"] = None
                        lead["website_issues"] = []
                except Exception:
                    lead["website_issues"] = ["Website audit failed"]

            # ── Social check ───────────────────────────────────────────────────
            if check_social:
                try:
                    lead = enrich_with_social(lead)
                except Exception:
                    pass

            # ── Score ──────────────────────────────────────────────────────────
            lead = score_lead(lead)

            # ── Filter ─────────────────────────────────────────────────────────
            if tier1_only and lead["tier"] > 1:
                continue
            if no_website_only and lead.get("has_website"):
                continue
            if lead["warmth_score"] < min_score:
                continue

            enriched.append(lead)

        tier1 = sum(1 for l in enriched if l["tier"] == 1)
        tier2 = sum(1 for l in enriched if l["tier"] == 2)
        print_scan_progress(scan_city, niche_display, len(enriched), tier1, tier2)

        all_leads.extend(enriched)

    if not all_leads:
        console.print("[yellow]No leads found. Try different city/niche or lower --min-score.[/yellow]")
        return

    # ── Sort all leads by warmth score ─────────────────────────────────────────
    all_leads.sort(key=lambda x: x.get("warmth_score", 0), reverse=True)

    # ── Show dashboard ─────────────────────────────────────────────────────────
    console.rule("[bold cyan]Results[/bold cyan]")
    print_summary_stats(all_leads)
    console.print()
    print_lead_table(all_leads[:50], title=f"Top 50 Leads — Ranked by Warmth Score")

    # ── Save outputs ───────────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    json_path = save_leads_json(all_leads, os.path.join(output_dir, "leads", "latest.json"))
    csv_path = export_leads_csv(all_leads, os.path.join(output_dir, "leads", "latest.csv"))
    console.print(f"\n  [green]✓[/green] JSON saved: {json_path}")
    console.print(f"  [green]✓[/green] CSV saved: {csv_path}")

    # ── Generate HTML reports for Tier 1 + 2 ──────────────────────────────────
    top_leads = [l for l in all_leads if l["tier"] <= 2][:20]
    if top_leads:
        reports_dir = os.path.join(output_dir, "reports")
        console.print(f"\n  Generating HTML reports for {len(top_leads)} top leads...")
        for lead in top_leads:
            path = save_lead_report(lead, reports_dir, contact_name=contact_name, contact_phone=contact_phone)
            console.print(f"  [green]✓[/green] {lead['name'][:30]} — {path}")

    console.rule()
    console.print(f"[bold green]Done![/bold green] {len(all_leads)} leads found. {len([l for l in all_leads if l['tier']==1])} are 🔥 Tier 1.")
    console.print(f"Open [cyan]{os.path.join(output_dir, 'reports')}[/cyan] to view individual business reports.")
    console.print(f"Open [cyan]{csv_path}[/cyan] in Excel/Sheets for the full ranked list.")

    # ── Auto-import to CRM ─────────────────────────────────────────────────────
    if auto_import:
        from crm.database import init_db, import_leads
        init_db()
        result = import_leads(all_leads)
        console.print(
            f"\n[green]✓ CRM updated:[/green] "
            f"[cyan]{result['imported']} new[/cyan] · "
            f"[yellow]{result['updated']} updated[/yellow]"
        )
        console.print("  Open dashboard: [cyan]python main.py serve[/cyan]")


@cli.command()
@click.option("--input", "-i", "input_file", required=True, help="JSON file from a previous scan")
@click.option("--contact-name", default="Philip Smith", help="Your name for reports")
@click.option("--contact-phone", default="", help="Your phone for reports")
@click.option("--tier", default=2, help="Max tier to generate reports for (1=only tier1, 2=tier1+2, etc.)")
def report(input_file, contact_name, contact_phone, tier):
    """Generate HTML reports from a saved leads JSON file."""
    from reports.generator import save_lead_report
    from dashboard.display import print_summary_stats

    with open(input_file) as f:
        leads = json.load(f)

    console.print(f"Loaded {len(leads)} leads from {input_file}")
    print_summary_stats(leads)

    filtered = [l for l in leads if l.get("tier", 4) <= tier]
    console.print(f"\nGenerating reports for {len(filtered)} leads (tier 1-{tier})...")

    for lead in filtered:
        path = save_lead_report(lead, "output/reports", contact_name=contact_name, contact_phone=contact_phone)
        console.print(f"  [green]✓[/green] {lead.get('name', 'Unknown')[:35]}")

    console.print(f"\n[green]Done![/green] Open output/reports/ to view.")


@cli.command()
@click.option("--input", "-i", "input_file", required=True, help="JSON leads file")
@click.option("--detail", default=None, help="Show detail for lead # (1-based rank)")
def dashboard(input_file, detail):
    """Show the lead dashboard from a saved JSON file."""
    from dashboard.display import print_lead_table, print_summary_stats, print_lead_detail

    with open(input_file) as f:
        leads = json.load(f)

    sorted_leads = sorted(leads, key=lambda x: x.get("warmth_score", 0), reverse=True)

    if detail:
        idx = int(detail) - 1
        if 0 <= idx < len(sorted_leads):
            print_lead_detail(sorted_leads[idx])
        else:
            console.print(f"[red]Lead #{detail} not found (only {len(sorted_leads)} leads)[/red]")
        return

    console.rule("[bold cyan]Lead Dashboard[/bold cyan]")
    print_summary_stats(sorted_leads)
    console.print()
    print_lead_table(sorted_leads, "All Leads — Ranked by Warmth Score")


@cli.command()
def list_niches():
    """List all available niche keys."""
    from config import NICHES
    table_data = [(k, v[1], v[2]) for k, v in NICHES.items()]
    console.print("\n[bold]Available niches:[/bold]\n")
    for key, display, budget in sorted(table_data):
        color = "green" if budget == "high" else ("yellow" if budget == "mid" else "white")
        console.print(f"  [cyan]{key:<20}[/cyan] {display:<30} [{color}]{budget} budget[/{color}]")
    console.print()


@cli.command()
def list_cities():
    """List all Florida cities in the database."""
    from config import FLORIDA_CITIES
    console.print("\n[bold]Florida cities:[/bold]\n")
    for city in FLORIDA_CITIES:
        console.print(f"  {city}")
    console.print()


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind")
@click.option("--port", default=8000,        show_default=True, type=int, help="Port")
@click.option("--no-browser", is_flag=True,  help="Don't auto-open Chrome")
def serve(host, port, no_browser):
    """Start the local web dashboard at http://localhost:8000

    \b
    Opens your full CRM in the browser — pipeline, lead detail, contact logging,
    revenue stats. Same database as the terminal CRM, no data loss switching between them.

    Run a scan first, then:
      python main.py serve
    """
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Missing dependency: uvicorn[/red]")
        console.print("Fix: [cyan]pip install fastapi \"uvicorn[standard]\"[/cyan]")
        sys.exit(1)

    if not no_browser:
        import threading, webbrowser
        def _open():
            time.sleep(1.8)
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=_open, daemon=True).start()

    console.print(f"[bold green]LeadSystem Web[/bold green] → http://{host}:{port}")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")
    uvicorn.run("server.app:app", host=host, port=port, reload=False, log_level="warning")


# ═══════════════════════════════════════════════════════════════════════════════
# CRM COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group("crm", invoke_without_command=True)
@click.pass_context
def crm(ctx):
    """CRM — track your lead pipeline from first call to closed deal.

    \b
    Quick reference:
      python main.py crm                     # Dashboard (default)
      python main.py crm import-leads        # Import latest scan
      python main.py crm pipeline            # Full pipeline table
      python main.py crm lead <id>           # Detail view for one lead
      python main.py crm update <id>         # Update status / notes (interactive)
      python main.py crm log <id>            # Log a contact attempt (interactive)
      python main.py crm follow-ups          # All scheduled follow-ups
      python main.py crm stats               # Revenue and conversion stats
    """
    if ctx.invoked_subcommand is None:
        from crm.database import init_db, get_pipeline_stats, get_follow_ups, total_leads
        from crm.display import print_crm_dashboard
        init_db()
        if total_leads() == 0:
            console.print("[yellow]No leads in CRM yet.[/yellow]")
            console.print("Run a scan first, then import it:")
            console.print("  [cyan]python main.py scan --city \"Clearwater, FL\" --niche hvac --contact-phone \"727-XXX-XXXX\"[/cyan]")
            console.print("  [cyan]python main.py crm import-leads[/cyan]")
            return
        stats     = get_pipeline_stats()
        follow_ups = get_follow_ups()
        print_crm_dashboard(stats, follow_ups)


@crm.command("import-leads")
@click.option("--input", "-i", "input_file", default="output/leads/latest.json",
              show_default=True, help="JSON file from a scan")
def crm_import(input_file):
    """Import leads from a scan JSON into the CRM database.

    Safe to run multiple times — existing leads keep their CRM state.
    """
    from crm.database import init_db, import_leads
    init_db()

    if not os.path.exists(input_file):
        console.print(f"[red]File not found:[/red] {input_file}")
        console.print("Run a scan first: [cyan]python main.py scan --city \"Clearwater, FL\" --niche hvac[/cyan]")
        sys.exit(1)

    with open(input_file, encoding="utf-8") as f:
        leads = json.load(f)

    console.print(f"Importing [bold]{len(leads)}[/bold] leads from [dim]{input_file}[/dim]...")
    result = import_leads(leads)
    console.print(
        f"[green]Done![/green]  "
        f"[cyan]{result['imported']} new[/cyan]  ·  "
        f"[yellow]{result['updated']} updated[/yellow]  ·  "
        f"[dim]{result['skipped']} skipped[/dim]"
    )
    console.print("Open your CRM: [cyan]python main.py crm[/cyan]")


@crm.command("pipeline")
@click.option("--status", "-s", default=None,
              help="Filter: new / called / interested / proposal / closed / lost")
@click.option("--tier",   "-t", default=None, type=int,
              help="Filter by tier (1–4)")
@click.option("--city",   "-c", default=None, help="Filter by city name")
@click.option("--niche",  "-n", default=None, help="Filter by niche key")
def crm_pipeline(status, tier, city, niche):
    """Show the full pipeline as a ranked table."""
    from crm.database import get_leads
    from crm.display import print_pipeline

    leads = get_leads(status=status, tier=tier, city=city, niche=niche)
    if not leads:
        console.print("[yellow]No leads match those filters.[/yellow]")
        return

    title = "Lead Pipeline"
    if status:
        title += f" — {status.title()}"
    if tier:
        title += f" — Tier {tier}"
    print_pipeline(leads, title=title)
    console.print(f"[dim]  {len(leads)} leads shown[/dim]")


@crm.command("lead")
@click.argument("lead_id", type=int)
def crm_lead(lead_id):
    """View full detail for a single lead, including contact history."""
    from crm.database import get_lead, get_contact_log
    from crm.display import print_lead_detail

    lead = get_lead(lead_id)
    if not lead:
        console.print(f"[red]Lead #{lead_id} not found.[/red]")
        sys.exit(1)

    log = get_contact_log(lead_id)
    print_lead_detail(lead, log)


@crm.command("update")
@click.argument("lead_id", type=int)
@click.option("--status",    "-s", default=None, help="new/called/interested/proposal/closed/lost")
@click.option("--notes",     "-n", default=None, help="Append a note (timestamped automatically)")
@click.option("--follow-up", "-f", default=None, help="Follow-up date YYYY-MM-DD")
@click.option("--value",     "-v", default=None, type=float, help="Deal value in dollars")
def crm_update(lead_id, status, notes, follow_up, value):
    """Update a lead's status, notes, follow-up date, or deal value.

    \b
    Run with just the ID for interactive mode:
      python main.py crm update 3

    Or pass flags directly:
      python main.py crm update 3 --status interested --follow-up 2026-06-05
      python main.py crm update 3 --notes "Said to call back Thursday"
      python main.py crm update 3 --status closed --value 750
    """
    from crm.database import get_lead, update_lead
    from crm.models import STATUS_ORDER

    lead = get_lead(lead_id)
    if not lead:
        console.print(f"[red]Lead #{lead_id} not found.[/red]")
        sys.exit(1)

    updates = {}

    # ── Non-interactive (flags provided) ──────────────────────────────────────
    if any(x is not None for x in [status, notes, follow_up, value]):
        if status:
            if status not in STATUS_ORDER:
                console.print(f"[red]Invalid status:[/red] {status}")
                console.print(f"Valid values: {', '.join(STATUS_ORDER)}")
                sys.exit(1)
            updates["status"] = status
            if status == "closed" and not lead.get("closed_at"):
                updates["closed_at"] = datetime.now().isoformat()

        if notes:
            existing = (lead.get("notes") or "").strip()
            stamp    = datetime.now().strftime("%Y-%m-%d")
            updates["notes"] = (existing + f"\n[{stamp}] {notes}").strip()

        if follow_up:
            updates["follow_up_date"] = follow_up

        if value is not None:
            updates["deal_value"] = value

    else:
        # ── Interactive mode ───────────────────────────────────────────────────
        from crm.models import STATUS_CONFIG
        scfg = STATUS_CONFIG.get(lead.get("status","new"), STATUS_CONFIG["new"])

        console.print()
        console.print(f"[bold]#{lead_id} — {lead['name']}[/bold]")
        console.print(f"  Phone:   {lead.get('phone') or '—'}")
        console.print(f"  Status:  [{scfg['color']}]{scfg['emoji']} {scfg['label']}[/{scfg['color']}]")
        console.print(f"  Score:   {lead.get('warmth_score')}/100  ·  Tier {lead.get('tier')}")
        if lead.get("notes"):
            last_note = (lead["notes"] or "").split("\n")[-1]
            console.print(f"  Notes:   [dim]{last_note}[/dim]")
        console.print()

        # Status
        console.print("  Status options:")
        for i, s in enumerate(STATUS_ORDER, 1):
            cfg = STATUS_CONFIG[s]
            marker = " [green]← current[/green]" if s == lead.get("status") else ""
            console.print(f"    [{i}] [{cfg['color']}]{cfg['emoji']} {cfg['label']}[/{cfg['color']}]{marker}")
        s_in = console.input("\n  New status # (Enter to skip): ").strip()
        if s_in.isdigit() and 1 <= int(s_in) <= len(STATUS_ORDER):
            new_status = STATUS_ORDER[int(s_in) - 1]
            updates["status"] = new_status
            if new_status == "closed" and not lead.get("closed_at"):
                updates["closed_at"] = datetime.now().isoformat()

        # Notes
        n_in = console.input("  Add note (Enter to skip): ").strip()
        if n_in:
            existing = (lead.get("notes") or "").strip()
            stamp    = datetime.now().strftime("%Y-%m-%d")
            updates["notes"] = (existing + f"\n[{stamp}] {n_in}").strip()

        # Follow-up
        current_fu = lead.get("follow_up_date") or "not set"
        f_in = console.input(f"  Follow-up date YYYY-MM-DD (current: {current_fu}, Enter to skip): ").strip()
        if f_in:
            updates["follow_up_date"] = f_in

        # Deal value (show when relevant)
        new_status_val = updates.get("status", lead.get("status","new"))
        if new_status_val in ("proposal", "closed"):
            current_val = lead.get("deal_value") or 0
            v_in = console.input(f"  Deal value $ (current: ${current_val:,.0f}, Enter to skip): ").strip()
            if v_in:
                try:
                    updates["deal_value"] = float(v_in.replace("$","").replace(",",""))
                except ValueError:
                    console.print("[yellow]  Could not parse value — skipped.[/yellow]")

    # ── Apply ──────────────────────────────────────────────────────────────────
    if updates:
        update_lead(lead_id, **updates)
        console.print(f"\n[green]✓ Lead #{lead_id} updated.[/green]")
        for k, v in updates.items():
            if k not in ("updated_at", "closed_at"):
                console.print(f"  [dim]{k}:[/dim] {v}")
    else:
        console.print("[dim]No changes made.[/dim]")


@crm.command("log")
@click.argument("lead_id", type=int)
@click.option("--method",  "-m", default=None,
              help="call / email / sms / in-person / other")
@click.option("--outcome", "-o", default=None,
              help="no-answer / left-vm / not-interested / interested / proposal-sent / closed")
@click.option("--notes",   "-n", default="", help="Optional notes")
def crm_log(lead_id, method, outcome, notes):
    """Log a contact attempt for a lead.

    \b
    Interactive (recommended):
      python main.py crm log 3

    Or with flags:
      python main.py crm log 3 --method call --outcome interested --notes "Very receptive, wants proposal"
    """
    from crm.database import get_lead, log_contact
    from crm.models import METHOD_CONFIG, OUTCOME_CONFIG

    lead = get_lead(lead_id)
    if not lead:
        console.print(f"[red]Lead #{lead_id} not found.[/red]")
        sys.exit(1)

    console.print()
    console.print(f"[bold]#{lead_id} — {lead['name']}[/bold]  {lead.get('phone','') or ''}")
    console.print()

    # Method
    if not method:
        methods = list(METHOD_CONFIG.keys())
        console.print("  How did you contact them?")
        for i, m in enumerate(methods, 1):
            cfg = METHOD_CONFIG[m]
            console.print(f"    [{i}] {cfg['emoji']} {cfg['label']}")
        m_in = console.input("\n  Select # (Enter = call): ").strip()
        method = methods[int(m_in)-1] if m_in.isdigit() and 1 <= int(m_in) <= len(methods) else "call"

    # Outcome
    if not outcome:
        outcomes = list(OUTCOME_CONFIG.keys())
        console.print("\n  What happened?")
        for i, o in enumerate(outcomes, 1):
            cfg = OUTCOME_CONFIG[o]
            console.print(f"    [{i}] [{cfg['color']}]{cfg['emoji']} {cfg['label']}[/{cfg['color']}]")
        o_in = console.input("\n  Select # (Enter = no-answer): ").strip()
        outcome = outcomes[int(o_in)-1] if o_in.isdigit() and 1 <= int(o_in) <= len(outcomes) else "no-answer"

    # Notes
    if not notes:
        notes = console.input("  Notes (optional, Enter to skip): ").strip()

    log_contact(lead_id, method, outcome, notes)

    mcfg = METHOD_CONFIG.get(method, {"emoji":"","label": method})
    ocfg = OUTCOME_CONFIG.get(outcome, {"emoji":"","color":"white","label": outcome})
    console.print(
        f"\n[green]✓ Logged:[/green] "
        f"{mcfg['emoji']} {mcfg['label']}  →  "
        f"[{ocfg['color']}]{ocfg['emoji']} {ocfg['label']}[/{ocfg['color']}]"
    )

    # Context-aware next-step tips
    if outcome == "interested":
        console.print(f"\n[yellow]Next:[/yellow] Set a follow-up and send a proposal.")
        console.print(f"  [cyan]python main.py crm update {lead_id} --status interested --follow-up {datetime.now().strftime('%Y-%m-%d')}[/cyan]")
    elif outcome == "proposal-sent":
        console.print(f"\n[yellow]Next:[/yellow] Follow up in 2-3 days.")
        console.print(f"  [cyan]python main.py crm update {lead_id} --status proposal --follow-up {datetime.now().strftime('%Y-%m-%d')}[/cyan]")
    elif outcome == "closed":
        console.print(f"\n[green]Nice close![/green] Log the deal value:")
        console.print(f"  [cyan]python main.py crm update {lead_id} --status closed --value 750[/cyan]")
    elif outcome == "no-answer":
        console.print(f"\n[dim]Tip:[/dim] Try again in 24-48 hours. Leave a voicemail on the 2nd attempt.")


@crm.command("follow-ups")
def crm_followups():
    """Show all leads with a scheduled follow-up date."""
    from crm.database import get_follow_ups
    from crm.display import print_follow_up_list

    leads = get_follow_ups()
    if not leads:
        console.print("[dim]No follow-ups scheduled yet.[/dim]")
        console.print("Set one: [cyan]python main.py crm update <id> --follow-up YYYY-MM-DD[/cyan]")
        return
    print_follow_up_list(leads)


@crm.command("stats")
def crm_stats():
    """Show revenue, pipeline value, and conversion stats."""
    from crm.database import get_pipeline_stats
    from crm.display import print_stats

    stats = get_pipeline_stats()
    print_stats(stats)


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
