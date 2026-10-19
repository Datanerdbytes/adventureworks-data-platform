-- Apply to the app's Supabase project before enabling AUTH_PASSWORD_LOCKOUT_ENABLED.
-- Only the Flask server can call this RPC. Browser roles cannot read counters.
begin;

create table public.qe_password_attempts (
    email text primary key,
    failures integer not null default 0 check (failures between 0 and 5),
    window_started_at timestamptz,
    locked_until timestamptz,
    attempt_id uuid,
    attempt_expires_at timestamptz,
    updated_at timestamptz not null default clock_timestamp()
);
alter table public.qe_password_attempts enable row level security;
revoke all on public.qe_password_attempts from public, anon, authenticated;

create function public.qe_password_attempt(
    p_email text,
    p_action text,
    p_attempt uuid default null,
    p_valid boolean default null
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    account_email text := lower(btrim(p_email));
    state public.qe_password_attempts%rowtype;
    current_time_at timestamptz;
    lease uuid;
begin
    if account_email is null or length(account_email) not between 3 and 254
       or p_action not in ('start', 'finish', 'status') or p_action is null then
        raise exception 'Invalid password attempt request';
    end if;

    if p_action = 'status' then
        select * into state from public.qe_password_attempts where email = account_email;
        current_time_at := clock_timestamp();
        if found and state.locked_until > current_time_at then
            return jsonb_build_object('allowed', false, 'error', 'account_locked',
                'retry_after', ceil(extract(epoch from state.locked_until - current_time_at))::integer);
        end if;
        return jsonb_build_object('allowed', true, 'retry_after', 0);
    end if;

    insert into public.qe_password_attempts(email) values (account_email)
        on conflict (email) do nothing;
    select * into strict state from public.qe_password_attempts
        where email = account_email for update;
    -- Read the clock AFTER taking the row lock; each account has one active lease.
    current_time_at := clock_timestamp();

    if state.locked_until > current_time_at then
        return jsonb_build_object('allowed', false, 'error', 'account_locked',
            'retry_after', ceil(extract(epoch from state.locked_until - current_time_at))::integer);
    end if;

    if p_action = 'start' then
        if state.attempt_expires_at > current_time_at then
            return jsonb_build_object('allowed', false, 'error', 'attempt_in_progress',
                'retry_after', ceil(extract(epoch from state.attempt_expires_at - current_time_at))::integer);
        end if;
        if state.locked_until is not null or state.window_started_at <= current_time_at - interval '15 minutes' then
            state.failures := 0;
            state.window_started_at := null;
        end if;
        lease := pg_catalog.gen_random_uuid();
        update public.qe_password_attempts set
            failures = state.failures, window_started_at = state.window_started_at,
            locked_until = null, attempt_id = lease,
            attempt_expires_at = current_time_at + interval '30 seconds', updated_at = current_time_at
            where email = account_email;
        return jsonb_build_object('allowed', true, 'attempt_id', lease, 'retry_after', 0);
    end if;

    if p_attempt is null or state.attempt_id is distinct from p_attempt
       or state.attempt_expires_at is null or state.attempt_expires_at <= current_time_at then
        return jsonb_build_object('allowed', false, 'error', 'attempt_expired', 'retry_after', 1);
    end if;
    if p_valid is true then
        state.failures := 0;
        state.window_started_at := null;
    elsif p_valid is false then
        if state.window_started_at is null or state.window_started_at <= current_time_at - interval '15 minutes' then
            state.failures := 0;
            state.window_started_at := current_time_at;
        end if;
        state.failures := state.failures + 1;
        if state.failures >= 5 then
            state.locked_until := current_time_at + interval '15 minutes';
        end if;
    end if;
    -- Null means a provider/configuration failure: release the lease, do not count it.
    update public.qe_password_attempts set
        failures = state.failures, window_started_at = state.window_started_at,
        locked_until = state.locked_until, attempt_id = null, attempt_expires_at = null,
        updated_at = current_time_at where email = account_email;
    if state.locked_until > current_time_at then
        return jsonb_build_object('allowed', false, 'error', 'account_locked', 'retry_after', 900);
    end if;
    return jsonb_build_object('allowed', p_valid is true, 'error',
        case when p_valid is false then 'invalid_credentials' when p_valid is null then 'auth_unavailable' else null end,
        'retry_after', 0);
end;
$$;
revoke all on function public.qe_password_attempt(text, text, uuid, boolean) from public, anon, authenticated;
grant execute on function public.qe_password_attempt(text, text, uuid, boolean) to service_role;
-- Only a real password-hash change clears a lock; requesting an email never does.
create function public.qe_clear_password_lockout() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if old.encrypted_password is distinct from new.encrypted_password then
        delete from public.qe_password_attempts
            where email in (lower(btrim(old.email)), lower(btrim(new.email)));
    end if;
    return new;
end;
$$;
revoke all on function public.qe_clear_password_lockout() from public, anon, authenticated;
create trigger qe_password_changed
    after update of encrypted_password on auth.users
    for each row execute function public.qe_clear_password_lockout();
notify pgrst, 'reload schema';
commit;
