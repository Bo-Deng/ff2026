# roblox & friends — Fantasy league newsletter

Static public archive of weekly statistical reports. Includes Week 9 of the 2026 season, annotated matchup graphs, and a shared methodology page. Week 9 includes the confirmed Zay Flowers-for-Garrett Wilson autosub.

## Publish with GitHub Pages

1. Use the public repository `Bo-Deng/ff2026`, with `main` as its default branch.
2. Commit the contents of this package at the repository root, including `.github/workflows/pages.yml`.
3. In **Settings → Pages → Build and deployment**, choose **GitHub Actions**.
4. Push to `main` or run **Publish newsletter** from the Actions tab.
5. The completed deployment provides the live Pages URL.

No paid services, API keys, JavaScript framework, or external build dependencies are required. A Python-only build produces `docs/`.

## Edit and add reports

- Edit prose in `content/week-XX.html`.
- Add the matching summary JSON to `data/week-XX.json`.
- Add the annotated chart to `docs/assets/week-XX.png`.
- Run `python3 scripts/build_site.py`.
- The homepage reads its standings, matchup projections and season odds from `data/dashboard.json`. Refresh the forecast snapshot separately from report prose.

All links are relative so the site works under a GitHub project-site path. The homepage is `docs/index.html`. Large raw analysis bundles are deliberately excluded from the public repository.

## Local preview

Run `python3 -m http.server --directory docs 8000` and open http://localhost:8000. No external requests are needed to render the site.

## Data and model notes

Scores are reconciled effective-lineup results and remain subject to NFL stat corrections. Probability charts are experimental, not archived live Sleeper probabilities. Details and caveats are in `docs/methodology.html`.

Attribution: Sleeper league data and projections; nflverse/nflfastR play-by-play (CC BY 4.0); DynastyProcess/ffverse player-ID crosswalk. Keep attribution on republished charts and reports. This repository contains public report summaries and charts, not full NFL datasets or private credentials.

## League dashboard

The homepage shows standings after Week 9, optimized Week 10 lineups and win odds, and playoff/bye/championship probabilities from 100,000 simulated seasons. Assumptions and snapshot time are visible on the page.

- The raw forecast input stays outside this public repository. It contains rosters, weekly projections, schedule and uncertainty parameters.
- `scripts/simulate_season.py --input /path/to/private-forecast-input.json` optimizes each team's lineup and regenerates the display-only `data/dashboard.json`. Running it locally requires NumPy and SciPy. It does not fetch data.
- `scripts/dashboard_view.py` renders the dashboard; the Pages build only needs the Python standard library.

Week 10 excludes current Out/IR players and reserve slots. Future weeks permit projected recovery and reserve activation. No waiver additions, new injuries or trades are modeled. Empty starting slots contribute zero. The six-team fixed bracket starts Week 15, with two byes and the championship in Week 17.

Updating the site does not automatically refresh source projections. Refresh frozen inputs before rerunning the season model. Scores are experimental model draws, not Sleeper's official odds.
