"""
火山引擎 LLM 客户端
基于 OpenAI 兼容 API
"""
import json
from typing import Dict, Any, Optional, List
from openai import OpenAI
from ..config import settings


class LLMClient:
    """火山引擎 LLM 客户端"""
    
    def __init__(self):
        """初始化客户端"""
        if not settings.VOLC_API_KEY:
            raise ValueError("VOLC_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=settings.VOLC_API_KEY,
            base_url=settings.VOLC_API_BASE
        )
        self.model = settings.VOLC_LLM_MODEL
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数
        
        Returns:
            模型响应文本
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return response.choices[0].message.content
    
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


# 全局 LLM 客户端实例
llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端实例"""
    global llm_client
    if llm_client is None:
        llm_client = LLMClient()
    return llm_client
