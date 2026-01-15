-- Supabase Database Schema
-- Bu SQL dosyasını Supabase Dashboard'da SQL Editor'de çalıştırın

-- Market Data Cache Tablosu
CREATE TABLE IF NOT EXISTS market_data (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol);
CREATE INDEX IF NOT EXISTS idx_market_data_updated_at ON market_data(updated_at);

-- Positions Tablosu
CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    avg_price NUMERIC,
    market_value NUMERIC,
    unrealized_pnl NUMERIC,
    data JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);

-- Orders Tablosu
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL, -- 'BUY' or 'SELL'
    quantity NUMERIC NOT NULL,
    price NUMERIC,
    order_type TEXT, -- 'MARKET', 'LIMIT', etc.
    status TEXT, -- 'PENDING', 'FILLED', 'CANCELLED'
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- CSV Cache Tablosu
CREATE TABLE IF NOT EXISTS csv_cache (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_csv_cache_filename ON csv_cache(filename);

-- Scores Cache Tablosu (hesaplanmış skorları cache'lemek için)
CREATE TABLE IF NOT EXISTS scores_cache (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    scores JSONB NOT NULL,
    benchmark_type TEXT,
    benchmark_chg NUMERIC,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scores_cache_symbol ON scores_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_scores_cache_updated_at ON scores_cache(updated_at);

-- Real-time için Row Level Security (RLS) ayarları
-- NOT: Production'da RLS'yi düzgün yapılandırın!

-- Market data için RLS (şimdilik herkese açık - production'da değiştirin)
ALTER TABLE market_data ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable read access for all users" ON market_data FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON market_data FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON market_data FOR UPDATE USING (true);

-- Positions için RLS
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable read access for all users" ON positions FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON positions FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON positions FOR UPDATE USING (true);
CREATE POLICY "Enable delete access for all users" ON positions FOR DELETE USING (true);

-- Orders için RLS
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable read access for all users" ON orders FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON orders FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON orders FOR UPDATE USING (true);
CREATE POLICY "Enable delete access for all users" ON orders FOR DELETE USING (true);

-- CSV cache için RLS
ALTER TABLE csv_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable read access for all users" ON csv_cache FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON csv_cache FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON csv_cache FOR UPDATE USING (true);

-- Scores cache için RLS
ALTER TABLE scores_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable read access for all users" ON scores_cache FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON scores_cache FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON scores_cache FOR UPDATE USING (true);

-- Real-time için Realtime ayarları (Supabase Dashboard'da da yapılabilir)
-- ALTER PUBLICATION supabase_realtime ADD TABLE market_data;
-- ALTER PUBLICATION supabase_realtime ADD TABLE positions;
-- ALTER PUBLICATION supabase_realtime ADD TABLE orders;









