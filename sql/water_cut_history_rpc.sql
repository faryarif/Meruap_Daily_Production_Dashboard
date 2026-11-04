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
