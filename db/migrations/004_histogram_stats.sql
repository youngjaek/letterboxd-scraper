-- Store Letterboxd global histogram stats on films.
ALTER TABLE films
    ADD COLUMN IF NOT EXISTS letterboxd_rating_count INT,
    ADD COLUMN IF NOT EXISTS letterboxd_fan_count INT,
    ADD COLUMN IF NOT EXISTS letterboxd_weighted_average NUMERIC(4,2);
