from typing import Tuple, List, Generator
from deepsearcher import configuration
from deepsearcher.agent.academic_translator import AcademicTranslator
from deepsearcher.agent.prompts.article_title_prompts import ArticlePrompts
from deepsearcher.llm.base import BaseLLM
from deepsearcher.agent.base import BaseAgent
from deepsearcher.vector_db import RetrievalResult
from deepsearcher.tools.log import debug

class ArticleTitleAgent(BaseAgent):

    def __init__(self, reasoning_llm: BaseLLM, translator: AcademicTranslator, **kwargs):
        super().__init__(**kwargs)
        self.verbose = configuration.config.rbase_settings.get("verbose", False)
        self.reasoning_llm = reasoning_llm
        self.translator = translator

    def query(self, query: str, **kwargs) -> Tuple[str, List[RetrievalResult], dict]:
        collected_content = ""
        usage = {}
        for chunk in self.query_generator(query, **kwargs):
            if len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content is not None:
                    collected_content += delta.content
            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage
        
        return collected_content, [], usage


    def query_generator(self, query: str, **kwargs) -> Generator[str, None, None]:
        if kwargs.get("verbose"):
            self.verbose = True
        article = kwargs.get("article", None)
        if article is None or article.article_id is None or not article.article_id:
            raise Exception("article_id is 0")
        authors = kwargs.get("authors", [])
        title_count = kwargs.get("title_count", 3)

        author_list = []
        for author in authors:
            author_list.append(author.description())

        if article.chinese_abstract is None or len(article.chinese_abstract) < 10:
            article.chinese_abstract = self.translator.translate(article.abstract, "zh")

        prompt = ArticlePrompts.ARTICLE_TITLE_PROMPT.format(
            title=article.title,
            author_list=",".join(author_list),
            abstract=article.abstract,
            chinese_abstract=article.chinese_abstract,
            summary=article.summary,
            journal=article.journal_name,
            impact_factor=article.impact_factor,
            keywords=article.source_keywords,
            article_type=article.article_type(),
            title_count=title_count,
            query=query,
        )
        if self.verbose:
            debug(f"prompt: {prompt}")

        return self.reasoning_llm.stream_generator([{"role": "user", "content": prompt}])

