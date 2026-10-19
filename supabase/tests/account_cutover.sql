-- Runs after legacy checks, retirement and history separation in the same session.
reset role;
do $$
declare fn record;
begin
 if not exists (
  select 1 from legacy_cutover_snapshot
  where workspaces=(select count(*) from public.workspaces)
    and memberships=(select count(*) from public.workspace_memberships)
    and events=(select count(*) from public.governance_audit_events)
 ) then raise exception 'Cutover changed legacy history'; end if;
 for fn in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname in
   ('workspace_context','approve_workspace_email','change_workspace_member',
    'review_workspace_request','workspace_members_directory','workspace_governance_activity')
 loop
  if has_function_privilege('authenticated',fn.oid,'EXECUTE')
     or has_function_privilege('anon',fn.oid,'EXECUTE') then
   raise exception 'Legacy RPC remains accessible after cutover';
  end if;
 end loop;
 if has_table_privilege('authenticated','public.workspace_memberships','SELECT') then
  raise exception 'Legacy memberships remain accessible after cutover';
 end if;
 if not (public.qe_administrator_guard_ready()->>'ready')::boolean
    or not (public.qe_account_deletion_guard_ready()->>'ready')::boolean then
  raise exception 'Account safety guards unavailable after cutover';
 end if;
 if exists (select 1 from pg_trigger where tgrelid='auth.users'::regclass
  and tgname='queue_verified_registration' and not tgisinternal) then
  raise exception 'Legacy approval queue remains active after cutover';
 end if;
 if not exists (select 1 from pg_constraint
  where conrelid='public.workspace_memberships'::regclass
    and conname='workspace_memberships_user_id_fkey'
    and confrelid='governance_private.account_history_identities'::regclass) then
  raise exception 'Legacy account history separation missing';
 end if;
end $$;
