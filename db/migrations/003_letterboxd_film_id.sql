-- Track Letterboxd-specific film identifiers for slug stability
ALTER TABLE films
    ADD COLUMN IF NOT EXISTS letterboxd_film_id INT UNIQUE;
