#!/usr/bin/env python3
"""Fetch Korp frequencies for the words and corpora named by data/mats files.

Uses Korp API v8 and Python's standard library. Results are cached as compressed
API responses so an interrupted run can resume without repeating completed calls.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from html import escape as html_escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape


API = "https://ws.spraakbanken.gu.se/ws/korp/v8"
RESOURCES = ("lb", "tkr", "kubhist2")
COLORS = {"lb": "#2678a9", "tkr": "#d46a24", "kubhist2": "#2e8964"}
KORP_FRONTEND = "https://spraakbanken.gu.se/korp/"
KORP_MODES = {"lb": "lb", "tkr": "default", "kubhist2": "kubhist"}


def chunks(items, size):
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]


def discover_files(source: Path):
    records = []
    for resource in RESOURCES:
        paths = sorted((source / resource).glob("*.xlsx"))
        if not paths:
            raise ValueError(f"No workbooks found in {source / resource}")
        for path in paths:
            corpus, target = path.stem.rsplit("_", 1)
            records.append((str(path), resource, corpus.upper(), target))
    corpora = {resource: sorted({r[2] for r in records if r[1] == resource})
               for resource in RESOURCES}
    targets = sorted({r[3] for r in records})
    return records, corpora, targets


def api_json(endpoint, params, cache_dir: Path, refresh=False):
    payload = urlencode(params).encode("utf-8")
    key = hashlib.sha256(endpoint.encode() + b"?" + payload).hexdigest()[:20]
    cache_path = cache_dir / f"{endpoint or 'info'}-{key}.json.gz"
    if cache_path.exists() and not refresh:
        with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    request = Request(
        f"{API}/{endpoint}" if endpoint else f"{API}/",
        data=payload if params else None,
        headers={"User-Agent": "mats-korp-frequencies/1.0", "Accept": "application/json"},
        method="POST" if params else "GET",
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=240) as response:
                result = json.load(response)
            if "error" in result:
                raise ValueError(f"Korp {endpoint} error: {result['error']}")
            cache_dir.mkdir(parents=True, exist_ok=True)
            with gzip.open(cache_path, "wt", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False)
            return result
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt == 3 or isinstance(exc, HTTPError) and exc.code < 500:
                raise RuntimeError(f"Korp {endpoint} request failed: {exc}") from exc
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def parse_year_values(values):
    """Use dated yearly points; zero and null API end markers are omitted."""
    result = {}
    for label, value in values.items():
        if re.fullmatch(r"\d{4}", label) and value is not None and value > 0:
            result[int(label)] = int(value)
    return result


def cqp_contains(target):
    # Korp historical lemma fields contain pipe-delimited alternative lemmas.
    # `contains` matches a complete item in that field, unlike `lemma="word"`.
    return f'[lemma contains "{re.escape(target)}"]'


def fetch_group(resource, corpora, targets, cache_dir, corpus_batch, word_batch, refresh):
    tokens = Counter()
    hits = Counter()
    active_corpora = defaultdict(set)
    for corpus_names in chunks(corpora, corpus_batch):
        corpus_arg = ",".join(corpus_names)
        spans = api_json("timespan", {
            "corpus": corpus_arg, "granularity": "y", "strategy": "3",
        }, cache_dir, refresh)
        if "combined" not in spans:
            raise ValueError(f"No combined timespan for {resource}: {corpus_names}")
        for year, count in parse_year_values(spans["combined"]).items():
            tokens[(resource, year)] += count
        for corpus, values in spans["corpora"].items():
            for year in parse_year_values(values):
                active_corpora[(resource, year // 10 * 10)].add(corpus)
        print(f"{resource}: token totals for {len(corpus_names)} corpora", flush=True)

        for words in chunks(targets, word_batch):
            union = "|".join(re.escape(word) for word in words)
            params = {
                "corpus": corpus_arg,
                "cqp": f'[lemma contains "{union}"]',
                "granularity": "y",
                "strategy": "3",
            }
            for index, word in enumerate(words):
                params[f"subcqp{index}"] = cqp_contains(word)
            response = api_json("count_time", params, cache_dir, refresh)
            series = response.get("combined")
            if not isinstance(series, list) or len(series) != len(words) + 1:
                raise ValueError(f"Unexpected count_time result for {resource}, {words}")
            for index, word in enumerate(words, 1):
                if series[index].get("cqp") != cqp_contains(word):
                    raise ValueError(f"Unexpected subquery order for {word}")
                for year, count in parse_year_values(series[index]["absolute"]).items():
                    hits[(resource, word, year)] += count
            print(f"{resource}: {len(corpus_names)} corpora × {len(words)} words", flush=True)
    return tokens, hits, active_corpora


def korp_bar_url(resource, word, decade, corpus_names):
    """Open a KWIC search with the same year-contained material as strategy=3."""
    yearly = [
        f"(int(_.text_datefrom) >= {year}0101 & int(_.text_dateto) <= {year}1231)"
        for year in range(decade, decade + 10)
    ]
    cqp = f'[lemma contains "{re.escape(word)}" & ({" | ".join(yearly)})]'
    hash_params = urlencode({
        "corpus": ",".join(name.lower() for name in sorted(corpus_names)),
        "search": f"cqp|{cqp}",
        "search_tab": "2",
        "result_tab": "0",
    }, quote_via=quote)
    return f"{KORP_FRONTEND}?mode={KORP_MODES[resource]}#?{hash_params}"


def examples_bar_url(resource, word, decade):
    """Open the workbook examples for the exact bar grouping in the Pages site."""
    return "../examples.html?" + urlencode({
        "word": word, "resource": resource, "decade": decade,
    }, quote_via=quote)


def number(value, decimal=False):
    if decimal:
        return f"{value:.3g}" if value else "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2g}m"
    if value >= 10_000:
        return f"{value / 1_000:.2g}k"
    return str(round(value))


def label(x, y, content, size=13, anchor="start", color="#263747", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="{color}" font-weight="{weight}">'
            f'{xml_escape(str(content))}</text>')


def draw_plot(path: Path, word: str, decades_by_resource, decade_data, active_corpora):
    width, height = 1600, 940
    margin_left, margin_right = 85, 30
    col_gap = 90
    col_width = (width - margin_left - margin_right - col_gap) / 2
    plot_height, row_gap, top = 190, 60, 150
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{xml_escape(word)} frequency by decade and resource">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif}</style>',
        label(margin_left, 39, word, 27, weight="bold"),
        label(margin_left, 65, "Korp API frequency · click a bar for matching workbook examples", 14, color="#5a6876"),
        label(margin_left, 99, "Absolute frequency · hits", 17, weight="bold"),
        label(margin_left + col_width + col_gap, 99, "Relative frequency · hits per million tokens", 17, weight="bold"),
    ]
    for row, resource in enumerate(RESOURCES):
        decades = decades_by_resource[resource]
        step = col_width / len(decades)
        ytop = top + row * (plot_height + row_gap)
        baseline = ytop + plot_height
        for column, measure in enumerate(("absolute", "relative")):
            xleft = margin_left + column * (col_width + col_gap)
            values = [decade_data.get((decade, resource, word), (0, 0, None))[
                0 if measure == "absolute" else 2] for decade in decades]
            good = [v for v in values if v is not None]
            ceiling = max(1, max(good, default=0))
            if column == 0:
                parts.append(label(xleft, ytop - 12,
                                   f"{resource} · {decades[0]}–{decades[-1] + 9}",
                                   16, color=COLORS[resource], weight="bold"))
            for fraction in (0, .5, 1):
                gy = baseline - fraction * plot_height
                parts.append(f'<line x1="{xleft:.1f}" y1="{gy:.1f}" x2="{xleft+col_width:.1f}" '
                             f'y2="{gy:.1f}" stroke="#e1e7eb"/>')
                parts.append(label(xleft - 8, gy + 4, number(ceiling * fraction, measure == "relative"),
                                   11, anchor="end", color="#657381"))
            for index, (decade, value) in enumerate(zip(decades, values)):
                if value is None:
                    continue
                bar_height = value / ceiling * plot_height
                x = xleft + (index + .12) * step
                if value > 0:
                    url = examples_bar_url(resource, word, decade)
                    parts.append(
                        f'<a href="{xml_escape(url)}" target="_blank" rel="noopener noreferrer">'
                        f'<rect x="{x:.1f}" y="{baseline-bar_height:.1f}" '
                        f'width="{.76*step:.1f}" height="{bar_height:.1f}" '
                        f'fill="{COLORS[resource]}" style="cursor:pointer"><title>'
                        f'{resource}, {decade}s: {value:,.4f} '
                        f'{"hits/million" if measure == "relative" else "hits"} · open workbook examples'
                        '</title></rect></a>'
                    )
                if index % (2 if len(decades) > 24 else 1) == 0:
                    parts.append(label(xleft + (index + .5) * step, baseline + 17,
                                       decade, 10, anchor="middle", color="#5a6876"))
    parts.append(label(width / 2, height - 11, "Decade", 13, anchor="middle"))
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_index(path: Path, targets):
    links = " ".join(f'<a href="#word-{i}">{html_escape(word)}</a>'
                     for i, word in enumerate(targets))
    figures = "\n".join(
        f'<section id="word-{i}"><h2>{html_escape(word)}</h2>'
        f'<a href="targets/{quote(word)}.svg">Open SVG</a>'
        f'<object data="targets/{quote(word)}.svg" type="image/svg+xml" '
        f'aria-label="Absolute and relative frequencies for {html_escape(word)}">'
        f'<a href="targets/{quote(word)}.svg">Open plot</a></object></section>'
        for i, word in enumerate(targets)
    )
    path.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Korp word frequencies</title>'
        '<style>body{font:16px Arial,sans-serif;color:#263747;max-width:1640px;margin:2rem auto;padding:0 1rem}'
        'nav{display:flex;flex-wrap:wrap;gap:.7rem 1rem;margin:1.5rem 0 2rem}'
        'a{color:#17639b}section{border-top:1px solid #dbe3e9;padding:1.2rem 0}'
        'section object{width:100%;aspect-ratio:1600/940;display:block}</style>'
        '<h1>Korp frequencies for each word</h1>'
        '<p>Absolute counts and relative frequency per million tokens, by decade and resource. '
        'Each panel has its own vertical scale. Click a bar to open workbook examples '
        'for the same word, resource, and decade. The example page compares the workbook '
        'count with the Korp API count.</p>'
        f'<nav aria-label="Target words">{links}</nav>{figures}</html>',
        encoding="utf-8",
    )


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/mats"))
    parser.add_argument("--output", type=Path, default=Path("plots/korp_mats_frequencies"))
    parser.add_argument("--corpus-batch", type=int, default=30)
    parser.add_argument("--word-batch", type=int, default=5)
    parser.add_argument("--refresh", action="store_true", help="Repeat API calls instead of using cache")
    args = parser.parse_args()
    if args.corpus_batch < 1 or args.word_batch < 1:
        parser.error("Batch sizes must be positive")
    records, corpora, targets = discover_files(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    cache_dir = args.output / "api_cache"
    info = api_json("", {}, cache_dir, args.refresh)
    available = set(info.get("corpora", []))
    missing = sorted({corpus for names in corpora.values() for corpus in names} - available)
    if missing:
        raise ValueError(f"Corpora from filenames missing in Korp: {missing}")

    write_csv(args.output / "file_corpus_map.csv",
              ("file", "resource", "korp_corpus", "target"), records)
    print(f"Found {len(targets)} words and {sum(map(len, corpora.values()))} Korp corpora.", flush=True)
    all_tokens = Counter()
    all_hits = Counter()
    all_active_corpora = defaultdict(set)
    for resource in RESOURCES:
        tokens, hits, active_corpora = fetch_group(resource, corpora[resource], targets, cache_dir,
                                                   args.corpus_batch, args.word_batch, args.refresh)
        all_tokens.update(tokens)
        all_hits.update(hits)
        for key, names in active_corpora.items():
            all_active_corpora[key].update(names)

    for (resource, target, year), count in all_hits.items():
        if count and all_tokens[(resource, year)] == 0:
            raise ValueError(f"{resource} {target} {year}: hits but no token denominator")
    years = sorted({year for _, year in all_tokens})
    if not years:
        raise ValueError("Korp returned no dated tokens")
    decades = list(range(years[0] // 10 * 10, years[-1] // 10 * 10 + 1, 10))
    decades_by_resource = {}
    for resource in RESOURCES:
        resource_years = [year for (name, year), value in all_tokens.items()
                          if name == resource and value > 0]
        decades_by_resource[resource] = list(range(
            min(resource_years) // 10 * 10,
            max(resource_years) // 10 * 10 + 1, 10,
        ))
    decade_tokens = Counter()
    decade_hits = Counter()
    for (resource, year), value in all_tokens.items():
        decade_tokens[(year // 10 * 10, resource)] += value
    for (resource, target, year), value in all_hits.items():
        decade_hits[(year // 10 * 10, resource, target)] += value

    write_csv(args.output / "yearly_frequencies.csv",
              ("year", "resource", "target", "absolute", "tokens", "per_million"),
              ((year, resource, target, all_hits[(resource, target, year)],
                all_tokens[(resource, year)],
                all_hits[(resource, target, year)] * 1_000_000 / all_tokens[(resource, year)])
               for year in years for resource in RESOURCES for target in targets
               if all_tokens[(resource, year)] > 0))
    write_csv(args.output / "decade_frequencies.csv",
              ("decade", "resource", "target", "absolute", "tokens", "per_million"),
              ((decade, resource, target, decade_hits[(decade, resource, target)],
                decade_tokens[(decade, resource)],
                decade_hits[(decade, resource, target)] * 1_000_000 / decade_tokens[(decade, resource)])
               for decade in decades for resource in RESOURCES for target in targets
               if decade_tokens[(decade, resource)] > 0))

    decade_data = {
        (decade, resource, target):
        (decade_hits[(decade, resource, target)], decade_tokens[(decade, resource)],
         decade_hits[(decade, resource, target)] * 1_000_000 / decade_tokens[(decade, resource)]
         if decade_tokens[(decade, resource)] else None)
        for decade in decades for resource in RESOURCES for target in targets
    }
    target_dir = args.output / "targets"
    target_dir.mkdir(exist_ok=True)
    for word in targets:
        draw_plot(target_dir / f"{word}.svg", word, decades_by_resource,
                  decade_data, all_active_corpora)
    write_index(args.output / "index.html", targets)
    (args.output / "provenance.json").write_text(json.dumps({
        "api": API, "endpoints": ["count_time", "timespan"], "granularity": "year",
        "strategy": 3, "query_field": "lemma", "query_operator": "contains",
        "relative_unit": "hits per million tokens", "corpora": corpora, "targets": targets,
        "source_files": len(records), "bar_links": {
            "target": "../examples.html",
            "filters": ["word", "resource", "decade"],
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(targets)} word plots and frequency CSVs to {args.output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
