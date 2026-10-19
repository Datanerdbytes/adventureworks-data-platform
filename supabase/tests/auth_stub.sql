-- Test harness only: mimics the Supabase auth primitives in isolated Postgres.
create role anon;
create role authenticated;
create role supabase_auth_admin;
create role service_role;
create schema auth;
create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz,encrypted_password text,raw_user_meta_data jsonb default '{}'::jsonb,raw_app_meta_data jsonb default '{"provider":"email"}',banned_until timestamptz);
create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;
