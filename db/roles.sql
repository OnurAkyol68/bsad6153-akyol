-- db/roles.sql: who may do what in your database (Week 2, extended in Week 6).
--
-- NEVER PUT A PASSWORD IN THIS FILE. It is committed to GitHub.
-- Create each role here without a password, then set the password separately
-- in the Supabase SQL editor (and nowhere in your repository):
--
--     alter role app_reader with password '...long random password...';
--
-- Then put the role's connection string in .env as APP_DATABASE_URL.
--
-- Week 2/3: a read-only role for the website, chatbot, and golden-question checker.
-- Run this file in the Supabase SQL editor as postgres. Safe to run again.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'app_reader') then
        create role app_reader login;
    end if;
end $$;

grant usage on schema public to app_reader;
grant select on teams, team_seasons, players, matches, goals, standings to app_reader;
grant select on sync_runs to app_reader;   -- Week 3: read the sync history, never write it

-- Nothing else: no insert, update, delete, truncate, and no create in the schema.
revoke create on schema public from app_reader;
--
-- Week 6: the agent's own role (see the Week 6 page for the exact grants).
-- create role agent_writer login;
-- grant usage on schema public to agent_writer;
-- grant select on <your data tables>, sync_runs, agent_runs, agent_proposals to agent_writer;
-- grant insert on agent_runs, agent_proposals to agent_writer;
-- grant update on agent_runs to agent_writer;
--
-- Week 6: the one write your website may do, which covers only the review columns.
-- grant select on agent_runs, agent_proposals to app_reader;
-- grant update (status, reviewed_at, reviewer_note) on agent_proposals to app_reader;
