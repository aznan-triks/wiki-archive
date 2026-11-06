"""Small documentation sites served on localhost, shaped like the real engines
(Docusaurus, MkDocs Material, a bare site), for the website-mode tests."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# ── tiny HTTP server ──────────────────────────────────────────────────────────


@contextmanager
def serve(build_routes):
    """build_routes(base_url) -> {path: (status, content_type, body[, headers])}.
    Yields (base_url, requests) where requests lists every 'path?query' received."""
    seen: list[str] = []
    routes: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            path = urlsplit(self.path).path
            status, ctype, body, *extra = routes.get(path) or (404, "text/html", "<h1>Not found</h1>")
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra[0] if extra else {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    routes.update(build_routes(base))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base, seen
    finally:
        server.shutdown()
        server.server_close()


def sitemap(base: str, paths) -> str:
    urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in paths)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


HTML = "text/html; charset=utf-8"

# ── Docusaurus-like site ──────────────────────────────────────────────────────
DOCUSAURUS_PAGES = {
    # path: (title, [breadcrumb labels with optional link], body html)
    "/": ("Welcome", [], "<p>Welcome to the Source 2 test wiki. Start with the basics.</p>"),
    "/category/basics": ("Basics", [], "<p>Pages about the basics of working with the engine and tools.</p>"),
    "/Basics/what-is-source-2": ("What is Source 2", [("Basics", "/category/basics")],
                                 "<p>Source 2 is a game engine made by Valve for several games.</p>"),
    "/Basics/working-on-content": ("Working on content", [("Basics", "/category/basics")],
                                   "<p>Content lives in addons.</p>"
                                   '<div class="theme-code-block language-text"><pre class="prism-code language-text">'
                                   '<code><span class="token-line"><span class="token plain">content/</span><br></span>'
                                   '<span class="token-line"><span class="token plain">  game/</span><br></span></code>'
                                   '<button type="button" class="clean-btn">Copy</button></pre></div>'
                                   '<div class="theme-admonition theme-admonition-warning alert alert--warning">'
                                   '<div class="admonitionHeading_x"><span><svg viewBox="0 0 12 16"></svg></span>warning</div>'
                                   '<div class="admonitionContent_y"><p>Anything under game is overwritten.</p></div></div>'),
    "/Basics/working-on-content/addons": ("Addons", [("Basics", "/category/basics"),
                                                      ("Working on content", "/Basics/working-on-content")],
                                          "<p>An addon is a folder with maps and models.</p>"
                                          '<div class="tabs-container"><ul role="tablist" class="tabs">'
                                          '<li role="tab" aria-selected="true">Windows</li><li role="tab">Linux</li></ul>'
                                          '<div class="margin-top--md"><div role="tabpanel"><p>Use the launcher on Windows.</p></div>'
                                          '<div role="tabpanel" hidden><p>Use the shell script on Linux.</p></div></div></div>'),
    "/Basics/working-on-content/directory-layout": ("Directory layout", [("Basics", "/category/basics"),
                                                                          ("Working on content", "/Basics/working-on-content")],
                                                    "<p>Two folders: content and game, each with its own role.</p>"),
    "/Basics/hidden-doc": ("Hidden doc", [("Basics", "/category/basics")],
                           "<p>A page the sidebar does not list but the sitemap does.</p>"),
    "/EditorTools/asset-browser": ("Asset Browser", [("Editor Tools", None)],
                                   "<p>Browse every asset of the addon in one window.</p>"),
    "/EditorTools/hammer": ("Hammer Level Editor", [("Editor Tools", None)],
                            "<p>Hammer is the level editor of the engine.</p>"),
    "/entity-list": ("Entity List", [], "<p>All entities of the engine are listed in this page.</p>"),
}
# sidebar: (label, link|None, children) in reading order
DOCUSAURUS_SIDEBAR = [
    ("Welcome", "/", None),
    ("Basics", "/category/basics", [
        ("What is Source 2", "/Basics/what-is-source-2", None),
        ("Working on content", "/Basics/working-on-content", [
            ("Addons", "/Basics/working-on-content/addons", None),
            ("Directory layout", "/Basics/working-on-content/directory-layout", None)]),
        ("Dead page", "/Basics/dead", None)]),
    ("Editor Tools", None, [
        ("Asset Browser", "/EditorTools/asset-browser", None),
        ("Hammer Level Editor", "/EditorTools/hammer", None)]),
    ("Entity List", "/entity-list", None),
]


def _sidebar_html(items, level=1) -> str:
    out = ['<ul class="theme-doc-sidebar-menu menu__list">' if level == 1 else '<ul class="menu__list">']
    for label, link, kids in items:
        if kids is None:
            out.append(f'<li class="theme-doc-sidebar-item-link menu__list-item"><a class="menu__link" href="{link}">{label}</a></li>')
        else:
            head = (f'<a class="menu__link menu__link--sublist" href="{link}">{label}</a>' if link
                    else f'<a class="menu__link menu__link--sublist" role="button" aria-expanded="false">{label}</a>')
            out.append('<li class="theme-doc-sidebar-item-category menu__list-item menu__list-item--collapsed">'
                       f'<div class="menu__list-item-collapsible">{head}</div>{_sidebar_html(kids, level + 1)}</li>')
    out.append("</ul>")
    return "".join(out)


def docusaurus_page(path: str, base: str, query_note: str = "") -> str:
    title, crumbs, body = DOCUSAURUS_PAGES[path]
    items = ['<li class="breadcrumbs__item"><a aria-label="Home page" class="breadcrumbs__link" href="/"><svg viewBox="0 0 24 24"></svg></a></li>']
    for label, href in crumbs:
        inner = (f'<a class="breadcrumbs__link" href="{href}"><span>{label}</span></a>' if href
                 else f'<span class="breadcrumbs__link">{label}</span>')
        items.append(f'<li class="breadcrumbs__item">{inner}</li>')
    if path != "/":
        items.append(f'<li class="breadcrumbs__item breadcrumbs__item--active"><span class="breadcrumbs__link">{title}</span></li>')
    return f"""<!doctype html><html lang="en"><head><meta charset="UTF-8">
