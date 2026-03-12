"""
Sensitive Word Detection Agent Module

This module provides sensitive word detection functionality based on Alibaba Cloud Text Moderation Plus service.
Supports multiple detection scenarios including user nickname detection, chat content detection, comment detection, etc.

Author: Deep Academic Research Team
Created: 2024
"""

import json
import time
import os
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from alibabacloud_green20220302.client import Client
from alibabacloud_green20220302 import models
from alibabacloud_tea_openapi.models import Config

from deepsearcher.tools import log
from deepsearcher import configuration


class RiskLevel(Enum):
    """Risk level enumeration"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"


class DetectionService(Enum):
    """Detection service type enumeration"""
    NICKNAME_DETECTION_PRO = "nickname_detection_pro"  # User nickname detection - professional version
    CHAT_DETECTION_PRO = "chat_detection_pro"  # Chat content detection - professional version
    COMMENT_DETECTION_PRO = "comment_detection_pro"  # Comment detection - professional version
    UGC_MODERATION_BYLLM = "ugc_moderation_byllm"  # UGC content moderation - based on large model
    AD_COMPLIANCE_DETECTION_PRO = "ad_compliance_detection_pro"  # Ad compliance detection - professional version


@dataclass
class DetectionResult:
    """Detection result data class"""
    has_risk: bool  # Whether there is risk
    risk_level: str  # Risk level: low/medium/high
    risk_reason: str  # Risk reason description
    labels: list  # Risk label list
    confidence: float  # Confidence score
    risk_words: str  # Risk words
    raw_response: dict  # Raw API response


class SensitiveWordDetectionAgent:
    """
    Sensitive Word Detection Agent Class
    
    Based on Alibaba Cloud Text Moderation Plus service, provides sensitive word detection functionality.
    Supports multiple detection scenarios and custom configurations.
    """

    def __init__(self, 
                 access_key_id: Optional[str] = None,
                 access_key_secret: Optional[str] = None,
                 region: Optional[str] = None,
                 service_type: Optional[DetectionService] = None,
                 timeout: Optional[int] = None,
                 use_config: bool = True):
        """
        Initialize sensitive word detection agent
        
        Args:
            access_key_id: Alibaba Cloud access key ID, if None, get from config file or environment variable
            access_key_secret: Alibaba Cloud access key secret, if None, get from config file or environment variable  
            region: Alibaba Cloud region, if None, get from config file, default cn-shanghai
            service_type: Detection service type, if None, get from config file, default chat content detection professional version
            timeout: Request timeout, if None, get from config file, default 30 seconds
            use_config: Whether to use settings in config file, default True
        """
        # Get configuration
        config_settings = {}
        if use_config:
            try:
                config_settings = configuration.config.rbase_settings.get("sensitive_word_detection", {})
            except Exception as e:
                log.warning(f"无法读取配置文件中的敏感词检测设置: {e}")
        
        # Get access keys (priority: parameter > config file > environment variable)
        self.access_key_id = (
            access_key_id or 
            config_settings.get('access_key_id') or 
            os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID')
        )
        self.access_key_secret = (
            access_key_secret or 
            config_settings.get('access_key_secret') or 
            os.getenv('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
        )
        
        if not self.access_key_id or not self.access_key_secret:
            raise ValueError("阿里云访问密钥未配置。请在配置文件中设置或设置环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID 和 ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        
        # Get other configuration parameters (priority: parameter > config file > default value)
        self.region = region or config_settings.get('region', 'cn-shanghai')
        
        # Handle service_type configuration
        if service_type is None:
            service_type_str = config_settings.get('service_type', 'chat_detection_pro')
            # Convert string to enum
            service_type_map = {
                'nickname_detection_pro': DetectionService.NICKNAME_DETECTION_PRO,
                'chat_detection_pro': DetectionService.CHAT_DETECTION_PRO,
                'comment_detection_pro': DetectionService.COMMENT_DETECTION_PRO,
                'ugc_moderation_byllm': DetectionService.UGC_MODERATION_BYLLM,
                'ad_compliance_detection_pro': DetectionService.AD_COMPLIANCE_DETECTION_PRO
            }
            self.service_type = service_type_map.get(service_type_str, DetectionService.CHAT_DETECTION_PRO)
        else:
            self.service_type = service_type
            
        self.timeout = timeout or config_settings.get('timeout', 30)
        
        # Get batch detection configuration
        self.batch_size = config_settings.get('batch_size', 10)
        self.retry_count = config_settings.get('retry_count', 3)
        self.retry_delay = config_settings.get('retry_delay', 1)
        
        # Check if sensitive word detection is enabled
        self.enabled = config_settings.get('enabled', True)
        
        # Initialize Alibaba Cloud SDK client
        self._init_client()
        
        log.debug(f"敏感词检测代理初始化完成，使用服务: {self.service_type.value}, 地域: {self.region}, 启用状态: {self.enabled}")

    def _init_client(self):
        """Initialize Alibaba Cloud SDK client"""
        try:
            # Build SDK configuration
            config = Config(
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret,
                connect_timeout=self.timeout * 1000,  # SDK uses milliseconds
                read_timeout=self.timeout * 1000,
                region_id=self.region,
                endpoint=f'green-cip.{self.region}.aliyuncs.com'
            )
            
            # Create client
            self.client = Client(config)
            log.debug(f"阿里云SDK客户端初始化成功，端点: {config.endpoint}")
            
        except Exception as e:
            log.error(f"阿里云SDK客户端初始化失败: {e}")
            raise ValueError(f"阿里云SDK客户端初始化失败: {e}")



    def _parse_response(self, response) -> DetectionResult:
        """
        Parse SDK response
        
        Args:
            response: SDK response object
            
        Returns:
            Detection result object
        """
        try:
            # Get response body
            if hasattr(response, 'body') and response.body:
                response_data = response.body.to_map()
            else:
                raise Exception("响应体为空")
            
            # Check response code
            if response.status_code != 200:
                error_msg = response_data.get("Message", f"HTTP {response.status_code}")
                log.error(f"API调用失败: {error_msg}")
                raise Exception(f"敏感词检测API调用失败: {error_msg}")
            
            # Parse response data
            code = response_data.get("Code", 0)
            if code != 200:
                error_msg = response_data.get("Message", "未知错误")
                log.error(f"API返回错误: {error_msg}")
                raise Exception(f"敏感词检测API返回错误: {error_msg}")
            
            data = response_data.get("Data", {})
            results = data.get("Result", [])
            risk_level = data.get("RiskLevel", "low")
            
            # Determine if there is risk
            has_risk = risk_level in ["medium", "high"] 
            
            # Build risk reason description
            risk_descriptions = []
            all_labels = []
            max_confidence = 0.0
            all_risk_words = []
            
            for result in results:
                label = result.get("Label", "")
                description = result.get("Description", "")
                confidence = result.get("Confidence", 0.0)
                risk_words = result.get("RiskWords", "")
                if label == "nonLabel":
                    continue
                
                all_labels.append(label)
                max_confidence = max(max_confidence, confidence)
                
                if risk_words:
                    all_risk_words.append(risk_words)
                
                if description:
                    risk_descriptions.append(f"{description}(置信度: {confidence}%)")
            
            # Generate risk reason text
            if has_risk:
                risk_reason = f"检测到{len(results)}项风险: " + "; ".join(risk_descriptions)
                if all_risk_words:
                    risk_reason += f" | 风险词汇: {', '.join(all_risk_words)}"
            else:
                risk_reason = "内容安全，未检测到敏感词"
            
            return DetectionResult(
                has_risk=has_risk,
                risk_level=risk_level,
                risk_reason=risk_reason,
                labels=all_labels,
                confidence=max_confidence,
                risk_words=", ".join(all_risk_words),
                raw_response=response_data
            )
            
        except Exception as e:
            log.error(f"解析响应失败: {e}")
            raise Exception(f"解析响应失败: {e}")

    def detect_sensitive_words(self, content: str) -> DetectionResult:
        """
        Detect sensitive words in text
        
        Args:
            content: Text content to be detected
            
        Returns:
            Detection result object
            
        Raises:
            Exception: When API call fails or network error occurs
        """
        # Check if sensitive word detection is enabled
        if not self.enabled:
            log.info("敏感词检测功能未启用，返回无风险结果")
            return DetectionResult(
                has_risk=False,
                risk_level="low",
                risk_reason="敏感词检测功能未启用",
                labels=[],
                confidence=0.0,
                risk_words="",
                raw_response={}
            )
        
        if not content or not content.strip():
            log.warning("输入内容为空，返回无风险结果")
            return DetectionResult(
                has_risk=False,
                risk_level="low",
                risk_reason="输入内容为空",
                labels=[],
                confidence=0.0,
                risk_words="",
                raw_response={}
            )
        
        # SDK API call with retry
        last_exception = None
        for attempt in range(self.retry_count + 1):
            try:
                if attempt > 0:
                    log.debug(f"敏感词检测重试第 {attempt} 次")
                    time.sleep(self.retry_delay)
                
                log.debug(f"开始检测敏感词，内容长度: {len(content)}")
                
                # Build service parameters
                service_parameters = {"content": content}
                
                # Create request object
                request = models.TextModerationPlusRequest(
                    service=self.service_type.value,
                    service_parameters=json.dumps(service_parameters, ensure_ascii=False)
                )
                
                log.debug(f"服务类型: {self.service_type.value}")
                log.debug(f"服务参数: {service_parameters}")
                
                # Call SDK API
                response = self.client.text_moderation_plus(request)
                
                log.debug(f"响应状态码: {response.status_code}")
                
                # Parse response
                result = self._parse_response(response)
                
                log.debug(f"敏感词检测完成 - 有风险: {result.has_risk}, 风险等级: {result.risk_level}")
                if result.has_risk:
                    log.warning(f"检测到敏感内容: {result.risk_reason}")
                
                return result
                
            except Exception as e:
                last_exception = Exception(f"敏感词检测失败: {str(e)}")
                log.error(f"第 {attempt + 1} 次尝试失败: {last_exception}")
                
                # If it's a client configuration issue, no need to retry
                if "客户端初始化" in str(e) or "访问密钥" in str(e):
                    raise last_exception
        
        # All retries failed, throw the last exception
        if last_exception:
            raise last_exception
        else:
            raise Exception("敏感词检测失败，未知错误")

    def is_content_safe(self, content: str) -> Tuple[bool, str]:
        """
        Simplified interface: check if content is safe
        
        Args:
            content: Text content to be detected
            
        Returns:
            Tuple[is_safe, risk_reason]
        """
        try:
            result = self.detect_sensitive_words(content)
            return not result.has_risk, result.risk_reason
        except Exception as e:
            log.error(f"内容安全检查失败: {str(e)}")
            # For safety, return unsafe when error occurs
            return False, f"检测服务异常: {str(e)}"

    def batch_detect(self, contents: list) -> list:
        """
        Batch detect sensitive words (process by configured batch size)
        
        Args:
            contents: List of text content to be detected
            
        Returns:
            List of detection results
        """
        if not self.enabled:
            log.info("敏感词检测功能未启用，返回所有内容为安全")
            return [DetectionResult(
                has_risk=False,
                risk_level="low", 
                risk_reason="敏感词检测功能未启用",
                labels=[],
                confidence=0.0,
                risk_words="",
                raw_response={}
            ) for _ in contents]
        
        results = []
        total_count = len(contents)
        
        # Process by batch size
        for batch_start in range(0, total_count, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_count)
            batch_contents = contents[batch_start:batch_end]
            
            log.debug(f"处理批次 {batch_start//self.batch_size + 1}, 内容数量: {len(batch_contents)}")
            
            # Process current batch
            for i, content in enumerate(batch_contents):
                global_index = batch_start + i + 1
                try:
                    log.debug(f"批量检测进度: {global_index}/{total_count}")
                    result = self.detect_sensitive_words(content)
                    results.append(result)
                except Exception as e:
                    log.error(f"批量检测第{global_index}项失败: {str(e)}")
                    # Add error result
                    error_result = DetectionResult(
                        has_risk=True,  # Mark as risky when error occurs
                        risk_level="high",
                        risk_reason=f"检测失败: {str(e)}",
                        labels=["error"],
                        confidence=0.0,
                        risk_words="",
                        raw_response={}
                    )
                    results.append(error_result)
            
            # Pause between batches (avoid rate limiting)
            if batch_end < total_count:
                time.sleep(0.1)  # 100ms pause
        
        # Statistics
        risk_count = sum(1 for r in results if r.has_risk)
        safe_count = total_count - risk_count
        log.debug(f"批量检测完成: 总数={total_count}, 有风险={risk_count}, 安全={safe_count}")
        
        return results

    def change_service_type(self, service_type: DetectionService):
        """
        Change detection service type
        
        Args:
            service_type: New detection service type
        """
        self.service_type = service_type
        log.debug(f"检测服务类型已更改为: {service_type.value}")

    def get_supported_regions(self) -> list:
        """
        Get supported regions list
        
        Returns:
            List of supported regions
        """
        return [
            "cn-shanghai",    # East China 2 (Shanghai)
            "cn-beijing",     # North China 2 (Beijing)
            "cn-hangzhou",    # East China 1 (Hangzhou)
            "cn-shenzhen",    # South China 1 (Shenzhen)
            "cn-chengdu",     # Southwest China 1 (Chengdu)
            "ap-southeast-1", # Singapore
            "eu-west-1",      # UK (London)
            "us-east-1",      # US (Virginia)
            "us-west-1",      # US (Silicon Valley)
            "eu-central-1"    # Germany (Frankfurt)
        ]
