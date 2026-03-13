#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
生产环境 API 服务器启动脚本

支持多进程部署，用于解决接口阻塞问题。
"""

import os
import sys
import argparse
import multiprocessing
import platform
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import uvicorn
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config


def get_optimal_worker_count():
    """
    获取最优的工作进程数量
    
    针对socket.send()异常优化：降低worker数量，减少资源竞争
    """
    cpu_count = multiprocessing.cpu_count()
    # 对于I/O密集型应用，过多workers会导致socket异常
    # 优化策略：限制worker数量，避免资源竞争
    return min(max(cpu_count - 1, 2), 6)  # 最少2个，最多6个进程


def main():
    """
    主函数：启动多进程 API 服务器
    """
    parser = argparse.ArgumentParser(description="Rbase API 服务器启动脚本")
    parser.add_argument("--host", default=None, help="服务器主机地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="服务器端口 (默认: 8000)")
    parser.add_argument("--workers", "-w", type=int, default=None, 
                       help=f"工作进程数量 (默认: 自动计算，当前建议: {get_optimal_worker_count()})")
    # uvloop 仅支持 Linux/macOS，Windows 使用 asyncio
    default_loop = "asyncio" if platform.system() == "Windows" else "uvloop"
    parser.add_argument("--loop", choices=["auto", "asyncio", "uvloop"],
                       default=default_loop, help=f"事件循环实现 (默认: {default_loop})")
    parser.add_argument("--config", default="config.rbase.yaml", help="配置文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="是否开启详细日志")
    parser.add_argument("--reload", action="store_true", help="是否启用热重载 (仅单进程模式)")
    
    args = parser.parse_args()
    
    # 设置工作进程数量
    if args.workers is None:
        args.workers = get_optimal_worker_count()
    
    # 验证配置
    if args.workers > 1 and args.reload:
        print("警告: 多进程模式下不支持热重载，已禁用 reload 选项")
        args.reload = False
    
    # 初始化配置
    config_file = os.path.join(project_root, args.config)
    if not os.path.exists(config_file):
        print(f"错误: 配置文件 {config_file} 不存在!")
        sys.exit(1)
    
    print(f"加载配置文件: {config_file}")
    setattr(configuration, 'config', Configuration(config_file))
    init_config(configuration.config)
    
    # 获取服务器配置
    # 优先级：命令行参数 > 配置文件 > 默认值
    try:
        api_settings = configuration.config.rbase_settings.get('api', {})
        host = args.host if args.host is not None else api_settings.get('host', '0.0.0.0')
        port = args.port if args.port is not None else int(api_settings.get('port', 8000))
    except Exception as e:
        print(f"获取服务器配置失败: {e}")
        host = args.host if args.host is not None else '0.0.0.0'
        port = args.port if args.port is not None else 8000
    
    print(f"启动服务器: {host}:{port}")
    print(f"工作进程数: {args.workers}")
    print(f"事件循环实现: {args.loop}")
    print(f"热重载: {'启用' if args.reload else '禁用'}")
    print(f"详细日志: {'启用' if args.verbose else '禁用'}")
    print("-" * 50)
    
    # 配置日志
    # uvicorn 参数使用小写，logging 模块使用大写
    log_level = "debug" if args.verbose else "info"
    log_level_upper = "DEBUG" if args.verbose else "INFO"

    # 启动 uvicorn 服务器
    uvicorn.run(
        "deepsearcher.api.main:app",
        host=host,
        port=port,
        workers=args.workers if args.workers > 1 else None,
        loop=args.loop,
        reload=args.reload,
        log_level=log_level,
        access_log=True,
        # Socket异常优化的超时配置
        timeout_keep_alive=20,   # 缩短keep-alive，减少连接积压
        timeout_graceful_shutdown=60,  # 延长优雅关闭时间
        # Socket异常优化配置
        limit_concurrency=500,   # 降低并发连接数，减少socket压力
        limit_max_requests=400,  # 降低每进程请求数，避免资源竞争
        backlog=1024,           # 监听队列长度
        # 日志配置
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "access": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                }
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout"
                },
                "access": {
                    "formatter": "access",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout"
                }
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": log_level_upper},
                "uvicorn.error": {"level": log_level_upper},
                "uvicorn.access": {"handlers": ["access"], "level": log_level_upper, "propagate": False},
                # 控制asyncio日志，减少socket异常警告
                "asyncio": {"level": "WARNING"},
            }
        }
    )


if __name__ == "__main__":
    main() 