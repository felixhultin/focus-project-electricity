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

For local preview of the example and source-breakdown pages, serve `docs/` over HTTP (for example, `python3 -m http.server --bind 127.0.0.1 --directory docs 8000`) and open `http://localhost:8000/`. Both pages load data on demand.

GitHub Pages should use **GitHub Actions** as its publishing source. Pushing this repository's `main` branch runs `.github/workflows/pages.yml` and deploys `docs/`.

## Model cluster explorer

`docs/clusters.html` integrates sampled meaning clusters with the frequency site.
Use the **Clustering model**, **Corpus**, and **Word** selectors to inspect yearly
shares/counts and source passages. LLM-wsd also shows generated definitions;
XL-LEXEME groups passages directly and has no generated definitions.

Included in the local build:

| Model | Available corpora |
| --- | --- |
| `swap-uniba/LLM-wsd-FT-ALL` | TKR, Kubhist, Kubhist2, LB |
| `pierluigic/xl-lexeme` | TKR |

The page loads only the selected model/corpus JSON. Unsupported combinations are
omitted from the corpus selector. Cluster IDs are local to the model, word, and
corpus; matching IDs across models are not aligned senses. Counts describe the
sample and its recorded yearly or legacy decade cap, rather than full corpus frequencies.

Rebuild from this repository after updating clustering results:

```bash
python docs/downloads/build_cluster_pages.py
```

The builder discovers completed Mats result sets in the sibling
`focus-projects/data/clustered_definitions*_mats_*` directories and
`target_usages/*/mats_clustered_xllexeme` directories. Use `--workspace` to override
the workspace root. It verifies counts against clustering manifests, exports
source snippets and public model settings, and excludes local input paths.
Datasets without completed manifests are not listed. Rerun this builder after
rebuilding frequency pages to restore navigation links; running it repeatedly
does not duplicate links. The exported JSON and HTML are tracked site artifacts,
so deployment requires no Python execution or access to the HPC filesystem.

The index links each word directly to the explorer. Shareable links also accept
`model`, `corpus`, `word`, `from`, `to`, `cluster`, `metric`, and `q`, for example:

```text
clusters.html?model=xl-lexeme&corpus=tkr&word=attraktion
```

To preview locally, serve the site from the repository root:

```bash
python3 -m http.server --bind 127.0.0.1 --directory docs 8000
```

Open `http://localhost:8000/clusters.html`. As with the other data browsers, use
HTTP rather than opening this page directly as a file. A push to `main` deploys
the integrated explorer through the existing GitHub Pages workflow.

Checks:

```bash
python -m unittest discover -s tests -v
# Optional, with Playwright and Chromium installed:
python tests/browser_cluster_explorer.py
```

### Yearly cluster periods

The cluster explorer groups every corpus by individual year, including empty
years between the earliest and latest sampled usage. It uses the `year` retained
in each record; no new extraction, generation, or clustering is required.
Long ranges scroll horizontally, and year filters narrow the chart. The table
uses year labels consistently; original date fields remain in the JSON/CSV.
TKR and LB dates use January 1 placeholders, so only the stored year is used.

Sampling provenance travels with each dataset. New yearly runs cap each word
at 30 eligible usages per year, keeping all available usages when fewer exist.
Older results may still use a 30-per-decade cap until their replacement run
finishes. The notice follows the selected dataset and distinguishes these
cases; neither is a full-corpus frequency count. Years with n=0 have no sampled
usages.
The original Korp frequency plots are a separate view and retain their existing
period grouping.

### Shared clusters across corpora

Shared runs pool yearly samples from TKR, Kubhist, Kubhist2, and LB separately
for each word and model. LLM-wsd reuses generated definitions and embeds them
with multilingual MPNet; XL-LEXEME embeds the source usages. Both use average
linkage, cosine distance, and threshold 0.5. Every sampled usage contributes
once, so corpora spanning more years can contribute more examples.

The background pipeline lives in the sibling `focus-projects` directory:
`shared_clustering.py`, `slurm/shared_clustering.sbatch`, and
`slurm/finalize_shared_clustering.sbatch`. Submit from that directory with a
fresh `SHARED_RUN_DIR`; the model array uses task 0 for LLM-wsd and task 1 for
XL-LEXEME. The finalizer must depend on successful completion of the entire
model array. Each submitted run records job IDs in `jobs.json`.

The finalizer validates all eight model/corpus outputs against the source
samples and pooled labels, archives previous clustering directories, activates
the completed outputs, and rebuilds both local explorers. It does not deploy.
The sampling notice identifies shared results using their manifest metadata.
For shared results, IDs/colors are comparable across corpora for the same word
and model. They remain unrelated across words, models, or independent reruns.

### Definition generator and encoder combinations

The cluster explorer selects complete generator/encoder combinations. Its
catalog identifies both models, and separate encoders for the same generator
produce separate dataset IDs, share links, and caches. Public JSON records
include the encoder and combination ID.

The tutorial experiment uses `ltg/flan-t5-definition-en-xl` at revision
`f84a7b316a8787a0f1a10f93daf60fc4eb5dda9c` and
`sentence-transformers/all-mpnet-base-v2` at revision
`e8c3b32edf5434bc2275fc9bab85f82640a19130`. Its pending entry becomes selectable
when all four corpus results have been generated, jointly clustered, and
validated. Existing LLM-wsd/multilingual MPNet and XL-LEXEME results remain
available. Cluster IDs are comparable across corpora only within the same
word and combination.

This is an exploratory Swedish application of an English definition model;
neither successful execution nor a shared label establishes definition quality.


### Compact navigation

The frequency page uses a word dropdown and displays one plot at a time.
The selected word is preserved in the URL; existing word-section anchors still
work. Navigation focuses on plots, clusters, examples, and methodology. CSV,
script download, and Mia-site links are omitted from the main interface, and
the cluster explorer has no CSV export control. Existing data files remain
available in the repository. Both page builders apply the navigation cleanup
so rebuilding does not restore the old link lists.
