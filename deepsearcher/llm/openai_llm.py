import os
import time
import json
from datetime import datetime
from typing import Dict, List, Any, Generator

from deepsearcher.llm.base import BaseLLM, ChatResponse
from deepsearcher.tools import log

class OpenAI(BaseLLM):
    def __init__(self, model: str = "o1-mini", **kwargs):
        from openai import OpenAI as OpenAI_

        # model name has to be provided
        self.model = model
        # different service host has different parameters
        self.host = kwargs.pop("host", "default")
        # check if stream mode is enabled
        self.stream_mode = kwargs.pop("stream", False)
        # check if verbose mode is enabled
        self.verbose = kwargs.pop("verbose", False)
        # set max_tokens, if not specified, use default value (None means use model default value)
        self.max_tokens = kwargs.pop("max_tokens", None)
        # check if enable thinking mode
        self.enable_thinking = kwargs.pop("enable_thinking", False)
        # load price
        self.input_token_price = kwargs.pop("input_token_price", 0)
        self.output_token_price = kwargs.pop("output_token_price", 0)
        # CoT log path for reasoning content logging
        self.cot_log_path = kwargs.pop("cot_log_path", "logs/cot")
        # depress verbose print (for testing)
        self.depress_verbose_print = kwargs.pop("depress_verbose_print", False)

        if "api_key" in kwargs:
            api_key = kwargs.pop("api_key")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
        if "base_url" in kwargs:
            base_url = kwargs.pop("base_url")
        else:
            base_url = os.getenv("OPENAI_BASE_URL")
        
        self.client = OpenAI_(api_key=api_key, base_url=base_url, **kwargs)

    def add_api_params(self, api_params: Dict, key: str, value: Any) -> Dict:
        if value is None:
            return api_params

        if key == "max_tokens" or key == "timeout":
            api_params[key] = int(value)
        elif key == "enable_thinking":
            if self.host == "deepseek":
                if (bool(value)):
                    api_params["extra_body"] = {"thinking": {"type": "enabled"}}
                else:
                    api_params["extra_body"] = {"thinking": {"type": "disabled"}}
            else:
                api_params["extra_body"] = {"enable_thinking": bool(value)}
        elif key == "stream":
            api_params["stream"] = bool(value)
        elif key == "stream_options":
            api_params["stream_options"] = value
        else:
            api_params[key] = value
        return api_params

    def chat(self, messages: List[Dict], **kwargs) -> ChatResponse:
        if self.stream_mode:
            # stream mode
            return self._stream_chat(messages, **kwargs)
        else:
            # normal mode
            # build API call parameters
            api_params = {
                "model": self.model,
                "messages": messages,
            }
            api_params = self.add_api_params(api_params, "max_tokens", self.max_tokens)
            api_params = self.add_api_params(api_params, "enable_thinking", self.enable_thinking)
            api_params = self.add_api_params(api_params, "timeout", kwargs.get('timeout'))
            
            completion = self.client.chat.completions.create(**api_params)
            return ChatResponse(
                content=completion.choices[0].message.content,
                total_tokens=completion.usage.total_tokens,
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
            )

    def stream_generator(self, messages: List[Dict], **kwargs) -> Generator[object, None, None]:
        """
        Use stream mode to call API, return the original chunk object

        Args:
            messages: message list

        Returns:
            stream response object
        """
        # build stream request parameters
        api_params = {
            "model": self.model,
            "messages": messages,
        }
        api_params = self.add_api_params(api_params, "stream", True)
        api_params = self.add_api_params(api_params, "stream_options", {"include_usage": True})
        api_params = self.add_api_params(api_params, "max_tokens", self.max_tokens)
        api_params = self.add_api_params(api_params, "enable_thinking", self.enable_thinking)
        api_params = self.add_api_params(api_params, "timeout", kwargs.get('timeout', None))

        # create stream request
        return self.client.chat.completions.create(**api_params)


    def _stream_chat(self, messages: List[Dict], **kwargs) -> ChatResponse:
        """
        Use stream mode to call API

        Args:
            messages: message list

        Returns:
            stream response object
        """
        collected_content = ""  # collect complete response
        reasoning_content = ""  # collect reasoning content
        total_tokens = 0  # total tokens
        prompt_tokens = 0  # prompt tokens
        completion_tokens = 0  # completion tokens
        is_answering = False  # mark if already switched from reasoning to answering
        is_reasoning = False  # mark if reasoning is enabled
        finish_reason = None  # finish reason
        start_time = time.time()
        timeout = kwargs.get('timeout', None)
        cot_log_filename = kwargs.get('cot_log_filename', None) # check if CoT logging is enabled

        # use stream_generator to handle stream response
        for chunk in self.stream_generator(messages, **kwargs):
            if len(chunk.choices) > 0:
                if chunk.choices[0].finish_reason is not None:
                    finish_reason = chunk.choices[0].finish_reason
                delta = chunk.choices[0].delta
                # handle reasoning content 
                if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                    reasoning_content += delta.reasoning_content
                    self._print_verbose_content(delta.reasoning_content, is_start_reasoning=not is_reasoning)
                    is_reasoning = True
                # handle answering content
                elif hasattr(delta, "content") and delta.content is not None:
                    collected_content += delta.content
                    self._print_verbose_content(delta.content, is_start_answering=not is_answering)
                    is_answering = True

            # if there is token information, add to total tokens
            if hasattr(chunk, "usage") and chunk.usage:
                total_tokens += chunk.usage.total_tokens
                prompt_tokens += chunk.usage.prompt_tokens
                completion_tokens += chunk.usage.completion_tokens

            if timeout is not None and timeout > 0:
                if time.time() - start_time > timeout:
                    finish_reason = "timeout"
                    log.error(f"LLM invoke timeout for {time.time() - start_time} seconds")
                    break

        final_content = collected_content  # final content

        self._print_verbose_content("", is_finished=True)
        # Write CoT log if enabled
        if cot_log_filename:
            self._write_cot_log(cot_log_filename, reasoning_content, final_content, messages)

        return ChatResponse(
            content=final_content,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
        )

    def _write_cot_log(self, cot_log_filename: str, reasoning_content: str, answer_content: str, messages: List[Dict]):
        """
        Write chain-of-thought (reasoning and answering) content to log file

        Args:
            cot_log_filename: base filename for the log file
            reasoning_content: reasoning content to log
            answer_content: answering content to log
            messages: input messages to log
        """
        if not self.verbose:
            return
        # Generate timestamp in format: 20260119141315
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Construct log filename: {cot_log_filename}.{timestamp}.log
        log_filename = f"{cot_log_filename}.{timestamp}.log"

        # Construct full log path
        log_dir = self.cot_log_path
        os.makedirs(log_dir, exist_ok=True)
        log_filepath = os.path.join(log_dir, log_filename)

        # Prepare log content with formatted separators
        log_content = []
        log_content.append("==== reasoning content =====")
        log_content.append(reasoning_content if reasoning_content else "(empty)")
        log_content.append("==== reasoning content end ====")
        log_content.append("")
        log_content.append("")
        log_content.append("==== answering content ====")
        log_content.append(answer_content if answer_content else "(empty)")
        log_content.append("==== answering content end ====")
        log_content.append("")
        log_content.append("")
        log_content.append("==== input messages ====")
        try:
            # Format messages as pretty JSON
            messages_str = json.dumps(messages, ensure_ascii=False, indent=2)
            log_content.append(messages_str)
        except Exception as e:
            log_content.append(f"(failed to serialize messages: {e})")
        log_content.append("==== input messages end ====")

        # Write to file
        try:
            with open(log_filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_content))
            log.debug(f"CoT log written to: {log_filepath}")
        except Exception as e:
            log.error(f"Failed to write CoT log to {log_filepath}: {e}")

    def _print_verbose_content(self, content, is_start_reasoning: bool = False, is_start_answering: bool = False, is_finished: bool = False):
        if self.verbose and not self.depress_verbose_print:
            if is_start_reasoning:
                print("\n")
                log.debug("--- Start reasoning ---")

            if is_start_answering:
                print("\n")
                log.debug("--- Start answering ---")

            if is_finished:
                print(f"{content}\n")
            else:
                print(content, end="")
