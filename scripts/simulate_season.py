"""Optimize rostered lineups and simulate the remaining 2026 season.

Run manually with numpy and scipy installed; publishing consumes frozen JSON.
"""
from pathlib import Path
import json, math, argparse
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True, type=Path, help='Private frozen forecast input file; do not publish this file')
D = json.loads(parser.parse_args().input.read_text())
TEAMS = sorted(D['teams'], key=lambda t: t['id'])
N = 100_000
SEED = 202610
assert len(TEAMS) == 8 and D['settings']['playoff_teams'] == 6
assert D['settings']['playoff_week_start'] == 15
assert D['settings']['playoff_round_type'] == 0

def lineup(team, week):
    slots = D['slots']
    # A future recovery/activation is allowed when a weekly forecast exists.
    # Week 10 uses today's Out/IR designations and current reserve restrictions.
    candidates = []
    for sid in team['players']:
        p = D['players'][sid]
        if week == 10 and (sid in team['reserve'] or p['injury'] in ('Out', 'IR', 'PUP', 'Suspended')):
            continue
        if sid not in D['projections'][str(week)]:
            continue
        candidates.append(sid)
    candidates += [None] * len(slots)
    costs = np.full((len(slots), len(candidates)), 1e8)
    for i, slot in enumerate(slots):
        allowed = {'RB', 'WR', 'TE'} if slot == 'FLEX' else {slot}
        for j, sid in enumerate(candidates):
            if sid is None:
                costs[i,j] = 0
            elif allowed.intersection(D['players'][sid]['positions']):
                costs[i,j] = -D['projections'][str(week)][sid]
    rows, cols = linear_sum_assignment(costs)
    chosen = []
    for i,j in zip(rows,cols):
        sid = candidates[j]
        p = D['players'].get(sid, {})
        mean = D['projections'][str(week)].get(sid, 0)
        position = next((x for x in p.get('positions',[]) if x in D['uncertainty']), None)
        variance = D['uncertainty'][position]['scaled_rmse']**2 * max(mean,3) if sid else 0
        chosen.append({'slot':slots[i], 'id':sid, 'name':p.get('name','Open slot'), 'points':mean, 'variance':variance})
    assert len({p['id'] for p in chosen if p['id']}) == sum(p['id'] is not None for p in chosen)
    return {'points':sum(p['points'] for p in chosen), 'variance':sum(p['variance'] for p in chosen), 'players':chosen}

lineups = {w:[lineup(t,w) for t in TEAMS] for w in range(10,18)}
means = np.array([[x['points'] for x in lineups[w]] for w in range(10,18)])
sds = np.sqrt([[x['variance'] for x in lineups[w]] for w in range(10,18)])
index = {t['id']:i for i,t in enumerate(TEAMS)}
rng = np.random.default_rng(SEED)
draws = rng.normal(means, sds, size=(N,8,8)).round(2)
wins = np.tile([t['wins'] + .5*t['ties'] for t in TEAMS], (N,1))
pf = np.tile([t['pf'] for t in TEAMS], (N,1))
pa = np.tile([t['pa'] for t in TEAMS], (N,1))
for week in range(10,15):
    s = draws[:,week-10,:]
    pf += s
    for aid,bid in D['schedule'][str(week)]:
        a,b = index[aid],index[bid]
        wins[:,a] += (s[:,a]>s[:,b]) + .5*(s[:,a]==s[:,b])
        wins[:,b] += (s[:,b]>s[:,a]) + .5*(s[:,a]==s[:,b])
        pa[:,a] += s[:,b]; pa[:,b] += s[:,a]
# Descending record, PF, PA; random final tiebreak only after all three tie.
order = np.lexsort((rng.random((N,8)), -pa, -pf, -wins), axis=1)
sim = np.arange(N)
def advance(a,b,week):
    a_score,b_score = draws[sim,week-10,a],draws[sim,week-10,b]
    # Lower playoff seed wins an exact score tie.
    seed_a = (order == a[:,None]).argmax(axis=1)
    seed_b = (order == b[:,None]).argmax(axis=1)
    return np.where((a_score>b_score)|((a_score==b_score)&(seed_a<seed_b)), a,b)
q45 = advance(order[:,3],order[:,4],15)
q36 = advance(order[:,2],order[:,5],15)
s1 = advance(order[:,0],q45,16)
s2 = advance(order[:,1],q36,16)
champion = advance(s1,s2,17)
playoffs = np.bincount(order[:,:6].ravel(),minlength=8)/N
byes = np.bincount(order[:,:2].ravel(),minlength=8)/N
titles = np.bincount(champion,minlength=8)/N
assert abs(playoffs.sum()-6)<1e-10 and abs(byes.sum()-2)<1e-10 and abs(titles.sum()-1)<1e-10
current = sorted(TEAMS,key=lambda t:(t['wins']+.5*t['ties'],t['pf'],t['pa']),reverse=True)
table=[]
for rank,t in enumerate(current,1):
    i=index[t['id']]
    table.append({k:t[k] for k in ('id','name','wins','losses','ties','pf','pa')} | {'rank':rank,'projected':means[0,i],'playoffs':playoffs[i],'bye':byes[i],'champion':titles[i],'expected_wins':float(wins[:,i].mean())})
matchups=[]
for a,b in D['schedule']['10']:
    i,j=index[a],index[b]
    p=float(ndtr((means[0,i]-means[0,j])/math.sqrt(sds[0,i]**2+sds[0,j]**2)))
    matchups.append({'teams':[{'id':a,'name':TEAMS[i]['name'],'probability':p,**lineups[10][i]}, {'id':b,'name':TEAMS[j]['name'],'probability':1-p,**lineups[10][j]}]})
public_matchups = [{'teams':[{'name':t['name'],'points':t['points'],'probability':t['probability'],'players':[{'slot':p['slot'],'name':p['name'],'points':p['points']} for p in t['players']]} for t in m['teams']]} for m in matchups]
public_standings = [{k:v for k,v in t.items() if k not in ('pa','expected_wins','id')} for t in table]
out={'as_of':D['as_of'],'completed_week':9,'next_week':10,'simulations':N,'seed':SEED,'standings':public_standings,'matchups':public_matchups}
(ROOT/'data/dashboard.json').write_text(json.dumps(out,indent=2))
for t in table: print(t['name'],f"W10 {t['projected']:.1f} | playoffs {t['playoffs']:.1%} | bye {t['bye']:.1%} | champion {t['champion']:.1%}")
for m in matchups:
    for t in m['teams']: print(t['name'],f"{t['probability']:.1%}", 'open slots:',sum(p['id'] is None for p in t['players']))
