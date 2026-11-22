-- db/quality_checks.sql: the query behind every number in docs/data_quality.md (Week 3).
-- Read-only: every query here works as app_reader. Each check has a label (QC01, QC02, ...)
-- that docs/data_quality.md refers to.

-- QC01 Row counts per table
select 'teams' as table_name, count(*) as row_count from teams
union all select 'team_seasons', count(*) from team_seasons
union all select 'players', count(*) from players
union all select 'matches', count(*) from matches
union all select 'goals', count(*) from goals
union all select 'standings', count(*) from standings
union all select 'sync_runs', count(*) from sync_runs;

-- QC02 Null rates for the most important goal fields
select count(*)                                                          as goals,
       round(100.0 * count(*) filter (where player_id is null) / count(*), 2)       as pct_no_scorer,
       round(100.0 * count(*) filter (where minute is null) / count(*), 2)          as pct_no_minute,
       round(100.0 * count(*) filter (where scoring_team_id is null) / count(*), 2) as pct_no_team
from goals;

-- QC03 Null rates for match scores: finished matches must have scores, unplayed must not
select is_finished,
       count(*)                                              as matches,
       count(*) filter (where home_goals is null)            as no_final_score,
       count(*) filter (where home_goals_halftime is null)   as no_halftime_score
from matches group by is_finished order by is_finished;

-- QC04 Duplicates by natural ID (must be 0: primary keys)
select 'matches' as table_name, count(*) - count(distinct match_id) as duplicates from matches
union all select 'goals', count(*) - count(distinct goal_id) from goals
union all select 'players', count(*) - count(distinct player_id) from players
union all select 'teams', count(*) - count(distinct team_id) from teams;

-- QC05 "Same thing, different ID": the same pairing twice in one season
select season, home_team_id, away_team_id, count(*) as times
from matches group by season, home_team_id, away_team_id having count(*) > 1;

-- QC06 "Same thing, different ID": players with the same short name but different IDs
select short_name, count(*) as ids, string_agg(player_id::text, ', ') as player_ids
from players group by short_name having count(*) > 1 order by ids desc, short_name;

-- QC07 "Same thing, different ID": the same goal twice (same match, minute and score after)
select match_id, minute, home_score_after, away_score_after, count(*) as times
from goals group by match_id, minute, home_score_after, away_score_after having count(*) > 1;

-- QC08 Out of range / inconsistent: goal records don't add up to the final score
select m.match_id, m.season, m.matchday, m.home_goals + m.away_goals as final_goals,
       count(g.goal_id) as goal_records
from matches m left join goals g on g.match_id = m.match_id
where m.is_finished
group by m.match_id
having count(g.goal_id) <> m.home_goals + m.away_goals
order by m.season, m.matchday;

-- QC09 Out of range / inconsistent: placeholder goals with a 0:0 score after the goal
select count(*) as zero_zero_goals from goals where home_score_after = 0 and away_score_after = 0;

-- QC10 Out of range / inconsistent: matches marked unfinished whose kickoff is over 3 hours ago
select match_id, season, matchday, kickoff_at
from matches where not is_finished and kickoff_at < now() - interval '3 hours'
order by kickoff_at;

-- QC11 Out of range / inconsistent: time zones. source_updated_at before kickoff for finished matches
-- would mean the German-time conversion is wrong.
select count(*) as finished_but_updated_before_kickoff
from matches where is_finished and source_updated_at < kickoff_at;

-- QC12 Inconsistent: the stored table vs. points computed from our own matches (running season)
with r as (
    select home_team_id as team_id, case when home_goals > away_goals then 3 when home_goals = away_goals then 1 else 0 end as pts
    from matches where season = 2026 and is_finished
    union all
    select away_team_id, case when away_goals > home_goals then 3 when away_goals = home_goals then 1 else 0 end
    from matches where season = 2026 and is_finished
)
select t.short_name, s.points as table_points, sum(r.pts) as computed_points
from standings s join teams t on t.team_id = s.team_id join r on r.team_id = s.team_id
where s.season = 2026
group by t.short_name, s.points having s.points <> sum(r.pts);

-- QC13 Orphans: goals whose match, team or player is missing (foreign keys make these 0)
select count(*) filter (where m.match_id is null)                              as goals_without_match,
       count(*) filter (where g.player_id is not null and p.player_id is null) as goals_without_player,
       count(*) filter (where g.scoring_team_id is not null and t.team_id is null) as goals_without_team
from goals g
left join matches m on m.match_id = g.match_id
left join players p on p.player_id = g.player_id
left join teams t   on t.team_id = g.scoring_team_id;

-- QC14 Orphans the other way: players without any goal, teams without a season
select (select count(*) from players p where not exists (select 1 from goals g where g.player_id = p.player_id)) as players_without_goals,
       (select count(*) from teams t where not exists (select 1 from team_seasons ts where ts.team_id = t.team_id)) as teams_without_season;

-- QC15 Fairness: how many goals (= evidence) each scorer has in the running season
select case when n = 1 then '1 goal' when n = 2 then '2 goals' when n <= 4 then '3-4 goals' else '5+ goals' end as evidence,
       count(*) as players
from (select player_id, count(*) as n from goals g join matches m on m.match_id = g.match_id
      where m.season = 2026 and g.player_id is not null and not g.is_own_goal group by player_id) x
group by 1 order by min(n);

-- QC16 Fairness: goals vs. defenders. Share of all 2026 goals scored by the top 10% of scorers
with per_player as (
    select player_id, count(*) as n from goals g join matches m on m.match_id = g.match_id
    where m.season = 2026 and g.player_id is not null and not g.is_own_goal group by player_id
), ranked as (
    select n, ntile(10) over (order by n desc) as decile from per_player
)
select round(100.0 * sum(n) filter (where decile = 1) / sum(n), 1) as pct_goals_top10pct_players,
       count(*) as scorers
from ranked;

-- QC17 Fairness: newly promoted clubs have only one season of history
select t.short_name, count(distinct ts.season) as seasons_in_db,
       (select count(*) from matches m where m.is_finished and (m.home_team_id = t.team_id or m.away_team_id = t.team_id)) as finished_matches
from teams t join team_seasons ts on ts.team_id = t.team_id
group by t.team_id, t.short_name order by finished_matches, t.short_name;

-- QC18 Freshness: the last successful sync
select max(finished_at) as last_success, now() - max(finished_at) as age
from sync_runs where status = 'success';
