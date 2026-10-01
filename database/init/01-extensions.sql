-- Runs once, on first start of an empty data volume.
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for automated tests.
SELECT 'CREATE DATABASE shopsathi_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'shopsathi_test')\gexec

\connect shopsathi_test
CREATE EXTENSION IF NOT EXISTS vector;
