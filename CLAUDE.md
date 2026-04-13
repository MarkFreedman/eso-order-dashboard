# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask web app where Eschenbach Optik's customer service team reviews AI-extracted orders before they go into Sage 100 via Visual Integrator. The team (led by Lauren) opens this in a browser, sees a queue of extracted orders, clicks into one, reviews/edits the fields, and hits Submit. Submit generates a VI import file and updates the order status.

This is one of three repos for the Eschenbach order automation project:
- **vi-export-generator** (sibling repo) — converts extracted order JSON to Visual Integrator CSV for Sage 100 import.
- **intake-service** (sibling repo) — email monitoring, AI extraction, G drive storage, staging DB owner.
- **order-dashboard** (this repo) — review UI for Lauren's team.

## Tech Stack

- **Flask** with Jinja2 templates (server-rendered).
- **SQLite** staging database (owned by intake-service, this app connects read/write).
- **Entra ID SSO** via OpenID Connect for authentication (Lauren's team logs in with their Microsoft accounts).
- Hosted on **Fly.io** as a subdomain of eschenbach.com (e.g., orders.eschenbach.com).

## Key Reference Files

- Sibling repo `intake-service/db/schema.sql` — the staging DB schema this app reads from and writes to.
- Sibling repo `intake-service/db/design-notes.md` — schema rationale.
- Project-level docs in `~/Dropbox/projects/eschenbach-optic/`:
  - `design-decisions.md` — architectural decisions (SSO via Entra ID, sources model, needs-review fallback, attachment storage).
  - `task-list.md` — full task list. Dashboard is task #14. Auth is in #11e.
  - `everything-we-know.md` — comprehensive project knowledge base.

## Core Features

From task #14 and the build plan:

1. **Order queue.** List of all orders with status, customer name, date, item count, and a completeness/confidence score. Filterable by status (extracted, in_review, submitted, error).
2. **Order detail view.** Click into an order to see all extracted fields. Fields with low confidence scores are visually highlighted so the team knows where to look.
3. **Inline editing.** Team can correct any extracted field directly in the detail view.
4. **Side-by-side document view.** Original source document (from G drive) displayed next to the extracted data so the team can compare.
5. **"Submit to Sage" button.** Generates the VI import file (calls vi-export-generator logic), updates order status to "submitted", writes the VI file where Visual Integrator can pick it up.
6. **Needs-review resolution.** Orders flagged as needs-review (no order number found) show a prompt for the team to supply or correct the order number. On resolve, the G drive file is renamed from the placeholder to the proper `{order-number}.pdf`.
7. **Hold management.** All AI orders come in on Hold with an AI reason code. The dashboard shows this status clearly.

## Critical Business Rules

These are non-negotiable and must never be violated:

1. **All orders import on Hold.** OrderStatus = "H" always. The team reviews in this dashboard before anything is released in Sage.
2. **Ship-to address comes from the order document**, not the Sage customer record. Many orders ship to patients/veterans at addresses not in Sage.
3. **Price flagging.** Non-VA orders with a price mismatch between extracted price and expected Price Level must be flagged for approval. VA orders get a pass on price discrepancies.
4. **No credit card numbers displayed.** PCI compliance. Only last 4 digits, formatted as "VISA*1024" or similar.
5. **Order Source is FAX or EMAIL.** Display but don't allow editing to other values.
6. **Order Type defaults to Standard ("S").** Only switch to Quote ("Q") if the source document explicitly says "quote."

## Authentication

SSO via Entra ID (Microsoft). Lauren confirmed this on 4/8. Her reasoning: two employees are fully remote, so IP restriction wouldn't work, and Microsoft accounts are simpler to manage when someone leaves.

Implementation: OpenID Connect sign-in flow against an Entra ID app registration (Jason/Southridge provisions this, separate from the Graph API registration used by the intake service). Access can optionally be gated on an Entra security group Lauren manages.

The `reviewed_by` field in the orders table stores the display name or email from the SSO token. No local user table needed.

## Database

This app connects to the same SQLite database that the intake-service owns. Schema is at `../intake-service/db/schema.sql`. Four tables:
- **orders** — one row per sales order. Status flow: extracted -> in_review -> submitted -> error.
- **line_items** — one row per line item, joined to orders.
- **sources** — one row per source document (attachments, email body PDFs). Contains G drive paths for the side-by-side view.
- **email_watermark** — intake-service only, dashboard doesn't touch this.

The dashboard reads all four tables (except watermark) and writes to orders (status updates, field edits, review tracking), line_items (field edits), and sources (order_id assignment, placeholder rename on needs-review resolution).

## Repo Structure

```
order-dashboard/
  CLAUDE.md                   # this file
  .gitignore
  order_dashboard/            # Flask app package
    __init__.py
    templates/                # Jinja2 templates
    static/                   # CSS, JS, images
  tests/                      # pytest tests
```

## Development Commands

```bash
# Install dependencies (once requirements.txt exists)
pip3 install -r requirements.txt --break-system-packages

# Run the dev server (port 5001 — macOS AirPlay Receiver owns 5000)
flask --app order_dashboard run --debug --port 5001

# Run tests
python3 -m pytest tests/ -v
```

## Open Dependencies (not yet resolved)

- Entra ID app registration for dashboard SSO (Jason/Southridge, included in 4/10 email).
- DNS change pointing orders.eschenbach.com at Fly.io (Tim Gels / Marketing, Lauren connecting).
- Confirmation of G drive UNC path for source document links in side-by-side view (Jason/Southridge).
- VI import file landing location on Sage server (Avron/BrainSell).

## Design Guidance

- The goal is functional, not beautiful. Lauren's team needs to process orders quickly.
- Keep it simple. Server-rendered pages, minimal JavaScript. No SPA complexity.
- The team is not technical. UI should be obvious. No jargon, clear labels, big buttons.
- Confidence scores should map to visual cues (green/yellow/red or similar) so low-confidence fields are immediately visible without reading numbers.
