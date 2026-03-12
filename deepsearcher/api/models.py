"""
API数据模型定义

本模块定义了FastAPI接口的请求和响应数据结构。
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class ExceptionResponse(BaseModel):
    """异常响应模型"""
    code: int = Field(
        ...,
        description="响应码：0-成功，非0-失败"
    )
    message: str = Field(..., description="响应消息")

class RelatedType(int, Enum):
    """关联类型枚举"""
    CHANNEL = 1  # 频道
    COLUMN = 2   # 栏目
    ARTICLE = 3   # 文章

    @staticmethod
    def IsValid(related_type: int) -> bool:
        return related_type in [RelatedType.CHANNEL, RelatedType.COLUMN, RelatedType.ARTICLE]


class DepressCache(int, Enum):
    """缓存抑制枚举"""
    ENABLE = 1  # 禁用缓存
    DISABLE = 0 # 启用缓存

class Purpose(str, Enum):
    """目的枚举"""
    SUMMARY = "summary"  # 总结
    POPULAR = "popular"  # 科普
    PPT = "ppt"  # PPT提纲
    FOOTAGE = "footage"  # 视频脚本
    OPPORTUNITY = "opportunity"  # 商机


class SummaryRequest(BaseModel):
    """AI概述接口请求模型"""
    related_type: RelatedType = Field(
        ...,
        description="关联类型：1-频道，2-栏目，3-文章"
    )
    related_id: Optional[int] = Field(
        None,
        description="关联ID，可选"
    )
    purpose: Optional[Purpose] = Field(
        Purpose.SUMMARY,
        description="目的：summary-总结，popular-科普，ppt-PPT提纲，footage-视频脚本，opportunity-商机"
    )
    term_tree_node_ids: Optional[List[int]] = Field(
        None,
        description="关键词ID列表，可选"
    )
    ver: int = Field(
        ...,
        description="版本号"
    )
    depress_cache: DepressCache = Field(
        ...,
        description="缓存抑制：0-启用缓存，1-禁用缓存"
    )
    stream: bool = Field(
        ...,
        description="是否使用流式响应"
    )
    discuss_thread_uuid: Optional[str] = Field(
        None,
        description="讨论话题UUID"
    )
    discuss_reply_uuid: Optional[str] = Field(
        None,
        description="讨论回复UUID"
    )


class SummaryResponse(BaseModel):
    """AI概述接口响应模型"""
    code: int = Field(
        ...,
        description="响应码：0-成功，非0-失败"
    )
    message: str = Field(
        ...,
        description="响应消息"
    )
    id: Optional[str] = Field(
        None,
        description="ID"
    )
    content: Optional[str] = Field(
        None,
        description="内容"
    )
    created: Optional[int] = Field(
        None,   
        description="创建时间"
    )
    model: Optional[str] = Field(
        None,
        description="模型"
    )
    object: Optional[str] = Field(
        None,
        description="对象"
    )
    choices: Optional[List[dict]] = Field(
        None,
        description="回答选项"
    )

    def setContent(self, content: str):
        self.content = content
        self.created = int(datetime.now().timestamp())
        self.id = f"chatcmpl-{self.created}"
        self.model = "rbase-rag"
        self.object = "chat.completion"
        self.choices = [
            {
                "index": 0,
                "message": {
                    "content": content,
                    "role": "assistant",
                },
                "finish_reason": "stop"
            }
        ]

class QuestionRequest(BaseModel):
    """AI推荐问题接口请求模型"""
    related_type: RelatedType = Field(
        ...,
        description="关联类型：1-频道，2-栏目，3-文章"
    )
    related_id: Optional[int] = Field(
        None,
        description="关联ID，可选"
    )
    term_tree_node_ids: Optional[List[int]] = Field(
        None,
        description="关键词ID列表，可选"
    )
    ver: int = Field(
        ...,
        description="版本号"
    )
    depress_cache: DepressCache = Field(
        ...,
        description="缓存抑制：0-启用缓存，1-禁用缓存"
    )
    count: int = Field(
        ...,
        description="问题数量"
    )
    thread_uuid: Optional[str] = Field(
        None,
        description="讨论话题UUID"
    )


class QuestionResponse(BaseModel):
    """AI推荐问题接口响应模型"""
    code: int = Field(
        ...,
        description="响应码：0-成功，非0-失败"
    )
    message: str = Field(
        ...,
        description="响应消息"
    ) 
    questions: Optional[List[str]] = Field(
        None,
        description="问题列表"
    )

    def setQuestions(self, content: str):
        # 将content按换行符分割，得到问题列表
        questions = [q for q in content.strip().split('\n') if q]
        self.questions = questions

class DiscussCreateRequest(BaseModel):
    """创建讨论话题请求模型"""
    related_type: RelatedType = Field(
        ...,
        description="关联类型：1-频道，2-栏目，3-文章"
    )
    related_id: Optional[int] = Field(
        None,
        description="关联ID，可选"
    )
    term_tree_node_ids: Optional[List[int]] = Field(
        None,
        description="关键词ID列表，可选"
    )
    ver: int = Field(
        ...,
        description="版本号"
    )
    user_hash: str = Field(
        ...,
        description="用户hash"
    )
    user_id: int = Field(
        ...,
        description="用户ID"
    )
    title: Optional[str] = Field(
        "",
        description="话题标题"
    )
    article_count: Optional[int] = Field(
        0,
        description="文章数量"
    )
    is_manually: Optional[int] = Field(
        0,
        description="是否手动创建：0-否，1-是"
    )
    sub_title: Optional[str] = Field(
        "",
        description="子标题"
    )

class DiscussCreateResponse(BaseModel):
    """创建讨论话题响应模型"""
    code: int = Field(
        ...,
        description="响应码：0-成功，非0-失败"
    )
    message: str = Field(
        ...,
        description="响应消息"
    )
    thread_uuid: str = Field(
        ...,
        description="话题UUID"
    )
    thread_title: str = Field(
        ...,
        description="话题标题"
    )
    has_summary: bool = Field(
        ...,
        description="是否存在总结"
    )
    depth: int = Field(
        ...,
        description="深度"
    )
    is_title_modified: int = Field(
        0,
        description="是否修改过标题"
    )

class DiscussPostRequest(BaseModel):
    """发布讨论内容请求模型"""
    thread_uuid: str = Field(
        ...,
        description="话题UUID"
    )
    reply_uuid: str = Field(
        ...,
        description="回复UUID"
    )
    content: str = Field(
        ...,
        description="对话内容"
    )
    user_hash: str = Field(
        ...,
        description="用户hash"
    )
    user_id: int = Field(
        ...,
        description="用户ID"
    )


class DiscussPostResponse(BaseModel):
    """发布讨论内容响应模型"""
    code: int = Field(
        ...,
        description="响应码：0-成功，非0-失败"
    )
    message: str = Field(
        ...,
        description="响应消息"
    )
    uuid: str = Field(
        ...,
        description="讨论UUID"
    )
    depth: int = Field(
        ...,
        description="深度"
    )

class DiscussAIReplyRequest(BaseModel):
    """
    API Request for generating AI reply to discuss
    """
    thread_uuid: str = Field(..., description="UUID of the thread")
    reply_uuid: str = Field(..., description="UUID of the discuss to reply to")
    user_hash: str = Field(..., description="User hash")
    user_id: int = Field(..., description="User ID")
    further_question_count: int = Field(3, description="Further question count, default is 3")

class CloseAIReplyResponse(BaseModel):
    """关闭AI讨论回复响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    discuss_uuid: str = Field(..., description="讨论UUID")

