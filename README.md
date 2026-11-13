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

The Mia site also includes the Kvinnsam target-usage JSONL exports: 892,245
matches from Dagny, Framåt, Hertha, Idun, Morgonbris, Tidevarvet, and Tidskrift
för hemmet. These add 128 terms (139 across all Mia sources). Plots include
exported-match counts, the example browser has a **Kvinnsam journals** resource,
and the source breakdown has a **Kvinnsam · journals** view. Kvinnsam has no
supplied corpus token totals, so per-million rates and Korp API comparisons are
unavailable. All 69,654 undated matches remain in the example browser and journal
breakdown; they are excluded from dated plots. Published excerpts are a
deterministic reservoir sample of up to 100 per term/decade (seed 42); counts
use every supplied record. Private filesystem paths are not published.

After a normal Mia build, add or refresh Kvinnsam from the workspace root:

```bash
.vn315/bin/python focus-project-electricity/docs/mia/downloads/add_kvinnsam.py \
  --source target_usages/kvinnsam_target_usages
```

The importer updates the existing static site without querying Korp or changing
its counts. It is safe to repeat. The full Mia builder also accepts
`--kvinnsam-source /path/to/kvinnsam_target_usages` to run this step last.
Provenance is recorded in `docs/mia/data/kvinnsam_provenance.json`. Local preview:

```bash
python3 -m http.server --bind 127.0.0.1 --directory focus-project-electricity/docs 8000
```

Open `http://localhost:8000/mia/`. This build does not push or deploy.

### Mats associated words over time

Open `http://localhost:8000/associations.html` or choose **Associated words** in
the Mats navigation. Term and corpus dropdowns cover TKR, Kubhist, Kubhist2 and
LB. The measure selector switches between yearly co-occurrence share (unique
neighbouring words within ±10 tokens per target usage) and Word2Vec cosine
similarity. Select a dot for excerpts and sample counts; yearly filters,
minimum sample size, label controls and SVG export are available.

The **Resource** dropdown restricts the graph to one newspaper in Kubhist or
Kubhist2, one TKR document collection, or one Litteraturbanken author ID
recovered from its public source URL. Newspaper names use the site's existing
title map; source files for different years of the same paper are grouped
together. The default **All resources** retains the corpus-wide analysis.
Resource deep links use e.g. `?word=ström&corpus=kubhist2&resource=aftonbladet`.
Resource counts, denominators, excerpts and Word2Vec training contexts are
independent. The original 30-per-year quota applies across the whole corpus,
so resource subsets are smaller and are not separately balanced. Sparse years
may have no co-occurrence points or insufficient data for Word2Vec.

Both measures use the existing 73,057 yearly-balanced Mats samples, rather than
the full corpora. Independent corpus/year Word2Vec models pool sample contexts
from the centred five-year window (±2 years), with 100-dimensional skip-gram,
window 5, minimum frequency 5, 15 epochs, and seed 42. Displayed points remain
yearly. Neighbours are lowercased surface forms; spelling, OCR, sample size and
changing genres affect results. Similarity between independent time windows
is descriptive and is not a calibrated estimate of semantic change.

From the workspace root, build the initial co-occurrence view:

```bash
.vn315/bin/python focus-project-electricity/docs/downloads/build_word_associations.py
```

Then submit `sbatch slurm/mats_word_associations.sbatch` from `focus-projects`
to train and publish Word2Vec neighbours in a four-corpus CPU array. Per-year
checkpoints in `focus-projects/association_runs/mats_word2vec_v1` make this
resumable. Corpus metadata enables similarity after all its results are
published; reload the page to pick up completed jobs. Rebuilding the initial
co-occurrence view resets similarity to pending until this training step runs
again (unchanged checkpoints are reused). No deployment is performed.

Build resource-level co-occurrence data without altering corpus-wide results:

```bash
.vn315/bin/python focus-project-electricity/docs/downloads/build_word_associations.py --resources
```

Then submit from `focus-projects`:

```bash
sbatch --job-name=mats_resource_associations --export=ALL,ASSOCIATION_RESOURCES=1 slurm/mats_word_associations.sbatch
```

Resource checkpoints live under each corpus's `resources/` subdirectory in the
same run folder. Resources with insufficient contexts retain explicit missing
model results. Rebuilding corpus-wide data preserves its resource catalog
when the source digest is unchanged; changed samples require rebuilding the
resource catalog too.

Graph tests are `tests/test_word_associations.py` and the optional Playwright
script `tests/browser_word_associations.py`. Use the workspace
`.venv-languagechange-cpu` environment to exercise the actual Gensim training test.

### Mia meaning clusters

`docs/mia/clusters.html` provides Mia's definition-cluster explorer, with the
same cluster summaries, yearly charts, and passage browser as Mats. Its initial
combination is **LlamaDictionary-sv-de-en_ML38BI + KBLab Swedish Sentence-BERT**
using usage-guide v2 decoding. Results are generated in the sibling
`focus-projects` workspace; the page displays a pending state until they finish.
Mia results are separate from Mats and load one term at a time.

