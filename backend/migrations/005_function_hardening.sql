-- Hardening from Supabase's security advisor (2026-10-10).
--
-- 1. Our trigger functions pin search_path so a role-controlled path can never redirect what they call.
-- 2. rls_auto_enable() is Supabase's own helper behind "automatic RLS" (an event trigger, SECURITY DEFINER).
--    Nothing outside the database needs to call it, but it was executable by anon/authenticated through the
--    REST API's /rpc. Revoke that; the event trigger keeps working (event triggers do not need EXECUTE grants).
alter function public.forbid_ledger_mutation()   set search_path = public, pg_temp;
alter function public.watch_resolves_once()      set search_path = public, pg_temp;
alter function public.forbid_proposal_mutation() set search_path = public, pg_temp;

revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
