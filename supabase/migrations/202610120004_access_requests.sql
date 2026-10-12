begin;
-- Registration links identify a destination; they never grant membership.
alter table public.workspaces add column registration_code text not null default substr(replace(gen_random_uuid()::text||gen_random_uuid()::text,'-',''),1,48) unique;
alter table public.workspaces add column registration_enabled boolean not null default true;
alter table public.workspaces add column registration_default boolean not null default false;
create unique index one_default_registration on public.workspaces(registration_default) where registration_default;
update public.workspaces set registration_default=true where id=(select id from public.workspaces order by created_at,id limit 1);
create table public.workspace_access_requests (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.workspaces(id),
 user_id uuid not null references auth.users(id), status text not null default 'pending' check(status in ('pending','approved','rejected','cancelled')),
 requested_at timestamptz not null default now(), reviewed_by uuid references auth.users(id), reviewed_at timestamptz,
 granted_role text check(granted_role in ('viewer','admin','owner')), decision_reason text not null default '' check(length(decision_reason)<=1000),
 check ((status='pending' and reviewed_by is null and reviewed_at is null and granted_role is null)
     or (status='approved' and reviewed_by is not null and reviewed_at is not null and granted_role is not null)
     or (status in ('rejected','cancelled') and reviewed_by is not null and reviewed_at is not null and granted_role is null))
);
create unique index one_pending_workspace_request on public.workspace_access_requests(workspace_id,user_id) where status='pending';
create index request_workspace_queue on public.workspace_access_requests(workspace_id,requested_at,id) where status='pending';
alter table public.workspace_access_requests enable row level security;
revoke all on public.workspace_access_requests from public,anon,authenticated;
grant select on public.workspace_access_requests to authenticated;
create policy request_read on public.workspace_access_requests for select to authenticated
 using (user_id=auth.uid() or governance_private.role_for(workspace_id) in ('owner','admin','platform_admin'));

create function public.registration_workspace(p_code text default null) returns jsonb
 language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
 select jsonb_build_object('name',name,'code',registration_code) into result from public.workspaces
 where registration_enabled and ((p_code is null and registration_default) or registration_code=p_code);
 if result is null and p_code is null and not exists(select 1 from public.workspaces) then
  return jsonb_build_object('name','Initial Account Registration','code',null);
 end if;
 return result;
end $$;
revoke all on function public.registration_workspace(text) from public;
grant execute on function public.registration_workspace(text) to anon,authenticated;

create function public.request_workspace_access(p_code text default null) returns uuid
 language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); w uuid; existing_id uuid;
begin
 select id into w from public.workspaces where registration_enabled and
 ((p_code is null and registration_default) or registration_code=p_code) for update;
 if w is null then raise exception 'Registration link is unavailable' using errcode='22023'; end if;
 if exists(select 1 from public.workspace_memberships where workspace_id=w and user_id=actor) then
  raise exception 'Use member controls for an existing membership' using errcode='22023'; end if;
 select id into existing_id from public.workspace_access_requests where workspace_id=w and user_id=actor and status='pending';
 if existing_id is not null then return existing_id; end if;
 insert into public.workspace_access_requests(workspace_id,user_id) values(w,actor) returning id into existing_id;
 insert into public.governance_audit_events(workspace_id,actor_id,action,target_id) values(w,actor,'access_requested',existing_id);
 return existing_id;
end $$;
revoke all on function public.request_workspace_access(text) from public,anon;
grant execute on function public.request_workspace_access(text) to authenticated;

-- Queue confirmed email-first registrations even when the user never returns to the app.
-- Metadata supplies only a validated registration destination, never authorization or a role.
create function governance_private.queue_verified_registration() returns trigger language plpgsql security definer set search_path='' as $$
declare w uuid; request_id uuid; code text;
begin
 if new.email_confirmed_at is null or new.email is null then return new; end if;
 if tg_op='UPDATE' then
  if old.email_confirmed_at is not null then return new; end if;
 end if;
 if new.raw_app_meta_data->>'provider' <> 'email' then return new; end if;
 code := new.raw_user_meta_data->>'workspace_registration_code';
 select id into w from public.workspaces where registration_enabled and
 ((code is null and registration_default) or registration_code=code) for update;
 if w is null or exists(select 1 from public.workspace_memberships where workspace_id=w and user_id=new.id) then return new; end if;
 insert into public.workspace_access_requests(workspace_id,user_id) values(w,new.id)
 on conflict(workspace_id,user_id) where status='pending' do nothing returning id into request_id;
 if request_id is not null then
  insert into public.governance_audit_events(workspace_id,actor_id,action,target_id) values(w,new.id,'access_requested',request_id);
 end if;
 return new;
