## Copyright (C) 2026 darlopvil
##
## This file is part of Suds.
##
## Suds is free software: you can redistribute it and/or modify it under the
## terms of the GNU Affero General Public License as published by the Free
## Software Foundation, either version 3 of the License, or (at your option) any
## later version.
##
## This program is distributed in the hope that it will be useful, but WITHOUT
## ANY WARRANTY; without even the implied warranty of  MERCHANTABILITY or
## FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License
## for more details.
##
## You should have received a copy of the GNU Affero General Public License
## along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Local search index built from Snopes' public sitemaps.

Snopes renders its search results in the browser through Google Programmable
Search, so its search page has no results to scrape. Instead, every article
URL listed in the monthly sitemaps is indexed locally and matched against the
words of its slug. Search queries never leave the instance.

The index is stored as a JSON file so it survives restarts and is shared by
all uWSGI workers. Each worker reloads it when the file changes.

Nobody waits for Snopes:
- Run as a script (`python3 search_index.py`) before the web server starts,
  it builds the index on first deployment and refreshes it if it is stale.
- While serving, a stale index triggers a refresh in a background thread
  and the request is answered with the current index.
Refreshes are guarded by a file lock, so only one process talks to Snopes at
a time.
"""

import fcntl
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

# Where the index is stored; it must be writable and persistent
DATA_DIR = os.environ.get(
    "SUDS_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

SITEMAP_INDEX = "https://media.snopes.com/sitemaps/sitemap-index.xml"
MONTHLY_SITEMAP = re.compile(r"/sitemap-articles-(\d{4})-(\d{2})\.xml$")
LOC = re.compile(r"<loc>\s*https://www\.snopes\.com(/[^<\s]*)\s*</loc>")

# Sections Suds has routes for, with their display label
SECTIONS = {
    "fact-check": "Fact Check",
    "news": "News",
    "collections": "Collection",
    "articles": "Article",
}

# Snopes adds 6-7 articles per day, so one refresh a day is enough
REFRESH_SECONDS = 24 * 60 * 60
# After a failed refresh, retry after this long instead of on every search
RETRY_SECONDS = 60 * 60
# Newest monthly sitemaps re-fetched on every refresh (covers month boundaries)
RECENT_SITEMAPS = 2
FETCH_WORKERS = 6
FETCH_TIMEOUT = 20
FETCH_ATTEMPTS = 2

# Words dropped from queries because slugs rarely contain them
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does",
    "for", "from", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "was", "were", "with",
}

# Shorter words only match whole slug words; as prefixes they match almost
# everything (a single letter matched 2,090 articles)
MIN_PREFIX = 3

WORD = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return WORD.findall(text.lower())


class SearchIndex:
    def __init__(self, data_dir=DATA_DIR):
        self.path = os.path.join(data_dir, "search-index.json")
        self.lock_path = os.path.join(data_dir, "search-index.lock")
        self.data_dir = data_dir
        self._mtime = None
        self._entries = []
        # One background refresh per process at a time
        self._refreshing = threading.Lock()

    # Building and refreshing

    def _fetch(self, url):
        for attempt in range(FETCH_ATTEMPTS):
            try:
                response = requests.get(url, timeout=FETCH_TIMEOUT)
                response.raise_for_status()
                return response.text
            except requests.RequestException:
                if attempt == FETCH_ATTEMPTS - 1:
                    raise

    def _sitemap_entries(self, url):
        year, month = MONTHLY_SITEMAP.search(url).groups()
        entries = []
        for path in LOC.findall(self._fetch(url)):
            if path.strip("/").split("/")[0] in SECTIONS:
                entries.append([path, f"{year}-{month}"])
        return url, entries

    def _refresh(self, sitemaps):
        """Fetch new and recent monthly sitemaps; reuse the rest."""
        started = time.monotonic()
        listed = [m.group(0) for m in re.finditer(
            r"https://media\.snopes\.com/sitemaps/sitemap-articles-\d{4}-\d{2}\.xml",
            self._fetch(SITEMAP_INDEX))]
        listed = sorted(set(listed))
        recent = set(listed[-RECENT_SITEMAPS:])
        todo = [url for url in listed if url not in sitemaps or url in recent]

        with ThreadPoolExecutor(FETCH_WORKERS) as pool:
            fetched = dict(pool.map(self._sitemap_entries, todo))

        updated = {url: fetched.get(url, sitemaps.get(url)) for url in listed}
        self._write({"built": time.time(), "sitemaps": updated})
        count = sum(len(entries) for entries in updated.values())
        print(f"search index: fetched {len(todo)} of {len(listed)} sitemaps, "
              f"{count} articles, {time.monotonic() - started:.1f}s",
              file=sys.stderr, flush=True)

    def _write(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, self.path)

    def _read(self):
        with open(self.path) as f:
            return json.load(f)

    def _age(self):
        try:
            return time.time() - os.stat(self.path).st_mtime
        except FileNotFoundError:
            return None

    def update_if_needed(self):
        """Build or refresh the index file if it is missing or stale.

        Skips the work if another process holds the lock or has just
        refreshed it. Returns True if the index was updated.
        """
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.lock_path, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            try:
                age = self._age()
                if age is not None and age < REFRESH_SECONDS:
                    return False
                sitemaps = self._read()["sitemaps"] if age is not None else {}
                self._refresh(sitemaps)
                return True
            except (requests.RequestException, OSError, ValueError) as e:
                print(f"search index: refresh failed: {e!r}",
                      file=sys.stderr, flush=True)
                if os.path.exists(self.path):
                    # Keep serving the previous index; retry later
                    retry_at = time.time() - REFRESH_SECONDS + RETRY_SECONDS
                    os.utime(self.path, (time.time(), retry_at))
                return False
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _update_in_background(self):
        if not self._refreshing.acquire(blocking=False):
            return

        def run():
            try:
                self.update_if_needed()
            finally:
                self._refreshing.release()

        threading.Thread(target=run, name="search-index-update",
                         daemon=True).start()

    def _ensure_fresh(self):
        """Return False if there is no index to search yet.

        A missing or stale index is updated in the background; the caller
        never waits for Snopes.
        """
        age = self._age()
        if age is None or age >= REFRESH_SECONDS:
            self._update_in_background()
        return age is not None

    def _load(self):
        mtime = os.stat(self.path).st_mtime
        if mtime == self._mtime:
            return
        entries = []
        seen = set()
        for sitemap in self._read()["sitemaps"].values():
            for path, month in sitemap:
                if path in seen:
                    continue
                seen.add(path)
                parts = path.strip("/").split("/")
                slug = parts[-1]
                entries.append((path, SECTIONS[parts[0]], month,
                                slug, frozenset(tokenize(slug))))
        self._entries = entries
        self._mtime = mtime

    # Searching

    def search(self, query):
        """Return matching articles, best first, or None if there is no
        index yet."""
        if not self._ensure_fresh():
            return None
        self._load()

        words = tokenize(query)
        meaningful = [w for w in words if w not in STOP_WORDS]
        words = list(dict.fromkeys(meaningful or words))
        if not words:
            return []

        matches = []
        for path, section, month, slug, tokens in self._entries:
            score = 0
            for word in words:
                if word in tokens:
                    score += 2
                elif len(word) >= MIN_PREFIX and any(token.startswith(word) for token in tokens):
                    score += 1
                else:
                    break
            else:
                matches.append((score, month, path, section, slug))

        # Exact word matches first, then newest
        matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
        return [{
            "path": path,
            "section": section,
            "published": month,
            "title": slug.replace("-", " ").replace("_", " ").capitalize(),
        } for score, month, path, section, slug in matches]


if __name__ == "__main__":
    # Run before the web server starts, so no visitor waits for the build
    SearchIndex().update_if_needed()
