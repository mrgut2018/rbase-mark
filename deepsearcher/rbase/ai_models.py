import hashlib
import json
import uuid
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from deepsearcher.api.models import SummaryRequest, QuestionRequest, RelatedType, DiscussCreateRequest, DiscussPostRequest, Purpose

class AIContentType(int, Enum):
    """AI内容类型枚举"""
    LONG_SUMMARY = 1  # 长综述
    SHORT_SUMMARY = 2   # 短综述
    DISCUSSION = 10   # 讨论
    RECOMMEND_READ = 20   # 推荐阅读
    ASSOCIATED_QUESTION = 30   # 关联提问

class ClassifierType(int, Enum):
    """分类器类型枚举"""
    VALUE_CLASSIFIER = 1  # 取值分类器
    ROUTE_CLASSIFIER = 2  # 路由分类器

class ClassifyMethod(int, Enum):
    """分类方法枚举"""
    GENERAL_CLASSIFICATION = 1  # 一般性分类（适用于类型较少的情况）
    NAMED_ENTITY_MATCHING = 2   # 命名实体匹配（按词语匹配）

class ClassifierStatus(int, Enum):
    """分类器状态枚举"""
    NORMAL = 1  # 正常
    INVALID = 0  # 无效

class ClassifierValueIsLabel(int, Enum):
    """分类器取值是否可用于标记枚举"""
    YES = 1  # 是
    NO = 0  # 否

class StreamResponse(int, Enum):
    """流式响应枚举"""
    DENY = 0  # 禁用流式响应
    ALLOW = 1 # 启用流式响应

class AIRequestStatus(int, Enum):
    """AI请求状态枚举"""
    START_REQ = 1 # 开始请求
    RECV_REQ = 2 # 收到请求
    HANDLING_REQ= 3 # 处理请求
    FINISHED = 10 # 已完成
    DEPRECATED = 100 # 已废弃

