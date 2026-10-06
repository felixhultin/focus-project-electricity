# Korp word frequencies

Static GitHub Pages gallery of absolute and relative Korp frequencies for the 25 words in `data/mats`. Each plot bar opens the matching word, resource, and decade in the workbook example browser. Open `docs/index.html` locally or the repository's Pages URL after deployment.

The site contains interactive SVG plots, summary CSVs, a bin-by-bin comparison of API hits and workbook rows, a breakdown by author and newspaper (including author-by-decade counts and rates), provenance, Python scripts, and a paginated browser of all 1,736,639 workbook examples. The 1,354,322 examples from `lb` and `kubhist2` link to external source pages. The 382,317 `tkr` examples have no external URL and remain visible as plain text. Korp API counts can differ from workbook counts, so the browser shows both. Raw workbooks, API caches, and local filesystem paths are excluded.

To rebuild `docs/` from the workspace root after running `korp_mats_frequencies.py`:

```bash
python korp_mats_frequencies.py
python build_korp_pages.py
```

The first source-breakdown build retrieves Korp author statistics and newspaper titles. Later builds use the compressed API cache in `plots/korp_mats_frequencies/api_cache`.

For local preview of the example and source-breakdown pages, serve `docs/` over HTTP (for example, `python3 -m http.server --directory korp-frequency-pages/docs 8000`) and open `http://localhost:8000/`. Both pages load data on demand.

GitHub Pages should use **GitHub Actions** as its publishing source. Pushing this repository's `main` branch runs `.github/workflows/pages.yml` and deploys `docs/`.
