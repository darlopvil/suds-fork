#!/usr/bin/env python

## Copyright (C) 2023-2025 Skylar Astaroth <cobra@vern.cc>
##
## This file is part of MeMe
##
## MeMe is free software: you can redistribute it and/or modify it under the
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

from flask import Flask, render_template, request, redirect, Response, stream_with_context, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.routing import BaseConverter
import requests
import re
import os
import http.cookiejar
from bs4 import BeautifulSoup
from copy import copy
from search_index import SearchIndex
from embeds import replace_embeds, FRAMED_FRONTENDS

def remove_all(tag, selector):
    """Remove every element matching selector; Snopes omits some of them"""
    for element in tag.select(selector):
        element.decompose()

# Elements that only format text: a paragraph made of these and blank
# space shows nothing
FORMATTING_TAGS = {"br", "font", "span", "b", "strong", "i", "em", "u"}

def remove_blank_paragraphs(article):
    """Legacy articles pad their text with dozens of empty paragraphs
    (<p>&nbsp;</p>, <p><br><br>&nbsp;</p>): 54 in a single fact-check.
    Paragraphs holding anything else (embeds, links...) are kept."""
    for p in article.find_all("p"):
        if getattr(p, "decomposed", False):
            continue
        if p.get_text().replace("\xa0", "").strip():
            continue
        if all(tag.name in FORMATTING_TAGS for tag in p.find_all(True)):
            p.decompose()

def cover_image(soup):
    """Cover image, alt text and caption; empty when Snopes only shows its
    generic placeholder (default_thumb), which says nothing about the article"""
    cover = soup.find(attrs={"id": ["cover-main"]})
    src = cover.get("src") or ""
    if "/default_thumb" in src:
        return "", "", ""
    desc = soup.find(attrs={"class": ["article_img_desc"]})
    caption = desc.select("span")[0].text if desc is not None and desc.select("span") != [] else ""
    return src, cover.get("alt"), caption

def rating_block(rating):
    """Return the rating block as HTML, or '' when Snopes ships it empty
    (older fact-checks have the container with no claim and no rating)"""
    if rating is None:
        return ''
    claim = rating.select_one(".claim_cont")
    has_claim = claim is not None and claim.get_text(strip=True) != ''
    if not has_claim and rating.select_one(".rating_wrapper") is None:
        return ''
    remove_all(rating, "svg")
    remove_all(rating, "img")
    return str(rating).replace("https://www.snopes.com", '')

search_index = SearchIndex()
SEARCH_RESULTS_PER_PAGE = 20

SNOPES = "https://www.snopes.com"
# Snopes answers in about half a second (0.52 s at most over 53 measured
# requests); these limits only stop a hung request from holding a worker
UPSTREAM_TIMEOUT = (5, 10)  # connect, read (seconds)

# Reusing connections cut the median page fetch from 0.46 s to 0.10 s.
# Cookies are refused, so every request still carries no state.
upstream = requests.Session()
upstream.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))

def fetch(url, **kwargs):
    """GET from Snopes through the shared connection pool, with timeouts"""
    return upstream.get(url, timeout=UPSTREAM_TIMEOUT, **kwargs)

# src= attributes go through the image proxy, except the iframes to privacy
# frontends that replace embeds
SRC_TO_PROXY = re.compile(r'(src=")' + (
    "(?!" + "|".join(re.escape(u) for u in FRAMED_FRONTENDS) + ")" if FRAMED_FRONTENDS else ""))

def proxy_sources(html):
    return SRC_TO_PROXY.sub(r"\1/proxy/?url=", html)

IMAGE_FILE = re.compile(r"\.(?:jpe?g|png|gif|webp)(?:[?#]|$)", re.I)

def proxy_image_links(article):
    """Links that wrap an image and open the full-size file go through the
    image proxy, wherever they sit in the article"""
    for a in article.select("a:has(img)"):
        href = a.get("href", "")
        if IMAGE_FILE.search(href):
            a["href"] = "/proxy/?url=" + href

