-- Prevent parallel promotion and suspension requests from creating a suspended
-- administrator. Revoking the admin role and restoring access remain possible.
begin;
-- Supabase owns auth.users; enforce singleton ownership through a public table
-- rather than requiring ownership privileges to create an index on auth.users.
create table public.qe_protected_owner (
    singleton boolean primary key default true check (singleton),
    user_id uuid not null unique
);
alter table public.qe_protected_owner enable row level security;
revoke all on public.qe_protected_owner from public, anon, authenticated, service_role;
insert into public.qe_protected_owner(singleton,user_id)
 select true,id from auth.users where raw_app_meta_data->'qe_owner'='true'::jsonb;
create function public.qe_guard_administrator_access() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if tg_op = 'UPDATE' then
        if old.raw_app_meta_data->'qe_owner' = 'true'::jsonb
           and (new.raw_app_meta_data->'qe_owner' is distinct from 'true'::jsonb
                or new.raw_app_meta_data->>'qe_role' is distinct from 'admin') then
            raise exception using errcode = '23514', message = 'The initial owner is protected';
        end if;
    end if;
    if new.raw_app_meta_data->'qe_owner' = 'true'::jsonb
       and new.raw_app_meta_data->>'qe_role' is distinct from 'admin' then
        raise exception using errcode = '23514', message = 'The owner must be an administrator';
    end if;
    if new.raw_app_meta_data->>'qe_role' = 'admin'
       and (new.email_confirmed_at is null or nullif(btrim(new.email), '') is null) then
        raise exception using errcode = '23514', message = 'Administrator email must be verified';
    end if;
    if new.raw_app_meta_data->>'qe_role' = 'admin'
       and (coalesce(new.raw_app_meta_data->'qe_suspended' = 'true'::jsonb, false)
           or coalesce(new.banned_until > clock_timestamp(), false)) then
        raise exception using errcode = '23514',
            message = 'Revoke administrator access before suspending this account';
    end if;
    if new.raw_app_meta_data->'qe_owner' = 'true'::jsonb then
        -- The singleton primary key serializes concurrent owner assignments.
        -- Avoid a foreign key: this BEFORE INSERT trigger runs before the Auth
        -- row exists. The registry write rolls back if the Auth write fails.
        insert into public.qe_protected_owner(singleton,user_id) values(true,new.id)
        on conflict(singleton) do update set user_id=excluded.user_id
         where public.qe_protected_owner.user_id=excluded.user_id;
        if not found then
            raise exception using errcode='23514', message='A different initial owner already exists';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function public.qe_guard_administrator_access() from public, anon, authenticated;
create trigger qe_guard_administrator_access
    before insert or update of raw_app_meta_data, banned_until, email_confirmed_at, email on auth.users
    for each row execute function public.qe_guard_administrator_access();
create function public.qe_administrator_guard_ready() returns jsonb
language sql security definer set search_path = '' as $$
 select jsonb_build_object('ready', exists (
  select 1 from pg_catalog.pg_trigger t where t.tgrelid='auth.users'::regclass
   and t.tgname='qe_guard_administrator_access'
   and t.tgfoid='public.qe_guard_administrator_access()'::regprocedure
   and t.tgenabled in ('O','A') and not t.tgisinternal
 ));
$$;
revoke all on function public.qe_administrator_guard_ready() from public,anon,authenticated;
grant execute on function public.qe_administrator_guard_ready() to service_role;
notify pgrst, 'reload schema';
commit;
