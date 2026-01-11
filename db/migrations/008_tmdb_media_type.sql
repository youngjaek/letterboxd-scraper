-- Add TMDB media-type metadata so movies/TV/episodes no longer collide on tmdb_id.

ALTER TABLE films
    DROP CONSTRAINT IF EXISTS films_tmdb_id_key;

ALTER TABLE films
    ADD COLUMN IF NOT EXISTS tmdb_media_type TEXT,
    ADD COLUMN IF NOT EXISTS tmdb_show_id INT,
    ADD COLUMN IF NOT EXISTS tmdb_season_number INT,
    ADD COLUMN IF NOT EXISTS tmdb_episode_number INT;

CREATE UNIQUE INDEX IF NOT EXISTS films_tmdb_media_key
    ON films (tmdb_id, tmdb_media_type)
    WHERE tmdb_id IS NOT NULL AND tmdb_media_type IS NOT NULL;
