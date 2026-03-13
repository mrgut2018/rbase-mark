"""
Main API Application

This module initializes and configures the FastAPI application.
"""

import os
import logging
import argparse
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.api.routes import router
from deepsearcher.api.models import ExceptionResponse
from deepsearcher.tools.log import set_dev_mode, set_level

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    CONFIG_FILE_PATH: str = "config.rbase.yaml"
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    )


# Configure logging
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Initialize configuration
    config_file = get_config_file()
    logger.info("Initializing Rbase API...")
    setattr(configuration, 'config', Configuration(config_file))
    init_config(configuration.config)

    # Dynamically set timezone from configuration if provided; otherwise skip
    rbase_settings = configuration.config.rbase_settings
    tz = rbase_settings.get('timezone') if isinstance(rbase_settings, dict) else None
    if tz:
        try:
            os.environ['TZ'] = tz
            time.tzset()
            logger.info(f"Timezone set to {tz}")
        except Exception as e:
            logger.warning(f"Failed to set timezone to {tz}: {e}")
    
    # Configure logging settings
    rbase_settings = configuration.config.rbase_settings
    api_settings = rbase_settings.get('api', {})
    log_file = api_settings.get('log_file', 'logs/api.log')
    
    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    
    # Set log level of httpx and httpcore to WARNING
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

    # Configure Python logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    logger.info("Rbase API initialized successfully")
    yield
    logger.info("Shutting down Rbase API...")

# Initialize FastAPI app
def _read_enable_docs():
    """从配置文件读取是否启用 API 文档"""
    import yaml
    settings = Settings()
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        settings.CONFIG_FILE_PATH,
    )
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("rbase_settings", {}).get("api", {}).get("enable_docs", False)
    except Exception:
        return False

_enable_docs = _read_enable_docs()
app = FastAPI(
    title="Rbase API",
    description="Rbase API for academic research",
    version="0.1.0",
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    """
    Root endpoint returning basic API information
    """
    return {
        "name": "Rbase Deep Searcher API",
        "version": "0.0.1",
        "description": "Rbase Deep Searcher API服务，提供AI概述和推荐问题功能",
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy"}

# Get server host/port from configuration file
def get_server_config(config_path: str = "config.rbase.yaml"):
    """
    Read server configuration from file
    
    Returns:
        tuple: (host, port) host and port
    """
    try:
        conf = Configuration(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                "..",
                config_path
            )
        )
        rbase_settings = conf.rbase_settings
        api_settings = rbase_settings.get('api', {})
        host = api_settings.get('host', '0.0.0.0')
        port = int(api_settings.get('port', 8000))
        return host, port
    except Exception as e:
        logger.error(f"Failed to get server config: {e}")
        return '0.0.0.0', 8000

# Global validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format validation errors for requests"""
    error_messages = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        message = f"字段 '{field}' 验证失败: {error['msg']}"
        error_messages.append(message)
    
    return JSONResponse(
        status_code=400,
        content=ExceptionResponse(
            code=400, 
            message="请求参数验证失败:\n" + "\n".join(error_messages)
        ).model_dump()
    )

# General exception handler
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=ExceptionResponse(code=500, message=str(exc)).model_dump()
    )

def get_config_file():
    s = Settings()
    if os.path.exists(s.CONFIG_FILE_PATH):
        config_file = s.CONFIG_FILE_PATH
    else:
        config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            "..",
            s.CONFIG_FILE_PATH
        )
    return config_file

# When running as the main program, start the server using settings from config
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rbase API")
    parser.add_argument("--verbose", "-v", action="store_true", help="是否开启详细日志")
    parser.add_argument("--workers", "-w", type=int, default=1, help="工作进程数量 (默认: 1)")
    parser.add_argument("--loop", choices=["auto", "asyncio", "uvloop"], default="auto", help="事件循环实现 (默认: auto)")
    args = parser.parse_args()

    config_file = get_config_file()
    host, port = get_server_config(config_file)
    logger.info(f"Starting server at {host}:{port} with {args.workers} workers")

    # Read log file path from configuration
    rbase_settings = configuration.config.rbase_settings
    api_settings = rbase_settings.get('api', {})
    log_file = api_settings.get('log_file', 'logs/api.log')
    
    # Ensure the log directory exists
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure uvicorn logging
    import uvicorn
    log_config = uvicorn.config.LOGGING_CONFIG
    
    # Unify log format across loggers
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_config["formatters"]["default"]["fmt"] = log_format
    log_config["formatters"]["access"]["fmt"] = log_format
    
    # Add file handler to all logger configurations
    for logger_name in log_config["loggers"]:
        logger_conf = log_config["loggers"][logger_name]
        if args.verbose:
            set_dev_mode(True)
            set_level(logging.DEBUG)
            logger_conf["level"] = "DEBUG"
            logger_conf["handlers"] = ["default", "file"]
        else:
            set_dev_mode(False)
            set_level(logging.INFO)
            logger_conf["level"] = "INFO"
            logger_conf["handlers"] = ["file"]
    
    # Define file handler
    log_config["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "formatter": "default",
        "filename": log_file
    }

    # Set log level of httpx and httpcore to WARNING
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    # 控制asyncio日志，减少socket异常警告
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    # Multi-process configuration
    if args.workers > 1:
        # Socket异常优化：添加并发控制和资源限制
        limit_concurrency = 400 if args.workers >= 6 else 600  # 高worker数时降低并发
        limit_max_requests = 300 if args.workers >= 6 else 500  # 限制每进程请求数
        timeout_keep_alive = 20  # 缩短keep-alive时间，减少连接积压
        
        print(f"🚀 Socket优化配置: 并发限制={limit_concurrency}, 请求限制={limit_max_requests}")
        
        # Multi-process mode: use uvicorn.run() to launch multiple workers
        uvicorn.run(
            "deepsearcher.api.main:app", 
            host=host, 
            port=port, 
            workers=args.workers,
            loop=args.loop,
            reload=False,  # Disable reload in multi-process mode
            log_config=log_config,
            access_log=True,
            # Socket异常优化配置
            timeout_keep_alive=timeout_keep_alive,
            timeout_graceful_shutdown=60,  # 延长优雅关闭时间
            limit_concurrency=limit_concurrency,  # 限制并发连接数
            limit_max_requests=limit_max_requests,  # 限制每进程最大请求数
            backlog=1024,  # 监听队列长度
        )
    else:
        # Single-process mode: use Config and Server
        uvicorn_config = uvicorn.Config(
            "deepsearcher.api.main:app", 
            host=host, 
            port=port, 
            reload=True, 
            log_config=log_config
        )
        server = uvicorn.Server(uvicorn_config)
        server.run()