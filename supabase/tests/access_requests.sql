\set ON_ERROR_STOP on
-- Migration preserves active/revoked members and historical approvals.
do $$begin
 if not exists(select 1 from public.workspace_memberships where user_id='00000000-0000-0000-0000-000000000004' and active) then raise exception 'Existing access lost'; end if;
 if exists(select 1 from public.workspace_memberships where user_id='00000000-0000-0000-0000-000000000005' and active) then raise exception 'Revoked access reactivated'; end if;
 if not exists(select 1 from public.workspace_memberships where user_id='a0000000-0000-0000-0000-000000000099' and active and role='viewer') then raise exception 'Legacy pending approval not preserved'; end if;
 if exists(select 1 from public.workspace_access_requests r join auth.users u on u.id=r.user_id where r.status='pending' and u.email_confirmed_at is null) then raise exception 'Unverified user queued'; end if;
end $$;
insert into auth.users(id,email) values('a0000000-0000-0000-0000-000000000001','queue@example.test');
do $$begin
 if exists(select 1 from public.workspace_access_requests where user_id='a0000000-0000-0000-0000-000000000001') then raise exception 'Unverified registration queued'; end if;
end $$;
update auth.users set email_confirmed_at=now() where id='a0000000-0000-0000-0000-000000000001';
update auth.users set raw_user_meta_data='{"role":"owner"}' where id='a0000000-0000-0000-0000-000000000001';
do $$begin
 if (select count(*) from public.workspace_access_requests where user_id='a0000000-0000-0000-0000-000000000001' and status='pending')<>1 then raise exception 'Confirmation did not create exactly one request'; end if;
 if exists(select 1 from public.workspace_memberships where user_id='a0000000-0000-0000-0000-000000000001') then raise exception 'Registration granted membership'; end if;
end $$;
set role authenticated;
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000001',false);
do $$declare r uuid; begin
 select id into r from public.workspace_access_requests where user_id=auth.uid() and status='pending';
 if public.request_workspace_access()<>r then raise exception 'Request not idempotent'; end if;
 if (select count(*) from public.workspace_access_requests)<>1 then raise exception 'Applicant read other requests'; end if;
 begin perform public.workspace_admin_data('10000000-0000-0000-0000-000000000001'); raise exception 'Applicant read queue'; exception when insufficient_privilege then null; end;
 begin perform public.review_workspace_request('10000000-0000-0000-0000-000000000001',r,'approved','owner',''); raise exception 'Self promotion'; exception when insufficient_privilege then null; end;
 begin perform public.claim_workspace_approvals(); raise exception 'Old claiming still enabled'; exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000003',false);
do $$declare r uuid; begin
 select id into r from public.workspace_access_requests where user_id='a0000000-0000-0000-0000-000000000001' and status='pending';
 begin perform public.review_workspace_request('10000000-0000-0000-0000-000000000001',r,'approved','owner',''); raise exception 'Admin granted Owner'; exception when insufficient_privilege then null; end;
 begin perform public.review_workspace_request('10000000-0000-0000-0000-000000000002',r,'approved','viewer',''); raise exception 'Cross workspace review'; exception when insufficient_privilege then null; end;
 perform public.review_workspace_request('10000000-0000-0000-0000-000000000001',r,'approved','viewer','Welcome');
 if not exists(select 1 from public.workspace_memberships where workspace_id='10000000-0000-0000-0000-000000000001' and user_id='a0000000-0000-0000-0000-000000000001' and role='viewer' and active) then raise exception 'Membership not immediate'; end if;
 begin perform public.review_workspace_request('10000000-0000-0000-0000-000000000001',r,'rejected','viewer',''); raise exception 'Stale decision accepted'; exception when invalid_parameter_value then null; end;
end $$;
reset role;
-- Workspace-specific registration cannot drift to the default or grant a browser-supplied role.
insert into auth.users(id,email,raw_user_meta_data) select 'a0000000-0000-0000-0000-000000000002','second-queue@example.test',jsonb_build_object('workspace_registration_code',registration_code,'role','owner') from public.workspaces where id='10000000-0000-0000-0000-000000000002';
update auth.users set email_confirmed_at=now() where id='a0000000-0000-0000-0000-000000000002';
do $$begin
 if not exists(select 1 from public.workspace_access_requests where user_id='a0000000-0000-0000-0000-000000000002' and workspace_id='10000000-0000-0000-0000-000000000002') then raise exception 'Workspace routing lost'; end if;
end $$;
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000007',false);
do $$declare r uuid; begin
 select id into r from public.workspace_access_requests where user_id='a0000000-0000-0000-0000-000000000002';
 perform public.review_workspace_request('10000000-0000-0000-0000-000000000002',r,'rejected','viewer','Not this team');
 if exists(select 1 from public.workspace_memberships where user_id='a0000000-0000-0000-0000-000000000002') then raise exception 'Rejected user granted access'; end if;
end $$;
reset role;
-- Requests never reactivate an existing revoked member.
insert into auth.users(id,email,email_confirmed_at) values('a0000000-0000-0000-0000-000000000003','revoked-queue@example.test',now());
insert into public.workspace_memberships(workspace_id,user_id,role,active) values('10000000-0000-0000-0000-000000000001','a0000000-0000-0000-0000-000000000003','viewer',false);
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000003',false);
do $$begin
 begin perform public.approve_workspace_email('10000000-0000-0000-0000-000000000001','revoked-queue@example.test','viewer'); raise exception 'Revocation bypassed'; exception when invalid_parameter_value then null; end;
end $$;
reset role;
set role anon;
do $$begin
 if public.registration_workspace() is null then raise exception 'Default registration unavailable'; end if;
 if public.registration_workspace('invalid') is not null then raise exception 'Invalid registration resolved'; end if;
 begin perform public.request_workspace_access(); raise exception 'Anonymous request accepted'; exception when insufficient_privilege then null; end;
 begin perform count(*) from public.workspace_access_requests; raise exception 'Anonymous queue exposure'; exception when insufficient_privilege then null; end;
end $$;
reset role;
