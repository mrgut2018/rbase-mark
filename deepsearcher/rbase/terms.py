from datetime import datetime
import uuid
from pydantic import BaseModel, Field
from typing import Optional

class TermTreeNode(BaseModel):
    """术语树节点模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    tree_id: int = Field(
        ...,
        description="树ID"
    )
    parent_node_id: int = Field(
        ...,
        description="父节点ID"
    )
    node_concept_name: str = Field(
        ...,
        description="节点概念名称"
    )
    node_concept_id: int = Field(
        ...,
        description="节点概念ID"
    )
    intro: Optional[str] = Field(
        None,
        description="介绍"
    )
    sequence: Optional[int] = Field(
        0,
        description="顺序"
    )
    children_count: Optional[int] = Field(
        0,
        description="子节点数量"
    )
    status: int = Field(
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

class Term(BaseModel):
    """术语模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    uuid: str = Field(
        ...,
        description="UUID"
    )
    name: Optional[str] = Field(
        "",
        description="名称"
    )
    intro: Optional[str] = Field(
        None,
        description="介绍"
    )
    concept_id: int = Field(
        0,
        description="所属概念ID"
    )
    is_concept_term: int = Field(
        0,
        description="是否为概念核心词"
    )
    is_abbr: int = Field(
        0,
        description="是否为缩写形式"
    )
    is_virtual: int = Field(
        0,
        description="是否为虚拟术语"
    )
    status: int = Field(
        10,
        description="状态"
    )
    related_article_count: int = Field(
        0,
        description="关联文章数量"
    )
    remark: Optional[str] = Field(
        None,
        description="备注"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

class Concept(BaseModel):
    """词簇模型"""
    id: int = Field(
        ...,
        description="ID"
    )
    name: str = Field(
        "",
        description="名称"
    )
    cname: Optional[str] = Field(
        None,
        description="中文名称"
    )
    abbr_name: Optional[str] = Field(
        None,
        description="英文缩写"
    )
    abbr_cname: Optional[str] = Field(
        None,
        description="中文缩写"
    )
    intro: Optional[str] = Field(
        None,
        description="介绍"
    )
    concept_term_id: Optional[int] = Field(
        None,
        description="英文术语Term ID"
    )
    concept_term_id2: Optional[int] = Field(
        None,
        description="中文术语Term ID"
    )
    concept_term_id3: Optional[int] = Field(
        None,
        description="缩写术语Term ID"
    )
    is_virtual: int = Field(
        0,
        description="是否虚拟术语"
    )
    is_preferred_concept: int = Field(
        0,
        description="是否首选概念"
    )
    preferred_concept_id: int = Field(
        0,
        description="首选概念ID"
    )
    concept_relation: int = Field(
        1,
        description="概念关系"
    )
    status: int = Field(
        10,
        description="状态"
    )
    related_article_count: int = Field(
        0,
        description="关联文章数量"
    )
    widely_related_article_count: int = Field(
        0,
        description="更大范围的关联文章数量"
    )
    created: datetime = Field(
        ...,
        description="创建时间"
    )
    modified: datetime = Field(
        ...,
        description="更新时间"
    )

    def is_complete(self) -> bool:
        """
        判断词簇是否完整
        """
        return self.name and self.cname and self.concept_term_id and self.concept_term_id2 