end $$;
revoke all on function governance_private.queue_verified_registration() from public,anon,authenticated;
create trigger queue_verified_registration after insert or update of email_confirmed_at on auth.users
 for each row execute function governance_private.queue_verified_registration();

create function public.review_workspace_request(p_workspace uuid,p_request uuid,p_decision text,p_role text default 'viewer',p_reason text default '') returns void
 language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text; target public.workspace_access_requests;
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 actor_role := governance_private.role_for(p_workspace);
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') then raise exception 'Administration required' using errcode='42501'; end if;
 if p_decision is null or p_decision not in ('approved','rejected') or p_role is null or p_role not in ('viewer','admin','owner') or p_reason is null or length(p_reason)>1000 then raise exception 'Invalid decision' using errcode='22023'; end if;
 if actor_role='admin' and p_role<>'viewer' then raise exception 'Admins manage viewers only' using errcode='42501'; end if;
 select * into target from public.workspace_access_requests where id=p_request and workspace_id=p_workspace for update;
 if target.id is null or target.status<>'pending' then raise exception 'Request is no longer pending' using errcode='22023'; end if;
 if target.user_id=actor then raise exception 'Self approval is not allowed' using errcode='42501'; end if;
 if not exists(select 1 from auth.users where id=target.user_id and email_confirmed_at is not null and email is not null) then raise exception 'A verified account is required' using errcode='22023'; end if;
 if p_decision='approved' then
  if exists(select 1 from public.workspace_memberships where workspace_id=p_workspace and user_id=target.user_id) then raise exception 'Use member controls for an existing membership' using errcode='22023'; end if;
  insert into public.workspace_memberships(workspace_id,user_id,role) values(p_workspace,target.user_id,p_role);
 end if;
 update public.workspace_access_requests set status=p_decision,reviewed_by=actor,reviewed_at=now(),
 granted_role=case when p_decision='approved' then p_role else null end,decision_reason=trim(p_reason) where id=p_request;
 insert into public.governance_audit_events(workspace_id,actor_id,action,target_id,details)
 values(p_workspace,actor,'access_'||p_decision,target.user_id,jsonb_build_object('request_id',p_request,'role',case when p_decision='approved' then p_role else null end,'reason',trim(p_reason)));
end $$;
revoke all on function public.review_workspace_request(uuid,uuid,text,text,text) from public,anon;
grant execute on function public.review_workspace_request(uuid,uuid,text,text,text) to authenticated;

-- Preserve existing approved access without waiting for another sign-in. Never reactivate revoked memberships.
insert into public.workspace_memberships(workspace_id,user_id,role)
 select a.workspace_id,u.id,a.role from public.workspace_approvals a join auth.users u on lower(u.email)=a.email
 where a.status='pending' and u.email_confirmed_at is not null on conflict do nothing;
insert into public.workspace_access_requests(workspace_id,user_id,status,requested_at,reviewed_by,reviewed_at,granted_role)
 select a.workspace_id,u.id,'approved',a.created_at,a.approved_by,a.updated_at,a.role from public.workspace_approvals a
 join auth.users u on lower(u.email)=a.email where a.status in ('pending','claimed') and u.email_confirmed_at is not null;
insert into public.governance_audit_events(workspace_id,actor_id,action,target_id)
 select a.workspace_id,a.approved_by,'legacy_approval_migrated',u.id from public.workspace_approvals a join auth.users u on lower(u.email)=a.email where a.status='pending' and u.email_confirmed_at is not null;
update public.workspace_approvals a set status='claimed',claimed_by=u.id,updated_at=now() from auth.users u where a.status='pending' and lower(u.email)=a.email and u.email_confirmed_at is not null;
-- Existing verified accounts without a membership join the initial workspace queue.
insert into public.workspace_access_requests(workspace_id,user_id)
 select w.id,u.id from public.workspaces w cross join auth.users u
 where w.registration_default and w.registration_enabled and u.email_confirmed_at is not null and u.email is not null
 and not exists(select 1 from public.workspace_memberships m where m.workspace_id=w.id and m.user_id=u.id)
 on conflict(workspace_id,user_id) where status='pending' do nothing;
