"""Build a final weekly report from this run's private Sleeper/nflverse inputs.

Requires pandas, pyarrow, matplotlib, numpy and scipy. Raw inputs stay private.
Run: python scripts/report_week.py --private-dir /tmp/current-run --week 10
Expected files: league/users/players/rosters/match-W/stats-W/proj-W.json,
preceding stats and matchups, playerids.csv and pbp-2026.parquet.
"""
import argparse, collections, datetime, html, json, math, statistics, textwrap
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from scipy.special import ndtr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from refresh_forecast import DEF_COUNTERS

R=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private-dir',required=True,type=Path);p.add_argument('--week',required=True,type=int);a=p.parse_args();w=a.week
    assert not a.private_dir.resolve().is_relative_to(R)
    def read(key):return json.loads((a.private_dir/(key+'.json')).read_text())
    league=read('league');assert w<=league['settings']['last_scored_leg']
    players=read('players');aliases=json.loads((R/'data/gotw.json').read_text())['aliases']
    users={u['user_id']:aliases.get(u['display_name'],u['display_name']) for u in read('users')}
    names={r['roster_id']:users[r['owner_id']] for r in read('rosters')}
    scoring=league['scoring_settings'];uncertainty=json.loads((R/'data/model-uncertainty.json').read_text())
    matches=read(f'match-{w}');prior={m['roster_id']:m for m in read(f'match-{w-1}')}
    for m in matches:
        assert abs(sum(m['starters_points'])-m['points'])<.011,'Effective lineup score mismatch'
        assert len(m['starters'])==len(set(m['starters'])), 'Duplicate effective starter'
    stats={s['player_id']:s for s in read(f'stats-{w}')}
    history=collections.defaultdict(list)
    for week in range(1,w):
        for row in read(f'stats-{week}'):
            if players.get(row['player_id'],{}).get('position')=='DEF' and row['stats'].get('gp',0)>0:history[row['player_id']].append(row['stats'])
    nfl=[s for h in history.values() for s in h]
    def score(row):
        s=dict(row['stats']);sid=row['player_id']
        if players.get(sid,{}).get('position')=='DEF':
            for k in DEF_COUNTERS:
                if k not in s:s[k]=(sum(x.get(k,0) for x in history[sid])+5*statistics.mean(x.get(k,0) for x in nfl))/(len(history[sid])+5)
        return sum(scoring.get(k,0)*v for k,v in s.items())
    projected={s['player_id']:score(s) for s in read(f'proj-{w}') if s['stats'].get('gp',0)>0}
    cross=pd.read_csv(a.private_dir/'playerids.csv',dtype=str).fillna('')
    ids={s:g for s,g in zip(cross.sleeper_id,cross.gsis_id) if s and g}
    reverse={g:s for s,g in ids.items()}
    pbp=pd.read_parquet(a.private_dir/'pbp-2026.parquet');pbp=pbp[pbp.week==w].copy()
    assert len(pbp)>1000,'Incomplete weekly play-by-play'
    alias_nfl=lambda s:{'LA':'LAR','WSH':'WAS'}.get(s,s)
    games={};nfl_games={}
    for gid,g in pbp.groupby('game_id',sort=False):
        assert any(g['desc']=='END GAME'),f'Incomplete game: {gid}'
        times=pd.to_datetime(g.time_of_day,utc=True,errors='coerce').ffill().bfill()
        assert times.notna().all()
        start=times.min().timestamp();end=times.max().timestamp()+1
        games[gid]=(start,end)
        for team in (g.iloc[0].home_team,g.iloc[0].away_team):nfl_games[alias_nfl(team)]=gid
        pbp.loc[g.index,'event_timestamp']=[t.timestamp() for t in times]
    selected={sid for m in matches for sid in m['starters'] if sid!='0'}
    player_game={}
    for sid in selected:
        team=stats.get(sid,{}).get('team') or players.get(sid,{}).get('team')
        if team in nfl_games:player_game[sid]=nfl_games[team]
        elif any(abs(m['players_points'].get(sid,0))>.001 for m in matches):raise AssertionError(f'No NFL game for scoring starter {sid}')
        assert players[sid]['position']=='DEF' or sid in ids or sid not in player_game,f'Missing player crosswalk: {sid}'
    # Score directly attributable offensive/kicking plays. Defense and any
    # residual categories are settled at game end, not assigned to invented plays.
    events=[];totals=collections.defaultdict(float)
    for row in pbp.fillna(0).to_dict('records'):
        delta=collections.defaultdict(float)
        def add(gsis,key,value):
            sid=reverse.get(gsis)
            if sid in selected:delta[sid]+=scoring.get(key,0)*float(value or 0)
        if row['play_type']=='no_play':continue
        two=row['two_point_attempt']==1
        if two:
            if row['two_point_conv_result']=='success':
                if row['pass_attempt']:
                    add(row['passer_player_id'],'pass_2pt',1);add(row['receiver_player_id'],'rec_2pt',1)
                else:add(row['rusher_player_id'],'rush_2pt',1)
        else:
            add(row['passer_player_id'],'pass_yd',row['passing_yards'])
            add(row['passer_player_id'],'pass_td',row['pass_touchdown'])
            add(row['passer_player_id'],'pass_int',row['interception'])
            add(row['receiver_player_id'],'rec',row['complete_pass'])
            add(row['receiver_player_id'],'rec_yd',row['receiving_yards'])
            add(row['receiver_player_id'],'rec_td',row['pass_touchdown'])
            add(row['rusher_player_id'],'rush_yd',row['rushing_yards'])
            add(row['rusher_player_id'],'rush_td',row['rush_touchdown'])
        if row['fumble_lost']:
            for i in (1,2):
                if row[f'fumbled_{i}_team'] and row[f'fumble_recovery_1_team']!=row[f'fumbled_{i}_team']:add(row[f'fumbled_{i}_player_id'],'fum_lost',1)
        if row['extra_point_attempt']:add(row['kicker_player_id'],'xpm' if row['extra_point_result']=='good' else 'xpmiss',1)
        if row['field_goal_attempt']:
            if row['field_goal_result']=='made':
                distance=row['kick_distance'];band='0_19' if distance<20 else '20_29' if distance<30 else '30_39' if distance<40 else '40_49' if distance<50 else '50_59' if distance<60 else '60p'
                add(row['kicker_player_id'],'fgm_'+band,1);add(row['kicker_player_id'],'fgm',1)
            else:add(row['kicker_player_id'],'fgmiss',1)
        delta={s:v for s,v in delta.items() if abs(v)>.00001}
        for s,v in delta.items():totals[s]+=v
        events.append(dict(time=row['event_timestamp'],game=row['game_id'],remaining=max(0,min(1,row['game_seconds_remaining']/3600)),delta=delta,desc=str(row['desc']),adjustment=False))
    residuals=[]
    for m in matches:
        for sid,actual in zip(m['starters'],m['starters_points']):
            if sid not in player_game:continue
            residual=actual-totals[sid]
            assert players[sid]['position']=='DEF' or abs(residual)<.011, f'Unreconciled offensive/kicking plays for {sid}: {residual}'
            if abs(residual)>.011:
                residuals.append((sid,residual))
                events.append(dict(time=games[player_game[sid]][1],game=player_game[sid],remaining=0,delta={sid:residual},desc='Unlocalized categories at game end',adjustment=True))
            totals[sid]+=residual
            assert abs(totals[sid]-actual)<.011
    # Explicit game-end events release all remaining forecast variance.
    for gid,(_,end) in games.items():events.append(dict(time=end+.01,game=gid,remaining=0,delta={},desc='NFL game final',adjustment=True))
    events.sort(key=lambda e:e['time'])
    windows=[]
    for start,end in sorted(games.values()):
        if windows and start<=windows[-1][1]:windows[-1]=(windows[-1][0],max(end,windows[-1][1]))
        else:windows.append((start,end))
    def compress(t):
        x=0
        for i,(start,end) in enumerate(windows):
            if t<start:return x
            if t<=end:return x+(t-start)/3600
            x+=(end-start)/3600
            if i<len(windows)-1:x+=.35
        return x
    groups=collections.defaultdict(list)
    for m in matches:groups[m['matchup_id']].append(m)
    summaries=[];contexts=[];fig,axes=plt.subplots(4,1,figsize=(15,19))
    for ax,(mid,pair) in zip(axes,sorted(groups.items())):
        assert len(pair)==2
        aa,bb=pair;sets=[set(t['starters']) for t in pair];actual=[0.,0.];remaining={g:1. for g in games};timeline=[];pivots=[]
        def probability():
            mean=list(actual);var=0.
            for j,team in enumerate(pair):
                for sid in team['starters']:
                    if sid not in player_game:continue
                    f=remaining[player_game[sid]];baseline=projected.get(sid,0)
                    mean[j]+=f*baseline
                    pos=players[sid]['position'];var+=uncertainty[pos]['scaled_rmse']**2*max(baseline,3)*f
            diff=mean[0]-mean[1]
            return float(ndtr(diff/math.sqrt(var))) if var>1e-9 else float((diff>0)+.5*(diff==0))
        timeline.append((compress(min(s for s,e in games.values())),probability()))
        for event in events:
            remaining[event['game']]=event['remaining']
            changes=[sum(v for sid,v in event['delta'].items() if sid in ss) for ss in sets]
            before=probability()
            actual=[v+c for v,c in zip(actual,changes)];after=probability()
            timeline.append((compress(event['time']),after))
            if any(abs(v)>.00001 for v in changes) and not event['adjustment']:
                pivots.append(dict(effect=100*(after-before),probability=after,x=compress(event['time']),time=event['time'],desc=event['desc'],changes=changes))
        for j,team in enumerate(pair):assert abs(actual[j]-team['points'])<.011,(names[team['roster_id']],actual[j],team['points'])
        winner=max(pair,key=lambda x:x['points']);loser=min(pair,key=lambda x:x['points'])
        summary=dict(matchup_id=mid,teams=[dict(roster_id=t['roster_id'],name=names[t['roster_id']],points=t['points']) for t in pair],winner=names[winner['roster_id']],winner_id=winner['roster_id'],margin=round(winner['points']-loser['points'],2));summaries.append(summary)
        x,y=zip(*timeline);ax.plot(x,100*np.array(y),color='#167d8d',lw=1.6);ax.set_ylim(-3,103);ax.set_yticks([0,25,50,75,100]);ax.grid(alpha=.15)
        ax.set_title(f"{names[aa['roster_id']]} {aa['points']:.2f} — {names[bb['roster_id']]} {bb['points']:.2f}",loc='left',fontweight='bold',fontsize=13)
        ax.set_ylabel(f"{names[aa['roster_id']]} win chance (%)")
        xgap=0
        for start,end in windows[:-1]:
            xgap+=(end-start)/3600;ax.axvspan(xgap,xgap+.35,color='#dddddd',hatch='///',alpha=.45);xgap+=.35
        ticks=[];labels=[]
        for start,end in windows:
            ticks.extend([compress(start),compress(end)]);labels.extend([datetime.datetime.fromtimestamp(start,ZoneInfo('America/Los_Angeles')).strftime('%a %I:%M %p'),datetime.datetime.fromtimestamp(end,ZoneInfo('America/Los_Angeles')).strftime('%I:%M %p')])
        ax.set_xticks(ticks,labels,fontsize=8,rotation=18);ax.set_xlabel('Pacific time · hatched no-game gaps compressed')
        top=sorted(pivots,key=lambda p:abs(p['effect']),reverse=True)[:3]
        for i,pivot in enumerate(top):
            desc=pivot['desc'];short=textwrap.fill(desc if len(desc)<=125 else desc[:122]+'…',width=46)
            label=f"{pivot['effect']:+.1f} pp · {datetime.datetime.fromtimestamp(pivot['time'],ZoneInfo('America/Los_Angeles')).strftime('%a %I:%M %p')} PT\n{short}"
            ax.annotate(label,xy=(pivot['x'],100*pivot['probability']),xytext=(.03+i*.32,.20+(i%2)*.50),textcoords='axes fraction',fontsize=7,wrap=True,bbox=dict(boxstyle='round,pad=.4',fc='white',ec='#bccbd0',alpha=.95),arrowprops=dict(arrowstyle='-',color='#667b82'))
        contexts.append((summary,top))
    fig.suptitle(f'Week {w} · experimental matchup probabilities',fontsize=20,fontweight='bold')
    fig.text(.01,.001,'Sources: Sleeper; nflverse/nflfastR (CC BY 4.0); DynastyProcess. Scoring-only play effects; not archived live odds.\nUnlocalized scoring categories settle at NFL game end and are excluded from play labels. Effective lineups fixed retrospectively.',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.97))
    fig.savefig(R/f'docs/assets/week-{w:02}.png',dpi=150,bbox_inches='tight');plt.close(fig)
    e=html.escape;mean=statistics.mean(m['points'] for m in matches);prevmean=statistics.mean(m['points'] for m in prior.values())
    prose=f'<p>Average scoring reached <strong>{mean:.2f}</strong>, a change of {mean-prevmean:+.2f} ({(mean/prevmean-1)*100:+.1f}%) from Week {w-1}. The median was {statistics.median(m["points"] for m in matches):.2f}.</p>'
    prose+='<h2>Week-over-week scoring</h2><div class="table"><table><thead><tr><th>Team</th><th>Previous week</th><th>This week</th><th>Change</th><th>Scoring rank</th></tr></thead><tbody>'
    ranked=sorted(matches,key=lambda m:m['points'],reverse=True)
    for rank,m in enumerate(ranked,1):
        old=prior[m['roster_id']]['points'];prose+=f'<tr><td>{e(names[m["roster_id"]])}</td><td>{old:.2f}</td><td>{m["points"]:.2f}</td><td>{m["points"]-old:+.2f}</td><td>{rank}</td></tr>'
    prose+='</tbody></table></div><h2>Trends through Week '+str(w)+'</h2><ul>'
    allweeks={week:{r['roster_id']:r['points'] for r in read(f'match-{week}')} for week in range(1,w+1)}
    for m in ranked:
        rid=m['roster_id'];values=[allweeks[k][rid] for k in range(1,w+1)];last3=statistics.mean(values[-3:]);allplay=sum(sum(v>other for oid,other in allweeks[k].items() if oid!=rid) for k,v in enumerate(values,1))
        high=' A new season high.' if values[-1]>max(values[:-1]) else ''
        prose+=f'<li><strong>{e(names[rid])}:</strong> {values[-1]-values[-2]:+.2f} points from last week; three-week average {last3:.2f}, season average {statistics.mean(values):.2f}. All-play wins: {allplay} of {7*w}.{high}</li>'
    prose+='</ul><h2>Highest-scoring starters</h2><div class="table"><table><thead><tr><th>Player</th><th>Fantasy team</th><th>Points</th></tr></thead><tbody>'
    leaders=sorted([(points,sid,names[m['roster_id']]) for m in matches for sid,points in zip(m['starters'],m['starters_points'])],reverse=True)[:8]
    for points,sid,team in leaders:prose+=f'<tr><td>{e(players[sid].get("full_name") or sid)}</td><td>{e(team)}</td><td>{points:.2f}</td></tr>'
    prose+='</tbody></table></div><h2>Matchup context and pivotal plays</h2>'
    for summary,top in contexts:
        prose+=f'<p><strong>{e(summary["winner"])} wins by {summary["margin"]:.2f}.</strong> '
        if top:
            pivot=top[0];prose+=f'The largest modeled scoring-only play effect changed {e(summary["teams"][0]["name"])}’s win chance by {pivot["effect"]:+.1f} percentage points: {e(pivot["desc"])}'
        prose+='</p>'
    prose+='<p class="note">Charts use current historical-week projections, not verified pre-kickoff archives. Defense scoring is settled at NFL game end; other categories not localized to individual plays are also settled at game end; these adjustments are excluded from pivotal-play labels. The charts do not reconstruct injury exits or changing usage.</p>'
    sources=['league','users','players','rosters',f'match-{w}',f'stats-{w}',f'proj-{w}'];asof=min(datetime.datetime.fromtimestamp((a.private_dir/(s+'.json')).stat().st_mtime,datetime.timezone.utc) for s in sources).isoformat()
    prose+=f'<p class="small">Source snapshot: {e(asof)}. Final scores remain subject to official stat corrections.</p>'
    (R/f'content/week-{w:02}.html').write_text(prose)
    (R/f'data/week-{w:02}.json').write_text(json.dumps(dict(week=w,season=2026,as_of=asof,matchups=summaries),indent=2))
    print('Report ready:',w,'games',len(games),'events',len(events),'unlocalized adjustments',[(players[s].get('full_name') or s,round(v,2)) for s,v in residuals])

if __name__=='__main__':main()
