-- Separate, optional account-deletion migration. Requires existing governance
-- tables and the 202610190001–0003 safety guards. Independent of cutover 0004.
-- Preserve all legacy rows and UUIDs; never cascade-delete governance history.
begin;
set local lock_timeout = '5s';

-- Stop concurrent Auth/legacy writes while backfilling and replacing references.
-- Locks are released at commit, or the entire migration rolls back on failure.
lock table auth.users in share row exclusive mode;
lock table public.workspace_memberships, public.platform_administrators,
 public.workspace_approvals, public.workspace_access_requests,
 public.governance_audit_events in access exclusive mode;

do $$
begin
 if not coalesce((public.qe_account_deletion_guard_ready()->>'ready')::boolean,false)
    or not coalesce((public.qe_administrator_guard_ready()->>'ready')::boolean,false) then
  raise exception 'Install and enable the account safety guards before separating legacy history';
 end if;
end $$;

create table governance_private.account_history_identities (
 user_id uuid primary key,
 deleted_at timestamptz
);
alter table governance_private.account_history_identities enable row level security;
revoke all on governance_private.account_history_identities from public,anon,authenticated,service_role;
-- Deliberately store no email, credentials, tokens or raw Auth metadata.
insert into governance_private.account_history_identities(user_id)
 select id from auth.users;

create function governance_private.register_account_history_identity() returns trigger
language plpgsql security definer set search_path='' as $$
declare removed_at timestamptz;
begin
 insert into governance_private.account_history_identities(user_id) values(new.id)
 on conflict(user_id) do nothing;
 select deleted_at into strict removed_at
 from governance_private.account_history_identities where user_id=new.id for update;
 if removed_at is not null then
  raise exception 'A deleted historical identity cannot be reused' using errcode='23514';
 end if;
 return new;
end;
$$;
revoke all on function governance_private.register_account_history_identity() from public,anon,authenticated,service_role;
-- BEFORE INSERT ensures that existing confirmation/approval AFTER triggers can
-- reference the identity immediately. A failed Auth insert rolls this back too.
create trigger register_account_history_identity before insert on auth.users
 for each row execute function governance_private.register_account_history_identity();

create function governance_private.mark_account_history_deleted() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 update governance_private.account_history_identities
 set deleted_at=clock_timestamp() where user_id=old.id;
 if not found then
  raise exception 'Historical identity is missing; deletion refused' using errcode='23514';
 end if;
 return old;
end;
$$;
revoke all on function governance_private.mark_account_history_deleted() from public,anon,authenticated,service_role;
create trigger mark_account_history_deleted after delete on auth.users
 for each row execute function governance_private.mark_account_history_deleted();

-- Explicit allowlist: no other application's constraints or Storage are changed.
alter table public.workspace_memberships
 drop constraint workspace_memberships_user_id_fkey,
 add constraint workspace_memberships_user_id_fkey foreign key(user_id)
 references governance_private.account_history_identities(user_id);
alter table public.platform_administrators
 drop constraint platform_administrators_user_id_fkey,
 add constraint platform_administrators_user_id_fkey foreign key(user_id)
 references governance_private.account_history_identities(user_id);
alter table public.workspace_approvals
 drop constraint workspace_approvals_approved_by_fkey,
 drop constraint workspace_approvals_claimed_by_fkey,
 add constraint workspace_approvals_approved_by_fkey foreign key(approved_by)
 references governance_private.account_history_identities(user_id),
 add constraint workspace_approvals_claimed_by_fkey foreign key(claimed_by)
 references governance_private.account_history_identities(user_id);
alter table public.workspace_access_requests
 drop constraint workspace_access_requests_user_id_fkey,
 drop constraint workspace_access_requests_reviewed_by_fkey,
 add constraint workspace_access_requests_user_id_fkey foreign key(user_id)
 references governance_private.account_history_identities(user_id),
 add constraint workspace_access_requests_reviewed_by_fkey foreign key(reviewed_by)
 references governance_private.account_history_identities(user_id);
alter table public.governance_audit_events
 drop constraint governance_audit_events_actor_id_fkey,
 add constraint governance_audit_events_actor_id_fkey foreign key(actor_id)
 references governance_private.account_history_identities(user_id);

comment on table governance_private.account_history_identities is
 'Private UUID-only history. A retained legacy role is historical evidence, not current account authorization. Deleted identities cannot be re-registered.';
notify pgrst, 'reload schema';
commit;
