ARTICLE_TYPE_UNKNOWN = 0
ARTICLE_TYPE_ARTICLE = 1
ARTICLE_TYPE_REVIEW = 2
ARTICLE_TYPE_PERSPECTIVE = 3
ARTICLE_TYPE_OPINION = 4
ARTICLE_TYPE_SHORT_ARTICLE = 5
ARTICLE_TYPE_GUIDELINE = 6
ARTICLE_TYPE_CONSENSUS = 7
ARTICLE_TYPE_MINI_REVIEW = 8
ARTICLE_TYPE_NEWS_VIEWS = 9
ARTICLE_TYPE_SYSTEMATIC_REVIEW_META_ANALYSIS = 10
ARTICLE_TYPE_CORRESPONDENCE = 11
ARTICLE_TYPE_COMMENTARY = 12
ARTICLE_TYPE_OTHER = 99

class RbaseAuthor:
    def __init__(self, name: str, ename: str = "", cname: str = "", is_corresponding: bool = False, **kwargs):
        self.name = name
        self.ename = ename
        self.cname = cname
        self.is_corresponding = is_corresponding
        self.is_co_corresponding = kwargs.get("is_co_corresponding", False)
        self.is_collected_expert = kwargs.get("is_collected_expert", False)
        self.is_first_author = kwargs.get("is_first_author", False) 
        self.is_co_first_author = kwargs.get("is_co_first_author", False)
        self.is_key_author = self.is_corresponding or self.is_first_author or self.is_co_first_author

    def set_author_ids(self, author_ids: list[int]):
        self.author_ids = author_ids

    def description(self):
        desc = ""
        if self.cname:
            desc = self.cname
        elif self.ename:
            desc = self.ename
        else:
            desc = self.name

        if self.is_collected_expert:
            desc = f"{desc} (智库专家)"

        if self.is_corresponding:
            desc = f"{desc} (最后通讯作者)"
        elif self.is_first_author:
            desc = f"{desc} (第一作者)"
        elif self.is_co_first_author:
            desc = f"{desc} (共同第一作者)"
        elif self.is_co_corresponding:
            desc = f"{desc} (普通通讯作者)"
        return desc


class RbaseArticle:
    """
    RbaseArticle class, load article data with author, txt_file(markdown file), raw_article_id,
    and some other metadata. Mainly used for markdown file processing and full text embedding.
    """
    def __init__(self, article_data: dict = None, **kwargs):
        """
        Initialize RbaseArticle object

        Args:
            article_data: Dictionary containing article data
            **kwargs: Other keyword arguments, can directly specify each attribute
        """
        if article_data is None:
            article_data = {}

        # 从字典或关键字参数中获取属性值
        self.article_id = kwargs.get("base_article_id") or article_data.get("base_article_id", 0)
        if self.article_id == 0 or self.article_id is None:
            self.article_id = (
                kwargs.get("article_id")
                or article_data.get("article_id", 0)
            )
        if self.article_id == 0 or self.article_id is None:
            self.article_id = (
                kwargs.get("id")
                or article_data.get("id", 0)
            )
        if self.article_id == 0 or self.article_id is None:
            raise Exception(f"article_id is 0, article_data: {article_data}")

        self.title = kwargs.get("title") or article_data.get("title", "")
        self.txt_file = kwargs.get("txt_file") or article_data.get("txt_file", "")
        self.authors = kwargs.get("authors") or article_data.get("authors", "")
        self.corresponding_authors = kwargs.get("corresponding_authors") or article_data.get(
            "corresponding_authors", ""
        )
        self.source_keywords = kwargs.get("source_keywords") or article_data.get(
            "source_keywords", ""
        )
        self.mesh_keywords = kwargs.get("mesh_keywords") or article_data.get("mesh_keywords", "")
        self.base_ids = kwargs.get("base_ids") or article_data.get("base_ids", "")
        self.impact_factor = kwargs.get("impact_factor") or article_data.get("impact_factor", 0)
        self.rbase_factor = kwargs.get("rbase_factor") or article_data.get("rbase_factor", 0)
        self.pubdate = kwargs.get("pubdate") or article_data.get("pubdate", None)
        if self.pubdate is not None:
            # 将datetime.date类型转换为datetime.datetime，然后获取时间戳
            import datetime

            if isinstance(self.pubdate, datetime.date) and not isinstance(
                self.pubdate, datetime.datetime
            ):
                self.pubdate = datetime.datetime.combine(self.pubdate, datetime.time()).timestamp()
            else:
                # 如果已经是datetime.datetime类型，直接获取时间戳
                self.pubdate = self.pubdate.timestamp()
        else:
            self.pubdate = 0
        self.author_objects = []
        self.abstract = kwargs.get("abstract") or article_data.get("abstract", "")
        self.chinese_abstract = kwargs.get("chinese_abstract") or article_data.get("chinese_abstract", "")
        self.summary = kwargs.get("summary") or article_data.get("summary", self.abstract)
        self.journal_name = kwargs.get("journal_name") or article_data.get("journal_name", "")
        self.raw_article_id = kwargs.get("raw_article_id") or article_data.get("raw_article_id", 0)
        self.type = kwargs.get("type") or article_data.get("type", 0)

    def set_author(self, author: RbaseAuthor):
        self.author_objects.append(author)

    def article_type(self) -> str:
        if self.type == ARTICLE_TYPE_ARTICLE or self.type == ARTICLE_TYPE_SHORT_ARTICLE:
            return "Article"
        elif self.type == ARTICLE_TYPE_REVIEW or self.type == ARTICLE_TYPE_MINI_REVIEW or self.type == ARTICLE_TYPE_SYSTEMATIC_REVIEW_META_ANALYSIS:
            return "Review"
        elif self.type == ARTICLE_TYPE_PERSPECTIVE or self.type == ARTICLE_TYPE_OPINION or self.type == ARTICLE_TYPE_CONSENSUS:
            return "Perspective"
        elif self.type == ARTICLE_TYPE_NEWS_VIEWS or self.type == ARTICLE_TYPE_COMMENTARY:
            return "News"
        else:
            return "Other"

