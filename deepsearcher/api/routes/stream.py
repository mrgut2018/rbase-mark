"""
Stream Response Handler

This module contains functions for handling streaming responses.
"""

import asyncio
import json
import random
import time
from typing import AsyncGenerator
from deepsearcher.agent.summary_rag import SummaryRag, ProgressHint

async def generate_text_stream(text: str, response_id: int) -> AsyncGenerator[bytes, None]:
    """
    Generate a streaming response for text content.

    Args:
        text (str): The text content to be streamed
        response_id (int): The unique identifier for this response

    Yields:
        bytes: Chunks of the streaming response data
    """
    # Send role message
    summary_rag = SummaryRag(None, None)
    yield summary_rag.build_role_json_str(response_id)
    yield summary_rag.build_progress_json_str(ProgressHint["SEARCH_DOCUMENT"], response_id)
    
    # 将文本均匀划分为60段
    text_length = len(text)
    total_chunks = text_length // 5
    chunk_size = max(1, text_length // total_chunks)
    chunks = []
    
    for i in range(total_chunks - 1):
        start_idx = i * chunk_size
        end_idx = (i + 1) * chunk_size
        if start_idx < text_length:
            chunks.append(text[start_idx:end_idx])
    
    # 添加最后一段，包含所有剩余文本
    if (total_chunks - 1) * chunk_size < text_length:
        chunks.append(text[(total_chunks - 1) * chunk_size:])
    
    # 移除空块
    chunks = [chunk for chunk in chunks if chunk]
    
    # 发送每一段内容
    for i, chunk in enumerate(chunks):
        await asyncio.sleep(random.uniform(0.1, 0.2))  # random delay
        content_chunk = {
            "id": f"chatcmpl-{response_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "rbase-summary-agent",
            "choices": [{
                "index": i,
                "delta": {"content": chunk, "progress": ProgressHint["GENERATE_ANSWER"]},
                "finish_reason": None if i < len(chunks) - 1 else "stop"
            }]
        }
        yield f"data: {json.dumps(content_chunk)}\n\n".encode('utf-8')
    
    # Send end marker
    yield "data: [DONE]\n\n".encode('utf-8') 