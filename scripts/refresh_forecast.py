"""Fetch private Sleeper inputs. Never put --private-dir inside the public repo.

Uses only the stdlib; simulate_season.py subsequently needs NumPy/SciPy.
Stops on incomplete source data instead of overwriting the last public forecast.
"""
import argparse, concurrent.futures, datetime, json, statistics, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
LEAGUE = '1392364226512699392'
BASE = 'https://api.sleeper.app'
POSITIONS = ('QB','RB','WR','TE','K','DEF')
# Mutually exclusive score bands stay zero when absent; only missing counters
# are estimated, avoiding duplicate defense touchdown or yardage-band scores.
DEF_COUNTERS = ('def_3_and_out','def_4_and_stop','def_pass_def','def_st_ff',
                'def_st_fum_rec','def_st_td','safe','def_2pt')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--use-cache', action='store_true', help='Use this run’s already fetched sources')
    args = parser.parse_args()
    private = args.private_dir.resolve()
    assert not private.is_relative_to(ROOT), 'Private inputs must be outside the public repository'
    private.mkdir(parents=True, exist_ok=True)
    times = {}
    def get(key, endpoint):
        path = private / f'{key}.json'
        if not args.use_cache or not path.exists():
            with urllib.request.urlopen(endpoint if endpoint.startswith('https://') else BASE+endpoint, timeout=60) as response:
                data = json.load(response)
            path.write_text(json.dumps(data))
        times[key] = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc).isoformat()
        return json.loads(path.read_text())
    league = get('league', f'/v1/league/{LEAGUE}')
    state = get('state', '/v1/state/nfl')
    assert league['season'] == state['season'] == '2026'
    completed = league['settings']['last_scored_leg']
    first = completed+1
    assert 1 <= first <= 17
    roster = get('rosters', f'/v1/league/{LEAGUE}/rosters')
    users = {u['user_id']:u['display_name'] for u in get('users',f'/v1/league/{LEAGUE}/users')}
    players = get('players','/v1/players/nfl')
    bracket = get('bracket',f'/v1/league/{LEAGUE}/winners_bracket')
    tasks = [(f'proj-{w}',f'/projections/nfl/2026/{w}?season_type=regular') for w in range(first,18)]
    tasks += [(f'stats-{w}',f'/stats/nfl/2026/{w}?season_type=regular') for w in range(1,first+1)]
    tasks += [(f'match-{w}',f'/v1/league/{LEAGUE}/matchups/{w}') for w in range(1,18)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        payload = dict(pool.map(lambda task:(task[0],get(*task)), tasks))
    assert all(v for k,v in payload.items() if k != f'stats-{first}'), 'Empty source payload'
    assert all(r['settings']['wins']+r['settings']['losses']+r['settings']['ties']==completed for r in roster)
    aliases = json.loads((ROOT/'data/gotw.json').read_text())['aliases']
    teams=[]
    for r in roster:
        s=r['settings']; name=users[r['owner_id']]
        teams.append(dict(id=r['roster_id'],name=aliases.get(name,name),players=sorted(set((r['players'] or [])+(r['reserve'] or []))),reserve=(r['reserve'] or [])+(r.get('taxi') or []),wins=s['wins'],losses=s['losses'],ties=s['ties'],pf=s['fpts']+s['fpts_decimal']/100,pa=s['fpts_against']+s['fpts_against_decimal']/100))
    # Confirm game completion independently; never infer finality from a nonzero score.
    dates = sorted({row['date'][:10].replace('-', '') for row in payload[f'proj-{first}'] if row.get('date') and row['stats'].get('gp',0)>0})
    assert dates
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        daily_boards = list(pool.map(lambda date: get('scoreboard-'+date, 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates='+date), dates))
    scoreboard = {'events':[event for board in daily_boards for event in board['events']]}
    expected_teams={row['team'] for row in payload[f'proj-{first}'] if row['stats'].get('gp',0)>0 and row.get('team')}
    scheduled_teams=set()
    finished = set()
    aliases_nfl = {'WSH':'WAS','LA':'LAR'}
    for event in scoreboard['events']:
        status = event['status']['type']
        assert status['state'] != 'in', 'An NFL game is still live; preserve previous forecast until final'
        for competitor in event['competitions'][0]['competitors']:
            abbr=competitor['team']['abbreviation']
            scheduled_teams.add(aliases_nfl.get(abbr,abbr))
        if status['completed']:
            for competitor in event['competitions'][0]['competitors']:
                abbr = competitor['team']['abbreviation']
                finished.add(aliases_nfl.get(abbr,abbr))
    assert expected_teams <= scheduled_teams, 'Incomplete NFL schedule status coverage'
    current = {row['roster_id']:row for row in payload[f'match-{first}']}
    slots = [p for p in league['roster_positions'] if p not in ('BN','IR')]
    for team in teams:
        row=current[team['id']]
        team['locked']={str(i):{'id':sid,'points':row['starters_points'][i]} for i,sid in enumerate(row['starters']) if players.get(sid,{}).get('team') in finished}
        assert abs(sum(x['points'] for x in team['locked'].values())-row['points'])<.011, 'Actual points do not reconcile with completed-game starters'
    unavailable = [sid for sid,p in players.items() if p.get('team') in finished]
    owned={sid for t in teams for sid in t['players']}
    metadata={sid:dict(name=p.get('full_name') or sid,positions=p.get('fantasy_positions') or [p.get('position')],injury=p.get('injury_status')) for sid,p in players.items()}
    # Five pseudo-games of NFL average stabilize short team histories. This
    # implements the documented shrinkage; actual league scoring is unchanged.
    history={sid:[] for sid,p in players.items() if p.get('position')=='DEF'}
    for w in range(1,completed+1):
        for row in payload[f'stats-{w}']:
            if row['player_id'] in history and row['stats'].get('gp',0)>0:
                history[row['player_id']].append(row['stats'])
    nfl=[s for rows in history.values() for s in rows]
    assert nfl
    scoring=league['scoring_settings']
    def points(row):
        s=dict(row['stats']); sid=row['player_id']
        if sid in history:
            for k in DEF_COUNTERS:
                if k not in s:
                    avg=statistics.mean(x.get(k,0) for x in nfl)
                    h=history[sid]
                    s[k]=(sum(x.get(k,0) for x in h)+5*avg)/(len(h)+5)
        return sum(scoring.get(k,0)*v for k,v in s.items())
    projections={};replacements={}
    for w in range(first,18):
        rows=payload[f'proj-{w}']
        values={row['player_id']:points(row) for row in rows if row['stats'].get('gp',0)>0}
        assert sum(sid in values for sid in owned)>20, f'Incomplete Week {w} projections'
        projections[str(w)]=values
        pool={p:[] for p in POSITIONS}
        for sid,value in values.items():
            if sid in owned or sid not in metadata or value<=0:continue
            p=metadata[sid]
            if w==first and (sid in unavailable or p['injury'] in ('Out','IR','PUP','Suspended')):continue
            for pos in set(p['positions']) & set(POSITIONS):pool[pos].append(value)
        assert all(len(v)>=5 for v in pool.values()), f'Insufficient Week {w} free agents'
        replacements[str(w)]={p:{'points':statistics.median(sorted(v,reverse=True)[:5])} for p,v in pool.items()}
    schedule={}
    for w in range(first,15):
        pairs={}
        for r in payload[f'match-{w}']:pairs.setdefault(r['matchup_id'],[]).append(r['roster_id'])
        assert len(pairs)==4 and all(len(v)==2 for v in pairs.values())
        schedule[str(w)]=[sorted(v) for k,v in sorted(pairs.items())]
    forecast=dict(as_of=min(times.values()),completed_week=completed,teams=teams,players=metadata,projections=projections,replacements=replacements,schedule=schedule,slots=[p for p in league['roster_positions'] if p not in ('BN','IR')],in_progress=bool(finished),unavailable=unavailable,settings=league['settings'],uncertainty=json.loads((ROOT/'data/model-uncertainty.json').read_text()),final_scores={})
    (private/'forecast-input.json').write_text(json.dumps(forecast))
    (private/'source-times.json').write_text(json.dumps(times,indent=2))
    # Reconcile only completed official GOTW scores; never promote live scores.
    gotw=json.loads((ROOT/'data/gotw.json').read_text())
    names={t['id']:t['name'] for t in teams}
    for fixture in gotw['schedule']:
        if fixture['week']>completed:continue
        official={names[r['roster_id']]:r for r in payload[f"match-{fixture['week']}"]}
        a,b=(official[t['name']] for t in fixture['teams'])
        assert a['matchup_id']==b['matchup_id'], 'Commissioner GOTW fixture differs from actual schedule'
        for t in fixture['teams']:t['points']=official[t['name']]['points']
    (private/'gotw-verified.json').write_text(json.dumps(gotw,indent=2))
    # Reports require their own effective-lineup and play-by-play reconciliation.
    for path in (ROOT/'data').glob('week-*.json'):
        report=json.loads(path.read_text()); official={r['roster_id']:r['points'] for r in payload[f"match-{report['week']}"]}
        for m in report['matchups']:
            for t in m['teams']:assert abs(t['points']-official[t['roster_id']])<.005, f'Report score correction needed: {path.name}'
    print(f'Ready: completed Week {completed}; upcoming Week {first}; private input {private / "forecast-input.json"}')

if __name__=='__main__':main()
