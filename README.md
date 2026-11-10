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
- Update the homepage's manually curated headline metrics when adding a new week; these intentionally remain editorially reviewed rather than inferred from every summary field.

All links are relative so the site works under a GitHub project-site path. The homepage is `docs/index.html`. Large raw analysis bundles are deliberately excluded from the public repository.

## Local preview

Run `python3 -m http.server --directory docs 8000` and open http://localhost:8000. No external requests are needed to render the site.

## Data and model notes

Scores are reconciled effective-lineup results and remain subject to NFL stat corrections. Probability charts are experimental, not archived live Sleeper probabilities. Details and caveats are in `docs/methodology.html`.

Attribution: Sleeper league data and projections; nflverse/nflfastR play-by-play (CC BY 4.0); DynastyProcess/ffverse player-ID crosswalk. Keep attribution on republished charts and reports. This repository contains public report summaries and charts, not full NFL datasets or private credentials.