def pagination(soup):
    """Current page and number of pages of a list, from Snopes' page form
    (its value and max); (None, None) when the list has no pages"""
    field = soup.select_one("form.pagenumber input[name=pagenum]")
    value, total = (field.get("value", ""), field.get("max", "")) if field else ("", "")
    if value.isdigit() and total.isdigit():
        return int(value), int(total)
    return None, None

def secondary_list(path, params=None):
    data = fetch(SNOPES + "/" + path, params=params)

    if data.status_code == 200:
        soup = BeautifulSoup(data.text, "html.parser")

        # Tags
        tags = []
        for tag in soup.select(".tag_wrapper"):
            tag.a["href"] = tag.a["href"].replace("https://www.snopes.com", '')
            tag_link = tag.a["href"]
            tag_name = tag.text
            tags.append([tag_link, tag_name])

        # Header
        article_type = soup.find(attrs={"class": ["section_title"]})
        if (article_type.find("svg") != None):
            article_type.find("svg").decompose()
        head = article_type.find("span")
        if head != None:
            head = head.text
        else:
            head = article_type.text
        article_type_head = soup.find(attrs={"class": ["img_title_wrap"]})
        description = soup.find(attrs={"class": ["desc_cont_wrap"]}).text

        # Article list
        article_list = []
        for div in soup.select(".article_wrapper"):
            div.a["href"] = div.a["href"].replace("https://www.snopes.com", '')
            link = div.a["href"]
            image = "/proxy/?url=" + div.select("img")[0].get("data-src")
            alt = div.select("img")[0].get("alt")
            if len(list(div.select(".article_text"))) != 0:
                text = div.find(attrs={"class": ["article_text"]})
                title = text.select("h3")[0].text
                author = ''
                if text.select(".article_author") != []:
                    author = text.find(attrs={"class": ["article_author"]}).text
                date = text.find(attrs={"class": ["article_date"]}).text
                byline = text.find(attrs={"class": ["article_byline"]}).text
                article_list.append([link, image, alt, title, author, date, byline])

        page, pages = pagination(soup)

        return [article_type, description, article_list, page, pages, tags, head]

    else:
        return data.status_code


def article_list(path, params=None):
    data = fetch(SNOPES + "/" + path, params=params)

    if data.status_code == 200:
        soup = BeautifulSoup(data.text, "html.parser")

        # Tags
        tags = []
        for tag in soup.select(".tag_wrapper"):
            tag.a["href"] = tag.a["href"].replace("https://www.snopes.com", '')
            tag_link = tag.a["href"]
            tag_name = tag.text
            tags.append([tag_link, tag_name])

        # Header
        article_type = soup.find(attrs={"class": ["section_title"]})
        remove_all(article_type, "svg")
        head = article_type.find("span")
        if head != None:
            head = head.text
        else:
            head = article_type.text
        article_type_head = soup.find(attrs={"class": ["img_title_wrap"]})
        description = soup.find(attrs={"class": ["page_desc_wrapper"]}).text

        # Article list
        article_list = []
        for div in soup.select(".article_wrapper"):
            div.a["href"] = div.a["href"].replace("https://www.snopes.com", '')
            link = div.a["href"]
            image = "/proxy/?url=" + div.select("img")[0].get("data-src")
            alt = div.select("img")[0].get("alt")
            if len(list(div.select(".article_text"))) != 0:
                text = div.find(attrs={"class": ["article_text"]})
                title = text.select("h3")[0].text
                author = text.find(attrs={"class": ["article_author"]}).text
                date = text.find(attrs={"class": ["article_date"]}).text
                byline = text.find(attrs={"class": ["article_byline"]}).text
                article_list.append([link, image, alt, title, author, date, byline])

        page, pages = pagination(soup)

        return [article_type, description, article_list, page, pages, tags, head]

    else:
        return data.status_code


LIVE_UPDATE_LINK = re.compile(r"copy_live_update_link\('(live_update_\d+)'\)")

