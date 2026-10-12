begin;
create schema if not exists governance_private;
revoke all on schema governance_private from public, anon, authenticated;
create table public.workspaces (
 id uuid primary key default gen_random_uuid(), name text not null check (length(trim(name)) between 1 and 120),
 purpose text not null check (length(purpose) <= 1000), responsible_team text not null check (length(responsible_team) between 1 and 120),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.workspace_memberships (
 workspace_id uuid not null references public.workspaces(id), user_id uuid not null references auth.users(id),
 role text not null check (role in ('owner','admin','viewer')), active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), primary key(workspace_id,user_id)
);
create table public.workspace_approvals (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.workspaces(id),
 email text not null check (email = lower(trim(email)) and email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' and length(email)<=254),
 role text not null check (role in ('owner','admin','viewer')), status text not null default 'pending' check (status in ('pending','claimed','revoked')),
 claimed_by uuid references auth.users(id), approved_by uuid not null references auth.users(id),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(workspace_id,email)
);
create table public.platform_administrators (user_id uuid primary key references auth.users(id), created_at timestamptz not null default now());
create table public.governance_audit_events (
 id bigint generated always as identity primary key, workspace_id uuid not null references public.workspaces(id),
 actor_id uuid not null references auth.users(id), action text not null, target_id uuid,
 details jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index membership_user_active on public.workspace_memberships(user_id) where active;
create index approval_pending_email on public.workspace_approvals(email) where status='pending';
create index audit_workspace_time on public.governance_audit_events(workspace_id,created_at desc);
alter table public.workspaces enable row level security;
alter table public.workspace_memberships enable row level security;
alter table public.workspace_approvals enable row level security;
alter table public.platform_administrators enable row level security;
alter table public.governance_audit_events enable row level security;
revoke all on public.workspaces, public.workspace_memberships, public.workspace_approvals, public.platform_administrators, public.governance_audit_events from anon, authenticated;
-- Writes are only through checked, audited RPCs. No direct client write grants.
grant select on public.workspaces, public.workspace_memberships to authenticated;

create function governance_private.verified_user() returns uuid language plpgsql stable security definer set search_path='' as $$
begin
 if auth.uid() is null or not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null and email is not null) then
  raise exception 'Confirmed authentication required' using errcode='42501';
 end if;
 return auth.uid();
end $$;
create function governance_private.is_platform_admin() returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.platform_administrators p join auth.users u on u.id=p.user_id where p.user_id=auth.uid() and u.email_confirmed_at is not null)
$$;
create function governance_private.role_for(w uuid) returns text language sql stable security definer set search_path='' as $$
 select case when not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then null when governance_private.is_platform_admin() then 'platform_admin' else
 (select role from public.workspace_memberships where workspace_id=w and user_id=auth.uid() and active) end
$$;
-- Policy helpers are executable, but neither grant writes nor expose another user's role.
grant usage on schema governance_private to authenticated;
revoke all on all functions in schema governance_private from public, anon, authenticated;
grant execute on function governance_private.role_for(uuid), governance_private.is_platform_admin() to authenticated;
create policy workspace_read on public.workspaces for select to authenticated using (governance_private.role_for(id) is not null);
create policy member_read on public.workspace_memberships for select to authenticated using (user_id=auth.uid() or governance_private.role_for(workspace_id) in ('owner','admin','platform_admin'));

create function public.workspace_context() returns jsonb language plpgsql stable security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); result jsonb;
begin
 select coalesce(jsonb_agg(jsonb_build_object('id',w.id,'name',w.name,'purpose',w.purpose,'responsible_team',w.responsible_team,
 'role',governance_private.role_for(w.id), 'owners', (select coalesce(jsonb_agg(u.email order by u.email),'[]'::jsonb)
 from public.workspace_memberships m join auth.users u on u.id=m.user_id where m.workspace_id=w.id and m.active and m.role='owner')) order by w.name,w.id),'[]'::jsonb)
 into result from public.workspaces w where governance_private.role_for(w.id) is not null;
 return jsonb_build_object('platform_admin',governance_private.is_platform_admin(),'workspaces',result);
