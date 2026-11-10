"""Display the commissioner's official Game of the Week schedule."""
from html import escape as E

def outcome(game):
    a,b = game['teams']
    if 'points' not in a or 'points' not in b:
        return None, None
    if a['points'] == b['points']:
        return None, None
    return (a,b) if a['points'] > b['points'] else (b,a)

def report_note(data, week):
    game = next((g for g in data['schedule'] if g['week']==week), None)
    if not game:
        return ''
    winner,loser = outcome(game)
    if not winner:
        return ''
    return f'<aside class="gotw-report-note"><span class="gotw-badge">WEEK {week} · GAME OF THE WEEK</span><p><strong>{E(winner["name"])} wins {winner["points"]:.2f}–{loser["points"]:.2f}.</strong> Weekly punishment: <strong>{E(loser["name"])}</strong>.</p></aside>'

def render(data, completed_week, next_week):
    completed = [g for g in data['schedule'] if g['week']<=completed_week and all('points' in t for t in g['teams'])]
    latest = max(completed, key=lambda g:g['week']) if completed else None
    result = ''
    if latest:
        winner,loser = outcome(latest)
        score_rows = ''.join(f'<div class="gotw-score"><strong>{E(t["name"])}</strong><b>{t["points"]:.2f}</b></div>' for t in latest['teams'])
        punishment = f'<span>Weekly punishment</span><strong>{E(loser["name"])}</strong>' if loser else '<span>Tied result</span><strong>Commissioner decision needed</strong>'
        margin = f'{E(winner["name"])} wins by {winner["points"]-loser["points"]:.2f} points.' if winner else 'Final score tied.'
        result = f'<article class="gotw-result"><p class="eyebrow">WEEK {latest["week"]} · FINAL</p>{score_rows}<p class="gotw-margin">{margin}</p><div class="punishment-recipient">{punishment}</div><a href="reports/2026/week-{latest["week"]:02}.html">Read the Week {latest["week"]} report →</a></article>'
    upcoming = ''
    for g in data['schedule']:
        if g['week']<=completed_week:
            continue
        a,b=g['teams']
        is_next = g['week']==next_week
        label = '<span class="next-tag">UP NEXT</span>' if is_next else ''
        cls = ' class="gotw-up-next"' if is_next else ''
        upcoming += f'<li{cls}><div><span class="schedule-week">WEEK {g["week"]}</span>{label}</div><strong>{E(a["name"])} <span>vs.</span> {E(b["name"])}</strong></li>'
    history_rows = ''
    for g in reversed(completed):
        if latest and g['week']==latest['week']:
            continue
        a,b=g['teams'];winner,loser=outcome(g)
        history_rows += f'<tr><td>{g["week"]}</td><td>{E(a["name"])} vs. {E(b["name"])}</td><td class="num">{a["points"]:.2f}–{b["points"]:.2f}</td><td>{E(loser["name"]) if loser else "Commissioner decision"}</td></tr>'
    history = f'<details class="gotw-history"><summary>Earlier Games of the Week</summary><div class="table"><table><caption>Completed GOTW results; punishment recipients are the losing teams</caption><thead><tr><th>Week</th><th>Matchup</th><th>Final score</th><th>Weekly punishment</th></tr></thead><tbody>{history_rows}</tbody></table></div></details>' if history_rows else ''
    return f'<section id="gotw" class="gotw-section" aria-labelledby="gotw-title"><div class="section-heading"><h2 id="gotw-title">Game of the Week</h2><span>The loser takes the weekly punishment</span></div><div class="gotw-grid">{result}<article class="gotw-schedule"><h3>Coming up</h3><ol>{upcoming}</ol></article></div>{history}</section>'