class SortType(int, Enum):
    """排序类型枚举"""
    ASC = 1  # 升序
    DESC = -1  # 降序


class DiscussListRequest(BaseModel):
    """列出讨论话题请求模型"""
    thread_uuid: str = Field(
        ...,
        description="话题UUID"
    )
    user_hash: Optional[str] = Field(
        "", 
        description="用户hash"
    )
    user_id: Optional[int] = Field(
        0,
        description="用户ID"
    )
    limit: int = Field(
        ...,
        description="限制数量"
    )
    from_depth: int = Field(
        ...,
        description="从深度开始"
    )
    sort: Optional[SortType] = Field(
        SortType.ASC, 
        description="排序类型"
    )

class DiscussListEntity(BaseModel):
    """讨论话题实体"""
    uuid: str = Field(..., description="话题UUID")
    depth: int = Field(..., description="深度")
    content: str = Field(..., description="内容")
    created: int = Field(..., description="创建时间时间戳")
    role: str = Field(..., description="用户角色")
    is_summary: int = Field(..., description="是否存在总结")
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(..., description="用户ID")
    user_name: str = Field(..., description="用户名")
    user_avatar: str = Field(..., description="用户头像")
    status: int = Field(..., description="状态")

class DiscussListResponse(BaseModel):
    """列出讨论话题响应模型"""
    code: int = Field(
        ...,
        description="响应码：0-成功，非0-失败"
    )
    message: str = Field(
        ...,
        description="响应消息"
    )
    count: int = Field(
        ...,
        description="数量"
    )
    discuss_entities: Optional[List[DiscussListEntity]] = Field(
        None,
        description="讨论列表"
    )

