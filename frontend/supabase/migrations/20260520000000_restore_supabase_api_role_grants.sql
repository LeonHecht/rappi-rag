-- Restore the standard grants expected by Supabase API keys.
--
-- Supabase's new sb_secret_... keys authorize requests as the built-in
-- service_role Postgres role. That role bypasses RLS, but it still needs table
-- privileges. A previous remote schema migration revoked these grants, causing
-- backend calls made with SUPABASE_SECRET_KEY to fail with "permission denied".
--
-- This migration is defensive because some deployments may not have every
-- optional app table yet.

grant usage on schema public to anon, authenticated, service_role;

do $$
declare
  app_table text;
begin
  foreach app_table in array array[
    'user_profiles',
    'orgs',
    'members',
    'spaces',
    'files',
    'chats',
    'chat_messages',
    'user_settings',
    'payment_accounts'
  ]
  loop
    if to_regclass(format('public.%I', app_table)) is not null then
      execute format(
        'grant select, insert, update, delete on table public.%I to service_role',
        app_table
      );
    end if;
  end loop;
end $$;

do $$
begin
  if to_regclass('public.user_profiles') is not null then
    grant select, insert, update, delete on table public.user_profiles to authenticated;
  end if;

  if to_regclass('public.members') is not null then
    grant select on table public.members to authenticated;
  end if;

  if to_regclass('public.spaces') is not null then
    grant select, insert, update, delete on table public.spaces to authenticated;
    grant select on table public.spaces to anon;
  end if;

  if to_regclass('public.files') is not null then
    grant select, insert, delete on table public.files to authenticated;
  end if;

  if to_regclass('public.chats') is not null then
    grant select, insert, update, delete on table public.chats to authenticated;
  end if;

  if to_regclass('public.chat_messages') is not null then
    grant select, insert, update, delete on table public.chat_messages to authenticated;
  end if;

  if to_regclass('public.user_settings') is not null then
    grant select, insert, update, delete on table public.user_settings to authenticated;
  end if;

  if to_regclass('public.payment_accounts') is not null then
    grant select on table public.payment_accounts to authenticated;
  end if;
end $$;

grant usage, select on all sequences in schema public to anon, authenticated, service_role;