Additional combinations with `oxfrug/bge-m3-swedish-superlim` (768 dimensions)
and `Qwen/Qwen3-Embedding-8B` (4,096 dimensions) reuse the same LlamaDictionary
definitions. Their Mia comparisons are queued after the KBLab baseline and
appear as pending until model checks and clustering finish. Each completed
combination has its own selector entry and cluster IDs.

The analysis samples up to 30 eligible usages per term/year/source (seed 42)
from TKR, Kubhist2, LB and Kvinnsam, then clusters each term jointly across those
sources with cosine average linkage at threshold 0.5. Kvinnsam's seven journals
share one sampling quota, with journal identity retained in passages. Cluster
IDs match across Mia sources for the same term; they are not aligned with Mats.
Undated usages stay in the frequency site's example browser but are excluded
from this annual analysis. Full experiment and background-job instructions are
in the sibling `focus-projects/MIA_CLUSTERING.md`.

Rebuild Mia's cluster explorer from the workspace root:

```bash
.vn315/bin/python focus-project-electricity/docs/downloads/build_cluster_pages.py \
  --dataset mia --site focus-project-electricity/docs/mia
```

Mia contains more than 22 million workbook rows. Its counts use every row, while the static example browser keeps up to 100 excerpts per word, resource, and decade so both sites fit in one Pages deployment.

The first source-breakdown build retrieves Korp author statistics and newspaper titles. Later builds use the compressed API cache in `plots/korp_mats_frequencies/api_cache`.

For local preview of the example and source-breakdown pages, serve `docs/` over HTTP (for example, `python3 -m http.server --bind 127.0.0.1 --directory docs 8000`) and open `http://localhost:8000/`. Both pages load data on demand.

GitHub Pages should use **GitHub Actions** as its publishing source. Pushing this repository's `main` branch runs `.github/workflows/pages.yml` and deploys `docs/`.

Large Mats releases use gzip-compressed model JSON and one association-data
bundle per corpus to fit the GitHub Pages size limit. `assets/site-data.js`
resolves the original logical JSON paths through `data/asset-map.json`; local
analysis builds use an empty map and ordinary JSON. After building locally,
prepare an isolated release with
`python docs/downloads/prepare_pages_release.py /tmp/new-pages-release`.
The release starts from the committed site, overlays Mats updates, and retains
the committed Mia pages. The sibling `-upload.json` manifest lists changed Git
objects and deletions. Modern browsers decompress the data on demand. Run
`tests/browser_pages_release.py --site /tmp/new-pages-release/docs` with
Playwright to check the exact release before publishing.

## Model cluster explorer

The Mats selector also includes **Co-occurrence contexts · TF–IDF + K-means**.
It clusters usages of each target jointly across all four corpora using binary
presence of neighbouring word forms (±10 tokens), TF–IDF weighting and L2
normalization. Common Swedish/historical function words and the target lemma
are excluded. Terms need document frequency two; vocabulary is capped at 20,000
features per target. Candidate K-means counts 2–12 use five initializations,
seed 42 and cosine silhouette on up to 1,000 contexts. The smallest candidate
within 0.01 of the best score is selected. Scores below 0.02 produce one
informative cluster. Cluster 0 records contexts with no retained vocabulary.

Characteristic words are the largest centroid weights, with example passages
from the current selection. The **Resource** selector filters newspapers,
authors or TKR collections without refitting or changing shared cluster IDs.
Its `source` URL parameter preserves resource selections. Word groups can
reflect topics, OCR, spelling and genre alongside meaning; silhouette-based
selection is exploratory and some targets retain a single informative cluster.
The original cap of 30 usages per word/year/corpus applies to the whole corpus,
so resource subsets have no independent balancing quota.

From the workspace root, run unit tests in `.venv-languagechange-cpu`; optional
browser coverage is in `tests/browser_cooccurrence_clusters.py`. Submit the
resumable experiment from `focus-projects` with
`sbatch slurm/cooccurrence_clustering.sbatch`. Per-word checkpoints and selection
scores are in `cooccurrence_runs/tfidf_kmeans_v1`. Completed corpus outputs are
discovered by the usual site builder and published locally without deployment.

Three additional local generators are supported with distinct pending KBLab
combinations: `LlamaDictionary-sv_L27BCH`, `LlamaDictionary-sv_L38BI` and
`LlamaDictionary-sv_ML38BI`. Each uses its corresponding base and saved chat
template. Details and background-job instructions are in the sibling
`focus-projects/LOCAL_DICTIONARY_MODELS.md`.

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

### LlamaDictionary combinations

The explorer recognizes `FrancescoPeriti/LlamaDictionary-sv-de-en_ML38BI` with KBLab
Swedish Sentence-BERT, multilingual E5 large, and BGE-M3 dense embeddings as
separate combinations. The KBLab run is scheduled first; its pending entry
becomes selectable only after validated results exist. The sibling
`focus-projects/LLAMADICTIONARY_EXPERIMENT.md` documents pinned revisions,
Hugging Face base-model access, background jobs, and reusing definitions with
the other encoders. New local combinations require a separate deployment to
appear on GitHub Pages.