def live_updates(article):
    """Make live updates readable without JavaScript.

    Snopes prints each update's age ("786 days ago", frozen when the page is
    fetched) and keeps the timestamps in title attributes; the link icon only
    copies a permalink to the clipboard and shows "Link Copied!".
    """
    for date in article.select("div.template_date"):
        edited = date.select_one("span.live_update_time")
        text = date.get("title", "").removeprefix("Published: ")[:16]
        if edited:
            changed = edited.get("title", "").removeprefix("Edited: ")[:16]
            if changed != text:
                text += " · edited " + changed
        date.clear()
        date.string = text
        del date["title"]
    for link in article.select("a.live_link"):
        target = LIVE_UPDATE_LINK.search(link.get("onclick", ""))
        if target:
            link["href"] = "#" + target.group(1)
            link["title"] = "Link to this update"
        else:
            del link["href"]
        del link["onclick"]
        remove_all(link, "span.copy_link_text")

def news(path):
    data = fetch(SNOPES + "/" + path)

    if data.status_code == 200:
        soup = BeautifulSoup(data.text, "html.parser")

        # Header
        article_type = soup.find(attrs={"class": ["section_title"]})
        remove_all(article_type, "svg")
        title_container = soup.find(attrs={"class": ["title-container"]})
        title = title_container.select("h1")[0].text
        subtitle = title_container.select("h2")[0].text
        author_container = title_container.find(attrs={"class": ["author_info_wrapper"]})
        author_button = author_container.select("h3 a")[0]
        author_link = author_button.get('href')
        author = author_button.text
        date = author_container.find(attrs={"class": ["published_date"]}).text
        
        # Cover image
        cover, cover_alt, cover_desc = cover_image(soup)

        # Article
        article = soup.find(attrs={"id": ["article-content"]})
        replace_embeds(article)

        # Only ad slots go: other divs hold content (listicle items, tracker
        # tables, quotes, notes), about 106,000 words in 182 sampled pages
        for div in article.select("div.snopesad, div.proper-ad-unit"): div.decompose()
        for div in article.select("div"): del div["style"]
        for script in article.select("script"): script.decompose()
        # Tracker details are unfolded with JavaScript: show them all
        for row in article.select("tr.hidden_row"): del row["style"]
        live_updates(article)
        for field in article.select("input[type=hidden]"): field.decompose()

        remove_blank_paragraphs(article)
        proxy_image_links(article)
        article = proxy_sources(str(article))
        article = article.replace("https://www.snopes.com", '')

        # Author bio
        author_bio = soup.select("div.author_bio p")[0].text

        return [article_type, title, subtitle, author.strip(), author_link, date, cover, cover_alt, cover_desc, article, author_bio]
    else:
        return data.status_code

def fact_check(path):
    # With the trailing slash: without it Snopes answers with a redirect
    data = fetch(SNOPES + "/fact-check/" + path + "/")

    if data.status_code == 200:
        soup = BeautifulSoup(data.text, "html.parser")

        # Header
        article_type = soup.find(attrs={"class": ["section_title"]})
        remove_all(article_type, "svg")
        article_type = article_type.text
        title_container = soup.find(attrs={"class": ["title-container"]})
        title = title_container.select("h1")[0].text
        subtitle = title_container.select("h2")[0].text
        author_container = title_container.find(attrs={"class": ["author_info_wrapper"]})
        author_button = author_container.select("h3 a")[0]
        author_link = author_button.get('href')
        author = author_button.text
        date = author_container.find(attrs={"class": ["published_date"]}).text
        
        # Cover image
        cover, cover_alt, cover_desc = cover_image(soup)

        # Article
        article = soup.find(attrs={"id": ["article-content"]})
        replace_embeds(article)
        rating = copy(article.find(attrs={"id": ["fact_check_rating_container"]}))
        
        for div in article.select("div.snopesad"): div.decompose()
        for div in article.select("div"): del div["style"]
        for script in article.select("script"): script.decompose()
        if article.find("section") != None:
            article.find("section").decompose()

        remove_blank_paragraphs(article)
        proxy_image_links(article)
        article = proxy_sources(str(article))
        article = article.replace("https://www.snopes.com", '')

        rating = rating_block(rating)

        # Author bio
        author_bio = soup.select("div.author_bio p")[0].text

        return [article_type, title, subtitle, author.strip(), author_link, date, cover, cover_alt, cover_desc, rating, article, author_bio]
    else:
        return data.status_code

