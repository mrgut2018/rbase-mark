from abc import ABC
from enum import Enum

import langid
import json
from typing import Optional, List
from deepsearcher.llm.base import BaseLLM, ChatResponse
from deepsearcher.embedding.base import BaseEmbedding
from deepsearcher.tools.rbase_file_loader import load_rbase_txt_file
from deepsearcher.vector_db.base import BaseVectorDB
from deepsearcher.loader.file_loader.base import BaseLoader
from deepsearcher.rbase.ai_models import Classifier, ClassifierType, ClassifyMethod
from deepsearcher.rbase.raw_article import RawArticle
from deepsearcher.api.rbase_util import (
    load_classifier_by_id, load_classifier_by_alias,
    load_classifiers_by_ids,
    list_classifier_values_by_classifier_id,
    list_classifier_results_by_article_id,
    check_classifier_prerequisite_values_in,
    check_classifier_prerequisite_status_in,
    load_article_full_text
)
from deepsearcher.agent.prompts.classify_prompts import (
    GENERAL_VALUE_CLASSIFIER_PROMPT,
    GENERAL_VALUE_MERGED_CLASSIFIER_PROMPT,
    GENERAL_VALUE_DESC_PROMPT,
    NAMED_ENTITY_CLASSIFIER_PROMPT,
    NAMED_ENTITY_RECHECK_CLASSIFIER_PROMPT,
    NAMED_ENTITY_RECHECK_WITH_CONTEXT_PROMPT,
    NER_OUTPUT_REQUIREMENT,
    classifer_output_requirement,
    merged_classifer_output_requirement,
    value_route_table_to_markdown_table_tr,
    candidates_to_markdown_table,
    classifier_prerequisite_in_short
)
from deepsearcher.api.rbase_util.sync.classify import (
    load_classifier_value_route,
    extract_entity_context
)
from deepsearcher.agent.classifier_value_process import ClassifierValueProcess
from deepsearcher.tools.log import error, debug, critical
from deepsearcher.tools.json_util import json_strip


class ClassifierConditions(str, Enum):
    NEED_MATCH_TERM_TREE = "need_match_term_tree"
    NEED_SEARCH_VECTOR_DB = "need_search_vector_db"
    RECHECK_VECTOR_DB_UNEXACT_MATCH = "recheck_vector_db_unexact_match"
    CLASSIFIER_LANGUAGE_MATCH = "classifier_language_match"
    ALLOW_NO_MATCHING_RESULTS = "allow_no_matching_results"

class ClassifierPrerequisiteNotMetError(Exception):
    """
    当分类器前置条件不满足时抛出该异常，异常消息包含分类器alias
    """
    def __init__(self, classifier_alias: str):
        self.classifier_alias = classifier_alias
        super().__init__(f"分类器前置条件不满足，alias: {classifier_alias}")
    

class ClassifierAgentImpl(ABC):
    def __init__(self, classifier: Classifier) -> None:
        self.classifier = classifier
    
    def classify(self, raw_article: RawArticle, **kwargs) -> ChatResponse:
        pass

    def check(self, condition: str, **kwargs) -> bool:
        pass

