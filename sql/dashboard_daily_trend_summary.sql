-- Speed up the all-time dashboard trend by serving a maintained per-day summary.
-- The public RPC contract remains unchanged. The source table is never copied to Streamlit.

CREATE SCHEMA IF NOT EXISTS dashboard_private;
REVOKE ALL ON SCHEMA dashboard_private FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS dashboard_private.daily_trend_summary (
    summary_key text PRIMARY KEY,
    date date,
    oil numeric NOT NULL,
    gas numeric NOT NULL,
    water numeric NOT NULL,
    injection_rate numeric NOT NULL,
    water_source_rate numeric NOT NULL,
    reported_total numeric
);
REVOKE ALL ON TABLE dashboard_private.daily_trend_summary FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION dashboard_private.refresh_daily_trend_summary(p_dates date[] DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
DECLARE
    v_date date;
    v_key text;
BEGIN
    -- Serialize summary refreshes so concurrent uploads cannot leave a stale total.
    PERFORM pg_catalog.pg_advisory_xact_lock(20261104, 11082);

    IF p_dates IS NULL THEN
        DELETE FROM dashboard_private.daily_trend_summary;

        INSERT INTO dashboard_private.daily_trend_summary (
            summary_key, date, oil, gas, water, injection_rate,
            water_source_rate, reported_total
        )
        SELECT
            CASE WHEN p.date IS NULL THEN 'N' ELSE 'D:' || p.date::text END,
            p.date,
            coalesce(sum(p."OIL"), 0),
            coalesce(sum(p."GAS"), 0),
            coalesce(sum(p."WATER"), 0),
            coalesce(sum(p.injection_rate) FILTER (WHERE h.status = 'Injector'), 0),
            coalesce(sum(p."WATER") FILTER (WHERE h.status = 'Water Source'), 0),
            max(p.reported_total)
        FROM public."ProdWellBasiss" AS p
        LEFT JOIN public."HeaderID" AS h ON h."ALIAS" = p."ALIAS"
        GROUP BY p.date;

        RETURN;
    END IF;

    FOR v_date IN
        SELECT DISTINCT changed.date
        FROM unnest(p_dates) AS changed(date)
        ORDER BY changed.date NULLS LAST
    LOOP
        v_key := CASE WHEN v_date IS NULL THEN 'N' ELSE 'D:' || v_date::text END;

        INSERT INTO dashboard_private.daily_trend_summary (
            summary_key, date, oil, gas, water, injection_rate,
            water_source_rate, reported_total
        )
        SELECT
            v_key,
            p.date,
            coalesce(sum(p."OIL"), 0),
            coalesce(sum(p."GAS"), 0),
            coalesce(sum(p."WATER"), 0),
            coalesce(sum(p.injection_rate) FILTER (WHERE h.status = 'Injector'), 0),
            coalesce(sum(p."WATER") FILTER (WHERE h.status = 'Water Source'), 0),
            max(p.reported_total)
        FROM public."ProdWellBasiss" AS p
        LEFT JOIN public."HeaderID" AS h ON h."ALIAS" = p."ALIAS"
        WHERE p.date IS NOT DISTINCT FROM v_date
        GROUP BY p.date
        ON CONFLICT (summary_key) DO UPDATE SET
            date = EXCLUDED.date,
            oil = EXCLUDED.oil,
            gas = EXCLUDED.gas,
            water = EXCLUDED.water,
            injection_rate = EXCLUDED.injection_rate,
            water_source_rate = EXCLUDED.water_source_rate,
            reported_total = EXCLUDED.reported_total;

        IF NOT FOUND THEN
            DELETE FROM dashboard_private.daily_trend_summary
            WHERE summary_key = v_key;
        END IF;
    END LOOP;
END;
$function$;

REVOKE ALL ON FUNCTION dashboard_private.refresh_daily_trend_summary(date[]) FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION dashboard_private.refresh_daily_trend_after_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
DECLARE
    v_dates date[];
BEGIN
    SELECT coalesce(array_agg(DISTINCT new_rows.date), ARRAY[]::date[])
    INTO v_dates
    FROM new_rows;

    PERFORM dashboard_private.refresh_daily_trend_summary(v_dates);
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION dashboard_private.refresh_daily_trend_after_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
DECLARE
    v_dates date[];
BEGIN
    SELECT coalesce(array_agg(changed.date), ARRAY[]::date[])
    INTO v_dates
    FROM (
        SELECT old_rows.date FROM old_rows
        UNION
        SELECT new_rows.date FROM new_rows
    ) AS changed;

    PERFORM dashboard_private.refresh_daily_trend_summary(v_dates);
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION dashboard_private.refresh_daily_trend_after_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
DECLARE
    v_dates date[];
BEGIN
    SELECT coalesce(array_agg(DISTINCT old_rows.date), ARRAY[]::date[])
    INTO v_dates
    FROM old_rows;

    PERFORM dashboard_private.refresh_daily_trend_summary(v_dates);
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION dashboard_private.refresh_daily_trend_after_truncate()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
BEGIN
    PERFORM dashboard_private.refresh_daily_trend_summary(NULL);
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION dashboard_private.refresh_daily_trend_after_header_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
BEGIN
    PERFORM dashboard_private.refresh_daily_trend_summary(NULL);
    RETURN NULL;
END;
$function$;

REVOKE ALL ON FUNCTION dashboard_private.refresh_daily_trend_after_insert() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION dashboard_private.refresh_daily_trend_after_update() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION dashboard_private.refresh_daily_trend_after_delete() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION dashboard_private.refresh_daily_trend_after_truncate() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION dashboard_private.refresh_daily_trend_after_header_change() FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS refresh_daily_trend_after_insert ON public."ProdWellBasiss";
CREATE TRIGGER refresh_daily_trend_after_insert
AFTER INSERT ON public."ProdWellBasiss"
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_insert();

DROP TRIGGER IF EXISTS refresh_daily_trend_after_update ON public."ProdWellBasiss";
CREATE TRIGGER refresh_daily_trend_after_update
AFTER UPDATE ON public."ProdWellBasiss"
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_update();

DROP TRIGGER IF EXISTS refresh_daily_trend_after_delete ON public."ProdWellBasiss";
CREATE TRIGGER refresh_daily_trend_after_delete
AFTER DELETE ON public."ProdWellBasiss"
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_delete();

DROP TRIGGER IF EXISTS refresh_daily_trend_after_truncate ON public."ProdWellBasiss";
CREATE TRIGGER refresh_daily_trend_after_truncate
AFTER TRUNCATE ON public."ProdWellBasiss"
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_truncate();

DROP TRIGGER IF EXISTS refresh_daily_trend_after_header_insert ON public."HeaderID";
CREATE TRIGGER refresh_daily_trend_after_header_insert
AFTER INSERT ON public."HeaderID"
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_header_change();

DROP TRIGGER IF EXISTS refresh_daily_trend_after_header_update ON public."HeaderID";
CREATE TRIGGER refresh_daily_trend_after_header_update
AFTER UPDATE OF status, "ALIAS" ON public."HeaderID"
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_header_change();

DROP TRIGGER IF EXISTS refresh_daily_trend_after_header_delete ON public."HeaderID";
CREATE TRIGGER refresh_daily_trend_after_header_delete
AFTER DELETE ON public."HeaderID"
FOR EACH STATEMENT
EXECUTE FUNCTION dashboard_private.refresh_daily_trend_after_header_change();

-- Backfill the summary table once; subsequent writes refresh only changed dates.
SELECT dashboard_private.refresh_daily_trend_summary(NULL);

CREATE OR REPLACE FUNCTION public.dashboard_daily_trend(
    p_start_date date DEFAULT NULL::date,
    p_end_date date DEFAULT NULL::date
)
RETURNS TABLE (
    date date,
    oil numeric,
    gas numeric,
    water numeric,
    bfpd numeric,
    water_cut_pct numeric,
    injection_rate numeric,
    water_source_rate numeric,
    reported_total numeric
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO pg_catalog
AS $function$
    SELECT
        s.date,
        coalesce(s.oil, 0) AS oil,
        coalesce(s.gas, 0) AS gas,
        coalesce(s.water, 0) AS water,
        coalesce(s.oil, 0) + coalesce(s.water, 0) AS bfpd,
        round(
            CASE
                WHEN coalesce(s.oil, 0) + coalesce(s.water, 0) = 0 THEN 0
                ELSE 100.0 * coalesce(s.water, 0)
                    / (coalesce(s.oil, 0) + coalesce(s.water, 0))
            END,
            1
        ) AS water_cut_pct,
        coalesce(s.injection_rate, 0) AS injection_rate,
        coalesce(s.water_source_rate, 0) AS water_source_rate,
        s.reported_total
    FROM dashboard_private.daily_trend_summary AS s
    WHERE (p_start_date IS NULL OR s.date >= p_start_date)
      AND (p_end_date IS NULL OR s.date <= p_end_date)
    ORDER BY s.date;
$function$;

GRANT EXECUTE ON FUNCTION public.dashboard_daily_trend(date, date) TO anon, authenticated, service_role;
