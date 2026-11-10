"""Render the frozen league forecast as an accessible, buildless dashboard."""
import html
from datetime import datetime

E = html.escape

def pct(p):
    return '>99.9%' if p >= .9995 else '<0.1%' if p < .0005 else f'{100*p:.1f}%'

def render(d):
    rows = ''
    for t in d['standings']:
        record = f"{t['wins']}–{t['losses']}" + (f"–{t['ties']}" if t['ties'] else '')
        odds = ''.join(f'<td class="odds"><b>{E(pct(t[k]))}</b><span class="mini-bar" aria-hidden="true"><i style="width:{100*t[k]:.2f}%"></i></span></td>' for k in ('playoffs','bye','champion'))
        rows += f'<tr class="seed-{t["rank"]}"><td class="rank">{t["rank"]:02}</td><th scope="row">{E(t["name"])}</th><td class="record">{record}</td><td class="num">{t["pf"]:,.2f}</td><td class="num projection">{t["projected"]:.1f}</td>{odds}</tr>'
    cards = ''
    for m in d['matchups']:
        a,b = m['teams']
        team_rows = ''.join(f'<div class="match-team"><strong>{E(t["name"])}</strong><span>{t["points"]:.1f}<small>projected pts</small></span><b>{pct(t["probability"])}<small>win chance</small></b></div>' for t in (a,b))
        selected = ''
        for t in (a,b):
            lineup_rows = ''.join(f'<tr><td>{E(p["slot"])}</td><th scope="row">{E(p["name"])}</th><td>{p["points"]:.1f}</td></tr>' for p in t['players'])
            selected += f'<div class="selected-team"><h4>{E(t["name"])}</h4><table><caption class="sr-only">Projected starting lineup</caption><thead><tr><th>Slot</th><th>Player</th><th>Pts</th></tr></thead><tbody>{lineup_rows}</tbody></table></div>'
        cards += f'<article class="match-card">{team_rows}<div class="match-bar" aria-label="{E(a["name"])} {pct(a["probability"])}; {E(b["name"])} {pct(b["probability"])}"><span style="width:{100*a["probability"]:.2f}%"></span></div><details class="lineup-detail"><summary>View projected lineups</summary><div class="selected-lineups">{selected}</div></details></article>'
    replacement_text = ' · '.join(f'{pos} {points:.1f}' for pos,points in d['replacement_levels'].items())
    timestamp = datetime.fromisoformat(d['as_of']).strftime('%b %d, %Y · %H:%M UTC')
    return f'''<header class="dashboard-head"><div><p class="eyebrow">AFTER WEEK 9 · 2026 SEASON</p><h1>League at a glance.</h1><p class="lead">The standings today. The outlook for what comes next.</p></div><a class="latest-report" href="reports/2026/week-09.html"><span class="eyebrow">LATEST REPORT</span><strong>Week 9 statistical review →</strong><span>Scoring trends &amp; pivotal plays</span></a></header>
<div class="season-strip"><span><b>5</b> regular-season weeks left</span><span><b>6</b> playoff spots</span><span><b>2</b> first-round byes</span><span>Championship <b>Week 17</b></span></div>
<section class="standings-section" aria-labelledby="standings-title"><div class="section-heading"><h2 id="standings-title">Standings &amp; season outlook</h2><span>100,000 simulated seasons</span></div><div class="standings-wrap"><table class="standings"><caption class="sr-only">Standings after Week 9, Week 10 projected points, and simulated season probabilities</caption><thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">W–L</th><th scope="col">Points for</th><th scope="col">W10 proj.</th><th scope="col">Playoffs</th><th scope="col">Bye</th><th scope="col">Champion</th></tr></thead><tbody>{rows}</tbody></table></div><p class="note">Top six qualify. Top two earn a bye. Standings break ties by points for, then points against.</p></section>
<section class="next-week" aria-labelledby="matchups-title"><div class="section-heading"><h2 id="matchups-title">Week 10 matchups</h2><span>Optimized lineups · replacements included</span></div><div class="match-grid">{cards}</div></section>
<details class="forecast-notes"><summary>How to read these forecasts</summary><div><p>Week 10 uses the highest projected total from each current roster, respecting all 12 starting slots. Players marked Out or IR and players on reserve are excluded; questionable players remain eligible. Unavoidable vacancies are filled with generic replacement players, estimated separately each week as the median projection of the top five unrostered players at the needed position. FLEX takes the best eligible replacement baseline. Rostered players are retained wherever they can fill a slot.</p><p><strong>Week 10 replacement points:</strong> {replacement_text}.</p><p>Replacement players carry position-level scoring uncertainty. These are hypothetical fill-ins, not roster moves; competitive waiver access is not modeled.</p><p>Season odds simulate Weeks 10–14 on the real schedule, then a six-team bracket in Weeks 15–17. Seeds 1–2 get byes; seed 1 faces the 4/5 winner, and seed 2 the 3/6 winner. Future weeks re-optimize each roster using that week’s projections, allowing projected returns and reserve activations. No future trades or new injuries are modeled.</p><p>Player score uncertainty uses position-level projection error from Weeks 1–8. Scores are independent across players and weeks; these are approximate model probabilities, not Sleeper odds. Small differences should not be treated as precise. Forecasts reflect this snapshot and do not refresh automatically.</p><p><a href="methodology.html#season-forecasts">Full forecast methodology &amp; sources →</a></p></div></details><p class="snapshot">Projection snapshot: {timestamp}</p>'''
