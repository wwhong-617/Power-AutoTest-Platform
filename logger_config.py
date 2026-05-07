#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logger Configuration - 日志系统
================================

统一日志配置，支持：
- 分级输出：DEBUG / INFO / WARNING / ERROR / CRITICAL
- 多 Handler：文件（按日期分割）+ 控制台
- 回调 Handler：支持将日志实时推送到 UI Text 组件

核心原则（三通道各司其职）：
  - logger（文件）  ：永久记录，所有 WARNING 及以上
  - _log_callback   ：UI Text，所有 WARNING 及以上
  - messagebox      ：仅在 ERROR 且需用户操作时弹窗

用法：
    from logger_config import _log, info, warning, error, log_exceptions

    _log("INFO", "测试开始")
    warning("配置缺失，使用默认值")

    @log_exceptions
    def risky_operation():
        ...

    # 设置 UI 回调（供 config_ui.py 的日志文本框使用）
    def ui_append(level, message):
        text_widget.insert("end", f"[{level}] {message}\n")
        text_widget.see("end")
    set_ui_callback(ui_append)
"""

import logging
import os
import sys
import traceback as tb_module
from datetime import datetime
from functools import wraps
from logging.handlers import TimedRotatingFileHandler

# ---------------------- 路径配置 ----------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "test_run.log")

# ---------------------- 日志格式 ----------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ---------------------- UI 回调 ----------------------
_ui_callback = None


def set_ui_callback(callback):
    """
    设置 UI 回调函数。
    回调签名: callback(level: str, message: str)
    所有 INFO 及以上级别的日志都会触发回调。
    """
    global _ui_callback
    _ui_callback = callback


# ---------------------- Logger 初始化 ----------------------
def get_logger(name: str = "PowerAutoTest") -> logging.Logger:
    """
    获取或创建指定名称的 Logger。
    建议每个模块用 get_logger(__name__) 获取。
    """
    log = logging.getLogger(name)

    if log.handlers:
        return log  # 已有 handler，直接返回

    log.setLevel(logging.DEBUG)

    # 控制台 Handler（INFO 及以上）
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    # 文件 Handler（DEBUG 及以上，按日期滚动）
    fh = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        encoding="utf-8",
        backupCount=30,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    log.addHandler(ch)
    log.addHandler(fh)

    return log


# 全局 logger
logger = get_logger("PowerAutoTest")

# ---------------------- 统一分发入口 ----------------------

def _log(level: str, msg: str, exc_info=None):
    """
    统一日志分发 — 唯一入口。

    行为：
      - WARNING 及以上：写 logger（文件）+ _log_callback（UI Text）
      - ERROR 且 exc_info=True：同时返回错误详情，供调用方决定是否弹窗

    Args:
        level:   "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
        msg:     日志内容
        exc_info: True/False 或 sys.exc_info()，True 时写入完整 traceback
    """
    _level_map = {
        "DEBUG":    logging.DEBUG,
        "INFO":     logging.INFO,
        "WARNING":  logging.WARNING,
        "ERROR":    logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    numeric_level = _level_map.get(level.upper(), logging.INFO)

    # 写 logger（文件 + 控制台）
    if exc_info:
        logger.log(numeric_level, msg, exc_info=True)
    else:
        logger.log(numeric_level, msg)

    # 写 UI callback（INFO 及以上）
    if numeric_level >= logging.INFO and _ui_callback:
        _exc_suffix = ""
        if exc_info:
            _exc_suffix = "\n" + "".join(tb_module.format_exception(*sys.exc_info()))
        try:
            _ui_callback(level, msg + _exc_suffix)
        except Exception:
            pass  # UI 回调失败不影响主流程


# ---------------------- 兼容封装（内部不再直接调用 warning/error 等） -----

def debug(msg):
    _log("DEBUG", msg)


def info(msg):
    _log("INFO", msg)


def warning(msg):
    _log("WARNING", msg)


def error(msg, exc_info=False):
    _log("ERROR", msg, exc_info=exc_info)


def critical(msg, exc_info=False):
    _log("CRITICAL", msg, exc_info=exc_info)


# ---------------------- 异常处理装饰器 ----------------------

def log_exceptions(func):
    """
    装饰器：自动捕获被装饰函数的未处理异常，
    统一走 _log 分发，写文件 + UI Text，
    同时 re-raise 让调用方感知。

    用法：
        @log_exceptions
        def risky_operation():
            ...

        try:
            risky_operation()
        except Exception:
            # 异常已被记录，不需要重复记录
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            exc_type, exc_val, exc_tb = sys.exc_info()
            tb_str = "".join(tb_module.format_exception(exc_type, exc_val, exc_tb))
            _log("ERROR", f"{func.__name__} 执行异常: {exc_val}", exc_info=True)
            raise  # re-raise，调用方仍需处理
    return wrapper


# ---------------------- 便捷：错误消息格式化 ----------------------

def fmt_exc(exc_type, exc_val, exc_tb=None):
    """返回格式化的异常字符串（含 traceback）。"""
    if exc_tb is None:
        exc_tb = sys.exc_info()[2]
    return "".join(tb_module.format_exception(exc_type, exc_val, exc_tb))


if __name__ == "__main__":
    # 快速测试
    info("日志系统测试 - info")
    debug("日志系统测试 - debug（文件可见，控制台不显示）")
    warning("日志系统测试 - warning")
    error("日志系统测试 - error")
    print(f"日志文件: {LOG_FILE}")