end $$;

create function public.claim_workspace_approvals() returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); address text; item record;
begin
 select lower(trim(email)) into address from auth.users where id=actor;
 for item in select id,workspace_id from public.workspace_approvals where email=address and status='pending' order by workspace_id loop
  perform 1 from public.workspaces where id=item.workspace_id for update;
  -- Recheck after taking the workspace lock; approvals may have been revoked.
  if exists(select 1 from public.workspace_approvals where id=item.id and status='pending' and email=address) then
   insert into public.workspace_memberships(workspace_id,user_id,role)
   select workspace_id,actor,role from public.workspace_approvals where id=item.id
   on conflict(workspace_id,user_id) do nothing;
   update public.workspace_approvals set status='claimed',claimed_by=actor,updated_at=now() where id=item.id;
   insert into public.governance_audit_events(workspace_id,actor_id,action,target_id) values(item.workspace_id,actor,'approval_claimed',actor);
  end if;
 end loop;
end $$;

create function public.create_workspace(p_name text,p_purpose text,p_team text,p_owner_email text) returns uuid language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); owner_id uuid; w uuid;
begin
 if not governance_private.is_platform_admin() then raise exception 'Platform administrator required' using errcode='42501'; end if;
 select id into owner_id from auth.users where lower(email)=lower(trim(p_owner_email)) and email_confirmed_at is not null;
 if owner_id is null then raise exception 'Initial owner must have a confirmed account' using errcode='22023'; end if;
 insert into public.workspaces(name,purpose,responsible_team) values(trim(p_name),trim(p_purpose),trim(p_team)) returning id into w;
 insert into public.workspace_memberships values(w,owner_id,'owner',true,now(),now());
 insert into public.governance_audit_events(workspace_id,actor_id,action,target_id) values(w,actor,'workspace_created',owner_id);
 return w;
end $$;

create function public.update_workspace(p_workspace uuid,p_name text,p_purpose text,p_team text) returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user();
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 if governance_private.role_for(p_workspace) is null or governance_private.role_for(p_workspace) not in ('owner','platform_admin') then raise exception 'Workspace owner required' using errcode='42501'; end if;
 update public.workspaces set name=trim(p_name),purpose=trim(p_purpose),responsible_team=trim(p_team),updated_at=now() where id=p_workspace;
 insert into public.governance_audit_events(workspace_id,actor_id,action) values(p_workspace,actor,'workspace_updated');
end $$;

create function public.approve_workspace_email(p_workspace uuid,p_email text,p_role text) returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text; address text := lower(trim(p_email)); old_role text;
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 actor_role := governance_private.role_for(p_workspace);
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') then raise exception 'Membership administration required' using errcode='42501'; end if;
 if p_role not in ('owner','admin','viewer') then raise exception 'Invalid role' using errcode='22023'; end if;
 select role into old_role from public.workspace_approvals where workspace_id=p_workspace and email=address and status='pending';
 if actor_role='admin' and (p_role<>'viewer' or coalesce(old_role,'viewer')<>'viewer') then raise exception 'Admins manage viewers only' using errcode='42501'; end if;
 if exists(select 1 from public.workspace_memberships m join auth.users u on u.id=m.user_id where m.workspace_id=p_workspace and lower(u.email)=address) then
  raise exception 'Use member controls for an existing membership' using errcode='22023';
 end if;
 insert into public.workspace_approvals(workspace_id,email,role,approved_by) values(p_workspace,address,p_role,actor)
 on conflict(workspace_id,email) do update set role=excluded.role,status='pending',approved_by=actor,claimed_by=null,updated_at=now();
 insert into public.governance_audit_events(workspace_id,actor_id,action,details) values(p_workspace,actor,'email_approved',jsonb_build_object('email',address,'role',p_role));
end $$;