app = Flask(__name__, template_folder="templates", static_folder="static")

# AGPL-3.0 section 13: users of a modified version running on a network must
# be offered its source. Deployments of other forks point this to their own.
app.jinja_env.globals["source_url"] = os.environ.get("SUDS_SOURCE_URL", "https://github.com/darlopvil/suds-fork")

class SlugConverter(BaseConverter):
    """A URL segment as Snopes writes them (all 32,852 article URLs in its
    sitemaps use only these characters). Anything else is a 404 here
    instead of being forwarded to Snopes."""
    regex = r"[A-Za-z0-9_-]+"

app.url_map.converters["slug"] = SlugConverter

def page_param():
    """Forward ?pagenum= to Snopes only when it is a positive integer"""
    value = request.args.get('pagenum', '')
    if value.isascii() and value.isdigit() and int(value) > 0:
        return {"pagenum": int(value)}
    return {}

ERROR_MESSAGES = {
    400: "The request was malformed",
    404: "This resource cannot be found",
    500: "Something went wrong on this instance",
    502: "Snopes could not be reached or returned an error",
}

def error_page(code, message=None):
    message = message or ERROR_MESSAGES.get(code, "")
    return Response(render_template("error.html", code=code, message=message), code)

def upstream_error(status):
    """Answer a non-200 status from Snopes: its 404s are ours too, any
    other status is a bad gateway"""
    return error_page(404 if status == 404 else 502)

