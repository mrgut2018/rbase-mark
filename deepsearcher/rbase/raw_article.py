

class RawArticle:

    def __init__(self, raw_article_data: dict = None, **kwargs) -> None:
        if raw_article_data is None:
            raw_article_data = {}

        self.id = kwargs.get("id") or raw_article_data.get("id", 0)
        self.txt_file = kwargs.get("txt_file") or raw_article_data.get("txt_file", "")
        self.title = kwargs.get("title") or raw_article_data.get("title", "")
        self.summary = kwargs.get("summary") or raw_article_data.get("summary", "")
        self.journal_name = kwargs.get("journal_name") or raw_article_data.get("journal_name", "")
        self.journal_id = kwargs.get("journal_id") or raw_article_data.get("journal_id", 0)
        self.impact_factor = kwargs.get("impact_factor") or raw_article_data.get("impact_factor", 0)
        self.source_keywords = kwargs.get("source_keywords") or raw_article_data.get("source_keywords", "")
        self.mesh_keywords = kwargs.get("mesh_keywords") or raw_article_data.get("mesh_keywords", "")
        self.pubdate = kwargs.get("pubdate") or raw_article_data.get("pubdate", None)
        self.authors = kwargs.get("authors") or raw_article_data.get("authors", "")
        self.corresponding_authors = kwargs.get("corresponding_authors") or raw_article_data.get("corresponding_authors", "")