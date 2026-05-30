from __future__ import annotations

from fandom_api import FandomApiClient


class Wiki:
    def __init__(self, name_or_url: str, client: FandomApiClient | None = None):
        self.client = client or FandomApiClient()
        self.url = self.client.resolve_wiki_url(name_or_url)

        details = self.client.get_wiki_details(self.url)
        self.title = details.get("sitename") or name_or_url
        self.description = details.get("description")

    def __str__(self) -> str:
        return f"Wiki(title={self.title}, url={self.url})"

    def get_article(self, article_name: str):
        from .article import Article

        return Article(self, article_name)

    def list_pages(self, limit: int = 50, namespace: int = 0):
        return self.client.list_pages(self.url, limit=limit, namespace=namespace)

    def get_page(self, page_title: str):
        return self.client.get_page(self.url, page_title, include_wikitext=True)

    def get_all_categories(self, limit: int = 200):
        return self.client.list_categories(self.url, limit=limit)

    def get_category(self, category_name: str):
        return self.get_page(f"Category:{category_name}")
    