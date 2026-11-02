"""Builders shared by the pipeline tests."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "scripts" / "run.py"


def pipeline_env(tmp_path: Path, **over) -> dict:
    """Environment of one run.py call: generate phase, no network, wiki.test."""
    env = {
        **os.environ,
        "WIKI_API": "https://wiki.test/api.php",
        "JOB_DIR": str(tmp_path / "job"),
        "DATA_DIR": str(tmp_path / "data"),
        "EXPORT_FORMATS": "txt",
        "PHASE": "generate",
        "MAX_FILES": "0",
        "DEDUP": "false",
        "PYTHONPATH": str(ROOT / "scripts"),
    }
    env.pop("MISC_CATEGORY", None)
    env.update({k: str(v) for k, v in over.items()})
    return env


def run_pipeline(tmp_path: Path, **over) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RUN)], env=pipeline_env(tmp_path, **over),
                          capture_output=True, text=True)


def page_html(title: str) -> str:
    return f"<html><body><h1>{title}</h1><p>Body of {title}.</p></body></html>"


def dump_xml(*titles: str) -> str:
    pages = "".join(
        f"<page><title>{t}</title><ns>0</ns><revision><text>Text of {t}</text></revision></page>"
        for t in titles)
    return ('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">'
            f"{pages}</mediawiki>")
