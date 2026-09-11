# 📦 Quick-Commerce Restock Predictor

An autonomous agent that reads Blinkit order-confirmation emails, tracks per-item consumption patterns, and predicts when each item needs restocking — surfaced on a lightweight dashboard, at zero infrastructure cost.

![Stack](https://img.shields.io/badge/Frontend-Vanilla_HTML%2FJS-blue)
![Stack](https://img.shields.io/badge/Backend-Python_3.12-green)
![Stack](https://img.shields.io/badge/Database-Supabase-purple)
![Stack](https://img.shields.io/badge/Scheduler-GitHub_Actions-orange)

## How It Works

```
Gmail (IMAP) → Python Parser → Supabase (Postgres) → Static Dashboard
              (GitHub Actions cron, every 6h)        (GitHub Pages)
```

1. **Email Parser** connects to Gmail via IMAP, fetches Blinkit order confirmation emails, and extracts items, quantities, and prices
2. **Sync Pipeline** upserts items and orders into Supabase
3. **Forecaster** computes inter-purchase intervals using **Exponential Moving Average** (EMA, α=0.3) and predicts when each item will need restocking
4. **Dashboard** reads predictions from Supabase and displays a sorted restock timeline with urgency indicators

## Quick Start

### 1. Set Up Supabase
Follow the [Setup Guide](docs/setup_guide.md) to create your Supabase project and run the schema.

### 2. Configure Secrets
Add these to your GitHub repository secrets:

| Secret | Description |
|--------|-------------|
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail App Password ([generate one](https://myaccount.google.com/apppasswords)) |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key (never commit!) |

### 3. Update Dashboard Credentials
Edit `dashboard/app.js` and replace the placeholder `SUPABASE_URL` and `SUPABASE_ANON_KEY` with your values.

### 4. Deploy
- **Dashboard**: Enable GitHub Pages from `main` branch, `/dashboard` folder
- **Sync**: Runs automatically every 6 hours via GitHub Actions, or trigger manually from the Actions tab

## Project Structure

```
├── .github/workflows/sync.yml     # Cron job (every 6h)
├── backend/
│   ├── parsers/
│   │   ├── base.py                # Abstract email parser
│   │   └── blinkit.py             # Blinkit email parser
│   ├── forecaster.py              # SMA/EMA prediction engine
│   ├── sync.py                    # Orchestrator (entry point)
│   └── requirements.txt
├── dashboard/
│   ├── index.html                 # Dashboard page
│   ├── style.css                  # Dark glassmorphism theme
│   └── app.js                     # Supabase reads + rendering
├── supabase/
│   └── schema.sql                 # Tables + RLS policies
└── docs/
    └── setup_guide.md             # Step-by-step setup
```

## Forecasting Formula

```
Intervals:  gaps (days) between consecutive purchases of the same item
SMA:        (1/N) × Σ intervals[i]  for the last 3 intervals
EMA:        α × latest_interval + (1-α) × previous_EMA,  α = 0.3
Restock:    last_order_date + round(EMA)
Confidence: high (≥5 orders) · medium (3–4) · low (1–2)
```

## Supported Platforms

- ✅ **Blinkit** (Zomato)
- 🔜 Zepto
- 🔜 Swiggy Instamart
- 🔜 BigBasket

## Tech Choices

| Constraint | Choice |
|-----------|--------|
| Zero infra cost | GitHub Actions (free), Supabase (free tier), GitHub Pages (free) |
| No build step | Vanilla HTML/CSS/JS, CDN imports only |
| No persistent server | Single Python script, cron-scheduled |
| Read-only dashboard | Supabase RLS + anon key |
| Extensible parsers | Abstract base class pattern |

## License

MIT
