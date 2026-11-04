-- Return bounded AllLayer production history for the water-cut alert review in one RPC call.
-- Keep source rows intact so Python can continue to detect duplicate and invalid well-days.
CREATE OR REPLACE FUNCTION public.dashboard_water_cut_history(
    p_start_date date,
    p_end_date date,
    p_aliases text[] DEFAULT NULL
)
RETURNS TABLE (
    date date,
    "ALIAS" text,
    "UNIQUEID" text,
    "OIL" numeric,
    "WATER" numeric
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO pg_catalog
AS $function$
    SELECT p.date, p."ALIAS", p."UNIQUEID", p."OIL", p."WATER"
    FROM public."ProdWellBasiss" AS p
    WHERE p.date >= p_start_date
      AND p.date <= p_end_date
      AND p."UNIQUEID" LIKE 'M-%:AllLayer'
      AND (p_aliases IS NULL OR p."ALIAS" = ANY(p_aliases))
    ORDER BY p.date, p."ALIAS", p."UNIQUEID";
$function$;

GRANT EXECUTE ON FUNCTION public.dashboard_water_cut_history(date, date, text[])
TO anon, authenticated, service_role;

-- Compact one-row payload avoids PostgREST row caps while retaining duplicate detection.
CREATE OR REPLACE FUNCTION public.dashboard_water_cut_history_compact(
    p_start_date date,
    p_end_date date,
    p_aliases text[] DEFAULT NULL
)
RETURNS TABLE (history jsonb)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO pg_catalog
AS $function$
    WITH daily AS (
        SELECT
            p.date,
            p."ALIAS" AS alias,
            count(*)::integer AS row_count,
            CASE WHEN count(*) = 1 THEN max(p."OIL") END AS oil,
            CASE WHEN count(*) = 1 THEN max(p."WATER") END AS water
        FROM public."ProdWellBasiss" AS p
        WHERE p.date >= p_start_date
          AND p.date <= p_end_date
          AND p."UNIQUEID" = p."ALIAS" || ':AllLayer'
          AND (p_aliases IS NULL OR p."ALIAS" = ANY(p_aliases))
        GROUP BY p.date, p."ALIAS"
    )
    SELECT coalesce(
        jsonb_agg(
            jsonb_build_object(
                'date', d.date,
                'ALIAS', d.alias,
                'UNIQUEID', d.alias || ':AllLayer',
                'OIL', d.oil,
                'WATER', d.water,
                'row_count', d.row_count
            )
            ORDER BY d.date, d.alias
        ),
        '[]'::jsonb
    ) AS history
    FROM daily AS d;
$function$;

GRANT EXECUTE ON FUNCTION public.dashboard_water_cut_history_compact(date, date, text[])
TO anon, authenticated, service_role;
