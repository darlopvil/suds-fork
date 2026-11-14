# Suds

A privacy-respecting frontend to [Snopes](https://www.snopes.com): read fact-checks and news without your browser ever talking to Snopes, its ad networks or the social sites it embeds, and without JavaScript.

This is a fork of [Suds](https://codeberg.org/cobra/Suds) by Skylar Astaroth.

## What it does

- **Fact-checks** (`/fact-check/...`): claim, rating and context, the full article, and a link to the explanation of each rating (`/fact-check-ratings/`).
- **News and other articles**: news, articles, listicles (`/list/`), notes, trackers (`/tracker/`, with every row's details shown), live updates (`/live/`, with their timestamps and a permalink per update) and old posts under `/<year>/<month>/<day>/`.
- **Collections** (`/collections/...`): their introduction and the list of articles in them.
- **Lists**: latest, top, fact-checks, news, articles, classics, listicles, collections, categories, ratings, authors and tags, with page navigation.
- **RSS feeds**: every list has one at `<list>/feed/` (for example `/tag/elon-musk/feed/`), announced to feed readers on the list page.
- **Search** (`/search/?q=`): over a local index of Snopes' articles (see below).
- **Archives** (`/sitemap/`) and a random fact-check (`/random/`).

Replacing `www.snopes.com` with the instance's domain in any Snopes link opens the same page, and every article and list has a "View on Snopes" link back to the original.

## Changes from the original

### New features

- **Search** works again. Snopes moved its search to Google's client-side search, so the original's search page failed with a 500; Suds now searches a local index of Snopes' articles (see below).
- **New sections**: listicles (`/list/`), notes, trackers (`/tracker/`), live updates (`/live/`) and old posts under `/<year>/<month>/<day>/`, which all answered 404.
- **RSS feeds** for every list at `<list>/feed/`, built from the list Suds shows (Snopes' own feeds only match the page for some lists), with the thumbnail, author, summary and date of each item, and announced to feed readers on the list page.
- **Embeds** through self-hosted privacy frontends: YouTube by Invidious, tweets by Nitter, TikToks by ProxiTok, Reddit posts by eddrit, Instagram posts by Kittygram and Facebook posts by Phice, as sized iframes. About half of recent articles embed a post; without a configured frontend, each embed becomes a labelled link to the original.
- **Fact check ratings page** (`/fact-check-ratings/`) with the definition of every rating. The "About this rating" link on each fact-check leads to the definition of its own rating.
- **"View on Snopes"** link on every article and list.
- **Trackers** show every row's details (Snopes unfolds them with JavaScript), and **live updates** show their timestamps and a permalink to each update instead of a frozen "786 days ago" and a "copy link" button.

### Bug fixes

- Fact-checks without a rating and categories (moved by Snopes) render again.
- Listicle items, tracker tables, quotes, notes and collection text are no longer dropped: the parser removed every `<div>` of an article, about 106,000 words in 182 sampled pages.
- Collections show their own title and date instead of those of the last article in their list.
- Broken images went from 151 to 4 in the sampled articles (those 4 are broken on Snopes too), legacy image paths included, and links to full-size images work.
- List pagination shows the current page, and no longer offers a "Previous" on the first page or a "Next" past the last.
- Unknown pages answer 404 instead of a page that looked found (unknown tags answered 500), and other failures become proper error pages (400, 404, 502, 503) instead of bare 500s.
- Redirects keep their query string, and fact-checks are requested with their canonical URL (the other one cost a redirect and, for a while, looped).
- Old articles' markup is cleaned up: empty padding paragraphs, obsolete fonts, quote boxes and list items that sat outside their list.
- Snopes' collection navigation, ad slots and "Link Copied!" leftovers are left out, and the rating card no longer turns the whole rating into one link.
- Templates validate as HTML (382 errors in the W3C validator on ten pages, now none): language, alt texts, a malformed search field, obsolete tags and invalid styles.

### Privacy and security

- The HTML taken from Snopes is reduced to an allowlist of tags, attributes, inline styles and URL schemes, so no script, event handler, tracker, form or third-party iframe reaches the page.
- The image proxy only fetches from known hosts, only serves images and adds a sandboxing Content-Security-Policy, so a proxied file can never run as a page.
- Requests to Snopes carry no cookies, and the browser never contacts Snopes or the sites behind the embeds.
- Upstream URLs are built from validated paths and parameters, so a request can't make Suds fetch other pages or hosts.

### Performance and deployment

- Connections to Snopes are reused (a page fetch went from 0.46 s to 0.10 s at the median), and a hung request no longer holds a worker (5 s connect and 10 s read timeouts).
- Images keep Snopes' cache headers, so browsers cache them instead of fetching them on every visit.
- The Docker image is built from local source, runs as an unprivileged user, keeps the search index on a volume and stops cleanly.

The commit history explains each change in detail.

## About search

Snopes' own search is now Google's client-side search, which only answers browsers running Google's script. Suds searches a local index instead, built from the monthly sitemaps Snopes publishes (about 33,000 articles). Results match the words of each article's address, newest first; their titles come from those addresses too, since the sitemaps carry no titles.

The index is built when the container starts (about 20 seconds) and refreshed in the background once a day. Until the first build finishes, the search page answers 503 and asks to try again shortly. The index lives in `SUDS_DATA_DIR`, so keep that directory on a volume to avoid rebuilding it after every restart.

## Running

### Dependencies

Python 3.10 or later with Flask, Werkzeug, Beautiful Soup and requests (`pip3 install -r requirements.txt`), and uWSGI with its Python 3 plugin for production (`sudo apt install uwsgi uwsgi-plugin-python3` on Debian or Ubuntu).

### Bare metal

1. Install the dependencies.
2. `git clone https://github.com/darlopvil/suds-fork.git && cd suds-fork`
3. `python3 search_index.py` to build the search index.
4. `uwsgi --plugin python3 --http-socket 0.0.0.0:8001 --wsgi-file main.py --callable app --processes 4 --threads 2`
5. Point your reverse proxy at http://localhost:8001.

For development, `python3 main.py` serves the app on http://localhost:8001.

### Docker

1. Clone the repository and `cd` into it.
2. `cp docker-compose.yml.example docker-compose.yml` and adapt it to your setup. `docker-compose.yml` is ignored by git, so your setup stays out of the repository.
3. `docker compose up -d --build`

Run `docker compose up -d --build` again after pulling changes.

### Reverse proxy

Feeds need absolute links, so Suds builds them from the request it receives. Behind a reverse proxy that terminates TLS, the proxy must send `X-Forwarded-Proto` (most do by default); Suds trusts it from one proxy.

### Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUDS_SOURCE_URL` | this repository | Where the "Source code" link in the footer points. If you run a modified copy, the AGPL requires you to offer its source to your users, so point this at it. |
| `SUDS_DATA_DIR` | `data/` next to the code (`/data` in Docker) | Where the search index is stored. It must be writable. |
| `INVIDIOUS_URL` | unset | Invidious instance for YouTube embeds. |
| `NITTER_URL` | unset | Nitter instance for tweets. |
| `PROXITOK_URL` | unset | ProxiTok instance for TikToks. |
| `EDDRIT_URL` | unset | eddrit instance for Reddit posts. |
| `KITTYGRAM_URL` | unset | Kittygram instance for Instagram posts. |
| `PHICE_URL` | unset | Phice instance for Facebook posts. |

## License

Same license as the original: GNU Affero General Public License v3 or later. See [LICENSE](LICENSE).
