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
FIRST = D['completed_week'] + 1
WEEKS = list(range(FIRST, 18))
assert 1 <= FIRST <= 15, "Completed playoff rounds require bracket reconciliation before refresh"
assert len(TEAMS) == 8 and D['settings']['playoff_teams'] == 6
assert D['settings']['playoff_week_start'] == 15
assert D['settings']['playoff_round_type'] == 0

def lineup(team, week):
    slots = D['slots']
    replacements = D['replacements'][str(week)]
    def replacement(slot):
        eligible = ('RB','WR','TE') if slot == 'FLEX' else (slot,)
        pos = max(eligible, key=lambda p: replacements[p]['points'])
        return pos, replacements[pos]['points']
    # A future recovery/activation is allowed when a weekly forecast exists.
    # The upcoming week uses today's Out/IR designations and current reserve restrictions.
    locked = team.get('locked', {}) if week == FIRST else {}
    locked_ids = {p['id'] for p in locked.values()}
    candidates = []
    for sid in team['players']:
        p = D['players'][sid]
        if week == FIRST and (sid in D.get('unavailable', []) or sid in locked_ids):
            continue
        if week == FIRST and (sid in team['reserve'] or p['injury'] in ('Out', 'IR', 'PUP', 'Suspended')):
            continue
        if D['projections'][str(week)].get(sid, 0) <= 0:
            continue
        candidates.append(sid)
    candidates += sorted(locked_ids)
    candidates += [None] * len(slots)
    costs = np.full((len(slots), len(candidates)), 1e8)
    for i, slot in enumerate(slots):
        allowed = {'RB', 'WR', 'TE'} if slot == 'FLEX' else {slot}
        for j, sid in enumerate(candidates):
            if str(i) in locked:
                if sid == locked[str(i)]['id']:
                    costs[i,j] = -locked[str(i)]['points']
                continue
            if sid in locked_ids:
                continue
            if sid is None:
                # First maximize filled roster slots, then total projection
                # including replacement points for unavoidable vacancies.
                costs[i,j] = 10_000 - replacement(slot)[1]
            elif allowed.intersection(D['players'][sid]['positions']):
                costs[i,j] = -D['projections'][str(week)][sid]
    rows, cols = linear_sum_assignment(costs)
    chosen = []
    for i,j in zip(rows,cols):
        sid = candidates[j]
        assert costs[i,j] < 1e8, 'No legal assignment'
        p = D['players'].get(sid, {})
        if sid:
            allowed = {'RB','WR','TE'} if slots[i] == 'FLEX' else {slots[i]}
            assert allowed.intersection(p['positions'])
        if sid:
            mean = locked[str(i)]['points'] if str(i) in locked else D['projections'][str(week)][sid]
            position = next(x for x in p['positions'] if x in D['uncertainty'])
            name = p['name']
        else:
            position, mean = replacement(slots[i])
            name = f'Replacement {position}'
        actual = str(i) in locked
        if actual:
            mean = locked[str(i)]['points']
        variance = D['uncertainty'][position]['scaled_rmse']**2 * max(mean,3)
        if actual:
            variance = 0.0
        chosen.append({'actual':actual, 'slot':slots[i], 'id':sid, 'name':name, 'points':mean, 'variance':variance, 'replacement':sid is None})
    assert len({p['id'] for p in chosen if p['id']}) == sum(p['id'] is not None for p in chosen)
    return {'points':sum(p['points'] for p in chosen), 'variance':sum(p['variance'] for p in chosen), 'players':chosen}

lineups = {w:[lineup(t,w) for t in TEAMS] for w in WEEKS}
means = np.array([[x['points'] for x in lineups[w]] for w in WEEKS])
sds = np.sqrt([[x['variance'] for x in lineups[w]] for w in WEEKS])
index = {t['id']:i for i,t in enumerate(TEAMS)}
rng = np.random.default_rng(SEED)
draws = rng.normal(means, sds, size=(N,len(WEEKS),len(TEAMS))).round(2)
for week, scores in D.get('final_scores', {}).items():
    if int(week) in WEEKS:
        for rid, score in scores.items():
            draws[:,int(week)-FIRST,index[int(rid)]] = score
wins = np.tile([t['wins'] + .5*t['ties'] for t in TEAMS], (N,1))
pf = np.tile([t['pf'] for t in TEAMS], (N,1))
pa = np.tile([t['pa'] for t in TEAMS], (N,1))
for week in range(FIRST,15):
    s = draws[:,week-FIRST,:]
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
    a_score,b_score = draws[sim,week-FIRST,a],draws[sim,week-FIRST,b]
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
for a,b in D['schedule'][str(FIRST)]:
    i,j=index[a],index[b]
    variance = sds[0,i]**2+sds[0,j]**2
    p=float(ndtr((means[0,i]-means[0,j])/math.sqrt(variance))) if variance else float((means[0,i]>means[0,j])+.5*(means[0,i]==means[0,j]))
    matchups.append({'teams':[{'id':a,'name':TEAMS[i]['name'],'probability':p,**lineups[FIRST][i]}, {'id':b,'name':TEAMS[j]['name'],'probability':1-p,**lineups[FIRST][j]}]})
public_matchups = [{'teams':[{'name':t['name'],'points':t['points'],'probability':t['probability'],'players':[{'slot':p['slot'],'name':p['name'],'points':p['points'],'replacement':p['replacement'],'actual':p['actual']} for p in t['players']]} for t in m['teams']]} for m in matchups]
public_standings = [{k:v for k,v in t.items() if k not in ('pa','expected_wins','id')} for t in table]
out={'in_progress':D.get('in_progress',False),'as_of':D['as_of'],'completed_week':D['completed_week'],'next_week':FIRST,'simulations':N,'seed':SEED,'standings':public_standings,'matchups':public_matchups,'replacement_levels':{p:v['points'] for p,v in D['replacements'][str(FIRST)].items()}}
(ROOT/'data/dashboard.json').write_text(json.dumps(out,indent=2))
for t in table: print(t['name'],f"W{FIRST} {t['projected']:.1f} | playoffs {t['playoffs']:.1%} | bye {t['bye']:.1%} | champion {t['champion']:.1%}")
for m in matchups:
    for t in m['teams']: print(t['name'],f"{t['probability']:.1%}", 'replacements:',[(p['slot'],p['name'],p['points']) for p in t['players'] if p['replacement']])
