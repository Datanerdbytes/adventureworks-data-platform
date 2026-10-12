-- Approval requires a registered, verified account. Existing role checks and grants remain in force.
begin;
create or replace function public.approve_workspace_email(p_workspace uuid,p_email text,p_role text) returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text; address text := lower(trim(p_email)); old_role text;
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 actor_role := governance_private.role_for(p_workspace);
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') then raise exception 'Membership administration required' using errcode='42501'; end if;
 if p_role not in ('owner','admin','viewer') then raise exception 'Invalid role' using errcode='22023'; end if;
 select role into old_role from public.workspace_approvals where workspace_id=p_workspace and email=address and status='pending';
 if actor_role='admin' and (p_role<>'viewer' or coalesce(old_role,'viewer')<>'viewer') then raise exception 'Admins manage viewers only' using errcode='42501'; end if;
 if not exists(select 1 from auth.users u where lower(u.email)=address and u.email_confirmed_at is not null) then
  raise exception 'The user must sign up and verify this email before workspace approval.' using errcode='22023';
 end if;
 if exists(select 1 from public.workspace_memberships m join auth.users u on u.id=m.user_id where m.workspace_id=p_workspace and lower(u.email)=address) then
  raise exception 'Use member controls for an existing membership' using errcode='22023';
 end if;
 insert into public.workspace_approvals(workspace_id,email,role,approved_by) values(p_workspace,address,p_role,actor)
 on conflict(workspace_id,email) do update set role=excluded.role,status='pending',approved_by=actor,claimed_by=null,updated_at=now();
 insert into public.governance_audit_events(workspace_id,actor_id,action,details) values(p_workspace,actor,'email_approved',jsonb_build_object('email',address,'role',p_role));
end $$;

commit;
