-- Runs once when the "db" container initializes an empty data directory
-- (docker-entrypoint-initdb.d). Alembic's first migration also issues this
-- statement defensively, so it is safe if the database was created some
-- other way before migrations ran.
CREATE EXTENSION IF NOT EXISTS vector;
