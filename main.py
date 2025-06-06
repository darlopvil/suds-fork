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

from flask import Flask, render_template, request, redirect, Response, stream_with_context
import requests
import re
from bs4 import BeautifulSoup
from copy import copy

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
        article_type.find("svg").decompose()
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
        article_type.find("svg").decompose()
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
        article_type.find("svg").decompose()
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

        if rating != None:
            rating.find("svg").decompose()
            rating.find("img").decompose()
            rating = str(rating).replace("https://www.snopes.com", '')
        else:
            rating = ''

        # Author bio
        author_bio = soup.select("div.author_bio p")[0].text

        return [article_type, title, subtitle, author.strip(), author_link, date, cover, cover_alt, cover_desc, rating, article, author_bio]
    else:
        return data.status_code

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route('/fact-check/')
def route_fact_check_list():
    if request.args.get('pagenum') != None:
        data = article_list(f"fact-check/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("fact-check/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/fact-check/category/<category>/')
def route_fact_check_category(category):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"fact-check/category/{category}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"fact-check/category/{category}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/fact-check/rating/<rating>/')
def route_fact_check_rating(rating):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"fact-check/rating/{rating}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"fact-check/rating/{rating}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/latest/')
def route_latest():
    if request.args.get('pagenum') != None:
        data = article_list(f"latest/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("latest/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/top/')
def route_top():
    if request.args.get('pagenum') != None:
        data = article_list(f"top/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("top/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/news/')
def route_news_list():
    if request.args.get('pagenum') != None:
        data = article_list(f"news/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("news/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/news/category/<category>/')
def route_news_category(category):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"news/category/{category}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"news/category/{category}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/articles/')
def route_articles():
    if request.args.get('pagenum') != None:
        data = article_list(f"articles/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("articles/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/classics/')
def route_classics():
    if request.args.get('pagenum') != None:
        data = article_list(f"classics/?pagenum={request.args.get('pagenum')}")
    else:
        data = article_list("classics/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/news/<year>/<month>/<day>/<article>/')
def route_news(year, month, day, article):
    data = news(f"news/{year}/{month}/{day}/{article}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("news.html", data=data)

@app.route('/articles/<article_id>/<article>/')
def route_article(article_id, article):
    data = news(f"articles/{article_id}/{article}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("news.html", data=data)

@app.route('/fact-check/<article>/')
def route_fact_check(article):
    data = fact_check(article)
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("fact-check.html", data=data)

@app.route('/author/<author>/')
def route_author(author):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"author/{author}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"author/{author}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/tag/<tag>/')
def route_tag(tag):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"tag/{tag}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"tag/{tag}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/collections/')
def route_collections():
    if request.args.get('pagenum') != None:
        data = secondary_list(f"collections/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list("collections/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/collections/<collection>/')
def route_collection(collection):
    data = requests.get(f"https://www.snopes.com/collections/{collection}/")
    print(data)
    if data.status_code != 200:
        return Response(render_template(str(data.status_code) + ".html"), data.status_code)
    soup = BeautifulSoup(data.text, "html.parser")

    # Header
    article_type = soup.find(attrs={"class": ["section_title"]})
    article_type.find("svg").decompose()
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
def route_search_blank():
    if request.args.get('q') == None:
        if request.args.get('pagenum') != None:
            data = secondary_list(f"search/?pagenum={request.args.get('pagenum')}")
        else:
            data = secondary_list("search/")
        if type(data) == int:
            return Response(render_template(str(data) + ".html"), data)
        return render_template("list.html", data=data)
    else:
        return redirect(f"/search/{request.args.get('q')}/")

@app.route('/search/<query>/')
def route_search(query):
    if request.args.get('pagenum') != None:
        data = secondary_list(f"search/{query}/?pagenum={request.args.get('pagenum')}")
    else:
        data = secondary_list(f"search/{query}/")
    if type(data) == int:
        return Response(render_template(str(data) + ".html"), data)
    return render_template("list.html", data=data)

@app.route('/random/')
def route_random():
    data = requests.get("https://www.snopes.com/random/")
    if data.status_code != 200:
        return Response(render_template(str(data.status_code) + ".html"), data.status_code)
    return redirect(data.url.replace("https://www.snopes.com", ''), 307)

@app.route('/sitemap/')
def route_sitemap():
    data = requests.get("https://www.snopes.com/sitemap/")
    if data.status_code != 200:
        return Response(render_template(str(data.status_code) + ".html"), data.status_code)

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
            return Response(render_template("400.html"), status=400)
    else:
        return Response(render_template("400.html"), status=400)

@app.before_request
def add_slash():
    if not request.path.endswith('/'):
        return redirect(request.path + '/')

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html")

if __name__ == '__main__':
    app.run(port=8001)
