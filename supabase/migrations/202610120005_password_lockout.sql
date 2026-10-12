begin;

-- Hook activation is a separate Supabase Auth configuration step. This
-- migration alone does not enable lockout (Teams/Enterprise hook required).
create table governance_private.password_login_state (
  user_id uuid primary key references auth.users(id) on delete cascade,
  failed_attempts integer not null default 0 check (failed_attempts between 0 and 5),
  window_started_at timestamptz not null default clock_timestamp(),
  locked_until timestamptz,
  last_failed_at timestamptz
);
create table governance_private.password_lockout_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  action text not null check (action in ('password_locked', 'password_change_unlocked')),
  occurred_at timestamptz not null default clock_timestamp()
);
create index password_lockout_events_user_time
  on governance_private.password_lockout_events(user_id,occurred_at desc);
alter table governance_private.password_login_state enable row level security;
alter table governance_private.password_lockout_events enable row level security;
revoke all on governance_private.password_login_state,
  governance_private.password_lockout_events from public, anon, authenticated, service_role;
grant usage on schema governance_private, public to supabase_auth_admin;
grant select, insert, update on governance_private.password_login_state to supabase_auth_admin;
grant insert on governance_private.password_lockout_events to supabase_auth_admin;
create policy auth_password_state on governance_private.password_login_state
  for all to supabase_auth_admin using (true) with check (true);
create policy auth_password_events on governance_private.password_lockout_events
  for insert to supabase_auth_admin with check (true);

create function public.hook_password_lockout(event jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
  target uuid;
  valid_password boolean;
  moment timestamptz;
  state governance_private.password_login_state%rowtype;
begin
  -- Only Auth calls this hook. Never accept an outcome reported by a browser.
  if jsonb_typeof(event->'valid') is distinct from 'boolean'
     or jsonb_typeof(event->'user_id') is distinct from 'string' then
    raise exception 'Invalid password verification event' using errcode='22023';
  end if;
  target := (event->>'user_id')::uuid;
  valid_password := (event->>'valid')::boolean;
  insert into governance_private.password_login_state(user_id) values(target)
    on conflict (user_id) do nothing;
  select * into strict state from governance_private.password_login_state
    where user_id=target for update;
  moment := clock_timestamp();

  if state.locked_until is not null and state.locked_until > moment then
    -- Incorrect passwords retain Supabase's generic credentials error, avoiding
    -- an account-existence signal. Correct passwords cannot bypass the lock.
    -- Attempts during lockout never extend it or sign out existing sessions.
    if valid_password then
      return jsonb_build_object('decision','reject', 'should_logout_user',false,
        'message','Password sign-in is temporarily locked. Wait up to 15 minutes or reset your password.');
    end if;
    return jsonb_build_object('decision','continue');
  end if;

  if valid_password then
    update governance_private.password_login_state
      set failed_attempts=0, window_started_at=moment, locked_until=null, last_failed_at=null
      where user_id=target;
    return jsonb_build_object('decision','continue');
  end if;

  if state.failed_attempts=0 or state.locked_until is not null
     or state.window_started_at <= moment - interval '15 minutes' then
    state.failed_attempts := 0;
    state.window_started_at := moment;
  end if;
  state.failed_attempts := state.failed_attempts + 1;
  update governance_private.password_login_state
    set failed_attempts=state.failed_attempts, window_started_at=state.window_started_at,
      last_failed_at=moment,
      locked_until=case when state.failed_attempts=5 then moment + interval '15 minutes' else null end
    where user_id=target;
  if state.failed_attempts=5 then
    insert into governance_private.password_lockout_events(user_id,action)
      values(target,'password_locked');
  end if;
  return jsonb_build_object('decision','continue');
end;
$$;
revoke all on function public.hook_password_lockout(jsonb) from public, anon, authenticated, service_role;
grant execute on function public.hook_password_lockout(jsonb) to supabase_auth_admin;

-- Supabase owns this column. A browser cannot claim to have reset a password.
-- Lockout must not prevent verified email recovery; reset/change clears it.
create function governance_private.clear_password_lockout() returns trigger
language plpgsql security definer set search_path='' as $$
declare unlocked uuid;
begin
  if new.encrypted_password is distinct from old.encrypted_password
     and coalesce(new.encrypted_password,'') <> '' then
    update governance_private.password_login_state
      set failed_attempts=0, window_started_at=clock_timestamp(), locked_until=null, last_failed_at=null
      where user_id=new.id and (failed_attempts>0 or locked_until is not null)
      returning user_id into unlocked;
    if unlocked is not null then
      insert into governance_private.password_lockout_events(user_id,action)
        values(unlocked,'password_change_unlocked');
    end if;
  end if;
  return new;
end;
$$;
revoke all on function governance_private.clear_password_lockout() from public, anon, authenticated, service_role;
create trigger clear_password_lockout_after_change
  after update of encrypted_password on auth.users
  for each row execute function governance_private.clear_password_lockout();

notify pgrst, 'reload schema';
commit;