class ClassifyAgent:

    def __init__(self, 
                 llm: BaseLLM, 
                 reasoning_llm: BaseLLM, 
                 embedding_model: BaseEmbedding, 
                 vector_db: BaseVectorDB, 
                 file_loader: BaseLoader, 
                 rbase_settings: dict,
                 **kwargs) -> None:
        self.llm = llm
        self.reasoning_llm = reasoning_llm
        self.embedding_model = embedding_model
        self.vector_db = vector_db
        self.file_loader = file_loader
        self.rbase_settings = rbase_settings
        self.last_response = None
        self.usage = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.totalUsage = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def setReasoningLLM(self, reasoning_llm: BaseLLM):
        self.reasoning_llm = reasoning_llm

    def accumulateUsage(self, response: ChatResponse):
        self.usage["total_tokens"] += response.total_tokens
        self.usage["prompt_tokens"] += response.prompt_tokens
        self.usage["completion_tokens"] += response.completion_tokens
        self.totalUsage["total_tokens"] += response.total_tokens
        self.totalUsage["prompt_tokens"] += response.prompt_tokens
        self.totalUsage["completion_tokens"] += response.completion_tokens

    def resetUsage(self):
        self.usage = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def classify(self, classifier_id: int, raw_article: RawArticle, **kwargs) -> str:
        if not kwargs.get('entity_recheck', False): # 重新检查不重置usage
            self.resetUsage()
        classifier = load_classifier_by_id(classifier_id)
        if classifier is None:
            raise Exception(f"Classifier {classifier_id} not found")
        
        debug(f"Classifier: {classifier.name} / {classifier.alias} / {classifier.id}")
        debug(f"Raw Article: {raw_article.title} / {raw_article.id}")
        result_cache = kwargs.get("result_cache", None)
        allow_use_cache = kwargs.get("allow_use_cache", True)
        if result_cache is not None and allow_use_cache and classifier.alias in result_cache:
            debug(f"从缓存中获取分类器 {classifier.alias} 的分类结果...")
            self.last_response = ChatResponse(content=json.dumps(result_cache[classifier.alias]), total_tokens=0)
            return self.last_response.content

        # Check if the prerequisite is satisfied
        if not self.check_classifier_prerequisite([classifier], raw_article, kwargs.get("task_id", None)):
            raise ClassifierPrerequisiteNotMetError(classifier.alias)
        
        impl = self.get_classifier_agent_impl(classifier, **kwargs)
        kwargs["file_loader"] = self.file_loader
        kwargs["rbase_oss_settings"] = self.rbase_settings.get("oss", {})
        self.last_response = impl.classify(raw_article, **kwargs)
        if self.last_response.finish_reason and self.last_response.finish_reason != "stop":
            debug(f"LLM调用停止原因: {self.last_response.finish_reason}")
        self.accumulateUsage(self.last_response)
        return self.last_response.content

    def merged_classsify(self, classifier_ids: list[int], raw_article: RawArticle, **kwargs) -> str:
        self.resetUsage()
        # 批量加载所有分类器（一次 IN 查询替代 N 次单独查询）
        classifiers_map = load_classifiers_by_ids(classifier_ids)
        classifiers = []
        classifier_requirements = ""
        for classifier_id in classifier_ids:
            classifier = classifiers_map.get(classifier_id)
            if classifier is None:
                continue
            is_req_matched, classifier_requirements = self.check_merged_classifier_requirements(classifier, classifier_requirements)
            if is_req_matched:
                debug(f"Found classifier in merge group: {classifier.name} / {classifier.alias} / {classifier.id}")
                classifiers.append(classifier)
            else:
                raise Exception(f"Classifier {classifier.id} requirements not match with {classifier_requirements}")

        if len(classifiers) <= 0:
            raise Exception(f"Classifier {classifier_ids} not found")

        # Check if the prerequisite is satisfied (can be skipped by caller)
        skip_prerequisite = kwargs.pop("skip_prerequisite", False)
        if not skip_prerequisite:
            if not self.check_classifier_prerequisite(classifiers, raw_article, kwargs.get("task_id", None)):
                raise ClassifierPrerequisiteNotMetError(classifiers[0].alias)

        impl = self.get_merged_classifier_agent_impl(classifiers, **kwargs)
        kwargs["file_loader"] = self.file_loader
        kwargs["rbase_oss_settings"] = self.rbase_settings.get("oss", {})
        self.last_response = impl.classify(raw_article, **kwargs)
        if self.last_response.finish_reason and self.last_response.finish_reason != "stop":
            debug(f"LLM调用停止原因: {self.last_response.finish_reason}")
        self.accumulateUsage(self.last_response)
        return self.last_response.content

    def check_merged_classifier_requirements(self, classifier: Classifier, requirements: str) -> tuple[bool, str]:
        return True, ""
        is_matched = False
        if classifier:
            if requirements == "":
                requirements = self._classifier_requirements(classifier)
                is_matched = True
            elif requirements != self._classifier_requirements(classifier):
                is_matched = False
        return is_matched, requirements

    def get_merged_classifier_agent_impl(self, classifiers: list[Classifier], **kwargs) -> ClassifierAgentImpl:
        if classifiers[0].classify_method == ClassifyMethod.GENERAL_CLASSIFICATION:
            return GeneralValueMergedClassifier(classifiers, self.reasoning_llm)
        else:
            raise Exception(f"Classifier {classifiers[0].id} classify method not supported")

    def get_classifier_agent_impl(self, classifier: Classifier, **kwargs) -> ClassifierAgentImpl:
        if classifier.type == ClassifierType.VALUE_CLASSIFIER:
            if classifier.classify_method == ClassifyMethod.GENERAL_CLASSIFICATION:
                return GeneralValueClassifier(classifier, self.reasoning_llm)
            elif classifier.classify_method == ClassifyMethod.NAMED_ENTITY_MATCHING:
                recheck = kwargs.get('entity_recheck', False)
                if not recheck:
                    return NamedEntityMatchingClassifier(classifier, self.reasoning_llm)
                else:
                    return NamedEntityRecheckClassifier(classifier, self.reasoning_llm)
            else:
                raise Exception(f"Classifier {classifier.id} classify method not supported")
        elif classifier.type == ClassifierType.ROUTE_CLASSIFIER:
            return RouteClassifier(classifier, self.reasoning_llm)
        else:
            raise Exception(f"Classifier {classifier.id} type not supported")
    
    def check_classifier_prerequisite(self, classifiers: List[Classifier], raw_article: RawArticle, task_id: Optional[int] = None) -> bool:
        """
        Check if the prerequisite of the classifiers is satisfied

        Args:
            classifiers: List of Classifier objects
            raw_article: Article object to be classified
            task_id: Optional task id

        Returns:
            bool: True if all classifiers' prerequisites are satisfied, False if not
        """
        # 提取所有 classifiers 的 alias 列表，用于判断某个 prerequisite 是否会在处理过程中被判断
        classifier_aliases = {classifier.alias for classifier in classifiers}

        # 检查每一个 classifier 的前提条件
        for classifier in classifiers:
            if classifier.prerequisite is None:
                continue  # 如果没有 prerequisite，跳过这个 classifier

            try:
                prerequisite_rules = classifier.prerequisite
                for rule in prerequisite_rules:
                    classifier_alias = rule.get('classifier_alias', '')
                    value_in = rule.get('value_in', None)
                    status_in = rule.get('status_in', None)

                    if not classifier_alias or (not value_in and not status_in):
                        return False

                    # 如果这个 classifier_alias 在当前的 classifiers 列表中
                    # 说明这个条件会在处理过程中判断，跳过这条规则
                    if classifier_alias in classifier_aliases:
                        continue

                    # 实际检查前提条件
                    if value_in and not check_classifier_prerequisite_values_in(raw_article.id, classifier_alias, value_in, task_id):
                        return False

                    if status_in and not check_classifier_prerequisite_status_in(raw_article.id, classifier_alias, status_in, task_id):
                        return False

            except Exception as e:
                error(f"Check classifier prerequisite failed: {e}")
                return False

        # 所有 classifiers 的前提条件都满足
        return True

    def _classifier_requirements(self, classifier: Classifier) -> str:
        req = classifier.prerequisite if classifier.prerequisite else ""
        return f"pre: {req}, method: {classifier.classify_method}"


