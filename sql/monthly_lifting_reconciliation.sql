create table if not exists public.monthly_lifting_reconciliation (
    report_month date primary key,
    reporting_status text not null check (reporting_status in ('Actual', 'Provisional', 'Planned', 'Missing')),
    source_filename text not null,
    rc_bopd numeric,
    rc_volume_bbl numeric,
    rc_pumping_net_bbl numeric,
    rc_pumping_gross_bbl numeric,
    rc_received_bbl numeric,
    field_production_bbl numeric,
    bsa_production_bbl numeric,
    bsa_transfer_bbl numeric,
    bsa_storage_loss_gain_bbl numeric,
    bsa_stock_movement_bbl numeric,
    bsb_production_bbl numeric,
    bsb_transfer_bbl numeric,
    bsb_storage_loss_gain_bbl numeric,
    bsb_stock_movement_bbl numeric,
    sta_received_bbl numeric,
    sta_transfer_bbl numeric,
    sta_storage_loss_gain_bbl numeric,
    sta_stock_movement_bbl numeric,
    bajubang_received_bbl numeric,
    bajubang_pumped_bbl numeric,
    bajubang_storage_loss_gain_bbl numeric,
    bajubang_stock_movement_bbl numeric,
    shipping_received_bbl numeric,
    tempino_opening_stock_bbl numeric,
    tempino_closing_stock_bbl numeric,
    tempino_meter_gross_bbl numeric,
    tempino_storage_loss_gain_bbl numeric,
    tempino_pumping_net_bbl numeric,
    s_gerong_pumped_bbl numeric,
    s_gerong_received_bbl numeric,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint monthly_lifting_first_day check (report_month = date_trunc('month', report_month)::date)
);

alter table public.monthly_lifting_reconciliation enable row level security;

drop policy if exists "Monthly lifting reconciliation is readable" on public.monthly_lifting_reconciliation;
drop policy if exists "Service role manages monthly lifting reconciliation" on public.monthly_lifting_reconciliation;
create policy "Service role manages monthly lifting reconciliation"
on public.monthly_lifting_reconciliation
for all
to service_role
using (true)
with check (true);

revoke all on table public.monthly_lifting_reconciliation from anon, authenticated;
grant select, insert, update, delete on table public.monthly_lifting_reconciliation to service_role;

create or replace function public.set_monthly_lifting_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

revoke execute on function public.set_monthly_lifting_updated_at() from public, anon, authenticated;
grant execute on function public.set_monthly_lifting_updated_at() to service_role;

drop trigger if exists monthly_lifting_updated_at on public.monthly_lifting_reconciliation;
create trigger monthly_lifting_updated_at
before update on public.monthly_lifting_reconciliation
for each row execute function public.set_monthly_lifting_updated_at();

create or replace function public.dashboard_monthly_reconciliation(
    p_start_month date default null,
    p_end_month date default null
)
returns setof public.monthly_lifting_reconciliation
language sql
stable
security invoker
set search_path = ''
as $$
    select monthly.*
    from public.monthly_lifting_reconciliation as monthly
    where (p_start_month is null or monthly.report_month >= date_trunc('month', p_start_month)::date)
      and (p_end_month is null or monthly.report_month <= date_trunc('month', p_end_month)::date)
    order by monthly.report_month;
$$;

revoke execute on function public.dashboard_monthly_reconciliation(date, date) from public;
revoke execute on function public.dashboard_monthly_reconciliation(date, date) from anon, authenticated;
grant execute on function public.dashboard_monthly_reconciliation(date, date) to service_role;

