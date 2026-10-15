-- Bounded administrative reads. Existing transactional RPCs remain the only writes.
begin;

create function public.workspace_members_directory(
 p_workspace uuid default null, p_offset integer default 0, p_query text default '',
 p_role text default null, p_active boolean default null, p_user uuid default null
) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare
 actor uuid := governance_private.verified_user();
 total bigint; page_offset integer; rows jsonb;
begin
 if not exists(select 1 from public.workspaces w where governance_private.role_for(w.id) in ('owner','admin','platform_admin')) then
  raise exception 'Administration required' using errcode='42501';
 end if;
 if p_workspace is not null and (not exists(select 1 from public.workspaces where id=p_workspace) or coalesce(governance_private.role_for(p_workspace),'') not in ('owner','admin','platform_admin')) then
  raise exception 'Administration required' using errcode='42501';
 end if;
 if p_offset is null or p_offset<0 or p_offset>100000 or p_query is null or length(p_query)>200 or (p_role is not null and p_role not in ('owner','admin','viewer')) then
  raise exception 'Invalid directory filters' using errcode='22023';
 end if;
 select count(*) into total
 from public.workspace_memberships m join public.workspaces w on w.id=m.workspace_id join auth.users u on u.id=m.user_id
 where governance_private.role_for(w.id) in ('owner','admin','platform_admin')
 and (p_workspace is null or m.workspace_id=p_workspace)
 and (p_role is null or m.role=p_role) and (p_active is null or m.active=p_active)
 and (p_user is null or m.user_id=p_user)
 and position(lower(trim(p_query)) in lower(coalesce(u.email,'')))>0;
 page_offset := least(p_offset, greatest(((total-1)/10)*10,0)::integer);
 select coalesce(jsonb_agg(to_jsonb(t) order by t.email,t.workspace_name,t.workspace_id,t.user_id),'[]'::jsonb) into rows from (
  select m.workspace_id,w.name as workspace_name,m.user_id,u.email,m.role,m.active,m.created_at,m.updated_at,
   (u.email_confirmed_at is not null) as email_confirmed
  from public.workspace_memberships m join public.workspaces w on w.id=m.workspace_id join auth.users u on u.id=m.user_id
  where governance_private.role_for(w.id) in ('owner','admin','platform_admin')
  and (p_workspace is null or m.workspace_id=p_workspace)
  and (p_role is null or m.role=p_role) and (p_active is null or m.active=p_active)
  and (p_user is null or m.user_id=p_user)
  and position(lower(trim(p_query)) in lower(coalesce(u.email,'')))>0
  order by u.email,w.name,m.workspace_id,m.user_id limit 10 offset page_offset
 ) t;
 return jsonb_build_object('members',rows,'total',total,'offset',page_offset);
end $$;

create function public.workspace_governance_activity(p_workspace uuid,p_offset integer default 0)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare
 actor uuid := governance_private.verified_user();
 total bigint; page_offset integer; rows jsonb;
begin
 if coalesce(governance_private.role_for(p_workspace),'') not in ('owner','admin','platform_admin') then
  raise exception 'Administration required' using errcode='42501';
 end if;
 if p_offset is null or p_offset<0 or p_offset>100000 then
  raise exception 'Invalid offset' using errcode='22023';
 end if;
 select count(*) into total from public.governance_audit_events where workspace_id=p_workspace;
 page_offset := least(p_offset, greatest(((total-1)/5)*5,0)::integer);
 select coalesce(jsonb_agg(to_jsonb(t) order by t.created_at desc,t.id desc),'[]'::jsonb) into rows from (
  select e.id,e.action,e.actor_id,e.target_id,e.created_at,
   coalesce(a.email,case when e.actor_id is null then 'System' else 'Former member' end) as actor_email,
   target.email as target_email
  from public.governance_audit_events e
  left join auth.users a on a.id=e.actor_id left join auth.users target on target.id=e.target_id
  where e.workspace_id=p_workspace order by e.created_at desc,e.id desc limit 5 offset page_offset
 ) t;
 return jsonb_build_object('events',rows,'total',total,'offset',page_offset);
end $$;

revoke all on function public.workspace_members_directory(uuid,integer,text,text,boolean,uuid), public.workspace_governance_activity(uuid,integer) from public,anon,authenticated;
grant execute on function public.workspace_members_directory(uuid,integer,text,text,boolean,uuid), public.workspace_governance_activity(uuid,integer) to authenticated;
commit;
