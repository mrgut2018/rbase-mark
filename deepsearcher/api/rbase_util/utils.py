"""
Utility Functions

This module contains utility functions for database operations.
"""

import json
import hashlib
from pydantic import BaseModel

from deepsearcher.rbase.raw_article import RawArticle
from deepsearcher.tools import load_rbase_txt_file
from deepsearcher.tools.log import debug

def get_request_hash(request: BaseModel) -> str:
    """
    Calculate request hash value
    
    Args:
        request: Request object
        
    Returns:
        str: Request hash value
    """
    # Convert request object to dictionary
    request_dict = request.model_dump()
    
    # Remove fields that should not participate in hash calculation
    if 'user_hash' in request_dict:
        del request_dict['user_hash']
    if 'user_id' in request_dict:
        del request_dict['user_id']
        
    # Convert dictionary to JSON string
    request_json = json.dumps(request_dict, sort_keys=True)
    
    # Calculate hash value
    return hashlib.md5(request_json.encode()).hexdigest()


def load_article_full_text(raw_article: RawArticle, oss_config: dict, file_loader, is_need_full_text: int = 0) -> str:
    """
    加载文章全文的公共方法

    Args:
        raw_article: 文章对象
        oss_config: OSS配置
        file_loader: 文件加载器
        is_need_full_text: 是否需要全文 (1=需要, 0=不需要)

    Returns:
        str: 文章全文，如果不需要或无法加载则返回空字符串
    """
    if is_need_full_text != 1:
        return ""

    if not raw_article.txt_file:
        return ""

    docs = load_rbase_txt_file(
        oss_config, raw_article.txt_file, file_loader,
        include_references=False,
        save_downloaded_file=True
    )
    full_text = "\n\n".join([doc.page_content for doc in docs])
    debug(f"Full text length: {len(full_text.split())} words")
    return "文章全文如下：\n" + full_text