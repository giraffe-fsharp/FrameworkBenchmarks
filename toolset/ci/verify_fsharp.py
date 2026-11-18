#!/usr/bin/env python3

import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class FortuneParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            raise ValueError("Fortunes contain an unescaped script element")
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td":
            self.row.append("".join(self.cell))
            self.cell = None
        elif tag == "tr" and self.row:
            self.rows.append((int(self.row[0]), self.row[1]))


def expected_fortunes():
    sql = Path("toolset/databases/postgres/create-postgres.sql").read_text(
        encoding="utf-8"
    )
    rows = [
        (int(id_), message.replace("''", "'"))
        for id_, message in re.findall(
            r"INSERT INTO Fortune \(id, message\) VALUES \((\d+), '((?:[^']|'')*)'\);",
            sql,
        )
    ]
    if len(rows) != 12:
        raise ValueError("Expected the 12 canonical benchmark fortunes")
    rows.append((0, "Additional fortune added at request time."))
    return sorted(rows, key=lambda row: row[1])


def verify_response(kind, body, content_type, fortunes):
    expected_type = {
        "json": "application/json",
        "plaintext": "text/plain",
        "fortune": "text/html",
    }[kind]
    if content_type.split(";")[0].strip().lower() != expected_type:
        raise ValueError(f"{kind}: unexpected Content-Type {content_type!r}")
    if kind == "json":
        if json.loads(body) != {"message": "Hello, World!"}:
            raise ValueError("Unexpected JSON response")
    elif kind == "plaintext":
        if body.strip() != "Hello, World!":
            raise ValueError("Unexpected plaintext response")
    else:
        parser = FortuneParser()
        parser.feed(body)
        if parser.rows != fortunes:
            raise ValueError(f"Incorrect, missing or unsorted fortunes: {parser.rows!r}")


def verify(framework_dir, variant, base_url):
    config = json.loads((framework_dir / "benchmark_config.json").read_text())
    settings = next(test[variant] for test in config["tests"] if variant in test)
    endpoints = [
        (kind, settings[kind + "_url"])
        for kind in ("plaintext", "json", "fortune")
        if kind + "_url" in settings
    ]
    if not endpoints:
        raise ValueError("No configured endpoints to verify")

    deadline = time.monotonic() + 60
    readiness_url = base_url + endpoints[0][1]
    while True:
        try:
            with urlopen(readiness_url, timeout=5):
                break
        except HTTPError:
            raise
        except (URLError, TimeoutError) as error:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Benchmark did not start: {readiness_url}") from error
            time.sleep(1)

    fortunes = expected_fortunes() if "fortune_url" in settings else []
    for kind, path in endpoints:
        with urlopen(base_url + path, timeout=10) as response:
            verify_response(
                kind,
                response.read().decode("utf-8"),
                response.headers.get("Content-Type", ""),
                fortunes,
            )
        print(f"PASS {framework_dir.name}/{variant}: {path}", flush=True)


if __name__ == "__main__":
    verify(Path(sys.argv[1]), sys.argv[2], sys.argv[3].rstrip("/"))
