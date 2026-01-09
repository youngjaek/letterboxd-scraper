-- Rename legacy RSS timestamp to track incremental scrapes.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'last_rss_poll_at'
    ) THEN
        ALTER TABLE users RENAME COLUMN last_rss_poll_at TO last_incremental_scrape_at;
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'last_incremental_scrape_at'
    ) THEN
        ALTER TABLE users ADD COLUMN last_incremental_scrape_at TIMESTAMPTZ;
    END IF;
END $$;
