"""
Channel summary generator

This module implements the function of generating channel summary based on RAG.
"""

import json
import time
from typing import List, Tuple, Generator, Dict
from deepsearcher.agent.base import RAGAgent, describe_class
from deepsearcher.agent.prompts.summary_prompts import SummaryPrompts
from deepsearcher.rbase.rbase_article import RbaseArticle
from deepsearcher.llm.base import BaseLLM
from deepsearcher.vector_db import RetrievalResult
from deepsearcher.tools.log import debug
from deepsearcher import configuration
from openai.types.chat import ChatCompletionChunk

ProgressHint = {
    "LOAD_BACKGROUND": "正在获取AI对话栏目信息",
    "ANALYSIS": "正在分析用户的问题",
    "CREATE_SEARCH_QUERY": "正在生成检索条件",
    "SEARCH_DOCUMENT": "正在数据库中检索文献",
    "MERGE_DOCUMENT": "正在分析检索到的文献",
    "GENERATE_ANSWER": "正在生成回答",
    "FINISH": "回复完成"
}

PROMPT_MATCHES = {
    "summary_zh":  "channel_summary_01",
    "summary_en":  "channel_summary_02",
    "question_zh":  "channel_question_01",
    "question_en":  "channel_question_02",
    "popular_zh":  "popular_01",
    "ppt_zh":  "ppt_01",
    "footage_zh":  "footage_01",
    "opportunity_zh":  "opportunity_01",
}

class SummaryPromptTemplate:
    id = ""
    lang = "zh"
    target = "summary"
    purpose = ""
    prompt = ""

    def __init__(self, id: str, target: str, lang: str, prompt: str):
        self.id = id
        self.target = target
        self.lang = lang
        self.prompt = prompt

    def application_description(self) -> str:
        return f"Target Descirption: Used for generating summary articles for {self.target}, suitable for scenarios where the target language is {self.lang}"

    def generate_prompt(self, user_params: dict) -> str:
        """
        Generate prompt based on user parameters
        """
        return self.prompt.format(**user_params)


@describe_class(
    "This agent is designed to generate comprehensive academic summary on research articles following a structured approach with multiple sections."
)
class SummaryRag(RAGAgent):
    """Channel Summary generator"""
    
    def __init__(self, reasoning_llm: BaseLLM, writing_llm: BaseLLM, **kwargs):
        super().__init__(**kwargs)
        self.verbose = configuration.config.rbase_settings.get("verbose", False)
        self.reasoning_llm = reasoning_llm
        self.writing_llm = writing_llm
        if kwargs.get("target_lang"):
            self.target_lang = kwargs.get("target_lang")
        else:
            self.target_lang = "zh"
        self.prompt_templates = _prepare_prompt_templates()

    def query(
        self,
        query: str,
        articles: List[RbaseArticle],
        params: dict = {},
        **kwargs
    ) -> Tuple[str, List[RetrievalResult], dict]:
        """
        Generate channel summary

        Args:
            query: the key prompt of the content to be generated
            articles: article list
            min_words: minimum words
            max_words: maximum words
            **kwargs: other parameters

        Returns:
            str: the generated summary text
        """
        collected_content = ""
        usage = {}
        for chunk in self.query_generator(query, articles, params, **kwargs):
            if len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content is not None:
                    collected_content += delta.content

            # if there is token information, add it to usage
            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage
        return collected_content, [], usage

    def query_generator(self, query: str, articles: List[RbaseArticle], params: dict = {}, **kwargs) -> Generator[str, None, None]:
        """
        Generate channel summary chunks

        Args:
            query: the key prompt of the content to be generated
            articles: article list
            min_words: minimum words
            max_words: maximum words
            **kwargs: other parameters

        Returns:
            Generator[str, None, None]: the generated summary text
        """
        if kwargs.get("verbose"):
            self.verbose = True
        if kwargs.get("target_lang"):
            self.target_lang = kwargs.get("target_lang")
        if kwargs.get("purpose"):
            self.purpose = kwargs.get("purpose")
        else:
            self.purpose = ""
        
        prompt_template = self.select_prompt_template(query, self.target_lang, self.purpose)
        # build article info
        articles_info = []
        for article in articles:
            article_info = {
                "article_id": article.article_id,
                "title": article.title,
                "authors": article.authors,
                "journal": article.journal_name,
                "pubdate": article.pubdate,
                "abstract": article.abstract
            }
            articles_info.append(article_info)
        
        # build prompt
        params["query"] = query
        params["articles_info"] = articles_info
        params = self._format_user_params(params)
        prompt = prompt_template.generate_prompt(user_params=params)
        if self.verbose:
            debug(f"prompt: {prompt}")
        
        # call LLM to generate summary
        for chunk in self.writing_llm.stream_generator([{"role": "user", "content": prompt}]):
            if len(chunk.choices) > 0:
                if hasattr(chunk.choices[0].delta, "reasoning_content") and chunk.choices[0].delta.reasoning_content is not None:
                    chunk.choices[0].delta.progress = ProgressHint["MERGE_DOCUMENT"]
                if hasattr(chunk.choices[0].delta, "content") and chunk.choices[0].delta.content is not None:
                    chunk.choices[0].delta.progress = ProgressHint["GENERATE_ANSWER"]
            yield chunk

    def select_prompt_template(self, query: str, target_lang: str, purpose: str) -> SummaryPromptTemplate:
        """
        Select the most suitable prompt template based on the user query and target language

        Args:
            query: user query content
            target_lang: target language

        Returns:
            SummaryPromptTemplate: selected prompt template
        """

        selected_template_id = ""
        if purpose != "" and target_lang != "":
            key = f"{purpose}_{target_lang}"
            selected_template_id = PROMPT_MATCHES.get(key, "")

        # build possible templates info
        templates_info = []
        for template_id, template in self.prompt_templates.items():
            if template_id == selected_template_id:
                return template

            templates_info.append(f"Template ID: {template_id}\n{template.application_description()}\n")
        
        prompt = SummaryPrompts.PROMPT_ROUTER_PROMPT.format(
            query=query,
            target_lang=target_lang,
            templates_info='\n'.join(templates_info)
        )

        # use reasoning_llm to select template
        response = self.reasoning_llm.chat([{"role": "user", "content": prompt}])
        selected_template_id = response.content.strip()
        
        # validate selected template
        if selected_template_id not in self.prompt_templates:
            # if selected template is invalid, use the first template
            selected_template_id = list(self.prompt_templates.keys())[0]
            
        return self.prompt_templates[selected_template_id] 

    def _format_user_params(self, params: dict) -> dict:
        history = ""
        if params.get('user_history'):
            if self.target_lang == "zh":
                history += "\n用户最近的讨论记录：\n" 
            else:
                history += "\nUser's recent discussion record:\n"
            history += "\n\t".join([f"{item['role']}: {item['content']}" for item in params.get('user_history')])
            history += "\n\n"
        params["user_history"] = history
        return params

    
    def build_progress_chunk(self, progress: str) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=f"chatcmpl-0",
            object="chat.completion.chunk",
            created=int(time.time()),
            choices=[{
                "index": 0,
                "delta": {"progress": progress},
                "finish_reason": None
            }],
            model="rbase-summary-agent",
            usage=self.usage
        )

    def build_progress_json_str(self, progress: str, summary_id: int, is_finish: bool = False) -> str:
        progress_chunk = {
            "id": f"chatcmpl-{summary_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "rbase-summary-agent",
            "choices": [{
                "index": 0,
                "delta": {"progress": progress},
                "finish_reason": "stop" if is_finish else None
            }]
        }
        return f"data: {json.dumps(progress_chunk)}\n\n".encode('utf-8')

    def build_role_json_str(self, summary_id: int) -> str:
        role_chunk = {
            "id": f"chatcmpl-{summary_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }],
            "model": "rbase-summary-agent",
        }
        return f"data: {json.dumps(role_chunk)}\n\n".encode('utf-8')