@app.route('/fact-check/')
def route_fact_check_list():
    data = article_list("fact-check/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/category/<slug:category>/')
def route_category(category):
    data = secondary_list(f"category/{category}/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

# Snopes moved categories to /category/<name>/ and answers 404 on the old
# per-section paths; keep old links working
@app.route('/fact-check/category/<slug:category>/')
@app.route('/news/category/<slug:category>/')
def route_old_category(category):
    return redirect(url_for('route_category', category=category, **page_param()), 301)

@app.route('/fact-check/rating/<slug:rating>/')
def route_fact_check_rating(rating):
    data = secondary_list(f"fact-check/rating/{rating}/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/latest/')
def route_latest():
    data = article_list("latest/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/top/')
def route_top():
    data = article_list("top/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/news/')
def route_news_list():
    data = article_list("news/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)


@app.route('/articles/')
def route_articles():
    data = article_list("articles/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/classics/')
def route_classics():
    data = article_list("classics/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/listicles/')
def route_listicles():
    data = secondary_list("listicles/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/news/<slug:year>/<slug:month>/<slug:day>/<slug:article>/')
def route_news(year, month, day, article):
    data = news(f"news/{year}/{month}/{day}/{article}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("news.html", data=data)

# Old posts at /<YYYY>/<MM>/<DD>/<slug>/ and the listicle, notes, tracker
# and live update sections; the news parser reads all of them
@app.route('/<int(fixed_digits=4):year>/<int(fixed_digits=2):month>/<int(fixed_digits=2):day>/<slug:article>/')
def route_dated_post(year, month, day, article):
    data = news(f"{year:04d}/{month:02d}/{day:02d}/{article}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("news.html", data=data)

@app.route('/<any(list, notes, tracker, live):section>/<slug:article>/')
def route_section_article(section, article):
    data = news(f"{section}/{article}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("news.html", data=data)

@app.route('/articles/<slug:article_id>/<slug:article>/')
def route_article(article_id, article):
    data = news(f"articles/{article_id}/{article}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("news.html", data=data)

@app.route('/fact-check/<slug:article>/')
def route_fact_check(article):
    data = fact_check(article)
    if type(data) == int:
        return upstream_error(data)
    return render_template("fact-check.html", data=data)

@app.route('/author/<slug:author>/')
def route_author(author):
    data = secondary_list(f"author/{author}/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/tag/<slug:tag>/')
def route_tag(tag):
    data = secondary_list(f"tag/{tag}/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/collections/')
def route_collections():
    data = secondary_list("collections/", page_param())
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/collections/<slug:collection>/')
def route_collection(collection):
    data = fetch(f"{SNOPES}/collections/{collection}/")
    print(data)
    if data.status_code != 200:
        return upstream_error(data.status_code)
    soup = BeautifulSoup(data.text, "html.parser")

    # Header
    article_type = soup.find(attrs={"class": ["section_title"]})
    remove_all(article_type, "svg")
    article_type = article_type.text
    title_container = soup.find(attrs={"class": ["title-container"]})
    title = title_container.select("h1")[0].text
    subtitle = title_container.select("h2")[0].text
    author_container = title_container.find(attrs={"class": ["author_info_wrapper"]})
    author_button = author_container.select("h3 a")[0]
    author_link = author_button.get('href')
    author = author_button.text
    date = author_container.find(attrs={"class": ["published_date"]}).text

    # Cover image
    cover, cover_alt, cover_desc = cover_image(soup)

    # Article
    article = soup.find(attrs={"id": ["article-content"]})
    replace_embeds(article)
    article_copy = copy(article)

    # The list of articles is rendered from the copy and the collection
    # navigation is not content; other divs are (listicle items, alerts,
    # image captions), as in news()
    for div in article.select("div.article_wrapper, div.next_prev_wrapper, div.collections_number, "
                              "div.snopesad, div.proper-ad-unit"): div.decompose()
    for div in article.select("div"): del div["style"]
    for script in article.select("script"): script.decompose()

    remove_blank_paragraphs(article)
    proxy_image_links(article)
    article = proxy_sources(str(article))

    # Author bio
    author_bio = soup.select("div.author_bio p")[0].text

    # Article list
    article_list = []
    for div in article_copy.select(".article_wrapper"):
        div.a["href"] = div.a["href"].replace("https://www.snopes.com", '')
        link = div.a["href"]
        image = "/proxy/?url=" + div.select("img")[0].get("data-src")
        alt = div.select("img")[0].get("alt")
        if len(list(div.select(".article_text"))) != 0:
            # Own names: title and date are the collection's
            text = div.find(attrs={"class": ["article_text"]})
            item_title = text.select("h3")[0].text
            item_date = text.find(attrs={"class": ["article_date"]}).text
            byline = text.find(attrs={"class": ["article_byline"]}).text
            article_list.append([link, image, alt, item_title, item_date, byline])


    return render_template("collection.html", data=[article_type, title, subtitle, author_link, str(author).strip(), date, cover, cover_alt, cover_desc, article, author_bio, article_list])

@app.route('/search/')
def route_search():
    # Snopes renders its search results client-side through Google, so
    # searches are answered from a local index of its sitemaps instead
    query = request.args.get('q', '').strip()
    if not query:
        return render_template("search.html", query='', results=None)

    try:
        results = search_index.search(query)
    except Exception:
        app.logger.exception("search index unavailable")
        return Response(render_template("search.html", query=query, results=None, error=True), 503)
    if results is None:
        response = Response(render_template("search.html", query=query, results=None, building=True), 503)
        response.headers["Retry-After"] = "30"
        return response

    pages = max(1, -(-len(results) // SEARCH_RESULTS_PER_PAGE))
    try:
        page = min(max(1, int(request.args.get('pagenum', 1))), pages)
    except ValueError:
        page = 1
    start = (page - 1) * SEARCH_RESULTS_PER_PAGE
    return render_template("search.html", query=query, total=len(results),
                           results=results[start:start + SEARCH_RESULTS_PER_PAGE],
                           page=page, pages=pages)

@app.route('/search/<path:query>/')
def route_search_legacy(query):
    # Old search URLs kept the query in the path, which broke on "/"
    return redirect(url_for('route_search', q=query), 301)

@app.route('/random/')
def route_random():
    # Snopes answers with a redirect to a random article: pass it on
    # without downloading the article itself
    data = fetch(SNOPES + "/random/", allow_redirects=False)
    location = data.headers.get("Location", "")
    if location.startswith(SNOPES + "/"):
        location = location[len(SNOPES):]
    if data.status_code not in (301, 302, 303, 307, 308) or not location.startswith("/") or location.startswith("//"):
        return upstream_error(data.status_code)
    return redirect(location, 307)

@app.route('/sitemap/')
def route_sitemap():
    data = fetch(SNOPES + "/sitemap/")
    if data.status_code != 200:
        return upstream_error(data.status_code)

    soup = BeautifulSoup(data.text, "html.parser")
    title = soup.find("h2").text
    archives = []
    for archive_box in soup.select(".archive_box"):
        archive_type = archive_box.find(attrs={"class": ["section_title"]})
        if (archive_type.find("svg") != None):
            archive_type.find("svg").decompose()
        archive_sections = []
        for archive_section_item in archive_box.select(".archive_section_item"):
            archive_section_item.a["href"] = archive_section_item.a["href"].replace("https://www.snopes.com", '')
            archive_sections.append(archive_section_item.a)
        archives.append([archive_type, archive_sections])

    return render_template("sitemap.html", data=[title, archives])

@app.route('/')
def route_home():
    return render_template("index.html")


SNOPES_MEDIA = "https://media.snopes.com/"
# Snopes' own media proxy, which serves media.snopes.com files (fetched
# directly, they answer 403); 600 px is the width Snopes uses in articles
SNOPES_MEDIA_PROXY = "https://mediaproxy.snopes.com/width/600/"
# Third-party hosts of images that articles show inline (measured)
EXTERNAL_IMAGE_HOSTS = ("https://images.theconversation.com/",)
PROXY_PREFIXES = ("https://mediaproxy.snopes.com/", SNOPES_MEDIA, SNOPES + "/") + EXTERNAL_IMAGE_HOSTS
# image/* includes SVG, which can run scripts when opened directly: the
# proxied file may only be displayed, never executed or sniffed as HTML
PROXY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}
# Kept from the upstream response, so browsers cache images as the origin
# allows (Snopes' media: public, max-age of a year, Last-Modified)
UPSTREAM_CACHE_HEADERS = ("Cache-Control", "Expires", "Last-Modified", "ETag")

@app.route('/proxy/')
def route_proxy():
    # Image proxy for Snopes media. It only serves images, so it cannot be
    # used to serve Snopes' pages (and their scripts) from this origin.
    url = request.args.get("url", "")
    # Some legacy articles use paths relative to the site root without the
    # leading slash ("graphics/x.jpg")
    if url and not url.startswith(("/", "https://", "http://")):
        url = "/" + url
    if url.startswith("/") and not url.startswith("//"):
        url = SNOPES + url
    if not url.startswith(PROXY_PREFIXES):
        return error_page(400)
    data = None
    if url.startswith(SNOPES + "/"):
        # Legacy image paths (/uploads/, /images/, /tachyon/...) redirect to
        # media.snopes.com: follow that redirect here
        data = fetch(url, allow_redirects=False)
        location = data.headers.get("Location", "")
        if data.is_redirect and location.startswith(SNOPES_MEDIA):
            url, data = location, None
    if url.startswith(SNOPES_MEDIA):
        url = SNOPES_MEDIA_PROXY + url
    if data is None:
        data = fetch(url)
    if data.status_code != 200:
        return upstream_error(data.status_code)
    content_type = data.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        return error_page(502)
    headers = dict(PROXY_HEADERS)
    headers.update({name: data.headers[name] for name in UPSTREAM_CACHE_HEADERS if name in data.headers})
    return Response(data.content, content_type=content_type, headers=headers)

@app.before_request
def add_slash():
    # Pages live under URLs ending in "/". Keep the query string, and leave
    # static files alone: url_for() links them without a trailing slash.
    if request.path.endswith('/') or request.endpoint == 'static':
        return None
    url = request.path + '/'
    if request.query_string:
        url += '?' + request.query_string.decode()
    return redirect(url, 308)

@app.errorhandler(HTTPException)
def http_error(e):
    # Covers 404 and 405, and 500 after Flask has logged the traceback
    return error_page(e.code, ERROR_MESSAGES.get(e.code, e.name))

@app.errorhandler(requests.RequestException)
def upstream_unreachable(e):
    # Timeouts, connection errors and redirect loops from Snopes
    app.logger.warning("upstream request failed: %r", e)
    return error_page(502)

if __name__ == '__main__':
    app.run(port=8001)
