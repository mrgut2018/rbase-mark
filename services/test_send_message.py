#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本 - 向MNS队列发送测试消息

用于测试分类服务的消息接收和处理功能。

作者: AI Assistant
创建时间: 2025年11月14日
"""

import os
import sys
import json
import argparse
from contextlib import redirect_stdout
from io import StringIO

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mns.account import Account
from deepsearcher.configuration import Configuration


def send_test_message(config_path: str, message_data: dict):
    """
    向MNS队列发送测试消息
    
    Args:
        config_path: 配置文件路径
        message_data: 消息数据字典
    """
    # 加载配置
    config = Configuration(config_path)
    mns_config = config.rbase_settings.get('mns', {})
    
    # 验证配置
    endpoint = mns_config.get('endpoint')
    access_id = mns_config.get('access_id')
    access_key = mns_config.get('access_key')
    queue_name = mns_config.get('queue_name')
    verify_ssl = mns_config.get('verify_ssl', False)
    
    if not all([endpoint, access_id, access_key, queue_name]):
        print("错误: MNS配置不完整")
        return False
    
    try:
        # 如果不验证SSL，需要禁用SSL警告并设置环境变量
        if not verify_ssl:
            import ssl
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            # 设置不验证SSL
            ssl._create_default_https_context = ssl._create_unverified_context
            print("提示: SSL验证已禁用（不推荐用于生产环境）")
        
        # 连接MNS（设置debug=False以减少输出）
        print(f"连接MNS: {queue_name}")
        account = Account(endpoint, access_id, access_key, debug=False)
        queue = account.get_queue(queue_name)
        
        # 发送消息
        message_body = json.dumps(message_data, ensure_ascii=False)
        print(f"发送消息: {message_body}")
        
        msg = queue.send_message(message_body)
        print(f"消息发送成功!")
        print(f"  Message ID: {msg.message_id}")
        print(f"  Message Body MD5: {msg.message_body_md5}")
        
        return True
        
    except Exception as e:
        print(f"发送消息失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='向MNS队列发送测试消息')
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.rbase.yaml',
        help='配置文件路径（默认: config.rbase.yaml）'
    )
    parser.add_argument(
        '-t', '--auto-task-id',
        type=int,
        required=True,
        help='auto_task_id'
    )
    parser.add_argument(
        '-s', '--auto-sub-task-id',
        type=int,
        required=True,
        help='auto_sub_task_id'
    )
    parser.add_argument(
        '-a', '--raw-article-id',
        type=int,
        required=True,
        help='raw_article_id'
    )
    parser.add_argument(
        '-b', '--base-id',
        type=int,
        required=True,
        help='base_id'
    )
    parser.add_argument(
        '-C', '--classifier-id',
        type=int,
        help='classifier_id（与classifier_group_id二选一）'
    )
    parser.add_argument(
        '-G', '--classifier-group-id',
        type=int,
        help='classifier_group_id（与classifier_id二选一）'
    )
    
    args = parser.parse_args()
    
    # classifier_id 和 classifier_group_id 必须至少提供其中之一
    if not args.classifier_id and not args.classifier_group_id:
        print("错误: 必须提供 --classifier-id 或 --classifier-group-id 参数之一")
        return 1
    
    # 如果同时提供，给出提示（不报错，因为服务端会优先使用classifier_group_id）
    if args.classifier_id and args.classifier_group_id:
        print(f"提示: 同时提供了classifier_id({args.classifier_id})和classifier_group_id({args.classifier_group_id})")
        print(f"      服务端将优先使用classifier_group_id，忽略classifier_id")
    
    # 获取配置文件绝对路径
    if not os.path.isabs(args.config):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            args.config
        )
    else:
        config_path = args.config
    
    if not os.path.exists(config_path):
        print(f"错误: 配置文件不存在: {config_path}")
        return 1
    
    # 构造消息数据
    message_data = {
        'auto_task_id': args.auto_task_id,
        'auto_sub_task_id': args.auto_sub_task_id,
        'raw_article_id': args.raw_article_id,
        'base_id': args.base_id,
    }
    
    if args.classifier_id:
        message_data['classifier_id'] = args.classifier_id
    elif args.classifier_group_id:
        message_data['classifier_group_id'] = args.classifier_group_id
    
    # 发送消息
    success = send_test_message(config_path, message_data)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