class AIContentRequest(BaseModel):
    """AI内容接口请求模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    content_type: AIContentType = Field(
        ...,
        description="内容类型：1-长综述，2-短综述，10-讨论，20-推荐阅读，30-关联提问"
    )
    is_stream_response: StreamResponse = Field(
        ...,
        description="是否使用流式响应：0-禁用流式响应，1-启用流式响应"
    )
    query: str = Field(
        ...,
        description="查询内容"
    )
    params: dict = Field(
        ...,
        description="查询参数"
    )
    request_hash: str = Field(
        ...,
        description="请求hash"
    )
    status: AIRequestStatus = Field(
        ...,
        description="状态"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

    def hash(self) -> str:
        # 综合query、params和content_type计算hash值
        hash_str = f"{self.content_type}_{self.query}_{json.dumps(self.params, sort_keys=True)}"
        self.request_hash = hashlib.md5(hash_str.encode()).hexdigest()

class AIResponseStatus(int, Enum):
    """AI响应状态枚举"""
    GENERATING = 1 # 生成中
    FINISHED = 10 # 已完成
    MANUALLY_FINISHED = 11 # 手动完成
    DEPRECATED = 100 # 已废弃
    ERROR = 1000 # 错误

class AIContentResponse(BaseModel):
    """AI内容接口响应模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    ai_request_id: int = Field(
        ...,
        description="AI请求ID"
    )
    is_generating: int = Field(
        ...,
        description="是否正在生成：0-不在生成，1-正在生成"
    )
    content: str = Field(
        ...,
        description="内容"
    )
    tokens: dict = Field(
        ...,
        description="令牌"
    )
    usage: dict = Field(
        ...,
        description="使用情况"
    )
    cache_hit_cnt: int = Field(
        ...,
        description="缓存命中次数"
    )
    status: AIResponseStatus = Field(
        ...,
        description="状态"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

class DiscussThread(BaseModel):
    """讨论话题模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    uuid: str = Field(
        "",
        description="UUID"
    )
    related_type: RelatedType = Field(
        ...,
        description="关联类型"
    )
    title: str = Field(
        "",
        description="标题"
    )
    params: dict = Field(
        ...,
        description="参数"
    )
    request_hash: str = Field(
        "",
        description="请求hash"
    )
    user_hash: str = Field(
        "",
        description="用户hash"
    )
    user_id: int = Field(
        0, 
        description="用户ID"
    )
    depth: int = Field(
        0,
        description="深度"
    )
    background: str = Field(
        "",
        description="背景信息"
    )
    is_hidden: int = Field(
        0, 
        description="是否隐藏"
    )
    is_favorite: int = Field(
        0,
        description="是否收藏"
    )
    is_title_modified: int = Field(
        0,
        description="是否修改过标题"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )
    
    def hash(self) -> str:
        # 综合query、params和content_type计算hash值
        self.request_hash = hashlib.md5(f"{self.related_type}_{json.dumps(self.params, sort_keys=True)}".encode()).hexdigest()

    def create_uuid(self) -> str:
        self.uuid = str(uuid.uuid4())
        return self.uuid

class DiscussRole(str, Enum):
    """讨论角色枚举"""
    USER = "user" # 用户
    ASSISTANT = "assistant" # 助手
    SYSTEM = "system" # 系统

class Discuss(BaseModel):
    """讨论内容模型"""
    id: int = Field(
        0,
        description="ID"
    )
    uuid: str = Field(
        "",
        description="UUID"
    )
    related_type: RelatedType = Field(
        ...,
        description="关联类型"
    )
    thread_id: int = Field(
        None,
        description="话题ID"
    )
    thread_uuid: str = Field(
        ...,
        description="话题UUID"
    )
    reply_id: Optional[int] = Field(
        None,
        description="回复ID"
    )
    reply_uuid: Optional[str] = Field(
        None,
        description="回复UUID"
    )
    depth: int = Field(
        0,
        description="深度"
    )
    content: str = Field(
        "",
        description="内容"
    )
    tokens: dict = Field(
        ...,
        description="正在生成的tokens"
    )
    usage: dict = Field(
        ...,
        description="使用情况"
    )
    role: DiscussRole = Field(
        ...,
        description="角色"
    )
    user_id: Optional[int] = Field(
        None,
        description="用户ID"
    )
    is_hidden: int = Field(
        0,
        description="是否隐藏"
    )
    like: int = Field(
        0,
        description="点赞数"
    )
    trample: int = Field(
        0,
        description="踩数"
    )
    is_summary: int = Field(
        0,
        description="是否存在总结"
    )
    status: AIResponseStatus = Field(
        ...,
        description="状态"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )
    
    def create_uuid(self) -> str:
        self.uuid = str(uuid.uuid4())
        return self.uuid


class Classifier(BaseModel):
    """分类器模型"""
    id: int = Field(
        ...,
        description="ID编号"
    )
    name: str = Field(
        ...,
        description="分类器名称"
    )
    alias: str = Field(
        ...,
        description="分类器别名"
    )
    ver: str = Field(
        ...,
        description="分类器版本"
    )
    level: int = Field(
        ...,
        description="层级"
    )
    base_id: Optional[int] = Field(
        None,
        description="外键关联库，为空表示对总体数据"
    )
    parent_classifier_id: Optional[int] = Field(
        None,
        description="父节点ID"
    )
    type: ClassifierType = Field(
        ...,
        description="分类器类型"
    )
    classify_method: ClassifyMethod = Field(
        ...,
        description="分类方法"
    )
    classify_params: Optional[dict] = Field(
        None,
        description="分类方法参数"
    )
    prerequisite: Optional[list] = Field(
        None,
        description="内置方法，没有前置条件代表直接执行分类"
    )
    term_tree_id: Optional[int] = Field(
        None,
        description="外键关联term_tree，路由分类可能没有对应的term_tree"
    )
    term_tree_node_id: Optional[int] = Field(
        None,
        description="外键关联term_tree_node"
    )
    purpose: str = Field(
        ...,
        description="用途"
    )
    target: str = Field(
        ...,
        description="目标"
    )
    principle: str = Field(
        ...,
        description="原则"
    )
    criterion: str = Field(
        ...,
        description="标准"
    )
    is_need_full_text: int = Field(
        1,
        description="是否需要全文"
    )
    is_allow_other_value: int = Field(
        0,
        description="如果取值中没有适合的，是否可以设置为'其他'"
    )
    is_multi: bool = Field(
        0,
        description="是否支持多选"
    )
    multi_limit_min: int = Field(
        0,
        description="多选最少选项"
    )
    multi_limit_max: int = Field(
        0,
        description="多选最多选项"
    )
    is_include_sub_value: int = Field(
        0,
        description="包含子节点取值以利于prompt更好的生成"
    )
    status: ClassifierStatus = Field(
        ClassifierStatus.NORMAL,
        description="状态,1-正常, 0-无效"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

class ClassifierValue(BaseModel):

    """分类器取值模型"""
    id: int = Field(
        ...,
        description="ID编号"
    )
    classifier_id: int = Field(
        ...,
        description="外键关联classifier"
    )
    value: str = Field(
        ...,
        description="默认取值（可能为英文、中文）"
    )
    value_i18n: dict = Field(
        ...,
        description="国际化取值"
    )
    value_clue: str = Field(
        "",
        description="分类依据"
    )
    value_rule: str = Field(
        "",
        description="取值规则，取值依赖和互斥关系"
    )
    code: Optional[str] = Field(
        None,
        description="编码，没有编码的可以为NULL值"
    )
    alias: str = Field(
        ...,
        description="别名"
    )
    priority: int = Field(
        0,
        description="优先级，用于排序，大数靠前"
    )
    parent_id: Optional[int] = Field(
        None,
        description="外键关联classifier_value父节点"
    )
    term_tree_node_id: Optional[int] = Field(
        None,
        description="外键关联term_tree_node，可能为NULL值"
    )
    concept_id: Optional[int] = Field(
        None,
        description="外键关联concept，可能为NULL值"
    )
    term_id: Optional[int] = Field(
        None,
        description="外键关联term，可能为NULL值"
    )
    exclusive_with: str = Field(
        "",
        description="互斥的value ID列表，以英文逗号分割"
    )
    is_label: ClassifierValueIsLabel = Field(
        ClassifierValueIsLabel.YES,
        description="是否可用于标记"
    )
    status: ClassifierStatus = Field(
        ClassifierStatus.NORMAL,
        description="状态,1-正常，0-无效"
    )
    remark: str = Field(
        "",
        description="注释"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )


class LabelRawArticleTaskStatus(int, Enum):
    """标注任务状态枚举"""
    PENDING = 1  # 待运行
    RUNNING = 2  # 执行中
    COMPLETED = 10  # 已完成
    CANCELLED = 100  # 已取消
    UNEXPECTED_ERROR = 101  # 意外错误

class LabelRawArticleTask(BaseModel):
    """标注文章任务模型"""
    id: int = Field(
        0,
        description="ID编号"
    )
    raw_article_id: int = Field(
        ...,
        description="文章ID"
    )
    base_id: Optional[int] = Field(
        None,
        description="外键关联库，为空表示对总体数据"
    )
    desc: str = Field(
        ...,
        description="任务描述"
    )
    status: LabelRawArticleTaskStatus = Field(
        LabelRawArticleTaskStatus.PENDING,
        description="状态"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

class LabelRawArticleTaskItem(BaseModel):
    """标注文章任务项模型"""
    id: int = Field(
        0,
        description="ID编号"
    )
    label_raw_article_task_id: int = Field(
        ...,
        description="外键关联label_article_task"
    )
    term_tree_id: Optional[int] = Field(
        None,
        description="term树ID"
    )
    term_tree_node_id: Optional[int] = Field(
        None,
        description="term树节点ID"
    )
    label_item_key: str = Field(
        ...,
        description="标注项名称"
    )
    classifier_id: int = Field(
        ...,
        description="外键关联分类器ID"
    )
    classifier_ver: str = Field(
        ...,
        description="分类器版本"
    )
    status: LabelRawArticleTaskStatus = Field(
        LabelRawArticleTaskStatus.PENDING,
        description="状态"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

class LabelRawArticleTaskResult(BaseModel):
    """标注文章任务结果模型"""
    id: int = Field(
        0,
        description="ID编号"
    )
    label_item_key: str = Field(
        ...,
        description="标注项名称"
    )
    label_raw_article_task_id: int = Field(
        ...,
        description="文章标注任务ID"
    )
    label_raw_article_task_item_id: int = Field(
        ...,
        description="文章标注项ID"
    )
    classify_method: ClassifyMethod = Field(
        ClassifyMethod.GENERAL_CLASSIFICATION,
        description="是命名实体(2)或者是分类选项(1)"
    )
    location: int = Field(
        0,
        description="8-标题，4-摘要，1-正文（位运算）"
    )
    term_tree_id: Optional[int] = Field(
        None,
        description="term树ID"
    )
    term_tree_node_id: Optional[int] = Field(
        None,
        description="term树节点ID"
    )
    concept_id: Optional[int] = Field(
        None,
        description="词簇ID"
    )
    term_id: Optional[int] = Field(
        None,
        description="词条ID"
    )
    label_item_value: str = Field(
        ...,
        description="标注项取值"
    )
    metadata: Optional[dict] = Field(
        None,
        description="辅助信息"
    )
    status: LabelRawArticleTaskStatus = Field(
        LabelRawArticleTaskStatus.PENDING,
        description="状态, 1-待检查，10-已确认，100-已删除"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

class Base(BaseModel):
    """用户库模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    uuid: str = Field(
        ...,
        description="UUID"
    )
    name: str = Field(
        ...,
        description="名称"
    )
    intro: Optional[str] = Field(
        None,
        description="介绍"
    )
    created: Optional[datetime] = Field(
        None,
        description="创建时间"
    )
    modified: Optional[datetime] = Field(
        None,
        description="更新时间"
    )

class BaseCategory(BaseModel):
    """用户库分类模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    alias: str = Field(
        ...,
        description="别名"
    )
    base_id: int = Field(
        ...,
        description="基础ID"
    )
    type: int = Field(
        ...,
        description="类型"
    )
    name: str = Field(
        ...,
        description="名称"
    )
    base_name: Optional[str] = Field(
        None,
        description="用户库名称"
    )
    status: int = Field(
        ...,
        description="状态"
    )
    created: Optional[datetime] = Field(
        None,
        description="创建时间"
    )
    modified: Optional[datetime] = Field(
        None,
        description="更新时间"
    )


class AILogType(int, Enum):
    """AI日志类型枚举"""
    DISCUSS_AGENT = 1  # 讨论代理
    SUMMARY_AGENT= 2   # 长综述代理

class AILog(BaseModel):
    """AI日志模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    log_type: AILogType = Field(
        ...,
        description="日志类型"
    )
    uuid: str = Field(
        ...,
        description="UUID"
    )
    intention_duration: int = Field(
        0,
        description="意图分析时间"
    )
    intention: str = Field(
        "" ,
        description="意图"
    )
    search_query: str = Field(
        "",
        description="查询语句"
    )
    query_limit: str = Field(
        "",
        description="查询限制"
    )
    search_duration: int = Field(
        0,
        description="检索时间"
    )
    total_duration: int = Field(
        0,
        description="总时间"
    )
    resource_log: str = Field(
        "",
        description="资源日志"
    )
    article_count: int = Field(
        0,
        description="文献数量"
    )

    def is_valid(self) -> bool:
        return self.log_type and self.uuid != "" and self.intention != "" 

def initialize_ai_request_by_summary(request: SummaryRequest, metadata: dict = {}):
    """
    Initialize an AIContentRequest object from a SummaryRequest.
    
    Args:
        request (SummaryRequest): The source summary request
        
    Returns:
        AIContentRequest: A new AI content request object initialized with values from the summary request
    """
    ai_request = AIContentRequest(
        id=0,
        content_type=AIContentType.SHORT_SUMMARY,
        is_stream_response=StreamResponse.ALLOW if request.stream else StreamResponse.DENY,
        query=_create_query_by_summary_request(request, AIContentType.SHORT_SUMMARY, metadata),
        params=_create_params_by_summary_request(request, metadata),
        request_hash="",
        status=AIRequestStatus.START_REQ,
        created=datetime.now(),
        modified=datetime.now()
    )
    ai_request.hash()
    return ai_request

def initialize_ai_request_by_question(request: QuestionRequest, metadata: dict = {}):
    """
    Initialize an AIContentRequest object from a QuestionRequest.
    
    Args:
        request (QuestionRequest): The source question request
        
    Returns:
        AIContentRequest: A new AI content request object initialized with values from the question request
    """
    ai_request = AIContentRequest(
        id=0,
        content_type=AIContentType.ASSOCIATED_QUESTION,
        is_stream_response=StreamResponse.DENY,
        query=_create_query_by_question_request(request, metadata),
        params=_create_params_by_question_request(request, metadata),
        request_hash="",
        status=AIRequestStatus.START_REQ,
        created=datetime.now(),
        modified=datetime.now()
    )
    ai_request.hash()
    return ai_request

def initialize_ai_content_response(request: SummaryRequest, ai_content_request_id: int):
    """
    Initialize an AIContentResponse object from a SummaryRequest.
    
    Args:
        request (SummaryRequest): The source summary request
        
    Returns:
        AIContentResponse: A new AI content response object initialized with default values
    """
    ai_response = AIContentResponse(
        id=0,
        ai_request_id=ai_content_request_id,
        is_generating=0,
        content="",
        tokens={"generating": []},
        usage={},
        cache_hit_cnt=0,
        status=AIResponseStatus.GENERATING,
        created=datetime.now(),
        modified=datetime.now()
    )
    return ai_response

def _create_query_by_summary_request(request: SummaryRequest, content_type: AIContentType, metadata: dict = {}) -> str:
    """
    Create a query string based on the related type in the summary request.
    
    Args:
        request (SummaryRequest): The summary request containing the related type
        
    Returns:
        str: A query string appropriate for the related type
    """
    if request.related_type == RelatedType.CHANNEL or request.related_type == RelatedType.COLUMN:
        if request.purpose == Purpose.POPULAR:
            purpose_prompt= "请为这个栏目写一个科普介绍"
        elif request.purpose == Purpose.PPT:
            purpose_prompt= "请为这个栏目写一个PPT提纲"
        elif request.purpose == Purpose.FOOTAGE:
            purpose_prompt= "请为这个栏目写一个视频脚本"
        elif request.purpose == Purpose.OPPORTUNITY:
            purpose_prompt= "请结合这个栏目的内容，分析一下这个栏目可能存在的商机"
        else:
            purpose_prompt= "请分析这个栏目收录的这些文章的研究主题和科研成果，给首次来到这个栏目的读者一个阅读指引"
        if metadata.get('column_description'):
            return f"这是一个{metadata.get('column_description')}，{purpose_prompt}"
        else:
            return purpose_prompt
    elif request.related_type == RelatedType.ARTICLE:
        if request.purpose == Purpose.POPULAR:
            purpose_prompt= "请为这篇文章写一个科普介绍"
        elif request.purpose == Purpose.PPT:
            purpose_prompt= "请为这个栏目写一个PPT提纲"
        elif request.purpose == Purpose.FOOTAGE:
            purpose_prompt= "请为这个栏目写一个视频脚本"
        elif request.purpose == Purpose.OPPORTUNITY:
            purpose_prompt= "请结合这个栏目的内容，分析一下这个栏目可能存在的商机"
        else:
            purpose_prompt= "请分析这个栏目收录的这些文章的研究主题和科研成果，给首次来到这个栏目的读者一个阅读指引"

        if metadata.get('article_title'):
            query = f"这篇文章标题是：{metadata.get('article_title')}"
            if metadata.get('article_abstract'):
                query += f"\n摘要：{metadata.get('article_abstract')}\n"
            query += purpose_prompt
            return query
        else:
            return purpose_prompt
    
    return ""

def _create_params_by_summary_request(request: SummaryRequest, metadata: dict = {}) -> dict:
    """
    Create a parameters dictionary based on the summary request.
    
    Args:
        request (SummaryRequest): The summary request containing related type and ID
        
    Returns:
        dict: A dictionary containing the appropriate parameters based on the related type
    """
    if request.related_type == RelatedType.CHANNEL:
        params = {
            "channel_id": request.related_id
        }
    elif request.related_type == RelatedType.COLUMN:
        params = {
            "column_id": request.related_id
        }
        if metadata.get('base_id'):
            params["channel_id"] = metadata.get('base_id')
    elif request.related_type == RelatedType.ARTICLE:
        params = {
            "article_id": request.related_id
        }
    params["ver"] = request.ver
    params["purpose"] = request.purpose.value
    params["term_tree_node_ids"] = request.term_tree_node_ids
    return params

def _create_query_by_question_request(request: QuestionRequest, metadata: dict = {}) -> str:
    """
    Create a query string based on the related type in the question request.
    
    Args:
        request (QuestionRequest): The question request containing the related type
        
    Returns:
        str: A query string appropriate for the related type
    """
    query = ""
    if request.related_type == RelatedType.CHANNEL or request.related_type == RelatedType.COLUMN:
        if metadata.get('column_description'):
            query = f"这是一个{metadata.get('column_description')}，请根据栏目包含的文献内容提出用户可能会关心的科研问题，并尽可能避免重复用户问过的问题"
        else:
            query = "请根据栏目包含的文献内容提出用户可能会关心的科研问题，并尽可能避免重复用户问过的问题"
    elif request.related_type == RelatedType.ARTICLE:
        if metadata.get('article_title'):
            query = f"这篇文章标题是：{metadata.get('article_title')}"
            if metadata.get('article_abstract'):
                query += f"\n摘要：{metadata.get('article_abstract')}\n"
            query += "\n请根据文章的摘要提出用户可能会关心的科研问题，并尽可能避免重复用户问过的问题"
        else:
            query = "请根据文章的摘要提出用户可能会关心的科研问题，并尽可能避免重复用户问过的问题"

    return query

def _create_params_by_question_request(request: QuestionRequest, metadata: dict = {}) -> dict:
    """
    Create a parameters dictionary based on the question request.
    
    Args:
        request (QuestionRequest): The question request containing related type and ID
        
    Returns:
        dict: A dictionary containing the appropriate parameters based on the related type
    """
    if request.related_type == RelatedType.CHANNEL:
        params = {
            "channel_id": request.related_id
        }
    elif request.related_type == RelatedType.COLUMN:
        params = {
            "column_id": request.related_id
        }
        if metadata.get('base_id'):
            params["channel_id"] = metadata.get('base_id')
    elif request.related_type == RelatedType.ARTICLE:
        params = {
            "article_id": request.related_id
        }
    params["ver"] = request.ver
    params["term_tree_node_ids"] = request.term_tree_node_ids
    params["question_count"] = request.count
    params['user_history'] = metadata.get('user_history')
    return params

def initialize_discuss_thread(request: DiscussCreateRequest) -> DiscussThread:
    """
    Initialize a DiscussThread object from a DiscussCreateRequest.
    
    Args:
        request (DiscussCreateRequest): The source discuss create request
        
    Returns:
        DiscussThread: A new discuss thread object initialized with values from the discuss create request
    """
    params = {}
    if request.related_type == RelatedType.CHANNEL:
        params["channel_id"] = request.related_id
    elif request.related_type == RelatedType.COLUMN:
        params["column_id"] = request.related_id
    elif request.related_type == RelatedType.ARTICLE:
        params["article_id"] = request.related_id

    if request.term_tree_node_ids:
        params["term_tree_node_ids"] = request.term_tree_node_ids
    if request.ver is not None:
        params["ver"] = request.ver
    if request.article_count > 0:
        params["article_count"] = request.article_count
    if request.title:
        params["title"] = request.title
    if request.sub_title:
        params["sub_title"] = request.sub_title

    discuss_thread = DiscussThread(
        id=0,
        uuid="",
        related_type=request.related_type,
        title=request.title,
        params=params,
        request_hash="",
        user_hash=request.user_hash,
        user_id=request.user_id,
        created=datetime.now(),
        modified=datetime.now()
    )
    discuss_thread.hash()
    discuss_thread.create_uuid()
    return discuss_thread

def initialize_discuss(request: DiscussPostRequest, thread: DiscussThread, reply_id: int = 0) -> Discuss:
    """
    从DiscussPostRequest初始化Discuss对象
    
    Args:
        request (DiscussPostRequest): 讨论内容请求
        
    Returns:
        DiscussContent: 新的讨论内容对象
    """
    discuss = Discuss(
        id=0,
        thread_id=thread.id,
        thread_uuid=thread.uuid,
        reply_id=reply_id,
        reply_uuid=request.reply_uuid,
        content=request.content,
        user_hash=request.user_hash,
        user_id=request.user_id,
        created=datetime.now(),
        modified=datetime.now()
    )
    discuss.create_uuid()
    return discuss

