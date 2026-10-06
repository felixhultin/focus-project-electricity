#!/usr/bin/env python3
"""Build the static GitHub Pages bundle from the Korp frequency outputs."""

from __future__ import annotations

import shutil
import re
import csv
import json
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import quote, parse_qs, urlsplit

from build_mats_examples import build as build_examples
from korp_source_breakdown import build as build_source_breakdown


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "plots" / "korp_mats_frequencies"
SITE = ROOT / "korp-frequency-pages" / "docs"
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def annotate_plot_examples(plots, workbook):
    """Show the workbook row count alongside the API value in each bar tooltip."""
    for path in plots:
        published = SITE / "targets" / path.name
        tree = ET.parse(published)
        for link in tree.getroot().iter(f"{{{SVG}}}a"):
            query = parse_qs(urlsplit(link.attrib.get("href", "")).query)
            if not all(query.get(key) for key in ("word", "resource", "decade")):
                continue
            key = (query["word"][0], query["resource"][0], query["decade"][0])
            bucket = workbook.get(key, {})
            title = link.find(f"{{{SVG}}}rect/{{{SVG}}}title")
            if title is not None:
                title.text = (title.text or "") + f" · {bucket.get('count', 0):,} workbook examples"
        tree.write(published, encoding="unicode")


def main():
    plots = sorted((SOURCE / "targets").glob("*.svg"))
    if len(plots) != 25:
        raise ValueError(f"Expected 25 target SVG plots; found {len(plots)}")
    required = (
        SOURCE / "index.html",
        SOURCE / "yearly_frequencies.csv",
        SOURCE / "decade_frequencies.csv",
        SOURCE / "provenance.json",
        ROOT / "korp_mats_frequencies.py",
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    for directory in (SITE, SITE / "targets", SITE / "data", SITE / "downloads"):
        directory.mkdir(parents=True, exist_ok=True)
    for path in plots:
        shutil.copy2(path, SITE / "targets" / path.name)
    for filename in ("yearly_frequencies.csv", "decade_frequencies.csv", "provenance.json"):
        shutil.copy2(SOURCE / filename, SITE / "data" / filename)
    shutil.copy2(ROOT / "korp_mats_frequencies.py", SITE / "downloads" / "korp_mats_frequencies.py")
    shutil.copy2(ROOT / "build_mats_examples.py", SITE / "downloads" / "build_mats_examples.py")
    shutil.copy2(ROOT / "build_korp_pages.py", SITE / "downloads" / "build_korp_pages.py")
    shutil.copy2(ROOT / "mats_examples_viewer.html", SITE / "downloads" / "mats_examples_viewer.html")
    shutil.copy2(ROOT / "korp_source_breakdown.py", SITE / "downloads" / "korp_source_breakdown.py")
    shutil.copy2(ROOT / "source_breakdown_viewer.html", SITE / "downloads" / "source_breakdown_viewer.html")

    index = (SOURCE / "index.html").read_text(encoding="utf-8")
    marker = '<nav aria-label="Target words">'
    if index.count(marker) != 1:
        raise ValueError("Cannot locate target navigation in source index")
    links = (
        '<p class="site-links">'
        '<a href="examples.html">Browse workbook examples</a> · '
        '<a href="source-breakdown.html">Authors and newspapers</a> · '
        '<a href="methodology.html">Method and sources</a> · '
        '<a href="data/decade_frequencies.csv" download>Decade CSV</a> · '
        '<a href="data/yearly_frequencies.csv" download>Yearly CSV</a> · '
        '<a href="data/frequency_reconciliation.csv" download>Count comparison CSV</a> · '
        '<a href="downloads/korp_mats_frequencies.py" download>Korp script</a> · '
        '<a href="downloads/build_mats_examples.py" download>Examples script</a> · '
        '<a href="downloads/korp_source_breakdown.py" download>Source breakdown script</a> · '
        '<a href="downloads/build_korp_pages.py" download>Pages script</a>'
        '</p>'
    )
    index = index.replace(marker, links + marker)
    index = re.sub(
        r'(<section id="word-\d+"><h2>(.*?)</h2>)',
        lambda match: match.group(1)
        + f'<p><a href="examples.html?word={quote(unescape(match.group(2)))}">Browse workbook examples</a> · '
          f'<a href="source-breakdown.html?word={quote(unescape(match.group(2)))}">Authors and newspapers</a></p>',
        index,
    )
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / "methodology.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Method · Korp word frequencies</title>'
        '<style>body{font:17px/1.5 Arial,sans-serif;color:#263747;max-width:800px;margin:2rem auto;padding:0 1rem}'
        'a{color:#17639b}code{background:#f2f5f7;padding:.1em .25em}</style>'
        '<p><a href="index.html">← Word plots</a></p><h1>Method and sources</h1>'
        '<p>The 25 target words and 130 Korp corpus IDs come from the workbook filenames in '
        '<code>data/mats</code>. Within each of the three resource groups, the same corpus set is used for '
        'every word, including corpora with no hits for that word.</p>'
        '<p>Absolute frequency is the number of lemma matches. Relative frequency is matches per million '
        'tokens. The script retrieves yearly hits from Korp API v8 <code>/count_time</code> and yearly token '
        'totals from <code>/timespan</code>, then aggregates both by decade. A zero-token decade has no '
        'relative frequency. Queries use <code>lemma contains</code> to match historical corpora with '
        'multiple lemma alternatives.</p>'
        '<p>Both API requests use time strategy 3: dated material must fit entirely within a year. '
        'Each bar opens <a href="examples.html">workbook examples</a> with the same word, resource, '
        'and decade. The example browser shows the API and workbook counts side by side. '
        'The workbook rows are a separate export, so those counts can differ. '
        '<a href="data/frequency_reconciliation.csv">Download the comparison</a> for every bin.</p>'
        '<p>Examples with a source URL link to that page. Examples without a source URL remain '
        'visible as plain text; this applies to all <code>tkr</code> rows.</p>'
        '<p>The <a href="source-breakdown.html">author and newspaper breakdown</a> uses Korp '
        '<code>/count</code> grouped by <code>text_author</code> for all-date author totals. '
        'Author-by-decade counts group matches by author and text dates, retaining texts contained '
        'within one year, as in the main plots. <code>/struct_values</code> grouped by author and '
        'text dates supplies matching token totals for per-million rates. Workbook author IDs are '
        'counted separately from Litteraturbanken URLs. Newspaper frequencies use the same yearly '
        '<code>/count_time</code> and <code>/timespan</code> settings as the plots, aggregated by '
        'newspaper and decade. Rates divide hits by tokens for that author or newspaper and multiply '
        'by one million. Newspaper rows include workbook example counts for comparison.</p>'
        '<p>Source: <a href="https://ws.spraakbanken.gu.se/ws/korp/v8/">Språkbanken Korp API v8</a>. '
        'The corpus selection and query settings are in <a href="data/provenance.json">provenance.json</a>. '
        'The <a href="downloads/korp_mats_frequencies.py" download>Python script</a> reproduces the '
        'API retrieval and plots when run alongside the source workbooks.</p>'
        '</html>',
        encoding="utf-8",
    )
    manifest = build_examples(ROOT / "data" / "mats", SITE)
    workbook = {(b["word"], b["resource"], b["decade"]): b for b in manifest["buckets"]}
    annotate_plot_examples(plots, workbook)
    api = {}
    with (SOURCE / "decade_frequencies.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            key = (row["target"], row["resource"], str(row["decade"]))
            api[key] = row
    output = SITE / "data" / "frequency_reconciliation.csv"
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("word", "resource", "decade", "api_absolute", "workbook_examples",
                         "examples_with_source_url", "difference_api_minus_workbook", "tokens", "api_per_million"))
        for word, resource, decade in sorted(api.keys() | workbook.keys()):
            row = api.get((word, resource, decade))
            bucket = workbook.get((word, resource, decade), {})
            api_count = int(row["absolute"]) if row else 0
            example_count = bucket.get("count", 0)
            writer.writerow((word, resource, decade, api_count, example_count,
                             bucket.get("with_source_url", 0), api_count - example_count,
                             row["tokens"] if row else "", row["per_million"] if row else ""))
    manifest["api_buckets"] = [
        {"word": word, "resource": resource, "decade": decade, "absolute": int(row["absolute"])}
        for (word, resource, decade), row in sorted(api.items())
    ]
    provenance = json.loads((SOURCE / "provenance.json").read_text(encoding="utf-8"))
    manifest["korp"] = {
        "frontend": "https://spraakbanken.gu.se/korp/",
        "modes": {"lb": "lb", "tkr": "default", "kubhist2": "kubhist"},
        "corpora": provenance["corpora"],
    }
    (SITE / "example_data" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    build_source_breakdown(site=SITE)
    total = sum(bucket["count"] for bucket in manifest["buckets"])
    linked = sum(bucket["with_source_url"] for bucket in manifest["buckets"])
    print(f"Built {SITE} with {len(plots)} interactive plots and {total:,} examples; {linked:,} source links")


if __name__ == "__main__":
    main()
