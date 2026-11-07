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
import requests
import re
import os
from bs4 import BeautifulSoup
from copy import copy
from search_index import SearchIndex

def remove_all(tag, selector):
    """Remove every element matching selector; Snopes omits some of them"""
    for element in tag.select(selector):
        element.decompose()

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

def secondary_list(path):
    data = requests.get("https://www.snopes.com/" + path)

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

        # Next/previous buttons
        prev_button = next_button = ''
        if soup.select("#both-buttons") != []:
            buttons = soup.select("#both-buttons")[0].select("a")
            prev_button = buttons[0]
            next_button = buttons[1]
        pagenumber = soup.find(attrs={"class": ["pagenumber"]}).text

        return [article_type, description, article_list, prev_button, next_button, pagenumber, tags, head]

    else:
        return data.status_code


def article_list(path):
    data = requests.get("https://www.snopes.com/" + path)

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

        # Next/previous buttons
        buttons = soup.select("#both-buttons")[0].select("a")
        prev_button = buttons[0]
        next_button = buttons[1]
        pagenumber = soup.find(attrs={"class": ["pagenumber"]}).text

        return [article_type, description, article_list, prev_button, next_button, pagenumber, tags, head]

    else:
        return data.status_code


def news(path):
    data = requests.get("https://www.snopes.com/" + path)

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
        cover = soup.find(attrs={"id": ["cover-main"]}).get("src")
        cover_alt = soup.find(attrs={"id": ["cover-main"]}).get("alt")
        cover_desc = ""
        if soup.find(attrs={"class": ["article_img_desc"]}).select("span") != []:
            cover_desc = soup.find(attrs={"class": ["article_img_desc"]}).select("span")[0].text

        # Article
        article = soup.find(attrs={"id": ["article-content"]})
        
        for div in article.select("div"): div.decompose()
        for script in article.select("script"): script.decompose()

        for a in article.select("p a:has(img)"):
            a["href"] = re.sub(r"^(.*)$", r"/proxy/?url=\1", a["href"])
        article = re.sub(r"(src=\")", r"\1/proxy/?url=", str(article))
        article = article.replace("https://www.snopes.com", '')

        # Author bio
        author_bio = soup.select("div.author_bio p")[0].text

        return [article_type, title, subtitle, author.strip(), author_link, date, cover, cover_alt, cover_desc, article, author_bio]
    else:
        return data.status_code

def fact_check(path):
    data = requests.get("https://www.snopes.com/fact-check/" + path)

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
        cover = soup.find(attrs={"id": ["cover-main"]}).get("src")
        cover_alt = soup.find(attrs={"id": ["cover-main"]}).get("alt")
        cover_desc = ""
        if soup.find(attrs={"class": ["article_img_desc"]}).select("span") != []:
            cover_desc = soup.find(attrs={"class": ["article_img_desc"]}).select("span")[0].text

        # Article
        article = soup.find(attrs={"id": ["article-content"]})
        rating = copy(article.find(attrs={"id": ["fact_check_rating_container"]}))
        
        for div in article.select("div.snopesad"): div.decompose()
        for div in article.select("div"): del div["style"]
        for script in article.select("script"): script.decompose()
        if article.find("section") != None:
            article.find("section").decompose()

        for a in article.select("p a:has(img)"):
            a["href"] = re.sub(r"^(.*)$", r"/proxy/?url=\1", a["href"])
        article = re.sub(r"(src=\")", r"\1/proxy/?url=", str(article))
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
    if request.args.get('pagenum') != None:
        data = article_list(f"fact-check/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("fact-check/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/fact-check/category/<category>/')
def route_fact_check_category(category):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"fact-check/category/{category}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"fact-check/category/{category}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/fact-check/rating/<rating>/')
def route_fact_check_rating(rating):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"fact-check/rating/{rating}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"fact-check/rating/{rating}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/latest/')
def route_latest():
    if request.args.get('pagenum') != None:
        data = article_list(f"latest/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("latest/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/top/')
def route_top():
    if request.args.get('pagenum') != None:
        data = article_list(f"top/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("top/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/news/')
def route_news_list():
    if request.args.get('pagenum') != None:
        data = article_list(f"news/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("news/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/news/category/<category>/')
def route_news_category(category):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"news/category/{category}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"news/category/{category}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/articles/')
def route_articles():
    if request.args.get('pagenum') != None:
        data = article_list(f"articles/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("articles/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/classics/')
def route_classics():
    if request.args.get('pagenum') != None:
        data = article_list(f"classics/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("classics/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/news/<year>/<month>/<day>/<article>/')
def route_news(year, month, day, article):
    data = news(f"news/{year}/{month}/{day}/{article}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("news.html", data=data)

@app.route('/articles/<article_id>/<article>/')
def route_article(article_id, article):
    data = news(f"articles/{article_id}/{article}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("news.html", data=data)

@app.route('/fact-check/<article>/')
def route_fact_check(article):
    data = fact_check(article)
    if type(data) == int:
        return upstream_error(data)
    return render_template("fact-check.html", data=data)

@app.route('/author/<author>/')
def route_author(author):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"author/{author}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"author/{author}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/tag/<tag>/')
def route_tag(tag):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"tag/{tag}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"tag/{tag}/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/collections/')
def route_collections():
    if request.args.get('pagenum') != None:
        data = secondary_list(f"collections/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list("collections/")
    if type(data) == int:
        return upstream_error(data)
    return render_template("list.html", data=data)

@app.route('/collections/<collection>/')
def route_collection(collection):
    data = requests.get(f"https://www.snopes.com/collections/{collection}/")
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
    cover = soup.find(attrs={"id": ["cover-main"]}).get("src")
    cover_alt = soup.find(attrs={"id": ["cover-main"]}).get("alt")
    cover_desc = ""
    if soup.find(attrs={"class": ["article_img_desc"]}).select("span") != []:
        cover_desc = soup.find(attrs={"class": ["article_img_desc"]}).select("span")[0].text

    # Article
    article = soup.find(attrs={"id": ["article-content"]})
    article_copy = copy(article)

    for div in article.select("div"): div.decompose()
    for script in article.select("script"): script.decompose()

    for a in article.select("p a:has(img)"):
        a["href"] = re.sub(r"^(.*)$", r"/proxy/?url=\1", a["href"])
    article = re.sub(r"(src=\")", r"\1/proxy/?url=", str(article))

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
            text = div.find(attrs={"class": ["article_text"]})
            title = text.select("h3")[0].text
            date = text.find(attrs={"class": ["article_date"]}).text
            byline = text.find(attrs={"class": ["article_byline"]}).text
            article_list.append([link, image, alt, title, date, byline])


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
    data = requests.get("https://www.snopes.com/random/")
    if data.status_code != 200:
        return upstream_error(data.status_code)
    return redirect(data.url.replace("https://www.snopes.com", ''), 307)

@app.route('/sitemap/')
def route_sitemap():
    data = requests.get("https://www.snopes.com/sitemap/")
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


@app.route('/proxy/')
def route_proxy():
    url = request.args.get("url")
    if url != None:
        if url.startswith("https://mediaproxy.snopes.com/") or url.startswith("https://media.snopes.com/") or url.startswith("https://www.snopes.com/"):
            data = requests.get(url)
            return Response(data.content, content_type=data.headers["content-type"])
        elif url.startswith("/") and not url.startswith("//"):
            data = requests.get("https://www.snopes.com" + url)
            return Response(data.content, content_type=data.headers["content-type"])
        else:
            return error_page(400)
    else:
        return error_page(400)

@app.before_request
def add_slash():
    if not request.path.endswith('/'):
        return redirect(request.path + '/')

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
