#!/usr/bin/env python3
"""
敏感词检测代理使用示例

该示例展示如何使用SensitiveWordDetectionAgent进行敏感词检测。
需要配置阿里云的访问密钥才能正常运行。

作者: Deep Academic Research Team
创建时间: 2024
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.agent.sensitive_word_detection_agent import (
    SensitiveWordDetectionAgent,
    DetectionService,
    RiskLevel
)


def demo_basic_detection():
    """基础检测功能演示"""
    print("=" * 50)
    print("基础敏感词检测演示")
    print("=" * 50)
    
    try:
        # 初始化敏感词检测代理
        # 使用配置文件中的设置，无需手动指定参数
        agent = SensitiveWordDetectionAgent()
        
        # 测试文本列表
        test_texts = [
            "这是一段正常的学术讨论内容",
            "我们来讨论一下人工智能的发展前景",
            "请注意遵守相关法律法规",
            "",  # 空内容测试
            "   ",  # 空白内容测试
            "李强对这段怎么分析？",
            "天安门游行什么时候开始"
        ]
        
        for i, text in enumerate(test_texts, 1):
            print(f"\n测试 {i}: {repr(text)}")
            
            # 方法1：使用详细检测接口
            result = agent.detect_sensitive_words(text)
            print(f"  有风险: {result.has_risk}")
            print(f"  风险等级: {result.risk_level}")
            print(f"  风险原因: {result.risk_reason}")
            if result.labels:
                print(f"  风险标签: {result.labels}")
            if result.risk_words:
                print(f"  风险词汇: {result.risk_words}")
            print(f"  置信度: {result.confidence}")
            
            # 方法2：使用简化接口
            is_safe, reason = agent.is_content_safe(text)
            print(f"  简化结果 - 安全: {is_safe}, 原因: {reason}")
            
    except ValueError as e:
        print(f"配置错误: {e}")
        print("\n请检查配置文件 config.rbase.yaml 中的 sensitive_word_detection 设置:")
        print("- access_key_id: 阿里云访问密钥ID")
        print("- access_key_secret: 阿里云访问密钥Secret")
        print("- enabled: true  # 启用敏感词检测")
    except Exception as e:
        print(f"检测失败: {e}")


def demo_different_services():
    """不同检测服务演示"""
    print("\n" + "=" * 50)
    print("不同检测服务类型演示")
    print("=" * 50)
    
    try:
        # 测试文本
        test_text = "用户昵称测试内容"
        
        # 测试不同的检测服务
        services = [
            DetectionService.NICKNAME_DETECTION_PRO,
            DetectionService.CHAT_DETECTION_PRO,
            DetectionService.COMMENT_DETECTION_PRO,
            DetectionService.UGC_MODERATION_BYLLM,
        ]
        
        for service in services:
            print(f"\n使用服务: {service.value}")
            
            # 使用配置文件中的设置，仅覆盖服务类型
            agent = SensitiveWordDetectionAgent(service_type=service)
            
            result = agent.detect_sensitive_words(test_text)
            print(f"  检测结果: 风险={result.has_risk}, 等级={result.risk_level}")
            print(f"  风险原因: {result.risk_reason}")
            
    except Exception as e:
        print(f"服务测试失败: {e}")


def demo_batch_detection():
    """批量检测演示"""
    print("\n" + "=" * 50)
    print("批量敏感词检测演示")
    print("=" * 50)
    
    try:
        # 使用配置文件中的设置
        agent = SensitiveWordDetectionAgent()
        
        # 批量测试文本
        batch_texts = [
            "第一段测试内容：学术讨论",
            "第二段测试内容：技术交流",
            "第三段测试内容：正常对话",
            "第四段测试内容：研究分析",
            "第五段测试内容：数据统计"
        ]
        
        print(f"批量检测 {len(batch_texts)} 段文本...")
        
        # 执行批量检测
        results = agent.batch_detect(batch_texts)
        
        # 显示结果
        for i, (text, result) in enumerate(zip(batch_texts, results), 1):
            print(f"\n文本 {i}: {text}")
            print(f"  结果: 风险={result.has_risk}, 等级={result.risk_level}")
            print(f"  原因: {result.risk_reason}")
            
        # 统计结果
        total_count = len(results)
        risk_count = sum(1 for r in results if r.has_risk)
        safe_count = total_count - risk_count
        
        print(f"\n批量检测统计:")
        print(f"  总数: {total_count}")
        print(f"  有风险: {risk_count}")
        print(f"  安全: {safe_count}")
        
    except Exception as e:
        print(f"批量检测失败: {e}")


def demo_service_switching():
    """服务切换演示"""
    print("\n" + "=" * 50)
    print("服务类型切换演示")
    print("=" * 50)
    
    try:
        # 使用配置文件中的设置初始化代理
        agent = SensitiveWordDetectionAgent()
        
        test_text = "测试内容：服务切换演示"
        
        # 测试初始服务
        print(f"当前服务: {agent.service_type.value}")
        result1 = agent.detect_sensitive_words(test_text)
        print(f"检测结果: {result1.risk_reason}")
        
        # 切换到昵称检测服务
        agent.change_service_type(DetectionService.NICKNAME_DETECTION_PRO)
        print(f"\n切换后服务: {agent.service_type.value}")
        result2 = agent.detect_sensitive_words(test_text)
        print(f"检测结果: {result2.risk_reason}")
        
        # 显示支持的地域
        print(f"\n支持的地域: {agent.get_supported_regions()}")
        
    except Exception as e:
        print(f"服务切换演示失败: {e}")


def demo_error_handling():
    """错误处理演示"""
    print("\n" + "=" * 50)
    print("错误处理演示")
    print("=" * 50)
    
    # 测试无效配置
    try:
        # 测试覆盖配置文件中的设置
        agent = SensitiveWordDetectionAgent(
            access_key_id="invalid_key",
            access_key_secret="invalid_secret",
            use_config=False  # 不使用配置文件
        )
        
        result = agent.detect_sensitive_words("测试内容")
        print(f"意外成功: {result.risk_reason}")
        
    except Exception as e:
        print(f"预期的配置错误: {e}")
    
    # 测试网络超时配置
    try:
        # 使用配置文件设置，但覆盖超时时间
        agent = SensitiveWordDetectionAgent(timeout=1)  # 很短的超时时间
        
        print("测试超时配置（可能会超时）...")
        # 这里可能会因为超时而失败，这是正常的
        
    except Exception as e:
        print(f"网络配置测试: {e}")


def main():
    """主函数"""
    print("敏感词检测代理演示程序")
    print("使用配置文件 config.rbase.yaml 中的敏感词检测设置")
    
    # 检查配置文件设置
    try:
        from deepsearcher.configuration import init_rbase_config
        from deepsearcher import configuration
        # 初始化配置
        init_rbase_config()
        config_settings = configuration.config.rbase_settings.get("sensitive_word_detection", {})
        
        if not config_settings.get('enabled', False):
            print("\n警告: 敏感词检测功能未启用")
            print("请在配置文件中设置 enabled: true")
        
        if not config_settings.get('access_key_id') and not os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID'):
            print("\n警告: 未配置阿里云访问密钥")
            print("请在配置文件中设置或使用环境变量")
            
        print(f"\n当前配置:")
        print(f"  启用状态: {config_settings.get('enabled', False)}")
        print(f"  地域: {config_settings.get('region', 'cn-shanghai')}")
        print(f"  服务类型: {config_settings.get('service_type', 'chat_detection_pro')}")
        print(f"  超时时间: {config_settings.get('timeout', 30)}秒")
        
    except Exception as e:
        print(f"\n警告: 无法读取配置文件: {e}")
        print("请确保配置文件 config.rbase.yaml 存在且格式正确")
    
    # 运行演示
    demo_basic_detection()
    # demo_different_services()
    # demo_batch_detection()
    # demo_service_switching()
    # demo_error_handling()
    
    print("\n" + "=" * 50)
    print("演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
