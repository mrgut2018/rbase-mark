from typing import Tuple, List, AsyncGenerator
import time
from deepsearcher import configuration
from deepsearcher.llm.base import BaseLLM
from deepsearcher.embedding.base import BaseEmbedding
from deepsearcher.agent import AcademicTranslator, SensitiveWordDetectionAgent, AsyncAgent
from deepsearcher.agent.prompts.discuss_prompts import DiscussPrompts
from deepsearcher.vector_db.base import BaseVectorDB
from deepsearcher.vector_db import RetrievalResult
from deepsearcher.rbase.ai_models import AILogType, AILog
from deepsearcher.tools import log, json_util 
from deepsearcher.tools.milvus_query_builder import MilvusQueryBuilder
from openai.types.chat import ChatCompletionChunk
import json

ProgressHint = {
    "LOAD_BACKGROUND": "正在获取AI对话栏目信息",
    "SENSITIVE_WORD_DETECTION": "正在检查用户的提问内容",
    "ANALYSIS": "正在分析用户的问题",
    "EXTRACT_OBJECTS": "正在提取问题要素",
    "CREATE_SEARCH_QUERY": "正在生成查询条件",
    "SEARCH_DOCUMENT": "正在数据库中检索文献",
    "SEARCH_RESULTS": "检索到{article_count}篇相关文献，正在分析",
    "MERGE_DOCUMENT": "正在分析文献素材，整理回复思路",
    "GENERATE_ANSWER": "正在生成回答",
    "FINISH": "回复完成"
}

class DiscussIntention:
    def __init__(self, obj: dict):
        self.intention = obj.get("intention", "其他")
        self.intention = self.intention.strip()
        self.is_academic = obj.get("is_academic", True)

    def should_response(self) -> bool:
        if (self.intention == "其他" or self.intention == "语气表达") and not self.is_academic:
            return False
        else:
            return True


