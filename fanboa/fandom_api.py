from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen
import json


class FandomApiError(RuntimeError):
    """Raised when a Fandom API call fails or returns malformed data."""


@dataclass
class WikiSearchResult:
    id: int | None
    name: str
    url: str
    domain: str | None
    language: str | None
    hub: str | None


class FandomApiClient:
    """Simple client for Fandom and MediaWiki APIs."""

    COMMUNITY_API_BASE = "https://community.fandom.com/api/v1"

    def _get_json(self, base_url: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urlencode(params)
        full_url = f"{base_url}?{query}"

        try:
            with urlopen(full_url) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except Exception as exc:
            raise FandomApiError(f"Request failed: {full_url}") from exc

    def _normalize_wiki_url(self, wiki: str) -> str:
        wiki = wiki.strip()
        if wiki.startswith("http://") or wiki.startswith("https://"):
            parsed = urlparse(wiki)
            return f"https://{parsed.netloc}".rstrip("/")

        return f"https://{wiki}.fandom.com"

    def _wiki_api_url(self, wiki: str) -> str:
        return f"{self._normalize_wiki_url(wiki)}/api.php"

    def search_wikis(self, name: str, limit: int = 5) -> list[WikiSearchResult]:
        data = self._get_json(
            f"{self.COMMUNITY_API_BASE}/Wikis/ByString",
            {"string": name, "limit": max(1, min(limit, 25))},
        )

        items = data.get("items", [])
        results: list[WikiSearchResult] = []
        for item in items:
            wiki_url = item.get("url")
            if not wiki_url:
                domain = item.get("domain")
                wiki_url = f"https://{domain}" if domain else ""

            if not wiki_url:
                continue

            results.append(
                WikiSearchResult(
                    id=item.get("id"),
                    name=item.get("name") or item.get("title") or "",
                    url=wiki_url.rstrip("/"),
                    domain=item.get("domain"),
                    language=item.get("language"),
                    hub=item.get("hub"),
                )
            )

        return results

    def resolve_wiki_url(self, wiki_name_or_url: str) -> str:
        if wiki_name_or_url.startswith("http://") or wiki_name_or_url.startswith("https://"):
            return self._normalize_wiki_url(wiki_name_or_url)

        search_results = self.search_wikis(wiki_name_or_url, limit=10)
        wanted = wiki_name_or_url.strip().lower()

        for result in search_results:
            if result.name.strip().lower() == wanted:
                return result.url

            if result.domain and result.domain.split(".")[0].lower() == wanted:
                return result.url

        if search_results:
            return search_results[0].url

        return self._normalize_wiki_url(wiki_name_or_url)

    def get_wiki_details(self, wiki: str) -> dict[str, Any]:
        data = self._get_json(
            self._wiki_api_url(wiki),
            {
                "action": "query",
                "meta": "siteinfo",
                "siprop": "general",
                "format": "json",
                "formatversion": "2",
            },
        )
        return data.get("query", {}).get("general", {})

    def list_pages(self, wiki: str, limit: int = 50, namespace: int = 0) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        apcontinue: str | None = None

        while len(pages) < limit:
            chunk_size = min(500, limit - len(pages))
            params: dict[str, Any] = {
                "action": "query",
                "list": "allpages",
                "apnamespace": namespace,
                "aplimit": chunk_size,
                "format": "json",
                "formatversion": "2",
            }

            if apcontinue:
                params["apcontinue"] = apcontinue

            data = self._get_json(self._wiki_api_url(wiki), params)
            chunk = data.get("query", {}).get("allpages", [])
            pages.extend(chunk)

            apcontinue = data.get("continue", {}).get("apcontinue")
            if not apcontinue:
                break

        return pages

    def get_page(self, wiki: str, title: str, include_wikitext: bool = True) -> dict[str, Any] | None:
        props = ["info", "extracts"]
        if include_wikitext:
            props.append("revisions")

        params: dict[str, Any] = {
            "action": "query",
            "prop": "|".join(props),
            "titles": title,
            "redirects": "1",
            "inprop": "url",
            "explaintext": "1",
            "exintro": "0",
            "format": "json",
            "formatversion": "2",
        }

        if include_wikitext:
            params.update({"rvprop": "content", "rvslots": "main"})

        data = self._get_json(self._wiki_api_url(wiki), params)
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return None

        page = pages[0]
        if page.get("missing"):
            return None

        if include_wikitext:
            revisions = page.get("revisions", [])
            if revisions:
                main_slot = revisions[0].get("slots", {}).get("main", {})
                page["wikitext"] = main_slot.get("content") or revisions[0].get("*")

        return page

    def get_page_links(self, wiki: str, title: str, limit: int = 200) -> list[str]:
        links: list[str] = []
        plcontinue: str | None = None

        while len(links) < limit:
            params: dict[str, Any] = {
                "action": "query",
                "prop": "links",
                "titles": title,
                "pllimit": min(500, limit - len(links)),
                "format": "json",
                "formatversion": "2",
            }

            if plcontinue:
                params["plcontinue"] = plcontinue

            data = self._get_json(self._wiki_api_url(wiki), params)
            pages = data.get("query", {}).get("pages", [])
            if not pages:
                break

            page_links = pages[0].get("links", [])
            links.extend(link.get("title", "") for link in page_links if link.get("title"))

            plcontinue = data.get("continue", {}).get("plcontinue")
            if not plcontinue:
                break

        return links

    def list_categories(self, wiki: str, limit: int = 200) -> list[str]:
        categories: list[str] = []
        accontinue: str | None = None

        while len(categories) < limit:
            params: dict[str, Any] = {
                "action": "query",
                "list": "allcategories",
                "aclimit": min(500, limit - len(categories)),
                "format": "json",
                "formatversion": "2",
            }

            if accontinue:
                params["accontinue"] = accontinue

            data = self._get_json(self._wiki_api_url(wiki), params)
            chunk = data.get("query", {}).get("allcategories", [])
            categories.extend(item.get("category", "") for item in chunk if item.get("category"))

            accontinue = data.get("continue", {}).get("accontinue")
            if not accontinue:
                break

        return categories