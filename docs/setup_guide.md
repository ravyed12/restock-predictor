# Quick-Commerce Restock Predictor — Setup Guide

## Prerequisites

- A Google account with 2-Step Verification enabled
- A free [Supabase](https://supabase.com) account
- A GitHub account (for Actions + Pages)

---

## 1. Create a Supabase Project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard) and click **New Project**
2. Choose your org, give it a name (e.g. `restock-predictor`), set a DB password, and pick a region close to you
3. Wait for the project to finish provisioning (~1 minute)

## 2. Run the Schema

1. In your Supabase dashboard, go to **SQL Editor** (left sidebar)
2. Click **New Query**
3. Paste the entire contents of [`supabase/schema.sql`](../supabase/schema.sql) into the editor
4. Click **Run** — you should see "Success. No rows returned" for each statement
5. Verify: go to **Table Editor** — you should see `items`, `orders`, `order_items`, and `predictions`

## 3. Copy Your Keys

1. Go to **Settings → API** in the Supabase dashboard
2. Note these values:
   - **Project URL** — looks like `https://abcdefgh.supabase.co`
   - **anon (public) key** — safe to commit, used by the dashboard
   - **service_role key** — **NEVER commit this** — used only in GitHub Secrets

## 4. Generate a Gmail App Password

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Ensure **2-Step Verification** is ON
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Select app = "Mail", device = "Other (Custom name)", enter "Restock Predictor"
5. Click **Generate** — copy the 16-character password (spaces don't matter)

## 5. Configure GitHub Secrets

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Add these **Repository Secrets**:

| Secret name                | Value                          |
|---------------------------|--------------------------------|
| `GMAIL_ADDRESS`           | Your Gmail address             |
| `GMAIL_APP_PASSWORD`      | The 16-char app password       |
| `SUPABASE_URL`            | Your Supabase project URL      |
| `SUPABASE_SERVICE_ROLE_KEY` | Your service_role key (secret!) |

## 6. Update Dashboard Credentials

1. Open `dashboard/app.js`
2. Replace the placeholder values at the top:
   ```js
   const SUPABASE_URL  = 'https://your-project.supabase.co';
   const SUPABASE_ANON_KEY = 'your-anon-key-here';
   ```

## 7. Enable GitHub Pages

1. Go to **Settings → Pages** in your GitHub repo
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/dashboard`
4. Save — your dashboard will be live at `https://<username>.github.io/<repo>/`

## 8. Test the Pipeline

1. Go to **Actions** tab, find "Sync Orders & Predict Restocks"
2. Click **Run workflow** → **Run workflow** (manual trigger)
3. Watch the run — it should complete in under 2 minutes
4. Check your Supabase tables — you should see data in `items`, `orders`, `order_items`, and `predictions`
5. Visit your GitHub Pages URL — the dashboard should show your items and predictions

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Authentication failed" in Actions | Double-check `GMAIL_APP_PASSWORD` — re-generate if needed |
| No emails found | Verify the Gmail address has Blinkit order confirmations |
| Dashboard shows no data | Check browser console for Supabase errors; verify anon key in `app.js` |
| RLS error on INSERT | Make sure the backend uses `SUPABASE_SERVICE_ROLE_KEY`, not the anon key |
