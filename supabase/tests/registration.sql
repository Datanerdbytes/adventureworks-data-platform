begin;
insert into auth.users(id,email,raw_app_meta_data) values
 ('90000000-0000-0000-0000-000000000001','registered@example.test','{"provider":"email"}');
do $$
declare provider text;
begin
 foreach provider in array array['google','github',''] loop
  begin
   insert into auth.users(id,email,raw_app_meta_data) values
    ('90000000-0000-0000-0000-000000000002','new@example.test',jsonb_build_object('provider',provider));
   raise exception 'Unexpected social registration acceptance';
  exception when check_violation then null;
  end;
 end loop;
end $$;
-- Linking an identity to an existing account does not create another account.
update auth.users set raw_app_meta_data='{"provider":"email","providers":["email","google"]}'
 where id='90000000-0000-0000-0000-000000000001';
rollback;