create function public.revoke_workspace_approval(p_workspace uuid,p_approval uuid) returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text; target_role text;
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 actor_role := governance_private.role_for(p_workspace);
 select role into target_role from public.workspace_approvals where id=p_approval and workspace_id=p_workspace and status='pending';
 if target_role is null then raise exception 'Pending approval not found' using errcode='22023'; end if;
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') or (actor_role='admin' and target_role<>'viewer') then raise exception 'Permission denied' using errcode='42501'; end if;
 update public.workspace_approvals set status='revoked',updated_at=now() where id=p_approval;
 insert into public.governance_audit_events(workspace_id,actor_id,action,target_id) values(p_workspace,actor,'approval_revoked',p_approval);
end $$;

create function public.change_workspace_member(p_workspace uuid,p_user uuid,p_role text,p_active boolean) returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text; target public.workspace_memberships;
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 actor_role := governance_private.role_for(p_workspace);
 select * into target from public.workspace_memberships where workspace_id=p_workspace and user_id=p_user;
 if target.user_id is null then raise exception 'Member not found' using errcode='22023'; end if;
 if p_role not in ('owner','admin','viewer') or p_active is null then raise exception 'Invalid role or status' using errcode='22023'; end if;
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') or (actor_role='admin' and (target.role<>'viewer' or p_role<>'viewer' or p_user=actor)) then raise exception 'Permission denied' using errcode='42501'; end if;
 if target.active and target.role='owner' and (not p_active or p_role<>'owner') and
  (select count(*) from public.workspace_memberships where workspace_id=p_workspace and active and role='owner') <= 1 then
  raise exception 'Cannot remove the last active owner' using errcode='22023';
 end if;
 update public.workspace_memberships set role=p_role,active=p_active,updated_at=now() where workspace_id=p_workspace and user_id=p_user;
 insert into public.governance_audit_events(workspace_id,actor_id,action,target_id,details)
 values(p_workspace,actor,'member_changed',p_user,jsonb_build_object('role',p_role,'active',p_active));
end $$;

create function public.workspace_admin_data(p_workspace uuid,p_offset integer default 0) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text := governance_private.role_for(p_workspace);
begin
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') then raise exception 'Administration required' using errcode='42501'; end if;
 if p_offset < 0 or p_offset > 100000 then raise exception 'Invalid offset' using errcode='22023'; end if;
 return jsonb_build_object(
 'members',(select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from (select m.user_id,u.email,m.role,m.active from public.workspace_memberships m join auth.users u on u.id=m.user_id where m.workspace_id=p_workspace order by u.email limit 50 offset p_offset) t),
 'approvals',(select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from (select id,email,role,status from public.workspace_approvals where workspace_id=p_workspace and status='pending' order by email limit 50 offset p_offset) t),
 'events',(select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from (select action,actor_id,target_id,details,created_at from public.governance_audit_events where workspace_id=p_workspace order by created_at desc,id desc limit 20) t),
 'member_count',(select count(*) from public.workspace_memberships where workspace_id=p_workspace),
 'approval_count',(select count(*) from public.workspace_approvals where workspace_id=p_workspace and status='pending'));
end $$;
revoke all on function public.workspace_context(),public.claim_workspace_approvals(),public.create_workspace(text,text,text,text),public.update_workspace(uuid,text,text,text),public.approve_workspace_email(uuid,text,text),public.revoke_workspace_approval(uuid,uuid),public.change_workspace_member(uuid,uuid,text,boolean),public.workspace_admin_data(uuid,integer) from public,anon,authenticated;
grant execute on function public.workspace_context(),public.claim_workspace_approvals(),public.create_workspace(text,text,text,text),public.update_workspace(uuid,text,text,text),public.approve_workspace_email(uuid,text,text),public.revoke_workspace_approval(uuid,uuid),public.change_workspace_member(uuid,uuid,text,boolean),public.workspace_admin_data(uuid,integer) to authenticated;
commit;