class RefreshThreadTitleRequest(BaseModel):
    """刷新话题标题请求模型"""
    thread_uuid: str = Field(..., description="话题UUID")
    discuss_uuid: str = Field(..., description="讨论UUID")
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(..., description="用户ID")

class RefreshThreadTitleResponse(BaseModel):
    """刷新话题标题响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    title: str = Field(..., description="话题标题")

class UpdateThreadTitleRequest(BaseModel):
    """更新话题标题请求模型"""
    thread_uuid: str = Field(..., description="话题UUID")
    title: str = Field(..., description="话题标题")
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(..., description="用户ID")

class FavoriteThreadRequest(BaseModel):
    """收藏话题请求模型"""
    discuss_thread_uuid_list: List[str] = Field(..., description="讨论话题UUID列表")
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(..., description="用户ID")
    is_cancel: int = Field(..., description="是否取消收藏")

class FavoriteThreadResponse(BaseModel):
    """收藏话题响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    discuss_thread_uuid_list: List[str] = Field(..., description="讨论话题UUID列表")
    count: int = Field(..., description="收藏数量")

class HistoryDiscussThreadsRequest(BaseModel):
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(0, description="用户ID")
    limit: int = Field(..., description="限制数量")
    offset: int = Field(..., description="偏移量")
    is_favorite: int = Field(..., description="是否收藏")

class HistoryDiscussTheadEntity(BaseModel):
    """历史讨论话题实体"""
    uuid: str = Field(..., description="话题UUID")
    depth: int = Field(..., description="深度")
    title: str = Field(..., description="话题标题")
    created: int = Field(..., description="创建时间时间戳")
    modified: int = Field(..., description="创建时间时间戳")
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(..., description="用户ID")
    is_favorite: int = Field(..., description="是否收藏")
    is_title_modified: int = Field(..., description="是否修改过标题")
    article_count: int = Field(0, description="文章数量")
    sub_title: str = Field("", description="子标题")
    params: dict = Field({}, description="参数")

class HistoryDiscussThreadsResponse(BaseModel):
    """历史讨论话题响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    discuss_threads: List[HistoryDiscussTheadEntity] = Field(..., description="讨论话题列表")
    limit: int = Field(..., description="限制数量")
    offset: int = Field(..., description="偏移量")
    total: int = Field(..., description="总数")
    count: int = Field(..., description="数量")

class HideThreadRequest(BaseModel):
    """隐藏话题请求模型"""
    discuss_thread_uuid_list: List[str] = Field(..., description="讨论话题UUID列表")
    user_hash: str = Field(..., description="用户hash")
    user_id: int = Field(..., description="用户ID")

class HideThreadResponse(BaseModel):
    """隐藏话题响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    discuss_thread_uuid_list: List[str] = Field(..., description="讨论话题UUID列表")
    count: int = Field(..., description="隐藏数量")

