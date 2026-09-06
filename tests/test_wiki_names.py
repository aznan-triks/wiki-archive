"""Tests for scripts/wiki_names.py -- the single source of naming rules.

Regression guard: before this module, the same sanitizing logic was copied
in extract.py, build_categories.py, export_categories.py, merge_pdf.py,
run.py and server.py -- any drift silently breaks the grouping/paths.
"""
import importlib
import os

import wiki_names


def test_page_stem_sanitizes_and_truncates():
    assert wiki_names.page_stem("Foo: Bar/Baz") == "Foo_ Bar_Baz"
    assert wiki_names.page_stem("Keep-me_123") == "Keep-me_123"
    assert len(wiki_names.page_stem("x" * 200)) == 120


def test_cat_stem_flattens_to_filename():
    assert wiki_names.cat_stem("Weapons & Gadgets") == "Weapons___Gadgets"
    assert wiki_names.cat_stem("  Pistols ") == "Pistols"  # surrounding spaces are stripped
    assert len(wiki_names.cat_stem("a" * 200)) == 80


def test_cat_stem_collapses_whitespace_to_underscore():
    assert wiki_names.cat_stem("Melee Weapons") == "Melee_Weapons"


def test_wiki_slug_from_url():
    assert wiki_names.wiki_slug("https://wiki.play.eco/en/Eco_Wiki") == "wiki.play.eco"
    assert wiki_names.wiki_slug("https://finalstandtwo.fandom.com/wiki/Weapons") \
        == "finalstandtwo.fandom.com"
    # Unparseable/hostname-less input falls back to the raw string (never crashes)
    assert wiki_names.wiki_slug("not a url") == "not_a_url"


def test_misc_category_defaults_to_misc():
    assert wiki_names.MISC_CATEGORY == "Misc"


def test_misc_category_is_env_configurable():
    old = os.environ.get("MISC_CATEGORY")
    os.environ["MISC_CATEGORY"] = "Divers"
    try:
        importlib.reload(wiki_names)
        assert wiki_names.MISC_CATEGORY == "Divers"
    finally:
        if old is None:
            del os.environ["MISC_CATEGORY"]
        else:
            os.environ["MISC_CATEGORY"] = old
        importlib.reload(wiki_names)


def test_scripts_do_not_reimplement_the_naming_rules():
    """The shared helpers must be imported, not re-inlined, everywhere they
    were duplicated (DRY)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    checks = {  # file -> (helper that must be used, local def that must be gone)
        "scripts/extract.py":            "page_stem",
        "scripts/build_categories.py":   "page_stem",
        "scripts/export_categories.py":  "cat_stem",
        "scripts/merge_pdf.py":          "cat_stem",
        "scripts/run.py":                "wiki_slug",
    }
    for rel, helper in checks.items():
        src = (root / rel).read_text(encoding="utf-8")
        assert "from wiki_names import" in src, f"{rel} must import from wiki_names"
        assert helper in src, f"{rel} must use {helper}()"
    for rel, banned in (("scripts/build_categories.py", "def title_to_stem"),
                        ("scripts/export_categories.py", "def cat_to_stem"),
                        ("scripts/merge_pdf.py", "def cat_to_filename"),
                        ("scripts/run.py", "def wiki_slug")):
        src = (root / rel).read_text(encoding="utf-8")
        assert banned not in src, f"{rel} still defines the duplicate {banned}()"
    server_src = (root / "server.py").read_text(encoding="utf-8")
    assert "import wiki_names" in server_src
    assert "wiki_names.wiki_slug" in server_src
    # No script may keep its own copy of the raw stem-sanitizing regex
    for rel in ("scripts/extract.py", "scripts/export_categories.py", "scripts/merge_pdf.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert 're.sub(r"[^\\w\\s\\-]", "_"' not in src, f"{rel} re-inlines the stem regex"