def _prepare_prompt_templates() -> Dict[str, SummaryPromptTemplate]:
    templates = {}
    templates["channel_summary_01"] = SummaryPromptTemplate(id="channel_summary_01", 
                                          target="channel summary or column summary", 
                                          lang="Chinense", 
                                          prompt=SummaryPrompts.CHANNEL_SUMMARY_ZH)

    templates["channel_summary_02"] = SummaryPromptTemplate(id="channel_summary_02", 
                                          target="channel summary or column summary", 
                                          lang="English", 
                                          prompt=SummaryPrompts.CHANNEL_SUMMARY_EN)

    templates["channel_question_01"] = SummaryPromptTemplate(id="channel_question_01", 
                                          target="user cared questions about the channel", 
                                          lang="Chinense", 
                                          prompt=SummaryPrompts.CHANNEL_QUESTION_ZH)

    templates["channel_question_02"] = SummaryPromptTemplate(id="channel_question_02", 
                                          target="user cared questions about the channel", 
                                          lang="English", 
                                          prompt=SummaryPrompts.CHANNEL_QUESTION_EN)

    templates["popular_01"] = SummaryPromptTemplate(id="popular_01", 
                                          target="popular science short article", 
                                          lang="Chinense", 
                                          prompt=SummaryPrompts.CHANNEL_POPULAR_ZH)

    templates["ppt_01"] = SummaryPromptTemplate(id="ppt_01", 
                                          target="ppt outline", 
                                          lang="Chinense", 
                                          prompt=SummaryPrompts.CHANNEL_PPT_ZH)

    templates["footage_01"] = SummaryPromptTemplate(id="footage_01", 
                                          target="footage script", 
                                          lang="Chinense", 
                                          prompt=SummaryPrompts.CHANNEL_FOOTAGE_ZH)

    templates["opportunity_01"] = SummaryPromptTemplate(id="opportunity_01", 
                                          target="analyze business opportunity", 
                                          lang="Chinense", 
                                          prompt=SummaryPrompts.CHANNEL_OPPORTUNITY_ZH)

    return templates
