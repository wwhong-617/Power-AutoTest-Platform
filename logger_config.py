#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logger Configuration - 日志系统
================================

统一日志配置，支持：
- 分级输出：DEBUG / INFO / WARNING / ERROR
- 多 Handler：文件（按日期分割）+ 控制台
- 回调 Handler：支持将日志实时推送到 UI Text 组件

用法：
    from logger_config import logger, set_ui_callback

    logger.info("测试开始")
    logger.debug("详细调试信息")

    # 设置 UI 回调（供 config_ui.py 的日志文本框使用）
    def ui_append(text):
        text_widget.insert("end", text + "\n")
        text_widget.see("end")
    set_ui_callback(ui_append)
"""

import logging
import os
import sys
from datetime import datetime
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
    所有 INFO 及以上级别的日志都会推送一条到回调。
    回调签名: callback(level: str, message: str)
    """
    global _ui_callback
    _ui_callback = callback


def _emit_to_ui(level, message):
    if _ui_callback:
        try:
            _ui_callback(level, message)
        except Exception:
            pass


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
        backupCount=30,  # 保留30天日志
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    log.addHandler(ch)
    log.addHandler(fh)

    return log


# 全局 logger
logger = get_logger("PowerAutoTest")

# ---------------------- 便捷封装 ----------------------
def debug(msg):
    logger.debug(msg)


def info(msg):
    logger.info(msg)
    _emit_to_ui("INFO", msg)


def warning(msg):
    logger.warning(msg)
    _emit_to_ui("WARNING", msg)


def error(msg):
    logger.error(msg)
    _emit_to_ui("ERROR", msg)


def critical(msg):
    logger.critical(msg)
    _emit_to_ui("CRITICAL", msg)


if __name__ == "__main__":
    # 快速测试
    info("日志系统测试 - info")
    debug("日志系统测试 - debug（文件可见，控制台不显示）")
    warning("日志系统测试 - warning")
    error("日志系统测试 - error")
    print(f"日志文件: {LOG_FILE}")
