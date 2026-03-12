from deepsearcher.llm.base import BaseLLM

class JsonAgent:

    def __init__(self, 
                 llm: BaseLLM, 
                 **kwargs) -> None:
        self.llm = llm
    
    def recognize_json(self, json_str: str) -> dict:
        prompt = f"""
        You are a JSON recognizer. You will be given a JSON string and you need to recognize the JSON string.
        The JSON string might be broken for some reason, please fix it and try your best to recover the JSON string.
        The given JSON string is:
        {json_str}

        ====================================================
        Please output fixed JSON result directly, don't include any other text.
        """
        response = self.llm.chat([{'role': 'user', 'content': prompt}])
        return response.content.strip()