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

"""Third-party embeds in Snopes articles.

Snopes turns embeds into players with JavaScript, which Suds strips, so
they rendered as empty boxes or bare quotes. Each embed is replaced before
the article is serialised:

- YouTube, tweets, TikTok and Reddit become an iframe to a self-hosted
  privacy frontend (Invidious, Nitter, ProxiTok, eddrit).
- Instagram and Facebook posts become a one-line link through Kittygram or
  Phice, which have no compact embed view.
- Anything else, or an embed whose frontend is not configured, becomes a
  labelled link to the original.

Either way the browser never loads anything from those sites by itself.
Only embeds are rewritten; links in the article text are left alone.
"""

import os
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


def frontend_url(var):
    """Base URL of a frontend from the environment; unset or empty = none"""
    value = os.environ.get(var, "").strip().rstrip("/")
    return value or None


INVIDIOUS = frontend_url("INVIDIOUS_URL")
NITTER = frontend_url("NITTER_URL")
PROXITOK = frontend_url("PROXITOK_URL")
EDDRIT = frontend_url("EDDRIT_URL")
KITTYGRAM = frontend_url("KITTYGRAM_URL")
PHICE = frontend_url("PHICE_URL")

# Iframes pointing here must not be routed through the image proxy
FRAMED_FRONTENDS = tuple(u + "/" for u in (INVIDIOUS, NITTER, PROXITOK, EDDRIT) if u)

YOUTUBE_ID = re.compile(r"youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{6,})")
TIKTOK_ID = re.compile(r"tiktok\.com/(?:embed/(?:v2/)?|@[^/]+/video/)([0-9]+)")
TWEET_ID = re.compile(r"(?:twitter|x)\.com/[^/]+/status/([0-9]+)")
INSTAGRAM_POST = re.compile(r"instagram\.com/(p|reel|tv)/([A-Za-z0-9_-]+)")
REDDIT_POST = re.compile(
    r"reddit\.com(/(?:r|user|u)/[^/]+/comments/[A-Za-z0-9]+)(?:/([^/?#]+))?")
# Facebook paths Phice serves under the same path
PHICE_PATH = re.compile(
    r"^/(?:[^/]+/(?:posts|videos)/[^/]+(?:/[^/]+)?/?"
    r"|reel/[^/]+/?|photo(?:\.php)?|permalink\.php|story\.php|watch"
    r"|groups/[^/]+/(?:posts|permalink)/[^/]+/?)$")

# Hit counters of syndicated articles: invisible images that only report
# the visit to a third party
TRACKING_PIXEL = re.compile(r"^(?:https?:)?//counter\.theconversation\.com/")

EMBED_SELECTOR = ", ".join([
    "iframe",
    "blockquote.twitter-tweet", "blockquote.twitter-video",
    "blockquote.instagram-media", "blockquote.instagram-media-lazy",
    "blockquote.tiktok-embed",
    "blockquote.reddit-embed-bq", "blockquote.reddit-card",
    "div.fb-post", "div.fb-video",
    # Tweets Snopes fills in with Twitter's script from the id alone
    "div.twitter_tweet_display_box",
])

_factory = BeautifulSoup("", "html.parser")


def _frame(kind, src):
    figure = _factory.new_tag("figure", attrs={"class": f"embed embed-{kind}"})
    figure.append(_factory.new_tag("iframe", attrs={
        "src": src, "loading": "lazy", "frameborder": "0", "allowfullscreen": ""}))
    return figure


def _link(label, url):
    paragraph = _factory.new_tag("p", attrs={"class": "embed-link"})
    paragraph.append(label + ": ")
    anchor = _factory.new_tag("a", attrs={
        "href": url, "rel": "nofollow noopener noreferrer"})
    anchor.string = url
    paragraph.append(anchor)
    return paragraph


def _absolute(url):
    return "https:" + url if url.startswith("//") else url


def _links(element):
    return [a.get("href", "") for a in element.find_all("a")]


def _youtube(video_id):
    if INVIDIOUS:
        return _frame("video", f"{INVIDIOUS}/embed/{video_id}")
    return _link("YouTube video", f"https://www.youtube.com/watch?v={video_id}")


def _tiktok(video_id):
    if PROXITOK:
        return _frame("tiktok", f"{PROXITOK}/embed/v2/{video_id}")
    return _link("TikTok video", f"https://www.tiktok.com/embed/v2/{video_id}")


