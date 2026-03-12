import json
from typing import Any
from deepsearcher import configuration
from deepsearcher.agent.json_agent import JsonAgent


def json_strip(json_str: str):
    content = json_str.strip()
    # remove markdown code block
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def safe_json_loads(json_str: str, use_llm_agent: bool = True) -> Any:
    """
    容错的JSON解析函数，尝试多种方式解析JSON字符串
    
    Args:
        json_str: JSON字符串
        
    Returns:
        解析后的对象
        
    Raises:
        ValueError: 所有解析方式都失败时抛出
    """
    # 尝试1: 直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # 尝试2: 处理转义的引号（\"变为"）
    try:
        unescaped = json_str.replace('\\"', '"')
        return json.loads(unescaped)
    except json.JSONDecodeError:
        pass
    
    # 尝试3: 使用ast.literal_eval（处理单引号等情况）
    try:
        import ast
        return ast.literal_eval(json_str)
    except (ValueError, SyntaxError):
        pass
    
    # 尝试4: 移除外层可能多余的引号
    try:
        stripped = json_str.strip()
        if (stripped.startswith('"') and stripped.endswith('"')) or \
           (stripped.startswith("'") and stripped.endswith("'")):
            stripped = stripped[1:-1]
            return safe_json_loads(stripped)  # 递归调用
    except:
        pass
    
    if use_llm_agent:
        json_agent = JsonAgent(configuration.llm)
        json_str = json_agent.recognize_json(json_str)
        return safe_json_loads(json_strip(json_str), use_llm_agent=False)
    # 所有方法都失败
    raise ValueError(f"无法解析JSON字符串，原始字符串: {json_str[:200]}...")
            
def json_to_dict(json_str: str) -> dict:
    try:
        content = json_strip(json_str)
        rt = json.loads(content)
        if isinstance(rt, dict):
            return rt
        else:
            raise ValueError("JSON is not a dict")
    except json.JSONDecodeError as e:
        raise e

def json_to_list(json_str: str) -> list:
    try:
        content = json_strip(json_str)
        rt = json.loads(content)
        if isinstance(rt, list):
            return rt
        else:
            raise ValueError("JSON is not a list")
    except json.JSONDecodeError as e:
        raise e