insert into public.governance_audit_events(workspace_id,actor_id,action,target_id)
 select workspace_id,user_id,'access_request_migrated',id from public.workspace_access_requests where status='pending';
-- Keep old records for history, but old write/claim RPCs cannot grant or revoke anything.
revoke execute on function public.claim_workspace_approvals(),public.revoke_workspace_approval(uuid,uuid) from authenticated;

create or replace function public.approve_workspace_email(p_workspace uuid,p_email text,p_role text) returns void language plpgsql security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text; target_user uuid; request_id uuid;
begin
 perform 1 from public.workspaces where id=p_workspace for update;
 actor_role := governance_private.role_for(p_workspace);
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') then raise exception 'Administration required' using errcode='42501'; end if;
 if p_role is null or p_role not in ('viewer','admin','owner') then raise exception 'Invalid role' using errcode='22023'; end if;
 if actor_role='admin' and p_role<>'viewer' then raise exception 'Admins manage viewers only' using errcode='42501'; end if;
 select id into target_user from auth.users where lower(email)=lower(trim(p_email)) and email_confirmed_at is not null;
 if target_user is null then raise exception 'The user must sign up and verify this email before workspace approval.' using errcode='22023'; end if;
 if target_user=actor then raise exception 'Self approval is not allowed' using errcode='42501'; end if;
 if exists(select 1 from public.workspace_memberships where workspace_id=p_workspace and user_id=target_user) then raise exception 'Use member controls for an existing membership' using errcode='22023'; end if;
 select id into request_id from public.workspace_access_requests where workspace_id=p_workspace and user_id=target_user and status='pending';
 if request_id is null then
  insert into public.workspace_access_requests(workspace_id,user_id) values(p_workspace,target_user) returning id into request_id;
 end if;
 perform public.review_workspace_request(p_workspace,request_id,'approved',p_role,'Manual email approval');
end $$;

create or replace function public.workspace_admin_data(p_workspace uuid,p_offset integer default 0) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); actor_role text := governance_private.role_for(p_workspace);
begin
 if actor_role is null or actor_role not in ('owner','admin','platform_admin') then raise exception 'Administration required' using errcode='42501'; end if;
 if p_offset is null or p_offset<0 or p_offset>100000 then raise exception 'Invalid offset' using errcode='22023'; end if;
 return jsonb_build_object(
 'members',(select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from (select m.user_id,u.email,m.role,m.active from public.workspace_memberships m join auth.users u on u.id=m.user_id where m.workspace_id=p_workspace order by u.email,m.user_id limit 50 offset p_offset) t),
 'approvals',(select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from (select r.id,u.email,r.status,to_char(r.requested_at at time zone 'UTC','YYYY-MM-DD HH24:MI')||' UTC' as requested_at from public.workspace_access_requests r join auth.users u on u.id=r.user_id where r.workspace_id=p_workspace and r.status='pending' and u.email_confirmed_at is not null order by r.requested_at,r.id limit 50 offset p_offset) t),
 'events',(select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from (select action,actor_id,target_id,details,created_at from public.governance_audit_events where workspace_id=p_workspace order by created_at desc,id desc limit 20) t),
 'member_count',(select count(*) from public.workspace_memberships where workspace_id=p_workspace),
 'approval_count',(select count(*) from public.workspace_access_requests r join auth.users u on u.id=r.user_id where r.workspace_id=p_workspace and r.status='pending' and u.email_confirmed_at is not null),
 'registration_code',(select registration_code from public.workspaces where id=p_workspace and registration_enabled));
end $$;
create function public.my_access_request_status() returns text language plpgsql stable security definer set search_path='' as $$
declare actor uuid := governance_private.verified_user(); result text;
begin
 select status into result from public.workspace_access_requests where user_id=actor
 order by (status='pending') desc,requested_at desc,id desc limit 1;
 return case when result in ('pending','rejected','cancelled') then result else 'unavailable' end;
end $$;
revoke all on function public.my_access_request_status() from public,anon;
grant execute on function public.my_access_request_status() to authenticated;
notify pgrst,'reload schema';
commit;
