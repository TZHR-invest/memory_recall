-- Initialize database schema for Memory Recall
-- This file is automatically executed when Docker container starts for the first time

\echo 'Initializing Memory Recall database schema...'

-- Readand execute the main schema file
\i /docker-entrypoint-initdb.d/schema.sql

\echo 'Schema initialization complete!'