class GeneralValueClassifier(ClassifierAgentImpl):

    def __init__(self, classifier: Classifier, llm: BaseLLM) -> None:
        self.classifier = classifier
        self.llm = llm

    def classify(self, raw_article: RawArticle, **kwargs) -> ChatResponse:
        oss_config = kwargs.get("rbase_oss_settings", {})
        file_loader = kwargs.get("file_loader", None)
        classifier_values = list_classifier_values_by_classifier_id(self.classifier.id)
        full_text = load_article_full_text(raw_article, oss_config, file_loader, self.classifier.is_need_full_text)

        prompt = GENERAL_VALUE_CLASSIFIER_PROMPT.format(
            classify_name=self.classifier.name,
            purpose=self.classifier.purpose,
            target=self.classifier.target,
            principle=self.classifier.principle,
            criterion=self.classifier.criterion,
            value_table=ClassifierValueProcess.prompt_value_table(classifier_values),
            article_title=raw_article.title,
            article_journal_name=raw_article.journal_name,
            article_summary=raw_article.summary,
            article_keywords=raw_article.source_keywords,
            article_full_text=full_text,
            output_requirement=classifer_output_requirement(self.classifier),
        )
        debug(f"Classifier Prompt length: {len(prompt.split())} words")
        response = self.llm.chat([{'role': 'user', 'content': prompt}], cot_log_filename=f"raw_{raw_article.id}_c_{self.classifier.id}_v_{self.classifier.ver}")
        response.content = json_strip(response.content.strip())
        return response

    def check(self, condition: str, **kwargs) -> bool:
        return True

