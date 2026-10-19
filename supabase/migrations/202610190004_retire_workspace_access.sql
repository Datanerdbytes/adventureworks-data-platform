-- Non-destructive cutover: retain membership/audit history, retire client access.
-- Install alongside the new image. Rollback requires restoring these grants and triggers.
begin;
drop trigger if exists queue_verified_registration on auth.users;
drop trigger if exists require_email_registration on auth.users;
-- Retain email-first registration, with the new access policy in its message.
create or replace function governance_private.require_email_registration()
returns trigger language plpgsql set search_path='' as $$
begin
 if coalesce(new.raw_app_meta_data->>'provider','') <> 'email' then
  raise exception 'Create and verify an email account before signing in with a social provider.' using errcode='23514';
 end if;
 return new;
end $$;
create trigger require_email_registration before insert on auth.users
 for each row execute function governance_private.require_email_registration();
-- Previously authenticated RPCs must not remain as an alternate admin surface.
do $$
declare fn record;
begin
 for fn in select p.oid::regprocedure as signature
  from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname in (
    'workspace_context','claim_workspace_approvals','create_workspace','update_workspace',
    'approve_workspace_email','revoke_workspace_approval','change_workspace_member',
    'workspace_admin_data','registration_workspace','request_workspace_access',
    'review_workspace_request','my_access_request_status','workspace_members_directory',
    'workspace_governance_activity')
 loop
  execute format('revoke all on function %s from public, anon, authenticated',fn.signature);
 end loop;
end $$;
revoke all on public.workspaces, public.workspace_memberships, public.workspace_access_requests,
 public.workspace_approvals, public.governance_audit_events, public.platform_administrators from public, anon, authenticated;
notify pgrst, 'reload schema';
commit;
