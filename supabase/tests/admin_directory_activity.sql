\set ON_ERROR_STOP on
-- Synthetic fixtures in the network-isolated test database only.
begin;
insert into auth.users(id,email,email_confirmed_at)
select ('c0000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid,'directory-'||lpad(i::text,3,'0')||'@example.test',now()
from generate_series(1,24) i;
insert into public.workspace_memberships(workspace_id,user_id,role,active)
select '10000000-0000-0000-0000-000000000001',('c0000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid,'viewer',i%2=0
from generate_series(1,24) i;
insert into public.governance_audit_events(workspace_id,actor_id,action)
select '10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','directory_test_'||i
from generate_series(1,27) i;
set local role anon;
do $$begin
 begin perform public.workspace_members_directory(); raise exception 'Anonymous directory read'; exception when insufficient_privilege then null; end;
 begin perform public.workspace_governance_activity('10000000-0000-0000-0000-000000000001'); raise exception 'Anonymous audit read'; exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000004',true);
do $$begin
 begin perform public.workspace_members_directory(); raise exception 'Viewer directory read'; exception when insufficient_privilege then null; end;
 begin perform public.workspace_governance_activity('10000000-0000-0000-0000-000000000001'); raise exception 'Viewer audit read'; exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',true);
do $$declare first_page jsonb; next_page jsonb; result jsonb; begin
 first_page:=public.workspace_members_directory(null,0,'directory-');
 next_page:=public.workspace_members_directory(null,10,'directory-');
 if (first_page->>'total')::int<>24 or jsonb_array_length(first_page->'members')<>10 or (next_page->>'offset')::int<>10 then raise exception 'Directory pages/count failed'; end if;
 if (first_page->'members'->0->>'user_id')=(next_page->'members'->0->>'user_id') then raise exception 'Repeated directory page'; end if;
 if exists(select 1 from jsonb_array_elements(public.workspace_members_directory()->'members') m where m->>'workspace_id'<>'10000000-0000-0000-0000-000000000001') then raise exception 'All-scope leaked workspace'; end if;
 result:=public.workspace_members_directory(null,0,'directory-','viewer',false);
 if (result->>'total')::int<>12 then raise exception 'Global role/status filter failed'; end if;
 result:=public.workspace_members_directory(null,0,'absent@example.test');
 if (result->>'total')::int<>0 or jsonb_array_length(result->'members')<>0 then raise exception 'Empty directory failed'; end if;
 result:=public.workspace_members_directory(null,99990,'directory-');
 if (result->>'offset')::int<>20 or jsonb_array_length(result->'members')<>4 then raise exception 'Directory page clamp failed'; end if;
 result:=public.workspace_members_directory('10000000-0000-0000-0000-000000000001',0,'',null,null,'c0000000-0000-0000-0000-000000000001');
 if jsonb_array_length(result->'members')<>1 or result->'members'->0->>'workspace_name'<>'First' then raise exception 'Member detail lookup failed'; end if;
 begin perform public.workspace_members_directory('10000000-0000-0000-0000-000000000002'); raise exception 'Foreign directory read'; exception when insufficient_privilege then null; end;
 begin perform public.workspace_governance_activity('10000000-0000-0000-0000-000000000002'); raise exception 'Foreign activity read'; exception when insufficient_privilege then null; end;
 begin perform public.workspace_members_directory(null,-1); raise exception 'Negative directory offset'; exception when invalid_parameter_value then null; end;
 begin perform public.workspace_members_directory(null,0,'','forged'); raise exception 'Invalid role accepted'; exception when invalid_parameter_value then null; end;
 begin perform public.workspace_governance_activity('10000000-0000-0000-0000-000000000001',100001); raise exception 'Unbounded activity offset'; exception when invalid_parameter_value then null; end;
 first_page:=public.workspace_governance_activity('10000000-0000-0000-0000-000000000001',0);
 next_page:=public.workspace_governance_activity('10000000-0000-0000-0000-000000000001',5);
 result:=public.workspace_governance_activity('10000000-0000-0000-0000-000000000001',25);
 if jsonb_array_length(first_page->'events')<>5 or (next_page->>'offset')::int<>5 or jsonb_array_length(result->'events')=0 then raise exception 'Historical activity pagination failed'; end if;
 if (first_page->'events'->0->>'id')=(next_page->'events'->0->>'id') then raise exception 'Audit page repeated'; end if;
 if first_page->'events'->0->>'actor_email'<>'owner@example.test' then raise exception 'Actor display failed'; end if;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000003',true);
do $$begin
 if jsonb_array_length(public.workspace_members_directory(null,0,'directory-')->'members')<>10 then raise exception 'Admin directory access failed'; end if;
 begin perform public.change_workspace_member('10000000-0000-0000-0000-000000000001','c0000000-0000-0000-0000-000000000001','owner',true); raise exception 'Directory enabled admin promotion'; exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
do $$begin
 if jsonb_array_length(public.workspace_members_directory('10000000-0000-0000-0000-000000000002')->'members')=0 then raise exception 'Platform directory visibility failed'; end if;
end $$;
reset role;
rollback;
