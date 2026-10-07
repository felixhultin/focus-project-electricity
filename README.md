# Korp word frequencies

One GitHub Pages deployment containing two independent Korp frequency sites:

- `docs/` is the electricity site for the 25 words in `data/mats`.
- `docs/mia/` is the Mia site for the 127 terms in `data/mia`.

Each site has its own plots, data downloads, methodology, example browser, and author/newspaper breakdown.

The site contains interactive SVG plots, summary CSVs, a bin-by-bin comparison of API hits and workbook rows, a breakdown by author and newspaper (including author-by-decade counts and rates), provenance, Python scripts, and a paginated browser of all 1,736,639 workbook examples. The 1,354,322 examples from `lb` and `kubhist2` link to external source pages. The 382,317 `tkr` examples have no external URL and remain visible as plain text. Korp API counts can differ from workbook counts, so the browser shows both. Raw workbooks, API caches, and local filesystem paths are excluded.

To rebuild `docs/` from the workspace root after running `korp_mats_frequencies.py`:

```bash
python korp_mats_frequencies.py
python build_korp_pages.py
```

To rebuild the Mia section:

```bash
python korp_mia_frequencies.py
python build_mia_pages.py
```

Mia contains more than 22 million workbook rows. Its counts use every row, while the static example browser keeps up to 100 excerpts per word, resource, and decade so both sites fit in one Pages deployment.

The first source-breakdown build retrieves Korp author statistics and newspaper titles. Later builds use the compressed API cache in `plots/korp_mats_frequencies/api_cache`.

For local preview of the example and source-breakdown pages, serve `docs/` over HTTP (for example, `python3 -m http.server --directory korp-frequency-pages/docs 8000`) and open `http://localhost:8000/`. Both pages load data on demand.

GitHub Pages should use **GitHub Actions** as its publishing source. Pushing this repository's `main` branch runs `.github/workflows/pages.yml` and deploys `docs/`.
