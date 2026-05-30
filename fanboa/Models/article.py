from __future__ import annotations

from typing import TYPE_CHECKING
import re

if TYPE_CHECKING:
    from .wiki import Wiki


class Article:
    def __init__(self, wiki: "Wiki", title: str):
        self.wiki = wiki
        self.title = title

        self.content: str = ""
        self.profile: dict[str, str] = {}
        self.links: list[str] = []

        self._setup()

    def _setup(self):
        page = self.wiki.get_page(self.title)
        if not page:
            return

        wikitext = page.get("wikitext") or ""
        self.content = wikitext or page.get("extract") or ""
        self.profile = self._extract_infobox(wikitext)
        self.links = self.wiki.client.get_page_links(self.wiki.url, self.title)

    def _extract_infobox(self, wikitext: str) -> dict[str, str]:
        if not wikitext:
            return {}

        match = re.search(r"\{\{[Ii]nfobox(.*?)\n\}\}", wikitext, flags=re.DOTALL)
        if not match:
            return {}

        box_text = match.group(1)
        profile: dict[str, str] = {}

        for raw_line in box_text.splitlines():
            line = raw_line.strip()
            if not line.startswith("|") or "=" not in line:
                continue

            key, value = line[1:].split("=", 1)
            key = key.strip()
            value = value.strip()
            if key:
                profile[key] = value

        return profile

    def __str__(self):
        return self.title

    def get_content(self):
        return self.content

    def get_profile(self):
        return self.profile

    def get_links(self):
        return self.links
    