class GeneralValueMergedClassifier(ClassifierAgentImpl):

    def __init__(self, classifiers: list[Classifier], llm: BaseLLM) -> None:
        self.classifiers = classifiers
        self.llm = llm

    def classify(self, raw_article: RawArticle, **kwargs) -> ChatResponse:
        oss_config = kwargs.get("rbase_oss_settings", {})
        file_loader = kwargs.get("file_loader", None)
        is_need_full_text = any(c.is_need_full_text != 0 for c in self.classifiers)
        full_text = load_article_full_text(raw_article, oss_config, file_loader, is_need_full_text)

        classifier_descriptions = ""
        for index, classifier in enumerate(self.classifiers):
            classifier_values = list_classifier_values_by_classifier_id(classifier.id)
            classifier_descriptions += GENERAL_VALUE_DESC_PROMPT.format(
                seq=index+1,
                classifier_name=classifier.name,
                classifier_alias=classifier.alias,
                prerequisite=classifier_prerequisite_in_short(classifier),
                purpose=classifier.purpose,
                target=classifier.target,
                principle=classifier.principle,
                criterion=classifier.criterion,
                multiple_result_requirement="文章符合的分类可能有多个" if classifier.is_multi else "文章符合的分类有且只有1个",
                value_table=ClassifierValueProcess.prompt_value_table(classifier_values),
            )

        prompt = GENERAL_VALUE_MERGED_CLASSIFIER_PROMPT.format(
            classifier_descriptions=classifier_descriptions,
            article_title=raw_article.title,
            article_journal_name=raw_article.journal_name,
            article_summary=raw_article.summary,
            article_keywords=raw_article.source_keywords,
            article_full_text=full_text,
            output_requirement=merged_classifer_output_requirement(),
        )
        debug(f"Merged Classifier Prompt length: {len(prompt.split())} words")
        response = self.llm.chat([{'role': 'user', 'content': prompt}], cot_log_filename=f"raw_{raw_article.id}_mc_{self.classifiers[0].id}_v_{self.classifiers[0].ver}")
        response.content = json_strip(response.content.strip())
        return response

    def check(self, condition: str, **kwargs) -> bool:
        return True

