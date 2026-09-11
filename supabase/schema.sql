-- =============================================================
-- Quick-Commerce Restock Predictor — Supabase Schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- =============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----- 1. items -----
CREATE TABLE items (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name          TEXT NOT NULL UNIQUE,         -- full name from email e.g. "Amul Taaza Toned Fresh Milk 500 ml"
  display_name  TEXT,                         -- optional short name you can manually set
  category      TEXT,                         -- e.g. "dairy", "snacks" — nullable, for future use
  unit          TEXT NOT NULL DEFAULT 'pcs',  -- "pcs", "kg", "ml", "L" etc.
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----- 2. orders -----
CREATE TABLE orders (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  platform         TEXT NOT NULL DEFAULT 'blinkit',
  order_date       TIMESTAMPTZ NOT NULL,
  email_subject    TEXT,
  email_message_id TEXT UNIQUE,               -- IMAP Message-ID — dedup key
  total_amount     NUMERIC(10,2),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----- 3. order_items -----
CREATE TABLE order_items (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id    UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  item_id     UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  quantity    INTEGER NOT NULL DEFAULT 1,
  unit_price  NUMERIC(10,2),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_item  ON order_items(item_id);

-- ----- 4. predictions -----
CREATE TABLE predictions (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  item_id               UUID NOT NULL UNIQUE REFERENCES items(id) ON DELETE CASCADE,
  avg_interval_days     NUMERIC(6,2),          -- SMA of inter-purchase intervals
  ema_interval_days     NUMERIC(6,2),          -- EMA (α=0.3) of inter-purchase intervals
  last_ordered          TIMESTAMPTZ,
  predicted_restock_date DATE,
  confidence            TEXT CHECK (confidence IN ('high','medium','low')),
  times_purchased       INTEGER NOT NULL DEFAULT 0,
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_predictions_restock ON predictions(predicted_restock_date);

-- =============================================================
-- Row Level Security
-- =============================================================

ALTER TABLE items        ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders       ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items  ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions  ENABLE ROW LEVEL SECURITY;

-- Anon (dashboard) can only SELECT
CREATE POLICY "anon_read_items"        ON items        FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_orders"       ON orders       FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_order_items"  ON order_items  FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_predictions"  ON predictions  FOR SELECT TO anon USING (true);

-- Service role gets full access (bypasses RLS by default, but explicit for clarity)
CREATE POLICY "service_all_items"       ON items        FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_orders"      ON orders       FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_order_items" ON order_items  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_predictions" ON predictions  FOR ALL TO service_role USING (true) WITH CHECK (true);
