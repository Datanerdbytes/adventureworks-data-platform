-- Enforce email-first registration even for direct calls to Supabase OAuth.
-- Supabase sets raw_app_meta_data; user-editable raw_user_meta_data is ignored.
-- Existing users (including the initial social-login owner) are unaffected.
create function governance_private.require_email_registration()
returns trigger language plpgsql set search_path='' as $$
begin
 if coalesce(new.raw_app_meta_data->>'provider','') <> 'email' then
  raise exception 'Create an account with email first, then request workspace approval before signing in.'
   using errcode='23514';
 end if;
 return new;
end $$;
revoke all on function governance_private.require_email_registration() from public,anon,authenticated;
create trigger require_email_registration
before insert on auth.users
for each row execute function governance_private.require_email_registration();
