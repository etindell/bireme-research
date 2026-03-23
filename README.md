# Keelhaul

ERA compliance calendar and task engine for small private exempt funds.

> *Forked from [Bireme Research](https://github.com/etindell/bireme-research), a multi-tenant Django platform for investment research and portfolio management. Keelhaul extends the compliance module with ERA-specific obligations, NASAA EFD integration, and data-driven task generation.*

## What it does

Keelhaul tracks compliance obligations for Exempt Reporting Advisers (ERAs) — the small fund managers (1-3 people) who are personally responsible for regulatory filings but have no compliance team and no budget for enterprise software.

- **Pulls real filing data** from NASAA EFD — blue sky notice filings, first sale dates, expiry dates, per fund
- **Auto-generates tasks** from actual regulatory triggers — Form ADV annual amendments, Form D anniversaries, blue sky renewals, ADV-NR for non-US principals
- **Tracks per-fund compliance** — each fund entity has its own CIK, investor jurisdictions, and filing status
- **Links to source** — every filing status card links directly to NASAA EFD with the original filing and state notice PDFs

## Quick Start

```bash
# Clone and set up
git clone https://github.com/mikenvt/bireme-research.git keelhaul
cd keelhaul
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure local environment
cat > .env << 'EOF'
DATABASE_URL=postgres:///keelhaul
DEBUG=True
ALLOWED_HOSTS=*
SECRET_KEY=dev-secret-key-not-for-production
EOF

# Database setup
createdb keelhaul
python manage.py migrate
python manage.py createsuperuser

# Seed ERA obligations and run the compliance engine
python manage.py seed_era_obligations --org <your-org-slug>
python manage.py run_compliance_engine --org <your-org-slug>

# Start the server
python manage.py runserver
```

Then visit `http://localhost:8000/compliance/`

## Compliance Engine

The compliance engine scans real regulatory data and creates tasks for what needs doing:

| Trigger | Source | Task Created |
|---------|--------|-------------|
| Form ADV annual amendment | Calendar (90 days after FYE) | File Part 1A on IARD |
| Form D anniversary | NASAA EFD filing dates | File D/A on EDGAR before anniversary |
| Blue sky renewal | NASAA EFD expiry dates | Renew state notice before expiry |
| Form ADV-NR | Non-US principal residency | Renew with annual ADV amendment |
| AML/CFT (2028) | FinCEN rule deadline | Preparation milestones |

Run it manually or via cron:
```bash
python manage.py run_compliance_engine
python manage.py send_compliance_reminders
```

## NASAA EFD Integration

Keelhaul pulls per-state filing data directly from [NASAA EFD](https://nasaaefd.org):
- State notice filing dates and expiry dates
- First sale dates per state
- Investor counts and amounts sold
- Direct links to filing pages and state notice PDFs

Each fund imports independently by CIK — different funds have different investor states.

## Design System

See [DESIGN.md](DESIGN.md) for the Keelhaul visual identity: deep navy + warm amber maritime palette, Instrument Serif headings, DM Sans body.

## Architecture

Built on Django with:
- Multi-tenant via OrganizationMixin
- HTMX + Alpine.js for interactive UI
- Tailwind CSS
- Soft-delete models with audit trail
- Survey system (dormant — preserved for future RIA registration)

## License

Same as upstream Bireme Research.