class NamedEntityMatchingClassifier(ClassifierAgentImpl):

    def __init__(self, classifier: Classifier, llm: BaseLLM) -> None:
        self.classifier = classifier
        self.llm = llm

    def classify(self, raw_article: RawArticle, **kwargs) -> ChatResponse:
        if self.classifier.classify_params:
            classifier_results_alias = self.classifier.classify_params.get("use_classifier_results", False)
        else:
            classifier_results_alias = False
        oss_config = kwargs.get("rbase_oss_settings", {})
        file_loader = kwargs.get("file_loader", None)
        full_text = ""

        json_results = []
        if classifier_results_alias and classifier_results_alias != "":
            history_classifier = load_classifier_by_alias(classifier_results_alias)
            if history_classifier:
                classifier_results = list_classifier_results_by_article_id(raw_article.id, history_classifier, unique_value=True)
                for classifier_result in classifier_results:
                    json_results.append({
                        "entity_name": classifier_result.label_item_value,
                        "entity_type": classifier_result.label_item_key,
                        "entity_full_name": classifier_result.metadata.get("entity_full_name") if classifier_result.metadata else "",
                        "language": classifier_result.metadata.get("language") if classifier_result.metadata else "en",
                        "location": classifier_result.location,
                        "concept_id": classifier_result.concept_id,
                    })
        if len(json_results) <= 0:
            full_text = load_article_full_text(raw_article, oss_config, file_loader, self.classifier.is_need_full_text)

            prompt = NAMED_ENTITY_CLASSIFIER_PROMPT.format(
                purpose=self.classifier.purpose if self.classifier.purpose else "",
                target=self.classifier.target if self.classifier.target else "",
                criterion=self.classifier.criterion if self.classifier.criterion else "",
                principle=self.classifier.principle if self.classifier.principle else "无",
                article_title=raw_article.title,
                article_summary=raw_article.summary,
                article_keywords=raw_article.source_keywords,
                article_full_text=full_text,
                output_requirement=NER_OUTPUT_REQUIREMENT
            )
            debug(f"NER Prompt length: {len(prompt.split())} words")
            response = self.llm.chat([{'role': 'user', 'content': prompt}], cot_log_filename=f"raw_{raw_article.id}_ner_{self.classifier.id}_v_{self.classifier.ver}")
            response.content = json_strip(response.content.strip())
            
            # 尝试解析JSON，如果失败则调用LLM转换文本为JSON格式
            response = self._ensure_json_format(response)
        else:
            response = ChatResponse(content=json.dumps(json_results), total_tokens=0, prompt_tokens=0, completion_tokens=0)
        return response
    
    def _ensure_json_format(self, response: ChatResponse) -> ChatResponse:
        """
        确保响应内容是有效的JSON格式
        如果不是JSON格式，使用LLM将文本转换为JSON格式
        
        Args:
            response: LLM的原始响应
            
        Returns:
            包含有效JSON内容的ChatResponse对象
        """
        from deepsearcher.agent.prompts.classify_prompts import TEXT_TO_JSON_CONVERSION_PROMPT
        
        # 尝试解析JSON
        try:
            json.loads(response.content)
            # 如果解析成功，说明已经是JSON格式，直接返回
            debug("NER response is valid JSON, no conversion needed")
            return response
        except json.JSONDecodeError:
            # 解析失败，说明是文本格式，需要转换
            debug(f"Response is not valid JSON, converting text to JSON format...")
            debug(f"Original response content: {response.content}...")
            
            # 调用LLM进行格式转换
            conversion_prompt = TEXT_TO_JSON_CONVERSION_PROMPT.format(
                text_content=response.content
            )
            debug(f"NER Conversion Prompt length: {len(conversion_prompt.split())} words")
            conversion_response = self.llm.chat([{'role': 'user', 'content': conversion_prompt}])
            
            # 清理转换后的内容
            converted_content = json_strip(conversion_response.content.strip())
            debug(f"Converted response content: {converted_content}...")
            
            # 再次尝试解析JSON以验证
            try:
                json.loads(converted_content)
                debug(f"Successfully converted to JSON format")
                # 更新response的内容和token统计
                response.content = converted_content
                response.total_tokens += conversion_response.total_tokens
                response.prompt_tokens += conversion_response.prompt_tokens
                response.completion_tokens += conversion_response.completion_tokens
                return response
            except json.JSONDecodeError as e:
                # 转换后仍然无法解析，记录错误并返回空数组
                error(f"Failed to convert text to valid JSON: {e}")
                error(f"Converted content: {converted_content}")
                response.content = "[]"
                return response

    def check(self, condition: str, **kwargs) -> bool:
        if condition == ClassifierConditions.NEED_MATCH_TERM_TREE:
            return self.classifier.term_tree_id is not None and self.classifier.term_tree_node_id is not None
        elif condition == ClassifierConditions.RECHECK_VECTOR_DB_UNEXACT_MATCH:
            return self.classifier.classify_params.get("recheck_vector_db_unexact_match", False)
        elif condition == ClassifierConditions.NEED_SEARCH_VECTOR_DB:
            key = kwargs.get('entity_type')
            meta = kwargs.get('metadata')
            if meta is not None:
                parts = meta.get('parts', None)
            else:
                parts = None

            if parts and isinstance(parts, str) and parts.upper() == "RESULT":
                return False
            
            if self.classifier.classify_params and key:
                tables = self.classifier.classify_params.get("search_vector_db_types", [])
                key = key.upper()
                for t in tables:
                    if key == t.upper():
                        return True
                return False
            else:
                return False
        elif condition == ClassifierConditions.CLASSIFIER_LANGUAGE_MATCH:
            if not self.classifier.classify_params:
                return True
            lang = self.classifier.classify_params.get("language", None)
            if lang is None:
                return True
            value_lang = kwargs.get('value_lang', None)
            value = kwargs.get('value', None)
            if value_lang:
                return lang == value_lang
            elif value:
                langid_result = langid.classify(value)
                if langid_result:
                    return langid_result[0] == lang
                else:
                    return False
            else:
                return False
        elif condition == ClassifierConditions.ALLOW_NO_MATCHING_RESULTS:
            if self.classifier.classify_params:
                return self.classifier.classify_params.get("allow_no_matching_results", False)
            else:
                return False

        return True