def _instagram(kind, code):
    base = KITTYGRAM or "https://www.instagram.com"
    return _link("Instagram post", f"{base}/{kind}/{code}/")


def _facebook(href):
    url = urlparse(href)
    if not url.netloc.endswith("facebook.com"):
        return None
    path = url.path
    # Phice serves /photo and /watch without the trailing slash
    if path in ("/photo/", "/watch/"):
        path = path.rstrip("/")
    if PHICE and PHICE_PATH.match(path):
        # Query strings only carry ids for the .php, photo and watch routes
        keep_query = path.endswith(".php") or path in ("/photo", "/watch")
        target = PHICE + path + ("?" + url.query if keep_query and url.query else "")
        return _link("Facebook post", target)
    return _link("Facebook post", href)


def _iframe(element):
    src = _absolute(element.get("data-src") or element.get("src") or "")
    if not src:
        return None
    if (match := YOUTUBE_ID.search(src)):
        return _youtube(match.group(1))
    if (match := TIKTOK_ID.search(src)):
        return _tiktok(match.group(1))
    if (match := INSTAGRAM_POST.search(src)):
        return _instagram(match.group(1), match.group(2))
    if "facebook.com/plugins/" in src:
        href = parse_qs(urlparse(src).query).get("href", [""])[0]
        if href and (link := _facebook(href)):
            return link
    return _link("Embedded content", src)


def _tweet_by_id(tweet_id):
    if NITTER:
        return _frame("tweet", f"{NITTER}/i/status/{tweet_id}/embed")
    return _link("Tweet", f"https://x.com/i/status/{tweet_id}")


def _tweet(element):
    for href in _links(element):
        if (match := TWEET_ID.search(href)):
            if NITTER:
                return _tweet_by_id(match.group(1))
            return None  # the quote keeps the tweet's text and links
    return None


def _reddit(element):
    for href in _links(element):
        if (match := REDDIT_POST.search(href)):
            if not EDDRIT:
                return None  # the quote keeps its text and links
            path = match.group(1).replace("/u/", "/user/", 1)
            # eddrit needs the title segment; any placeholder works
            return _frame("reddit", f"{EDDRIT}{path}/{match.group(2) or '_'}/embed?theme=dark")
    return None


def _replacement(element):
    """New element for an embed, or None to leave it as it is"""
    classes = element.get("class") or []
    if element.name == "iframe":
        return _iframe(element)
    if "twitter-tweet" in classes or "twitter-video" in classes:
        return _tweet(element)
    if "instagram-media" in classes or "instagram-media-lazy" in classes:
        permalink = element.get("data-instgrm-permalink") or " ".join(_links(element))
        if (match := INSTAGRAM_POST.search(permalink)):
            return _instagram(match.group(1), match.group(2))
        return None
    if "tiktok-embed" in classes:
        video_id = element.get("data-video-id")
        if not video_id and (match := TIKTOK_ID.search(element.get("cite", ""))):
            video_id = match.group(1)
        return _tiktok(video_id) if video_id else None
    if "reddit-embed-bq" in classes or "reddit-card" in classes:
        return _reddit(element)
    if "twitter_tweet_display_box" in classes:
        # An empty box: the id is all there is, so without Nitter it
        # becomes a link
        tweet_id = element.get("data-tweet-id", "")
        return _tweet_by_id(tweet_id) if tweet_id.isdigit() else None
    if element.name == "div":  # fb-post, fb-video
        href = element.get("data-href", "")
        return _facebook(href) if href else None
    return None


def _lift(element):
    """Unwrap the divs and paragraphs that only hold this element: callers
    that drop every <div> of an article keep the embed, and no <figure> or
    link paragraph ends up inside a <p>, which browsers split into empty
    paragraphs"""
    parent = element.parent
    while parent is not None and parent.name in ("div", "p") and parent.get("id") != "article-content":
        siblings = [c for c in parent.contents if c is not element and str(c).strip()]
        if siblings:
            break
        grandparent = parent.parent
        parent.unwrap()
        parent = grandparent


def replace_embeds(article):
    """Replace the embeds of an article element in place, and drop the
    tracking pixels of syndicated articles"""
    for img in article.find_all("img"):
        if TRACKING_PIXEL.match(img.get("data-src") or img.get("src") or ""):
            img.decompose()
    for element in article.select(EMBED_SELECTOR):
        if element.parent is None:  # inside an embed replaced earlier
            continue
        new = _replacement(element)
        if new is None:
            continue
        element.replace_with(new)
        _lift(new)
