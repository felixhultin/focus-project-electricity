#!/usr/bin/env python3
"""Build the Mia section inside the existing GitHub Pages repository."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from build_mia_examples import build as build_examples
from korp_mia_source_breakdown import build as build_source_breakdown


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "plots" / "korp_mia_frequencies"
SITE = ROOT / "korp-frequency-pages" / "docs" / "mia"
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def annotate(plots, workbook):
    for source in plots:
        path = SITE / "targets" / source.name
        tree = ET.parse(path)
        for link in tree.getroot().iter(f"{{{SVG}}}a"):
            query = parse_qs(urlsplit(link.attrib.get("href", "")).query)
            if not all(query.get(key) for key in ("word", "resource", "decade")):
                continue
            key = tuple(query[name][0] for name in ("word", "resource", "decade"))
            bucket = workbook.get(key, {})
            title = link.find(f"{{{SVG}}}rect/{{{SVG}}}title")
            if title is not None:
                title.text = (title.text or "") + f" · {bucket.get('count', 0):,} workbook examples"
        tree.write(path, encoding="unicode")


def methodology(words: int, corpora: int):
    (SITE / "methodology.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Method · Mia Korp frequencies</title>'
        '<style>body{font:17px/1.5 Arial,sans-serif;color:#263747;max-width:800px;margin:2rem auto;padding:0 1rem}'
        'a{color:#17639b}code{background:#f2f5f7;padding:.1em .25em}</style>'
        '<p><a href="index.html">← Mia word plots</a> · <a href="../index.html">Electricity site</a></p>'
        '<h1>Method and sources</h1>'
        f'<p>The {words} target terms and {corpora} Korp corpus IDs come from workbook filenames in '
        '<code>data/mia</code>. Multiword targets are queried as consecutive lemma tokens.</p>'
        '<p>Absolute frequency is the number of lemma matches. Relative frequency is matches per million '
        'tokens. Korp API v8 <code>/count_time</code> supplies yearly hits and <code>/timespan</code> '
        'supplies yearly token totals. Both use time strategy 3, and the site aggregates them by decade.</p>'
        '<p>The workbook export contains more than 22 million rows. Counts and source breakdown totals use '
        'all rows. To keep the combined GitHub Pages site practical, the example browser publishes up to '
        '100 excerpts per word, resource, and decade. The displayed Korp and workbook counts remain exact.</p>'
        '<p>The author and newspaper page uses Korp statistics grouped by structural metadata. Per-million '
        'author rates use author token totals for the selected date scope. Newspaper totals use the same '
        'time settings as the plots.</p>'
        '<p>Source: <a href="https://ws.spraakbanken.gu.se/ws/korp/v8/">Språkbanken Korp API v8</a>. '
        '<a href="data/provenance.json">provenance.json</a> records the corpus and query settings.</p>'
        '</html>', encoding="utf-8")


def main(reuse_examples=False):
    plots = sorted((SOURCE / "targets").glob("*.svg"))
    provenance = json.loads((SOURCE / "provenance.json").read_text(encoding="utf-8"))
    expected = len(provenance["targets"])
    if len(plots) != expected:
        raise ValueError(f"Expected {expected} Mia plots; found {len(plots)}")
    for directory in (SITE, SITE / "targets", SITE / "data", SITE / "downloads"):
        directory.mkdir(parents=True, exist_ok=True)
    for plot in plots:
        shutil.copy2(plot, SITE / "targets" / plot.name)
    for filename in ("yearly_frequencies.csv", "decade_frequencies.csv", "provenance.json"):
        shutil.copy2(SOURCE / filename, SITE / "data" / filename)
    for filename in ("korp_mia_frequencies.py", "build_mia_examples.py", "build_mia_pages.py",
                     "korp_mia_source_breakdown.py", "mats_examples_viewer.html",
                     "source_breakdown_viewer.html"):
        shutil.copy2(ROOT / filename, SITE / "downloads" / filename)

    index = (SOURCE / "index.html").read_text(encoding="utf-8")
    index = index.replace("<title>Korp word frequencies</title>",
                          "<title>Mia · Korp word frequencies</title>")
    index = index.replace("<h1>Korp frequencies for each word</h1>",
                          "<h1>Mia · Korp frequencies for each term</h1>")
    marker = '<nav aria-label="Target words">'
    links = (
        '<p><a href="../index.html">← Electricity site</a></p>'
        '<p class="site-links"><a href="examples.html">Browse sampled workbook examples</a> · '
        '<a href="source-breakdown.html">Authors and newspapers</a> · '
        '<a href="methodology.html">Method and sources</a> · '
        '<a href="data/decade_frequencies.csv" download>Decade CSV</a> · '
        '<a href="data/yearly_frequencies.csv" download>Yearly CSV</a> · '
        '<a href="data/frequency_reconciliation.csv" download>Count comparison CSV</a> · '
        '<a href="downloads/korp_mia_frequencies.py" download>Korp script</a> · '
        '<a href="downloads/build_mia_examples.py" download>Examples script</a> · '
        '<a href="downloads/korp_mia_source_breakdown.py" download>Source breakdown script</a> · '
        '<a href="downloads/build_mia_pages.py" download>Pages script</a></p>'
    )
    index = index.replace(marker, links + marker)
    index = re.sub(
        r'(<section id="word-\d+"><h2>(.*?)</h2>)',
        lambda match: match.group(1)
        + f'<p><a href="examples.html?word={quote(unescape(match.group(2)))}">Workbook examples</a> · '
          f'<a href="source-breakdown.html?word={quote(unescape(match.group(2)))}">Authors and newspapers</a></p>',
        index)
    (SITE / "index.html").write_text(index, encoding="utf-8")
    shutil.copy2(ROOT / "mats_examples_viewer.html", SITE / "examples.html")
    if reuse_examples and (SITE / "example_data" / "manifest.json").is_file():
        manifest = json.loads((SITE / "example_data" / "manifest.json").read_text(encoding="utf-8"))
    else:
        manifest = build_examples(site=SITE)
    manifest["dataset"] = "the data/mia workbooks"
    workbook = {(b["word"], b["resource"], b["decade"]): b for b in manifest["buckets"]}
    annotate(plots, workbook)

    api = {}
    with (SOURCE / "decade_frequencies.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            api[(row["target"], row["resource"], row["decade"])] = row
    with (SITE / "data" / "frequency_reconciliation.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("word", "resource", "decade", "api_absolute", "workbook_examples",
                         "examples_with_source_url", "published_sample", "difference_api_minus_workbook",
                         "tokens", "api_per_million"))
        for key in sorted(api.keys() | workbook.keys()):
            row, bucket = api.get(key), workbook.get(key, {})
            api_count = int(row["absolute"]) if row else 0
            examples = bucket.get("count", 0)
            writer.writerow((*key, api_count, examples, bucket.get("with_source_url", 0),
                             bucket.get("sample_count", 0), api_count - examples,
                             row["tokens"] if row else "", row["per_million"] if row else ""))
    manifest["api_buckets"] = [
        {"word": word, "resource": resource, "decade": dec, "absolute": int(row["absolute"])}
        for (word, resource, dec), row in sorted(api.items())]
    manifest["korp"] = {
        "frontend": "https://spraakbanken.gu.se/korp/",
        "modes": {"lb": "lb", "tkr": "default", "kubhist2": "kubhist"},
        "corpora": provenance["corpora"],
    }
    (SITE / "example_data" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    methodology(len(provenance["targets"]), sum(map(len, provenance["corpora"].values())))
    build_source_breakdown(site=SITE)
    print(f"Built Mia site at {SITE} with {len(plots)} plots and "
          f"{sum(manifest['all_rows'].values()):,} exact workbook rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-examples", action="store_true",
                        help="Reuse an existing exact-count/sample build")
    args = parser.parse_args()
    main(args.reuse_examples)