class DiscussAgent(AsyncAgent):
    """
    Discuss agent class, used to process academic discussions between users and AI.
    
    This agent will analyze the intention of the user's question, decide whether to query more literature, and generate the corresponding reply.
    """
    def __init__(self, llm: BaseLLM, reasoning_llm: BaseLLM, translator: AcademicTranslator, embedding_model: BaseEmbedding, vector_db: BaseVectorDB, **kwargs):
        """
        Initialize discuss agent
        
        Args:
            llm: language model
            reasoning_llm: reasoning language model
            translator: academic translator
            embedding_model: vector model
            vector_db: vector database
        """
        self.llm = llm
        self.reasoning_llm = reasoning_llm
        self.translator = translator
        self.embedding_model = embedding_model
        self.vector_db = vector_db
        
        self.top_k_per_section = kwargs.get("top_k_per_section", 5)
        self.vector_db_collection = kwargs.get("vector_db_collection", self.vector_db.default_collection)
        self.verbose = kwargs.get("verbose", configuration.config.rbase_settings.get("verbose", False))
        self.ai_log = None
        self.swd_client = SensitiveWordDetectionAgent()
        self.resetUsage()

    def resetUsage(self):
        self.usage = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def addUsage(self, usage: dict):
        total_tokens = usage.get("total_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        self.usage["total_tokens"] += total_tokens
        self.usage["prompt_tokens"] += prompt_tokens
        self.usage["completion_tokens"] += completion_tokens

    async def query(self, query: str, **kwargs) -> Tuple[str, List[RetrievalResult], dict]:
        """
        Process user query and generate reply
        
        Args:
            query: user query
            **kwargs: other parameters, including background, history, target_lang, request_params etc.
            
        Returns:
            Tuple(reply text, retrieval results list, other metadata)
        """
        collected_content = ""
        async for chunk in self.query_generator(query, **kwargs):
            if len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content is not None:
                    collected_content += delta.content

            if hasattr(chunk, "usage") and chunk.usage:
                self.usage["total_tokens"] += chunk.usage.total_tokens
                self.usage["prompt_tokens"] += chunk.usage.prompt_tokens
                self.usage["completion_tokens"] += chunk.usage.completion_tokens
        return collected_content, [], self.usage


    async def query_generator(self, query: str, **kwargs) -> AsyncGenerator[object, None]:
        """
        Process user query and generate reply
        
        Args:
            query: user query
            **kwargs: other parameters, including background, history, target_lang, request_params etc.
            
        Returns:
            AsyncGenerator[object, None]: Async generator of reply text
        """
        self.resetUsage()
        # get parameters
        background = kwargs.get("background", "")
        history = kwargs.get("history", [])
        target_lang = kwargs.get("target_lang", "zh")
        self.top_k_per_section = kwargs.get("top_k_per_section", self.top_k_per_section)
        self.vector_db_collection = kwargs.get("vector_db_collection", self.vector_db_collection)
        self.verbose = kwargs.get("verbose", self.verbose)
        self.further_question_count = kwargs.get("further_question_count", 3)
        discuss_uuid = kwargs.get("discuss_uuid", "")
        self.ai_log = AILog(
            id=0,
            log_type=AILogType.DISCUSS_AGENT,
            uuid=discuss_uuid,
            intention="",
            search_query="",
            query_limit="",
            resource_log=""
        )
        start_time = time.time()

        yield self.build_progress_chunk(ProgressHint["SENSITIVE_WORD_DETECTION"])
        swd_result = self.swd_client.detect_sensitive_words(query)
        if swd_result.has_risk:
            yield self.build_ai_content_chunk("您的提问中包含敏感词汇，根据法律法规，Rbase AI不能回答您的问题")
            return 
        
        yield self.build_progress_chunk(ProgressHint["ANALYSIS"])
        
        try:
            intention_result = self.intention_analysis(background, history, query)
            intention = DiscussIntention(intention_result)

            # record intention analysis duration
            self.ai_log.intention_duration = int(time.time() - start_time)
            start_time = time.time()
            # check if need to response
            if not intention.should_response():
                yield self.build_ai_content_chunk("这个问题好像与学术讨论无关哦，我是Rbase AI，请问我关于学术方面的问题吧")
                return 
            
            query_filters = ""
            yield self.build_progress_chunk(ProgressHint["EXTRACT_OBJECTS"])
            query_objects = self.query_objects_analysis(query)
            if len(query_objects) > 0:
                builder = MilvusQueryBuilder()
                query_filters = await builder.build_filter_from_objects(query_objects)
                self._verbose(f"<查询过滤> 查询过滤条件: '{query_filters}' </查询过滤>")

            # search from vector db
            retrieval_results = []
            yield self.build_progress_chunk(ProgressHint["CREATE_SEARCH_QUERY"])
            search_query = self.create_search_query(background, history, query)
            search_query = self.translator.translate(search_query, target_lang="en")
            self.ai_log.search_query = search_query
            self.ai_log.query_limit = query_filters
            
            # execute search
            query_vector = self.embedding_model.embed_query(search_query)
            yield self.build_progress_chunk(ProgressHint["SEARCH_DOCUMENT"])
            self._verbose(f"<检索> 正在检索文献，查询语句: '{search_query}' </检索>")
            retrieval_results = self.vector_db.search_data(
                collection=self.vector_db_collection,
                vector=query_vector,
                top_k=self.top_k_per_section,
                filter=query_filters
            )
            
            # format retrieval results
            article_count, formatted_results = self.parse_search_results(retrieval_results)
            self.ai_log.search_duration = int(time.time() - start_time)
            self.ai_log.resource_log = formatted_results
            self.ai_log.article_count = article_count
            self._verbose(f"<检索> 检索到 {len(retrieval_results)} 条数据，{article_count} 篇文献")
            yield self.build_progress_chunk(ProgressHint["SEARCH_RESULTS"].format(article_count=article_count))
            
            further_question_prompt = ""
            further_question_requirement = ""
            if self.further_question_count > 0:
                further_question_prompt = f"，并提出用户可能会感兴趣的{self.further_question_count}个延伸提问"
                further_question_requirement = "6. 延伸提问在回复完成之后再提供，问题应与本次回复的内容相关，并且是历史对话中未曾提及的问题。\n"
                further_question_requirement += "7. 延伸提问在正文输出后直接输出，不需要呈现为一个章节，也无需添加任何markdown或其他类型的分隔符。延伸提问的每个问题请使用<question></question>标签包裹，每个问题一行，无需添加序号或其他辅助标记，提供问题之后，也无需再输出任何其他内容。"
            
            # generate answer
            answer_prompt = DiscussPrompts.DISCUSS_ANSWER_PROMPT.format(
                background=background,
                retrieval_results=formatted_results,
                history=self.format_history(history),
                query=query,
                intention=intention,
                target_lang=target_lang,
                further_question_prompt=further_question_prompt,
                further_question_requirement=further_question_requirement
            )
            
            self._verbose(f"<生成回复> 正在生成回复... </生成回复>", debug_msg=f"answer_prompt: {answer_prompt}")
            for chunk in self.reasoning_llm.stream_generator([{"role": "user", "content": answer_prompt}]):
                if len(chunk.choices) > 0:
                    if hasattr(chunk.choices[0].delta, "reasoning_content") and chunk.choices[0].delta.reasoning_content is not None:
                        chunk.choices[0].delta.progress = ProgressHint["MERGE_DOCUMENT"]
                    if hasattr(chunk.choices[0].delta, "content") and chunk.choices[0].delta.content is not None:
                        chunk.choices[0].delta.progress = ProgressHint["GENERATE_ANSWER"]
                    
                yield chunk
        except json.JSONDecodeError as e:
            log.error(f"解析LLM响应失败: {e}")
            return 

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
            model="rbase-discuss-agent",
            usage=self.usage
        )

    def build_content_chunk(self, content: str) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=f"chatcmpl-0",
            object="chat.completion.chunk",
            created=int(time.time()),
            choices=[{
                "index": 0,
                "delta": {"content": content},
                "finish_reason": None
            }],
            model="rbase-discuss-agent",
            usage=self.usage
        )

    def build_ai_content_chunk(self, content: str) -> ChatCompletionChunk:
        prompt = DiscussPrompts.POLISH_TEXT_RESPONSE_TEMPLATE.format(content=content)
        response = self.llm.chat([{"role": "user", "content": prompt}])
        self.addUsage(response.usage())
        return ChatCompletionChunk(
            id=f"chatcmpl-0",
            object="chat.completion.chunk",
            created=int(time.time()),
            choices=[{
                "index": 0,
                "delta": {"content": response.content.strip()},
                "finish_reason": None
            }],
            model="rbase-discuss-agent",
            usage=self.usage
        )

    def build_progress_json_str(self, progress: str, discuss_id: int, is_finish: bool = False) -> str:
        progress_chunk = {
            "id": f"chatcmpl-{discuss_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "rbase-discuss-agent",
            "choices": [{
                "index": 0,
                "delta": {"progress": progress},
                "finish_reason": "stop" if is_finish else None
            }]
        }
        return f"data: {json.dumps(progress_chunk)}\n\n".encode('utf-8')

    def build_role_json_str(self, discuss_id: int) -> str:
        role_chunk = {
            "id": f"chatcmpl-{discuss_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }],
            "model": "rbase-discuss-agent",
        }
        return f"data: {json.dumps(role_chunk)}\n\n".encode('utf-8')

    def format_history(self, history: list) -> str:
        """
        This function formats the conversation history into a string.
        It constructs a string by iterating through the history list and formatting each item.
        The function returns the formatted string.

        Args:
            history: The conversation history list.

        Returns:
            A string containing the formatted conversation history.
        """
        formatted_history = ""
        for item in history:
            if item.get("role") == "user":
                formatted_history += f"用户: {item.get('content', '')}\n"
            else:
                formatted_history += f"AI助理: {item.get('content', '')}\n\n"
        return formatted_history
    
    def intention_analysis(self, background: str, history: list, query: str) -> dict:
        """
        This function performs intention analysis based on the user's action, background information, formatted conversation history, and the current query.
        It constructs a prompt using these inputs and sends it to the reasoning language model for analysis.
        The function returns a dictionary representing the analyzed intention.

        Args:
            background: The background information about the user's action.
            formatted_history: The formatted conversation history.
            query: The current query from the user.

        Returns:
            A dictionary containing the analyzed intention.
        
        Raises:
            ValueError: If the response cannot be parsed as JSON.
        """
        prompt = DiscussPrompts.DISCUSS_INTENTION_PROMPT.format(
            background=background,
            history=self.format_history(history),
            query=query
        )
        
        self._verbose(f"<判断意图> 分析用户问题意图... </判断意图>", debug_msg=f"prompt: {prompt}")
        response = self.llm.chat([{"role": "user", "content": prompt}])
        self.addUsage(response.usage())
        try:
            return json_util.json_to_dict(response.content)
        except ValueError as e:
            raise e

    def query_objects_analysis(self, query: str) -> list:
        """
        This function performs query objects analysis based on the current query.
        It constructs a prompt using the query and sends it to the reasoning language model for analysis.
        The function returns a dictionary representing the analyzed query objects.

        Args:
            query: The current query from the user.

        Returns:
            A dictionary containing the analyzed query objects.

        Raises:
            ValueError: If the response cannot be parsed as JSON.
        """
        prompt = DiscussPrompts.QUERY_OBJECTS_PROMPT.format(query=query)
        self._verbose(f"<分析查询对象> 分析用户查询对象... </分析查询对象>", debug_msg=f"prompt: {prompt}")
        response = self.llm.chat([{"role": "user", "content": prompt}])
        self.addUsage(response.usage())
        try:
            rt = json_util.json_to_dict(response.content)
            return rt.get("objects", [])
        except ValueError as e:
            raise e

    def create_search_query(self, background: str, history: list, query: str) -> str:
        prompt = DiscussPrompts.SEARCH_QUERY_PROMPT.format(
            query=query,
            background=background,
            history=self.format_history(history)
        )
        self._verbose("<生成查询语句> 生成向量数据库查询语句... </生成查询语句>", debug_msg=f"prompt: {prompt}")
        response = self.llm.chat([{"role": "user", "content": prompt}])
        self.addUsage(response.usage())
        try:
            return response.content.strip()
        except ValueError as e:
            raise e
    
    def parse_search_results(self, retrieval_results: List[RetrievalResult]) -> Tuple[int, str]:
        formatted_results = ""
        article_ids = {}
        for i, result in enumerate(retrieval_results):
            formatted_results += f"[{result.metadata.get('reference_id', i+1)}] \n{result.text}\n\n\n"
            article_ids[result.metadata.get('reference_id', i+1)] = 1
        
        return len(article_ids), formatted_results

    def _verbose(self, msg: str, debug_msg: str = ""):
        if self.verbose:
            log.color_print(msg)
            if debug_msg:
                log.debug(debug_msg)
    