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

"""Allowlist for the HTML Suds takes from Snopes.

Suds shows parts of Snopes' pages as they come, so anything not listed here
goes: tags outside the allowlist are unwrapped (their text stays) or, for
the ones that run, load or submit something, removed with their content;
attributes outside the allowlist are dropped, including event handlers,
inline styles but for a few plain properties, and the stray attributes
Snopes' malformed markup produces; links keep only web and mail URLs, and iframes
only those to the configured privacy frontends.
"""

import re

from bs4 import Comment

from embeds import FRAMED_FRONTENDS

# Tags in articles, rating blocks, section titles and the sitemap (measured
# on 490 pages, legacy articles included), plus the usual text-level ones
ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "col",
    "colgroup", "dd", "del", "div", "dl", "dt", "em", "figcaption", "figure",
    "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "iframe", "img", "ins",
    "li", "mark", "ol", "p", "path", "pre", "q", "s", "section", "small", "span",
    "strong", "sub", "sup", "svg", "table", "tbody", "td", "tfoot", "th", "thead",
    "time", "tr", "u", "ul",
}
# Removed with their content: they run, load, embed or submit something
DROPPED_TAGS = {
    "applet", "base", "button", "embed", "form", "frame", "frameset", "head",
    "input", "link", "math", "meta", "noscript", "object", "option", "script",
    "select", "style", "template", "textarea", "title",
}
GLOBAL_ATTRIBUTES = {"class", "id", "dir", "lang", "title"}
TAG_ATTRIBUTES = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "iframe": {"src", "width", "height", "loading", "frameborder", "allowfullscreen"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start", "type", "reversed"},
    "li": {"value"},
    "time": {"datetime"},
    "font": {"color"},
    # Legacy quote boxes; the stylesheet styles table[bgcolor]
    "table": {"bgcolor"},
    "svg": {"viewbox", "xmlns", "role", "aria-hidden", "width", "height"},
    "path": {"d", "fill"},
}
URL_ATTRIBUTES = {"href", "src"}
URL_SCHEME = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9+.-]*):")
SAFE_SCHEMES = {"http", "https", "mailto"}
LINK_RELS = {"nofollow", "noopener", "noreferrer"}
# Inline style keeps only these properties (measured: centred paragraphs,
# coloured text in legacy articles, lists without bullets), and only plain
# values: no url(), expression() or anything else that could load
STYLE_PROPERTIES = {"text-align", "color", "list-style-type"}
STYLE_VALUE = re.compile(r"^[#\w\s.,%()-]+$")


def _safe_url(url):
    # Browsers ignore tabs and newlines in URLs ("java\tscript:") and
    # leading control characters and spaces
    url = re.sub(r"[\t\n\r]", "", url).lstrip("".join(map(chr, range(0x21))))
    match = URL_SCHEME.match(url)
    return match is None or match.group(1).lower() in SAFE_SCHEMES


def _clean_style(style):
    kept = []
    for declaration in style.split(";"):
        name, _, value = declaration.partition(":")
        name, value = name.strip().lower(), value.strip()
        if name in STYLE_PROPERTIES and STYLE_VALUE.match(value) and "url" not in value.lower() \
                and "expression" not in value.lower():
            kept.append(f"{name}: {value}")
    return "; ".join(kept)


def _clean_attributes(tag):
    allowed = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag.name, set())
    style = _clean_style(tag.get("style") or "")
    for name in list(tag.attrs):
        value = tag.attrs[name]
        if name not in allowed:
            del tag.attrs[name]
        elif name in URL_ATTRIBUTES and not _safe_url(str(value)):
            del tag.attrs[name]
    if style:
        tag["style"] = style
    if tag.name == "a":
        if tag.get("target") != "_blank":
            tag.attrs.pop("target", None)
        rels = [r for r in (tag.get("rel") or []) if r in LINK_RELS]
        if tag.get("target"):
            rels += [r for r in ("noopener", "noreferrer") if r not in rels]
        if rels:
            tag["rel"] = rels
        else:
            tag.attrs.pop("rel", None)


def sanitize(element):
    """Clean a BeautifulSoup element in place and return it"""
    if element is None:
        return None
    for comment in element.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for tag in element.find_all(True):
        if tag.decomposed:  # inside a tag removed earlier
            continue
        if tag.name in DROPPED_TAGS:
            tag.decompose()
        elif tag.name == "iframe" and not str(tag.get("src", "")).startswith(FRAMED_FRONTENDS):
            tag.decompose()
        elif tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            _clean_attributes(tag)
    if element.name in ALLOWED_TAGS:
        _clean_attributes(element)
    return element
