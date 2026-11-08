"""One command before any "done": tests + hard-coded URL search + layer violations.
Run from the repo root: python scripts/verify.py  (exit 0 = all clear)."""
import os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "scripts").glob("*.py"))
STEPS = "extract|run|server|convert|merge_pdf|build_categories|detect_wiki|pack_files|site_fetch|site_extract|build_site_categories"
NO_PDF = ["extract", "build_categories", "detect_wiki", "export_categories", "clean_html", "pack_files"]
URL = re.compile(r"https?://[a-z0-9.-]+\.[a-z]{2,}")
IMPORT_STEP = re.compile(rf"^\s*(from|import)\s+({STEPS})\b")
IMPORT_PDF = re.compile(r"^\s*(from|import)\s+.*(weasyprint|pikepdf)")
ALLOWED_IMPORT = {"run.py:21"}                      # known gap: run.py imports pack_files
ALLOWED_URL = ("User-Agent", "USER_AGENT", "# ", "->", '"""', "'{http")   # user agents, examples, docs


def scan(files, pattern, skip=lambda line: False):
    hits = []
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and not skip(line):
                hits.append(f"{f.name}:{n}")
    return hits


def main():
    code = subprocess.call([sys.executable, "-m", "pytest"], cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    urls = scan(SCRIPTS, URL, lambda l: any(a in l for a in ALLOWED_URL))
    layers = [h for h in scan(SCRIPTS, IMPORT_STEP) if h not in ALLOWED_IMPORT]
    pdf = scan([ROOT / "scripts" / f"{m}.py" for m in NO_PDF], IMPORT_PDF)
    for title, hits in (("hard-coded URLs", urls), ("layer violations", layers), ("PDF libs outside convert/merge", pdf)):
        if hits:
            print(f"FAIL {title}: {', '.join(hits)}")
    ok = code == 0 and not (urls or layers or pdf)
    print("verify: OK" if ok else "verify: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
