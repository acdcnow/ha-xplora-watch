"""Publish the repository documentation to the GitHub wiki.

The wiki (a separate git repository, `ha-xplora-watch.wiki.git`) mirrors `docs/` one page per file,
because GitHub wiki pages are addressed by filename and readers there expect the sidebar layout.
Duplication is a maintenance risk, so the mirror is generated instead of hand-edited: run this
script after changing anything in `docs/` and push the result.

    git clone https://github.com/acdcnow/ha-xplora-watch.wiki.git /tmp/xplora-wiki
    python scripts/mirror_wiki.py /tmp/xplora-wiki
    cd /tmp/xplora-wiki && git add -A && git commit -m "Sync the wiki with docs/" && git push

What it does per page:

* the wiki page name comes from `WIKI_PAGES` (dashes become spaces in the displayed title);
* every link to another `docs/*.md` file is rewritten to that page's wiki name, anchors included;
* images and repository-file links become absolute raw/`github.com` URLs, because the wiki has
  neither the images nor the rest of the repository;
* a short note at the top names the source file and the version, so a reader can tell which document
  they are looking at and how far it may have drifted.

The script also fails loudly if a page still links a raw `.md` file, and warns about a `;` inside a
Mermaid fence -- that terminates the statement and GitHub then renders "Unable to render rich
display" instead of the diagram.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
RAW = "https://raw.githubusercontent.com/acdcnow/ha-xplora-watch/main"

# docs/<file> -> wiki page name. The wiki shows the filename with dashes replaced by spaces, so the
# page names double as the human-readable titles of the mirrored manual.
WIKI_PAGES: dict[str, str] = {
    "index.md": "Home",
    "installation.md": "Installation-and-configuration",
    "migrating-from-ludy87.md": "Migrating-from-Ludy87-xplora-watch",
    "demo-mode.md": "Try-it-without-a-watch-demo-mode",
    "account-types.md": "Account-types-Guardian-vs-Contact",
    "polling.md": "Update-interval-polling",
    "ban-defense.md": "Why-this-fork-exists-the-ban-problem",
    "dashboards.md": "Ready-made-dashboards",
    "alarms-and-silent-times.md": "Alarms-and-silent-times",
    "location-history.md": "Location-history",
    "safe-zones.md": "Safe-zones",
    "notifications.md": "Call-and-notification-activity",
    "send-message.md": "Send-a-message",
    "media.md": "Voice-video-and-image-messages",
    "dashboard-cards.md": "Dashboard-cards",
    "services.md": "Services-reference",
    "troubleshooting.md": "Troubleshooting",
}

SIDEBAR = """### HA Xplora® Watch

**[Home](Home)**

---

### Getting started

- [Installation & configuration](Installation-and-configuration)
- [Migrating from Ludy87/xplora_watch](Migrating-from-Ludy87-xplora-watch)
- [Try it without a watch (demo mode)](Try-it-without-a-watch-demo-mode)
- [Account types: Guardian vs. Contact](Account-types-Guardian-vs-Contact)

---

### Keeping Xplora happy

- [Update interval (polling)](Update-interval-polling)
- [Why this fork exists: the ban problem](Why-this-fork-exists-the-ban-problem)

---

### Features

- [Ready-made dashboards](Ready-made-dashboards)
- [Alarms & silent times](Alarms-and-silent-times)
- [Location history](Location-history)
- [Safe zones](Safe-zones)
- [Call & notification activity](Call-and-notification-activity)
- [Send a message](Send-a-message)
- [Voice, video & image messages](Voice-video-and-image-messages)
- [Dashboard cards](Dashboard-cards)
- [Services reference](Services-reference)

---

### Reference

- [Troubleshooting](Troubleshooting)

---

[Repository](https://github.com/acdcnow/ha-xplora-watch) · [Issues](https://github.com/acdcnow/ha-xplora-watch/issues) · [Releases](https://github.com/acdcnow/ha-xplora-watch/releases)
"""

HEADER = (
    "> [!NOTE]\n"
    "> This page mirrors [`docs/{source}`]({repo_url}) from the repository at **{version}**.\n"
    "> The repository copy is the source of truth; if the two disagree, the repository wins.\n"
    "> Regenerate with `python scripts/mirror_wiki.py`.\n\n"
)


def current_version() -> str:
    """The integration version, i.e. the release this manual describes."""
    manifest = json.loads((REPO / "custom_components" / "xplora_watch" / "manifest.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def rewrite(markdown: str, source: str, version: str) -> str:
    """Point every docs link at its wiki page, and every image at the raw repository URL."""
    for filename, page in WIKI_PAGES.items():
        markdown = markdown.replace(f"]({filename})", f"]({page})")
        markdown = markdown.replace(f"]({filename}#", f"]({page}#")
    # Links that point back into the repository: a wiki reader can still open them, but only as URLs.
    markdown = markdown.replace("](../README.md)", f"]({RAW}/README.md)")
    markdown = markdown.replace("](../CONTRIBUTING.md)", f"]({RAW}/CONTRIBUTING.md)")
    markdown = markdown.replace("](../LICENSE)", f"]({RAW}/LICENSE)")
    markdown = markdown.replace("](../../issues/new)", "](https://github.com/acdcnow/ha-xplora-watch/issues/new)")
    markdown = markdown.replace("](../custom_components/", f"]({RAW}/custom_components/")
    markdown = markdown.replace("](../../blob/", "](https://github.com/acdcnow/ha-xplora-watch/blob/")
    markdown = markdown.replace("](images/", f"]({RAW}/images/")
    markdown = re.sub(r'src="images/', f'src="{RAW}/images/', markdown)
    markdown = re.sub(r"src='images/", f"src='{RAW}/images/", markdown)
    header = HEADER.format(source=source, repo_url=f"{RAW}/docs/{source}", version=version)
    return header + markdown.lstrip("\n")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.splitlines()[7].strip())
        print("usage: python scripts/mirror_wiki.py <wiki-checkout-dir>")
        return 2
    wiki_dir = pathlib.Path(sys.argv[1])
    if not wiki_dir.is_dir():
        print(f"not a directory: {wiki_dir}")
        return 2

    version = current_version()
    for filename, page in WIKI_PAGES.items():
        source = DOCS / filename
        if not source.exists():
            print(f"missing source file: {source}")
            return 1
        (wiki_dir / f"{page}.md").write_text(rewrite(source.read_text(encoding="utf-8"), filename, version), encoding="utf-8", newline="\n")
        print(f"{filename} -> {page}.md")
    (wiki_dir / "_Sidebar.md").write_text(SIDEBAR, encoding="utf-8", newline="\n")
    print("_Sidebar.md")
    print(f"{len(WIKI_PAGES) + 1} pages written to {wiki_dir} (version {version})")

    leftovers: list[str] = []
    mermaid_risks: list[str] = []
    for name in [f"{page}.md" for page in WIKI_PAGES.values()] + ["_Sidebar.md"]:
        text = (wiki_dir / name).read_text(encoding="utf-8")
        if re.search(r"\]\((?!https?:)(?:\.\./)*[a-z-]+\.md(#|\))", text):
            leftovers.append(name)
        for block in text.split("```mermaid")[1:]:
            body = block.split("```")[0]
            if ";" in body and "&gt;" not in body and "&lt;" not in body:
                mermaid_risks.append(name)
    print(f"unrewritten .md links: {leftovers or 'none'}")
    print(f"mermaid semicolon risks: {sorted(set(mermaid_risks)) or 'none'}")
    return 1 if leftovers else 0


if __name__ == "__main__":
    raise SystemExit(main())
