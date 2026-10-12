\set ON_ERROR_STOP on
insert into auth.users values
 ('00000000-0000-0000-0000-000000000001','platform@example.test',now()),
 ('00000000-0000-0000-0000-000000000002','owner@example.test',now()),
 ('00000000-0000-0000-0000-000000000003','admin@example.test',now()),
 ('00000000-0000-0000-0000-000000000004','viewer@example.test',now()),
 ('00000000-0000-0000-0000-000000000005','pending@example.test',now()),
 ('00000000-0000-0000-0000-000000000006','unconfirmed@example.test',null),
 ('00000000-0000-0000-0000-000000000007','second-owner@example.test',now()),
 ('00000000-0000-0000-0000-000000000008','revoked@example.test',now());
insert into public.platform_administrators(user_id) values('00000000-0000-0000-0000-000000000001');
insert into public.workspaces(id,name,purpose,responsible_team) values
 ('10000000-0000-0000-0000-000000000001','First','Reporting','Analytics'),
 ('10000000-0000-0000-0000-000000000002','Hidden','Reporting','Analytics');
insert into public.workspace_memberships(workspace_id,user_id,role) values
 ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','owner'),
 ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000003','admin'),
 ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000004','viewer'),
 ('10000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000007','owner');
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000004',false);
do $$begin
 if (select count(*) from public.workspaces)<>1 then raise exception 'Cross-workspace RLS failed'; end if;
 if (select count(*) from public.workspace_memberships)<>1 then raise exception 'Member privacy failed'; end if;
 begin perform public.approve_workspace_email('10000000-0000-0000-0000-000000000001','new@example.test','owner'); raise exception 'Viewer approved a member'; exception when insufficient_privilege then null; end;
 begin perform public.workspace_admin_data('10000000-0000-0000-0000-000000000001'); raise exception 'Viewer read admin data'; exception when insufficient_privilege then null; end;
 begin insert into public.platform_administrators(user_id) values(auth.uid()); raise exception 'Self promotion'; exception when insufficient_privilege then null; end;
 begin update public.workspace_memberships set role='owner' where user_id=auth.uid(); raise exception 'Direct role write'; exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000003',false);
do $$begin
 begin perform public.approve_workspace_email('10000000-0000-0000-0000-000000000001','new@example.test','owner'); raise exception 'Admin granted owner'; exception when insufficient_privilege then null; end;
 begin perform public.change_workspace_member('10000000-0000-0000-0000-000000000001',auth.uid(),'owner',true); raise exception 'Admin self-promotion'; exception when insufficient_privilege then null; end;
 begin perform public.approve_workspace_email('10000000-0000-0000-0000-000000000002','new@example.test','viewer'); raise exception 'Cross workspace write'; exception when insufficient_privilege then null; end;
end $$;
select public.approve_workspace_email('10000000-0000-0000-0000-000000000001','  Pending@Example.test  ','viewer');
do $$begin
 begin perform public.approve_workspace_email('10000000-0000-0000-0000-000000000001','unconfirmed@example.test','viewer'); raise exception 'Unverified email approved'; exception when invalid_parameter_value then null; end;
 begin perform public.approve_workspace_email('10000000-0000-0000-0000-000000000001','unknown@example.test','viewer'); raise exception 'Unregistered email approved'; exception when invalid_parameter_value then null; end;
 if exists(select 1 from jsonb_to_recordset(public.workspace_admin_data('10000000-0000-0000-0000-000000000001')->'approvals') as a(email text) where email in ('unconfirmed@example.test','unknown@example.test')) then raise exception 'Rejected approval persisted'; end if;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000005',false);
select public.claim_workspace_approvals();
select public.claim_workspace_approvals();
do $$begin
 if not exists(select 1 from public.workspace_memberships where user_id=auth.uid() and active and role='viewer') then raise exception 'Approval not claimed'; end if;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000006',false);
do $$begin
 begin perform public.claim_workspace_approvals(); raise exception 'Unconfirmed account claimed'; exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',false);
do $$begin
 begin perform public.change_workspace_member('10000000-0000-0000-0000-000000000001',auth.uid(),'viewer',true); raise exception 'Last owner demoted'; exception when invalid_parameter_value then null; end;
end $$;
select public.change_workspace_member('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000005','viewer',false);
select public.approve_workspace_email('10000000-0000-0000-0000-000000000001','revoked@example.test','viewer');
select public.revoke_workspace_approval('10000000-0000-0000-0000-000000000001',(select id from jsonb_to_recordset(public.workspace_admin_data('10000000-0000-0000-0000-000000000001')->'approvals') as a(id uuid,email text) where email='revoked@example.test'));
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000005',false);
select public.claim_workspace_approvals();
do $$begin
 if exists(select 1 from public.workspace_memberships where user_id=auth.uid() and active) then raise exception 'Revocation was bypassed'; end if;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
select public.create_workspace('Created','Reporting','Team','owner@example.test');
do $$begin
 if jsonb_array_length(public.workspace_context()->'workspaces')<>3 then raise exception 'Platform admin visibility'; end if;
end $$;
reset role;
-- Prepare two simultaneous owner demotions in the concurrency harness.
insert into public.workspace_memberships(workspace_id,user_id,role) values('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000007','owner');