class RouteClassifier(ClassifierAgentImpl):

    def __init__(self, classifier: Classifier) -> None:
        self.classifier = classifier
        
    def classify(self, raw_article: RawArticle, **kwargs) -> str:
        pass

class NamedEntityRecheckClassifier(NamedEntityMatchingClassifier):

    def __init__(self, classifier: Classifier, llm: BaseLLM) -> None:
        self.classifier = classifier
        self.llm = llm

    def classify(self, raw_article: RawArticle, **kwargs) -> ChatResponse:
        if self.classifier.classify_params:
            llm_invoke_params = self.classifier.classify_params.get("recheck_llm_invoke_params", {})
        else:
            llm_invoke_params = {}

        # 新模式：使用多候选 + 上下文
        candidates = kwargs.get("candidates", None)
        entity_name = kwargs.get("entity_name", None)

        if candidates and entity_name:
            return self._classify_with_context(raw_article, candidates, entity_name, kwargs, llm_invoke_params)

        # 兼容旧模式：使用 classifier_value + value_routes + 全文
        return self._classify_legacy(raw_article, kwargs, llm_invoke_params)

    def _classify_with_context(self, raw_article: RawArticle, candidates: list, entity_name: str,
                               kwargs: dict, llm_invoke_params: dict) -> ChatResponse:
        """
        新模式：基于多候选和上下文进行 recheck。

        Args:
            raw_article: 文章对象
            candidates: 候选列表 [(ClassifierValue, score, is_exact), ...]
            entity_name: 提取的实体名称
            kwargs: 包含 oss_config, file_loader 等参数
            llm_invoke_params: LLM 调用参数
        """
        if not candidates:
            return ChatResponse(content="[]", total_tokens=0, prompt_tokens=0, completion_tokens=0)

        # 为每个候选构建路径
        value_routes = []
        for cv, _, _ in candidates:
            route = load_classifier_value_route(cv)
            value_routes.append(route)

        # 构建候选表格
        candidates_table = candidates_to_markdown_table(candidates, value_routes)

        # 尝试加载全文以提取更准确的上下文
        oss_config = kwargs.get("rbase_oss_settings", {})
        file_loader = kwargs.get("file_loader", None)
        full_text = ""

        if raw_article.txt_file and file_loader:
            try:
                docs = load_rbase_txt_file(oss_config, raw_article.txt_file, file_loader,
                                           include_references=False,
                                           save_downloaded_file=True)
                full_text = "\n\n".join([doc.page_content for doc in docs])
                debug(f"Recheck: 已加载全文，长度: {len(full_text)}")
            except Exception as e:
                debug(f"Recheck: 加载全文失败: {e}，将使用标题+摘要")

        # 从全文或标题+摘要中提取上下文
        if full_text:
            entity_contexts = extract_entity_context(full_text, entity_name, context_chars=300, max_contexts=5)
        else:
            text = f"{raw_article.title or ''} {raw_article.summary or ''}"
            entity_contexts = extract_entity_context(text, entity_name, context_chars=300, max_contexts=5)

        # 如果仍然没有上下文，使用摘要
        if not entity_contexts:
            entity_contexts = raw_article.summary or raw_article.title or ""

        debug(f"Recheck: 实体上下文长度: {len(entity_contexts)}")
        prompt = NAMED_ENTITY_RECHECK_WITH_CONTEXT_PROMPT.format(
            entity_name=entity_name,
            candidates_table=candidates_table,
            entity_contexts=entity_contexts,
            article_title=raw_article.title or "",
            article_keywords=raw_article.source_keywords or ""
        )

        try:
            if llm_invoke_params is None:
                llm_invoke_params = {}
            llm_invoke_params['cot_log_filename'] = f"raw_{raw_article.id}_recheck_{self.classifier.id}_v_{self.classifier.ver}"
            response = self.llm.chat([{'role': 'user', 'content': prompt}], **llm_invoke_params)
            response.content = json_strip(response.content.strip())
            return response
        except Exception as e:
            critical(f"Recheck LLM调用失败: {str(e)}")
            return ChatResponse(content="[]", total_tokens=0, prompt_tokens=0, completion_tokens=0)

    def _classify_legacy(self, raw_article: RawArticle, kwargs: dict, llm_invoke_params: dict) -> ChatResponse:
        """
        兼容旧模式：基于单个 classifier_value + 全文进行 recheck。
        """
        oss_config = kwargs.get("rbase_oss_settings", {})
        file_loader = kwargs.get("file_loader", None)
        is_need_full_text = kwargs.get("is_need_full_text", True)

        full_text = ""
        if self.classifier.is_need_full_text == 1 and is_need_full_text:
            if raw_article.txt_file:
                docs = load_rbase_txt_file(oss_config, raw_article.txt_file, file_loader,
                                           include_references=False,
                                           save_downloaded_file=True)
                full_text = "\n\n".join([doc.page_content for doc in docs])
                debug(f"Use Full text(length: {len(full_text)})")
                full_text = "文章全文如下：\n" + full_text

        classifier_value = kwargs.get("classifier_value", None)
        value_routes = kwargs.get('value_routes', [])
        value_route_table = []
        for value_route in value_routes:
            value_route_table.append(value_route_table_to_markdown_table_tr(value_route))

        if classifier_value and value_route_table:
            prompt = NAMED_ENTITY_RECHECK_CLASSIFIER_PROMPT.format(
                value=classifier_value.value,
                value_route_table=value_route_table,
                article_title=raw_article.title,
                article_summary=raw_article.summary,
                article_keywords=raw_article.source_keywords,
                article_full_text=full_text,
                output_requirement=""
            )

            try:
                if llm_invoke_params is None:
                    llm_invoke_params = {}
                llm_invoke_params['cot_log_filename'] = f"raw_{raw_article.id}_recheck_{self.classifier.id}_v_{self.classifier.ver}"
                response = self.llm.chat([{'role': 'user', 'content': prompt}], **llm_invoke_params)
                response.content = json_strip(response.content.strip())
                return response
            except Exception as e:
                error_msg = str(e)
                critical(f"Recheck LLM调用失败: {error_msg}")

                if full_text:
                    critical(f"尝试不使用全文数据重新进行recheck...")
                    try:
                        prompt_without_fulltext = NAMED_ENTITY_RECHECK_CLASSIFIER_PROMPT.format(
                            value=classifier_value.value,
                            value_route_table=value_route_table,
                            article_title=raw_article.title,
                            article_summary=raw_article.summary,
                            article_keywords=raw_article.source_keywords,
                            article_full_text="",
                            output_requirement=""
                        )
                        response = self.llm.chat([{'role': 'user', 'content': prompt_without_fulltext}], 
                                                 cot_log_filename=f"raw_{raw_article.id}_recheck_{self.classifier.id}_v_{self.classifier.ver}")
                        response.content = json_strip(response.content.strip())
                        critical(f"不使用全文重试成功")
                        return response
                    except Exception as retry_e:
                        critical(f"不使用全文重试仍然失败: {str(retry_e)}")

                critical(f"Recheck失败，返回空结果，继续处理其他词条")
                return ChatResponse(content="[]", total_tokens=0, prompt_tokens=0, completion_tokens=0)
        else:
            return ChatResponse(content="[]", total_tokens=0, prompt_tokens=0, completion_tokens=0)

    def check(self, condition: str, **kwargs) -> bool:
        return True