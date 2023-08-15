CREATE TABLE film_database (
    title TEXT,
    letterboxd_url TEXT,
    watched_people INTEGER,
    avg_rating NUMERIC,
    popularity NUMERIC,
    watched BOOLEAN
);

CREATE TABLE processed_users (
    film_slug VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    rating FLOAT,
    PRIMARY KEY (film_slug, username)
);
