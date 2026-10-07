#!/usr/bin/env python3
"""Build exact Mia workbook counts and a bounded, browsable example sample.

The Mia export has more than 22 million rows. Counts cover every row, while the
static Pages bundle keeps at most SAMPLE_LIMIT excerpts per word/resource/decade.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from lxml import etree


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "mia"
SITE = ROOT / "korp-frequency-pages" / "docs" / "mia"
SAMPLE_LIMIT = 100
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
YEAR = re.compile(r"^(\d{4})")
DIMENSION = re.compile(rb'<dimension ref="[A-Z]+\d+:[A-Z]+(\d+)"')
SPACE = re.compile(r"\s+")


def cell_value(cell) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(NS + "t"))
    return cell.findtext(NS + "v") or ""


def values(row) -> dict[str, str]:
    return {cell.get("r", "")[:1]: cell_value(cell) for cell in row}


def excerpt(text: str, start: str, end: str) -> tuple[str, str, str]:
    try:
        left, right = int(float(start)), int(float(end))
    except (TypeError, ValueError):
        left = right = -1
    if not (0 <= left < right <= len(text)):
        return "", "", SPACE.sub(" ", text[:220]).strip()
    before = SPACE.sub(" ", text[max(0, left - 110):left])
    hit = SPACE.sub(" ", text[left:right])
    after = SPACE.sub(" ", text[right:right + 110])
    return (("…" if left > 110 else "") + before, hit,
            after + ("…" if right + 110 < len(text) else ""))


def row_count(path: Path) -> int:
    with ZipFile(path) as book, book.open("xl/worksheets/sheet1.xml") as stream:
        match = DIMENSION.search(stream.read(800))
    if not match:
        raise ValueError(f"No worksheet dimension in {path}")
    return int(match.group(1)) - 1


def rows(path: Path):
    with ZipFile(path) as book, book.open("xl/worksheets/sheet1.xml") as stream:
        for _, row in etree.iterparse(stream, events=("end",), tag=NS + "row"):
            if row.get("r") != "1":
                yield row
            row.clear()
            while row.getprevious() is not None:
                del row.getparent()[0]


def decade(date: str) -> str:
    found = YEAR.match(date)
    return str(int(found.group(1)) // 10 * 10) if found else "undated"


def author_id(url: str) -> str:
    found = re.search(r"/författare/([^/]+)", unquote(urlsplit(url).path))
    return found.group(1) if found else "(Unknown author ID)"


def add_sample(samples, key, data, linked):
    if len(samples[key]) < SAMPLE_LIMIT:
        samples[key].append(data)
    if linked:
        return 1
    return 0


def build(source: Path = SOURCE, site: Path = SITE):
    destination = site / "example_data"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    counts = Counter()
    linked = Counter()
    samples: dict[tuple[str, str, str], list] = {}
    authors = Counter()
    papers = Counter()
    corpora = []
    corpus_ids = {}
    words = set()

    def corpus_id(name):
        if name not in corpus_ids:
            corpus_ids[name] = len(corpora)
            corpora.append(name)
        return corpus_ids[name]

    for resource in ("lb", "tkr", "kubhist2"):
        for path in sorted((source / resource).glob("*.xlsx")):
            corpus, word = path.stem.rsplit("_", 1)
            words.add(word)
            cid = corpus_id(corpus)
            if resource == "kubhist2":
                found = re.search(r"-(\d{4})$", corpus)
                if not found:
                    raise ValueError(f"No decade in newspaper corpus name: {corpus}")
                dec = found.group(1)
                total = row_count(path)
                key = (word, resource, dec)
                counts[key] += total
                linked[key] += total
                paper = re.sub(r"^kubhist2-", "", corpus)
                paper = re.sub(r"-\d{4}$", "", paper)
                papers[(word, paper, dec)] += total
                samples.setdefault(key, [])
                if len(samples[key]) >= SAMPLE_LIMIT:
                    continue
                for row in rows(path):
                    data = values(row)
                    before, hit, after = excerpt(data.get("J", ""), data.get("H", ""), data.get("I", ""))
                    samples[key].append([data.get("E", ""), cid, before, hit, after, data.get("F") or None])
                    if len(samples[key]) >= SAMPLE_LIMIT:
                        break
                continue

            for row in rows(path):
                data = values(row)
                dec = decade(data.get("E", ""))
                key = (word, resource, dec)
                counts[key] += 1
                url = data.get("F") or None
                if url:
                    linked[key] += 1
                samples.setdefault(key, [])
                if resource == "lb":
                    authors[(word, author_id(url or ""), dec)] += 1
                if len(samples[key]) < SAMPLE_LIMIT:
                    before, hit, after = excerpt(data.get("J", ""), data.get("H", ""), data.get("I", ""))
                    samples[key].append([data.get("E", ""), cid, before, hit, after, url])

    for (word, resource, dec), selected in samples.items():
        folder = destination / word / resource / dec
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "0.json").write_text(
            json.dumps(selected, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    manifest = {
        "chunk_size": SAMPLE_LIMIT,
        "sample_limit": SAMPLE_LIMIT,
        "words": sorted(words), "resources": ["lb", "tkr", "kubhist2"],
        "corpora": corpora,
        "all_rows": {resource: sum(n for (word, r, dec), n in counts.items() if r == resource)
                     for resource in ("lb", "tkr", "kubhist2")},
        "without_source_url": {resource: sum(n for (word, r, dec), n in counts.items() if r == resource)
                               - sum(n for (word, r, dec), n in linked.items() if r == resource)
                               for resource in ("lb", "tkr", "kubhist2")},
        "buckets": [
            {"word": word, "resource": resource, "decade": dec, "count": count,
             "sample_count": len(samples[(word, resource, dec)]),
             "with_source_url": linked[(word, resource, dec)]}
            for (word, resource, dec), count in sorted(counts.items())
        ],
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    aggregate = {
        "authors": [[word, author, dec, count]
                    for (word, author, dec), count in sorted(authors.items())],
        "newspapers": [[word, paper, dec, count]
                       for (word, paper, dec), count in sorted(papers.items())],
    }
    (destination / "workbook_sources.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, default=SITE)
    args = parser.parse_args()
    result = build(args.source, args.site)
    print(f"Counted {sum(result['all_rows'].values()):,} workbook rows; "
          f"kept up to {SAMPLE_LIMIT} examples per bin")