<meta name="generator" content="Docusaurus v3.10.2"><title>{title} | Source 2 Wiki</title>
<link rel="alternate" href="{base}{path if path != '/' else ''}" hreflang="en">
<link rel="alternate" href="{base}/fr{path if path != '/' else ''}" hreflang="fr"></head>
<body><div id="__docusaurus">
<nav aria-label="Main" class="navbar"><a class="navbar__brand" href="/"><b class="navbar__title">Source 2 Wiki</b></a>
<a href="https://discord.example.org">Discord</a></nav>
<div class="main-wrapper"><aside class="theme-doc-sidebar-container"><nav aria-label="Docs sidebar" class="menu thin-scrollbar">
{_sidebar_html(DOCUSAURUS_SIDEBAR)}</nav></aside>
<main><article><nav class="theme-doc-breadcrumbs" aria-label="Breadcrumbs"><ul class="breadcrumbs">{''.join(items)}</ul></nav>
<div class="tocCollapsible theme-doc-toc-mobile"><button type="button">On this page</button></div>
<div class="theme-doc-markdown markdown"><header><h1>{title}</h1></header>{body}
<h2 class="anchor" id="more">More<a href="#more" class="hash-link" aria-label="Direct link to More">​</a></h2>
<p>See the <a href="/entity-list">entity list</a>, the <a href="/files/guide.pdf">PDF guide</a> and <a href="/blog/tags/news">news tag</a>. {query_note}</p>
<footer class="theme-doc-footer"><a class="theme-edit-this-page" href="https://github.com/x/y/edit/main/docs/a.md">Edit this page</a></footer></div></article>
<nav class="pagination-nav" aria-label="Docs pages"><a class="pagination-nav__link" href="/">Previous</a></nav></main></div>
<footer class="footer">Copyright Test</footer></div></body></html>"""


def docusaurus_routes(base: str) -> dict:
    routes = {p: (200, HTML, docusaurus_page(p, base)) for p in DOCUSAURUS_PAGES}
    routes["/sitemap.xml"] = (200, "application/xml", sitemap(base, list(DOCUSAURUS_PAGES) + ["/blog/tags/news", "/fr/entity-list"]))
    routes["/robots.txt"] = (200, "text/plain", f"User-agent: *\nDisallow: /private\nSitemap: {base}/sitemap.xml\n")
    routes["/fr/entity-list"] = (200, HTML, "<html><body><main><p>Liste des entités du moteur de jeu, en français.</p></main></body></html>")
    routes["/blog/tags/news"] = (200, HTML, "<html><body><main><p>Tagged posts that must not be archived at all.</p></main></body></html>")
    routes["/files/guide.pdf"] = (200, "application/pdf", b"%PDF-1.4")
    return routes


# ── MkDocs Material-like site (no sitemap, nested nav, no breadcrumbs) ───────
MKDOCS_NAV = [
    ("Home", "/", None),
    ("User guide", None, [("Install", "/guide/install", None), ("Usage", "/guide/usage", None)]),
    ("Reference", "/reference", None),
]
MKDOCS_BODY = {
    "/": "<h1>Home</h1><p>Welcome to the MkDocs test documentation site, built for tests.</p>",
    "/guide/install": '<h1>Install<a class="headerlink" href="#install">¶</a></h1><p>Run the installer and follow the steps.</p>'
                      '<div class="highlight language-bash"><pre><code><span class="line">pip install demo</span>\n'
                      '<span class="line">demo --help</span></code></pre></div>'
                      '<div class="admonition note"><p class="admonition-title">Note</p><p>Python 3.11 is required.</p></div>',
    "/guide/usage": "<h1>Usage</h1><p>Call the command with a configuration file to start working.</p>",
    "/reference": "<h1>Reference</h1><p>Every option of the command line tool is described here.</p>",
}


def _mk_nav(items) -> str:
    out = ['<ul class="md-nav__list">']
    for label, link, kids in items:
        if kids is None:
            out.append(f'<li class="md-nav__item"><a class="md-nav__link" href="{link}"><span class="md-ellipsis">{label}</span></a></li>')
        else:
            out.append('<li class="md-nav__item md-nav__item--nested"><input class="md-nav__toggle" type="checkbox">'
                       f'<label class="md-nav__link" for="x"><span class="md-ellipsis">{label}</span></label>'
                       f'<nav class="md-nav">{_mk_nav(kids)}</nav></li>')
    out.append("</ul>")
    return "".join(out)


def mkdocs_routes(base: str) -> dict:
    routes = {}
    for path, body in MKDOCS_BODY.items():
        routes[path] = (200, HTML, (
            f'<!doctype html><html><head><meta name="generator" content="mkdocs-1.5.3, mkdocs-material-9.5.3">'
            f"<title>{path.strip('/') or 'Home'} - Demo docs</title></head><body>"
            f'<header class="md-header"><a href="/">Demo docs</a></header>'
            f'<div class="md-sidebar md-sidebar--primary"><nav class="md-nav md-nav--primary">{_mk_nav(MKDOCS_NAV)}</nav></div>'
            f'<main><article class="md-content__inner md-typeset">{body}</article></main>'
            f'<footer class="md-footer">Made with Material</footer></body></html>'))
    return routes
