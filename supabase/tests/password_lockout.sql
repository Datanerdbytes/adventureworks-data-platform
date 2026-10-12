-- Synthetic accounts in the isolated test container only.
insert into auth.users(id,email,email_confirmed_at,encrypted_password)
  values('b0000000-0000-0000-0000-000000000001','lockout@example.test',now(),'fixture-initial');
set role supabase_auth_admin;
do $$
declare n integer; response jsonb;
begin
  for n in 1..5 loop
    response := public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":false}');
    assert response->>'decision'='continue', 'Preserve generic wrong-password errors';
  end loop;
  response := public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":true}');
  assert response->>'decision'='reject', 'A correct password cannot bypass active lockout';
  assert response->>'should_logout_user'='false', 'Do not log out existing sessions';
end $$;
reset role;
do $$
declare before_lock timestamptz;
begin
  select locked_until into before_lock from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001';
  assert before_lock between clock_timestamp()+interval '14 minutes' and clock_timestamp()+interval '16 minutes';
  perform public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":false}');
  assert (select locked_until=before_lock and failed_attempts=5 from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001'), 'Locked attempts cannot extend expiry';
  assert (select count(*)=1 from governance_private.password_lockout_events where action='password_locked');
end $$;

-- Expiry permits a valid sign-in, and a success resets the consecutive failures.
update governance_private.password_login_state set locked_until=now()-interval '1 second';
set role supabase_auth_admin;
select public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":true}');
select public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":false}');
select public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":true}');
reset role;
do $$ begin
  assert (select failed_attempts=0 and locked_until is null from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001');
end $$;

-- Old failed attempts cannot accumulate forever.
update governance_private.password_login_state set failed_attempts=4, window_started_at=now()-interval '16 minutes';
set role supabase_auth_admin;
select public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":false}');
reset role;
do $$ begin
  assert (select failed_attempts=1 and locked_until is null from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001');
end $$;

-- At expiry a failed attempt starts a fresh window instead of relocking.
update governance_private.password_login_state set failed_attempts=5, locked_until=now()-interval '1 second';
set role supabase_auth_admin;
select public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":false}');
reset role;
do $$ begin
  assert (select failed_attempts=1 and locked_until is null from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001');
end $$;

-- Editable metadata must not unlock the account; an Auth password change does.
update governance_private.password_login_state set failed_attempts=5, locked_until=now()+interval '15 minutes';
update auth.users set raw_user_meta_data='{"unlocked":true}' where id='b0000000-0000-0000-0000-000000000001';
do $$ begin
  assert (select locked_until>now() from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001');
end $$;
update auth.users set encrypted_password='fixture-new' where id='b0000000-0000-0000-0000-000000000001';
do $$ begin
  assert (select failed_attempts=0 and locked_until is null from governance_private.password_login_state
    where user_id='b0000000-0000-0000-0000-000000000001');
  assert (select count(*)=1 from governance_private.password_lockout_events where action='password_change_unlocked');
end $$;

-- Browser roles cannot spoof outcomes, read counters, or clear locks.
set role anon;
do $$ begin
  begin
    perform public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":true}');
    raise exception 'Anonymous caller reached hook';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set role service_role;
do $$ begin
  begin
    perform public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":true}');
    raise exception 'Service API caller reached hook';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set role authenticated;
do $$ begin
  begin
    perform public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":true}');
    raise exception 'Authenticated caller reached hook';
  exception when insufficient_privilege then null; end;
  begin
    perform 1 from governance_private.password_login_state;
    raise exception 'Browser read lockout state';
  exception when insufficient_privilege then null; end;
  begin
    update governance_private.password_login_state set failed_attempts=0;
    raise exception 'Browser modified lockout state';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set role supabase_auth_admin;
do $$ begin
  begin
    perform public.hook_password_lockout('{"user_id":"b0000000-0000-0000-0000-000000000001","valid":"true"}');
    raise exception 'Malformed hook accepted';
  exception when invalid_parameter_value then null; end;
end $$;
reset role;
