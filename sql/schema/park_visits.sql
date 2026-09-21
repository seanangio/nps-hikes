-- Park visits table schema
-- Stores individual park visit records. A park may have more than one row
-- here if it has been visited on more than one trip; the parks table's
-- visit_month/visit_year columns only ever hold the earliest visit.

CREATE TABLE IF NOT EXISTS park_visits (
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    visit_month VARCHAR(10) NOT NULL,
    visit_year INTEGER NOT NULL,

    PRIMARY KEY (park_code, visit_month, visit_year),
    FOREIGN KEY (park_code) REFERENCES parks(park_code)
);

CREATE INDEX IF NOT EXISTS idx_park_visits_park_code ON park_visits (park_code);

COMMENT ON TABLE park_visits IS 'Individual park visit records; a park has one row per trip it was visited on';
COMMENT ON COLUMN park_visits.visit_month IS 'Month of this particular visit';
COMMENT ON COLUMN park_visits.visit_year IS 'Year of this particular visit';
