"""
火山引擎 LLM 客户端
基于 OpenAI 兼容 API
"""
import json
import logging
from typing import Dict, Any, Optional, List
from openai import OpenAI, AsyncOpenAI

# 修改导入方式
try:
    from ..config import settings
    from ..cache.manager import cache_manager
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    from config import settings
    from cache.manager import cache_manager

logger = logging.getLogger(__name__)


class LLMClient:
    """火山引擎 LLM 客户端"""

    def __init__(self):
        """初始化客户端"""
        if settings.LLM_PROVIDER == "deepseek":
            if not settings.DEEPSEEK_API_KEY:
                raise ValueError("LLM_PROVIDER=deepseek 但未配置 DEEPSEEK_API_KEY")
            api_key = settings.DEEPSEEK_API_KEY
            base_url = settings.DEEPSEEK_API_BASE
            model = settings.DEEPSEEK_LLM_MODEL
        else:
            if not settings.VOLC_API_KEY:
                raise ValueError("VOLC_API_KEY 未配置")
            api_key = settings.VOLC_API_KEY
            base_url = settings.VOLC_API_BASE
            model = settings.VOLC_LLM_MODEL

        self.provider = settings.LLM_PROVIDER
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = model
        # 深度思考模型会先消耗思维链 token，调用方给的 max_tokens 过小时结果会被截断为空
        self._min_max_tokens = 1000 if self.provider == "deepseek" else 0

    def _effective_max_tokens(self, max_tokens: int) -> int:
        return max(max_tokens, self._min_max_tokens)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_cache: bool = False,  # ⚠️ 临时禁用缓存用于稳定性测试
        **kwargs
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            use_cache: 是否使用缓存
            **kwargs: 其他参数
        
        Returns:
            模型响应文本
        """
        # 尝试从缓存获取
        if use_cache:
            cache_key = json.dumps({
                "messages": messages,
                "temperature": temperature,
                "model": self.model
            }, sort_keys=True)
            cached = cache_manager.get_llm_result(cache_key)
            if cached is not None:
                return cached
        
        # 调用 API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=self._effective_max_tokens(max_tokens),
            **self._apply_reasoning_effort(kwargs)
        )
        
        result = response.choices[0].message.content
        
        # 缓存结果
        if use_cache:
            cache_manager.cache_llm_result(cache_key, result)
        
        return result

    def _apply_reasoning_effort(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """deepseek 思考型模型：默认 thinking effort=low（缩短思考链，
        防复杂任务思考吃光 max_tokens 导致 content 空；也更快更省）。
        调用方可传 reasoning_effort 覆盖；非 deepseek provider 不传。
        """
        if self.provider != "deepseek":
            return kwargs
        if "reasoning_effort" not in kwargs:
            kwargs["reasoning_effort"] = "low"
        return kwargs

    async def achat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_cache: bool = False,
        **kwargs
    ) -> str:
        """异步发送聊天请求"""
        if use_cache:
            cache_key = json.dumps({
                "messages": messages,
                "temperature": temperature,
                "model": self.model
            }, sort_keys=True)
            cached = cache_manager.get_llm_result(cache_key)
            if cached is not None:
                return cached

        response = await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=self._effective_max_tokens(max_tokens),
            **self._apply_reasoning_effort(kwargs)
        )

        result = response.choices[0].message.content

        if use_cache:
            cache_manager.cache_llm_result(cache_key, result)

        return result

    def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        发送带系统提示的聊天请求
        
        Args:
            system_prompt: 系统提示
            user_message: 用户消息
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数
        
        Returns:
            模型响应文本
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        return self.chat(messages, temperature, max_tokens, **kwargs)

    async def achat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """异步发送带系统提示的聊天请求"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        return await self.achat(messages, temperature, max_tokens, **kwargs)

    def extract_json(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Optional[Dict[str, Any]]:
        """
        从响应中提取 JSON
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            max_tokens: 最大 token 数
        
        Returns:
            解析后的 JSON 字典，失败返回 None
        """
        # 添加 JSON 格式要求
        full_prompt = f"{prompt}\n\n请以 JSON 格式返回结果，不要包含其他说明文字。"
        
        response = self.chat_with_system(
            "你是一个专业的信息提取助手，擅长从文本中提取结构化信息并以 JSON 格式返回。",
            full_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # 尝试解析 JSON
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 代码块
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
            
            # 尝试提取花括号内的内容
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
        
        return None

    async def aextract_json(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Optional[Dict[str, Any]]:
        """异步从响应中提取 JSON"""
        full_prompt = f"{prompt}\n\n请以 JSON 格式返回结果，不要包含其他说明文字。"

        response = await self.achat_with_system(
            "你是一个专业的信息提取助手，擅长从文本中提取结构化信息并以 JSON 格式返回。",
            full_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        return None

    def call_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_cache: bool = False  # ⚠️ 临时禁用缓存用于稳定性测试
    ) -> Dict[str, Any]:
        """
        使用 Function Calling 调用 LLM
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            tool_choice: 工具选择策略（"auto", "none", 或指定工具名）
            temperature: 温度参数
            max_tokens: 最大 token 数
            use_cache: 是否使用缓存
        
        Returns:
            {
                "tool_calls": [...],  # 工具调用列表
                "content": str        # 文本响应（如果没有工具调用）
            }
        """
        logger.info(f"[Function Calling] 开始调用，工具数量: {len(tools)}, tool_choice: {tool_choice}")
        
        # 尝试从缓存获取
        if use_cache:
            cache_key = json.dumps({
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "temperature": temperature,
                "model": self.model
            }, sort_keys=True)
            cached = cache_manager.get_llm_result(cache_key)
            if cached is not None:
                logger.info("[Function Calling] 使用缓存结果")
                return cached
        
        try:
            # 调用 API（带 tools 参数）
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=self._effective_max_tokens(max_tokens)
            )
            
            message = response.choices[0].message
            
            # 检查是否有工具调用
            if message.tool_calls:
                tool_calls = []
                for tool_call in message.tool_calls:
                    tool_calls.append({
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": json.loads(tool_call.function.arguments)
                    })
                
                result = {"tool_calls": tool_calls, "content": None}
                logger.info(f"[Function Calling] 工具调用成功，数量: {len(tool_calls)}")
                
                # 缓存结果
                if use_cache:
                    cache_manager.cache_llm_result(cache_key, result)
                
                return result
            else:
                # 没有工具调用，返回文本响应
                result = {"tool_calls": None, "content": message.content}
                logger.info(f"[Function Calling] 返回文本响应，长度: {len(message.content)}")
                
                # 缓存结果
                if use_cache:
                    cache_manager.cache_llm_result(cache_key, result)
                
                return result
                
        except Exception as e:
            logger.error(f"[Function Calling] 调用失败: {e}", exc_info=True)
            raise


# 全局 LLM 客户端实例
llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端实例"""
    global llm_client
    if llm_client is None:
        llm_client = LLMClient()
    return llm_client
