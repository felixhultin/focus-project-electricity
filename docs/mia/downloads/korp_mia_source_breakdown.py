#!/usr/bin/env python3
"""Build Korp author/newspaper frequencies and workbook source counts.

Run after build_mia_examples.py has produced docs/mia/example_data. Korp
responses are cached so later rebuilds are offline.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from korp_mia_frequencies import (
    api_json, chunks, cqp_contains, discover_files, parse_year_values, query_batches,
)


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "mia"
CACHE = ROOT / "plots" / "korp_mia_frequencies" / "api_cache"
OUTPUT = ROOT / "plots" / "korp_mia_source_breakdown"
SITE = ROOT / "korp-frequency-pages" / "docs" / "mia"


def grouped_query(words: list[str], attribute: str) -> tuple[dict, list, int]:
    batched = len(words) > 1
    params = {
        "corpus": "LB-OPEN",
        "cqp": (f'[lemma contains "{"|".join(re.escape(word) for word in words)}"]'
                if batched else cqp_contains(words[0])),
        "group_by_struct": attribute,
    }
    if batched:
        for index, word in enumerate(words):
            params[f"subcqp{index}"] = cqp_contains(word)
    return params, words, int(batched)


def newspaper_id(corpus: str) -> str:
    match = re.fullmatch(r"KUBHIST2-(.+)-\d{4}", corpus.upper())
    if not match:
        raise ValueError(f"Unexpected newspaper corpus ID: {corpus}")
    return match.group(1).lower()


def author_frequencies(targets: list[str], cache: Path) -> list[tuple]:
    metadata = api_json("struct_values", {
        "corpus": "LB-OPEN", "struct": "text_author", "count": "true",
    }, cache)
    tokens_by_author = metadata["combined"]["text_author"]
    output = []
    for words in query_batches(targets, 5):
        params, words, offset = grouped_query(words, "text_author")
        response = api_json("count", params, cache)
        series = response["combined"]
        if not isinstance(series, list) and not offset:
            series = [series]
        if not isinstance(series, list) or len(series) != len(words) + offset:
            raise ValueError(f"Unexpected author statistics for {words}")
        for index, word in enumerate(words, offset):
            if offset and series[index].get("cqp") != cqp_contains(word):
                raise ValueError(f"Unexpected author subquery order for {word}")
            rows = series[index]["rows"]
            if sum(int(row["absolute"]) for row in rows) != int(series[index]["sums"]["absolute"]):
                raise ValueError(f"Author statistics do not sum for {word}")
            for row in rows:
                author = row["value"].get("text_author") or "(Unknown author)"
                count = int(row["absolute"])
                tokens = int(tokens_by_author.get(author, 0))
                output.append((word, author, count, tokens,
                               count * 1_000_000 / tokens if tokens else None))
    return sorted(output)


def contained_year(start: str, end: str) -> int | None:
    """Match the year-contained texts used by Korp time strategy 3."""
    if not re.fullmatch(r"\d{8}", start) or not re.fullmatch(r"\d{8}", end):
        return None
    year = int(start[:4])
    if start[:4] != end[:4] or not (f"{year}0101" <= start <= end <= f"{year}1231"):
        return None
    return year


def author_decade_frequencies(targets: list[str], cache: Path, all_dates: list[tuple]) -> list[tuple]:
    metadata = api_json("struct_values", {
        "corpus": "LB-OPEN", "struct": "text_author>text_datefrom>text_dateto",
        "count": "true",
    }, cache)
    author_tokens = Counter()
    for author, starts in metadata["combined"]["text_author>text_datefrom>text_dateto"].items():
        for start, ends in starts.items():
            for end, count in ends.items():
                year = contained_year(start, end)
                if year is not None:
                    author_tokens[(author, year // 10 * 10)] += int(count)

    hits = Counter()
    all_grouped = Counter()
    for words in query_batches(targets, 5):
        params, words, offset = grouped_query(words, "text_author,text_datefrom,text_dateto")
        response = api_json("count", params, cache)
        series = response["combined"]
        if not isinstance(series, list) and not offset:
            series = [series]
        if not isinstance(series, list) or len(series) != len(words) + offset:
            raise ValueError(f"Unexpected dated author statistics for {words}")
        for index, word in enumerate(words, offset):
            if offset and series[index].get("cqp") != cqp_contains(word):
                raise ValueError(f"Unexpected dated author subquery order for {word}")
            for row in series[index]["rows"]:
                values = row["value"]
                author = values.get("text_author") or "(Unknown author)"
                count = int(row["absolute"])
                all_grouped[(word, author)] += count
                year = contained_year(values.get("text_datefrom", ""),
                                      values.get("text_dateto", ""))
                if year is not None:
                    hits[(word, author, year // 10 * 10)] += count
    expected_all = {(word, author): count for word, author, count, _, _ in all_dates}
    if all_grouped != expected_all:
        raise ValueError("Dated author grouping does not match all-date author counts")

    rows = []
    for (word, author, decade), count in sorted(hits.items()):
        tokens = author_tokens[(author, decade)]
        if not tokens:
            raise ValueError(f"No author token total for {word}, {author}, {decade}")
        rows.append((word, author, str(decade), count, tokens, count * 1_000_000 / tokens))

    expected_hits = {}
    expected_tokens = {}
    with (ROOT / "plots" / "korp_mia_frequencies" / "decade_frequencies.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            if row["resource"] == "lb":
                key = (row["target"], row["decade"])
                expected_hits[key] = int(row["absolute"])
                expected_tokens[row["decade"]] = int(row["tokens"])
    actual_hits = Counter()
    for word, _, decade, count, _, _ in rows:
        actual_hits[(word, decade)] += count
    for key, count in expected_hits.items():
        if actual_hits[key] != count:
            raise ValueError(f"Author decade hits differ from plot for {key}: {actual_hits[key]} != {count}")
    actual_tokens = Counter()
    for (_, decade), count in author_tokens.items():
        actual_tokens[str(decade)] += count
    for decade, count in expected_tokens.items():
        if actual_tokens[decade] != count:
            raise ValueError(f"Author decade tokens differ from plot for {decade}")
    return rows


def newspaper_frequencies(targets: list[str], corpora: list[str], cache: Path):
    tokens = Counter()
    hits = Counter()
    for corpus_batch in chunks(corpora, 30):
        corpus_arg = ",".join(corpus_batch)
        spans = api_json("timespan", {
            "corpus": corpus_arg, "granularity": "y", "strategy": "3",
        }, cache)
        for corpus, values in spans["corpora"].items():
            newspaper = newspaper_id(corpus)
            for year, count in parse_year_values(values).items():
                tokens[(newspaper, year // 10 * 10)] += count
        for words in query_batches(targets, 5):
            batched = len(words) > 1
            params = {
                "corpus": corpus_arg,
                "cqp": (f'[lemma contains "{"|".join(re.escape(word) for word in words)}"]'
                        if batched else cqp_contains(words[0])),
                "granularity": "y", "strategy": "3",
            }
            if batched:
                for index, word in enumerate(words):
                    params[f"subcqp{index}"] = cqp_contains(word)
            response = api_json("count_time", params, cache)
            for corpus, series in response["corpora"].items():
                newspaper = newspaper_id(corpus)
                if not isinstance(series, list) and not batched:
                    series = [series]
                offset = int(batched)
                if len(series) != len(words) + offset:
                    raise ValueError(f"Unexpected newspaper statistics for {corpus}")
                for index, word in enumerate(words, offset):
                    if batched and series[index].get("cqp") != cqp_contains(word):
                        raise ValueError(f"Unexpected newspaper subquery order for {word}")
                    for year, count in parse_year_values(series[index]["absolute"]).items():
                        hits[(word, newspaper, year // 10 * 10)] += count
    return tokens, hits


def newspaper_titles(corpora: list[str], cache: Path) -> dict[str, str]:
    representative = {}
    for corpus in corpora:
        representative.setdefault(newspaper_id(corpus), corpus)
    response = api_json("corpus_config", {
        "corpus": ",".join(representative.values()),
    }, cache)
    titles = {}
    for newspaper, corpus in representative.items():
        config = response.get("corpora", {}).get(corpus.lower(), {})
        title = config.get("title", {}).get("swe", "")
        title = re.sub(r"\s+\d{4}-talet$", "", title.removeprefix("Kubhist 2: "))
        titles[newspaper] = title or newspaper.replace("-", " ").title()
    return titles


def workbook_source_counts(site: Path):
    data = json.loads((site / "example_data" / "workbook_sources.json").read_text(encoding="utf-8"))
    authors = Counter({(word, author, decade): count for word, author, decade, count in data["authors"]})
    papers = Counter({(word, paper, decade): count for word, paper, decade, count in data["newspapers"]})
    return authors, papers


def csv_write(path: Path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def build(source: Path = SOURCE, cache: Path = CACHE, output: Path = OUTPUT, site: Path = SITE):
    _, corpus_groups, targets = discover_files(source)
    output.mkdir(parents=True, exist_ok=True)
    (site / "data").mkdir(parents=True, exist_ok=True)
    author_api = author_frequencies(targets, cache)
    author_decades = author_decade_frequencies(targets, cache, author_api)
    paper_tokens, paper_hits = newspaper_frequencies(targets, corpus_groups["kubhist2"], cache)
    paper_titles = newspaper_titles(corpus_groups["kubhist2"], cache)
    author_examples, paper_examples = workbook_source_counts(site)

    author_workbook = [
        (word, author_id, decade, count,
         f"https://litteraturbanken.se/författare/{quote(author_id)}"
         if author_id != "(Unknown author ID)" else "")
        for (word, author_id, decade), count in sorted(author_examples.items())
    ]
    newspaper = []
    for (paper, decade), total_tokens in sorted(paper_tokens.items()):
        for word in targets:
            count = paper_hits[(word, paper, decade)]
            examples = paper_examples[(word, paper, str(decade))]
            newspaper.append((word, paper, str(decade), count, total_tokens,
                              count * 1_000_000 / total_tokens if total_tokens else None,
                              examples, count - examples))

    # Per-newspaper API hits must reconcile exactly with the existing Korp plots.
    expected = {}
    with (ROOT / "plots" / "korp_mia_frequencies" / "decade_frequencies.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            if row["resource"] == "kubhist2":
                expected[(row["target"], row["decade"])] = int(row["absolute"])
    actual = Counter()
    for word, _, decade, count, _, _, _, _ in newspaper:
        actual[(word, decade)] += count
    for key, count in expected.items():
        if actual[key] != count:
            raise ValueError(f"Newspaper API breakdown does not match plot for {key}: {actual[key]} != {count}")

    csv_write(output / "author_frequencies.csv",
              ("word", "author", "api_absolute", "author_tokens", "api_per_million_author_tokens"),
              author_api)
    csv_write(output / "author_decade_frequencies.csv",
              ("word", "author", "decade", "api_absolute", "author_decade_tokens",
               "api_per_million_author_decade_tokens"), author_decades)
    csv_write(output / "workbook_author_examples.csv",
              ("word", "author_id", "decade", "workbook_examples", "author_url"),
              author_workbook)
    csv_write(output / "newspaper_frequencies.csv",
              ("word", "newspaper_id", "decade", "api_absolute", "newspaper_tokens",
               "api_per_million_newspaper_tokens", "workbook_examples", "difference_api_minus_workbook"),
              newspaper)
    data = {
        "words": targets,
        "newspaper_titles": paper_titles,
        "newspaper_corpora": {
            paper: [corpus for corpus in corpus_groups["kubhist2"] if newspaper_id(corpus) == paper]
            for paper in sorted(paper_titles)
        },
        "authors_api": author_api,
        "authors_api_decade": author_decades,
        "authors_workbook": author_workbook,
        "newspapers": newspaper,
    }
    (output / "source_breakdown.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    for filename in ("author_frequencies.csv", "author_decade_frequencies.csv",
                     "workbook_author_examples.csv",
                     "newspaper_frequencies.csv", "source_breakdown.json"):
        shutil.copy2(output / filename, site / "data" / filename)
    shutil.copy2(ROOT / "source_breakdown_viewer.html", site / "source-breakdown.html")
    print(f"Built source breakdown: {len(author_api):,} all-date and "
          f"{len(author_decades):,} dated Korp author rows, "
          f"{len(author_workbook):,} workbook author rows, "
          f"{len(newspaper):,} newspaper rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--site", type=Path, default=SITE)
    args = parser.parse_args()
    build(args.source, args.cache, args.output, args.site)
