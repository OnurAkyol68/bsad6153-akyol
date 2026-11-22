-- db/queries.sql: business questions answered with SQL (Week 2).
--
-- Each question comes from my baseline log (docs/baseline_log.md), column
-- "What I wished I knew". Season 2026 = the running season 2026/27.
--
-- Requirements covered:
--   JOINs:          Q1, Q2, Q3, Q4, Q5
--   GROUP BY:       Q1, Q2, Q6
--   filter by time: Q1, Q2 (last 30 days)
--   surprise:       Q5


-- Question 1 (log: "How good the players' current form is"):
-- Which players scored the most goals in the last 30 days?
-- Own goals don't count for the scorer, and goals without a known scorer are left out.
select p.short_name                 as player,
       t.short_name                 as team,
       count(*)                     as goals,
       count(*) filter (where g.is_penalty) as penalties
from goals g
join players p on p.player_id = g.player_id
join matches m on m.match_id = g.match_id
join teams   t on t.team_id   = g.scoring_team_id
where m.kickoff_at >= now() - interval '30 days'
  and not g.is_own_goal
group by p.short_name, t.short_name
order by goals desc, player
limit 15;


-- Question 2 (log: "How good the players' current form is", at team level):
-- Which teams are in the best form? Points and goals from their matches in the last 30 days.
with team_results as (
    select home_team_id as team_id, home_goals as scored, away_goals as conceded, kickoff_at
    from matches where is_finished
    union all
    select away_team_id, away_goals, home_goals, kickoff_at
    from matches where is_finished
)
select t.short_name                                   as team,
       count(*)                                       as played,
       sum(case when r.scored > r.conceded then 3
                when r.scored = r.conceded then 1
                else 0 end)                           as points,
       sum(r.scored)                                  as goals_for,
       sum(r.conceded)                                as goals_against
from team_results r
join teams t on t.team_id = r.team_id
where r.kickoff_at >= now() - interval '30 days'
group by t.short_name
order by points desc, sum(r.scored) - sum(r.conceded) desc;


-- Question 3 (log: "How strong the opponent is"):
-- For the next matchday (the first one in the running season that is not finished yet):
-- where do both teams stand in the current table?
select m.matchday,
       m.kickoff_at at time zone 'Europe/Berlin' as kickoff_german_time,
       home.short_name  as home_team,
       hs.position      as home_position,
       hs.points        as home_points,
       away.short_name  as away_team,
       aws.position     as away_position,
       aws.points       as away_points,
       aws.position - hs.position as position_gap   -- positive = home team is higher in the table
from matches m
join teams home     on home.team_id = m.home_team_id
join teams away     on away.team_id = m.away_team_id
join standings hs   on hs.team_id  = m.home_team_id and hs.season  = m.season
join standings aws  on aws.team_id = m.away_team_id and aws.season = m.season
where m.season = 2026
  and m.matchday = (select min(matchday) from matches where season = 2026 and not is_finished)
order by m.kickoff_at;


-- Question 4 (log: transfers "buy Upamecano, buy Burkardt, sell Nmecha" and lineup
-- changes with Caci, Mwene, Khedira, Poreba): did these players score this season, and when?
select p.short_name                         as player,
       m.matchday,
       home.short_name || ' - ' || away.short_name as match,
       g.minute,
       g.is_penalty
from goals g
join players p   on p.player_id = g.player_id
join matches m   on m.match_id  = g.match_id
join teams home  on home.team_id = m.home_team_id
join teams away  on away.team_id = m.away_team_id
where m.season = 2026
  and not g.is_own_goal
  and (p.short_name ilike '%Upamecano%' or p.short_name ilike '%Burkardt%'
       or p.short_name ilike '%Nmecha%' or p.short_name ilike '%Caci%'
       or p.short_name ilike '%Mwene%'  or p.short_name ilike '%Khedira%'
       or p.short_name ilike '%Poreba%')
order by p.short_name, m.matchday;


-- Question 5 (surprise, log: "How strong the opponent is"):
-- Which teams are at the bottom of the current table, and how far behind the leader are they?
-- Why it surprised me: Gladbach is last, although in recent years they were always
-- consistently in the top 10 of the Bundesliga.
select s.position,
       t.short_name                          as team,
       s.matches_played,
       s.won, s.draw, s.lost,
       s.goals_for || ':' || s.goals_against as goals,
       s.points,
       lead.points - s.points                as points_behind_leader
from standings s
join teams t        on t.team_id = s.team_id
join standings lead on lead.season = s.season and lead.position = 1
where s.season = 2026
order by s.position desc
limit 6;


-- Question 6 (log: "How good the players' current form is"):
-- In which part of the match are most goals scored? Goals per 15-minute block, both seasons.
-- Result: most goals fall in minutes 76-90. Not a surprise for me: players get tired at the end.
select case
         when minute is null then 'unknown'
         when minute <= 15 then '01-15'
         when minute <= 30 then '16-30'
         when minute <= 45 then '31-45'
         when minute <= 60 then '46-60'
         when minute <= 75 then '61-75'
         when minute <= 90 then '76-90'
         else '90+'
       end                                              as minute_block,
       count(*)                                         as goals,
       round(100.0 * count(*) / sum(count(*)) over (), 1) as percent_of_all_goals
from goals
group by minute_block
order by minute_block;
