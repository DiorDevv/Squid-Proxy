-- GIN trigram indexes that make the free-text search boxes (Events,
-- Blocked, Clients, Domains) index-backed instead of a sequential scan.
-- Split out of migration c9e4b7a15d02 because CREATE INDEX on a populated
-- raw_events table would block the app's startup migration; CONCURRENTLY
-- here builds them online, with the app running.
--
-- Safe to run any time, and to re-run: every statement is IF NOT EXISTS,
-- and the two DO blocks first drop any INVALID leftover from an
-- interrupted earlier attempt. Each raw_events index takes a few minutes
-- on ~60M rows; the aggregate ones are quick. Search stays slow until each
-- finishes, then flips to fast.
--
--   docker compose exec -T postgres psql -U squid -d squid_dashboard -f scripts/build_search_indexes.sql
--
-- or use scripts/build_search_indexes.sh which wraps that.

\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Drop any invalid trigram index a killed CONCURRENTLY build left behind,
-- so the IF NOT EXISTS creates below don't skip a broken one.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT indexrelid::regclass AS name
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE NOT i.indisvalid AND c.relname LIKE '%\_trgm'
  LOOP
    EXECUTE 'DROP INDEX IF EXISTS ' || r.name;
    RAISE NOTICE 'dropped invalid index %', r.name;
  END LOOP;
END $$;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_events_client_ip_trgm ON raw_events USING gin (client_ip gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_events_domain_trgm    ON raw_events USING gin (domain gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_events_user_trgm      ON raw_events USING gin ("user" gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_events_peer_trgm      ON raw_events USING gin (peer gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dma_domain_trgm    ON domain_minute_aggregates USING gin (domain gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cma_client_ip_trgm ON client_minute_aggregates USING gin (client_ip gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cma_user_trgm      ON client_minute_aggregates USING gin ("user" gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cha_client_ip_trgm ON client_hourly_aggregates USING gin (client_ip gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cha_user_trgm      ON client_hourly_aggregates USING gin ("user" gin_trgm_ops);

-- Show what exists now.
\di+ *_trgm