class VectorDbOperation(int, Enum):
    """向量数据库操作枚举"""
    UNKNOWN = 0  # 未知
    INSERT = 1  # 插入
    UPDATE = 2  # 更新
    DELETE = 3  # 删除
    ABSTRACT = 4  # 摘要

class VectorDbOperationStr(str, Enum):
    """向量数据库操作字符串枚举"""
    INSERT = "insert"  # 插入
    UPDATE = "update"  # 更新
    DELETE = "delete"  # 删除
    ABSTRACT = "abstract"  # 摘要
    UNKNOWN = "unknown"  # 未知

def vector_db_operation_to_int(operation: str) -> int:
    """将向量数据库操作字符串转换为整数"""
    if operation == VectorDbOperationStr.INSERT:
        return VectorDbOperation.INSERT.value
    elif operation == VectorDbOperationStr.UPDATE:
        return VectorDbOperation.UPDATE.value
    elif operation == VectorDbOperationStr.DELETE:
        return VectorDbOperation.DELETE.value
    elif operation == VectorDbOperationStr.ABSTRACT:
        return VectorDbOperation.ABSTRACT.value
    else:
        return VectorDbOperation.UNKNOWN.value

class RefreshArticleVectorDbRequest(BaseModel):
    """刷新文章向量数据库请求模型"""
    article_id: int = Field(..., description="文章ID")
    raw_article_id: int = Field(..., description="原始文章ID")

# 后台管理接口参数
class BackendArticleTitlesRequest(BaseModel):
    """后台管理接口参数"""
    article_id: int = Field(..., description="文章ID")
    count: int = Field(..., description="标题数量")
    extend_requirement: str = Field("", description="扩展要求")

class BackendArticleTitlesResponse(BaseModel):
    """后台管理接口响应参数"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    titles: List[str] = Field(..., description="标题列表")

class AiTranslateLang(str, Enum):
    """AI翻译语言枚举"""
    ZH = "zh"  # 中文
    EN = "en"  # 英文

class EmbeddingRequest(BaseModel):
    """文本转向量请求模型"""
    text: str = Field(..., description="待转换的文本")

class EmbeddingData(BaseModel):
    """向量数据"""
    embedding: List[float] = Field(..., description="向量")
    dimension: int = Field(..., description="向量维度")

class EmbeddingResponse(BaseModel):
    """文本转向量响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    data: Optional[EmbeddingData] = Field(None, description="向量数据")

class BatchEmbeddingItem(BaseModel):
    """批量文本转向量请求项"""
    id: str = Field(..., description="文本唯一标识")
    text: str = Field(..., description="待转换的文本")

class BatchEmbeddingRequest(BaseModel):
    """批量文本转向量请求模型"""
    items: List[BatchEmbeddingItem] = Field(..., description="待转换的文本列表")

class BatchEmbeddingResultItem(BaseModel):
    """批量文本转向量结果项"""
    id: str = Field(..., description="文本唯一标识")
    embedding: List[float] = Field(..., description="向量")

class BatchEmbeddingResponse(BaseModel):
    """批量文本转向量响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    data: Optional[List[BatchEmbeddingResultItem]] = Field(None, description="向量结果列表")
    dimension: int = Field(0, description="向量维度")
    count: int = Field(0, description="向量数量")

class AiTranslateRequest(BaseModel):
    """AI翻译请求模型"""
    sentence: str = Field(..., description="句子")
    target_lang: AiTranslateLang = Field(..., description="目标语言")

class AiTranslateResponse(BaseModel):
    """AI翻译响应模型"""
    code: int = Field(..., description="响应码：0-成功，非0-失败")
    message: str = Field(..., description="响应消息")
    translated: str = Field(..., description="翻译结果")
    target_lang: AiTranslateLang = Field(..., description="目标语言")