#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 自动同步脚本

修复：push 前临时注入 token 到 remote URL，完成后立即恢复，
      避免 token 被写入 .git/config 或任何磁盘文件。
"""
import subprocess
import sys
import os
from datetime import datetime

REPO_DIR = os.path.dirname(__file__)
REPO_URL = "https://github.com/wwhong-617/Power-AutoTest-Platform.git"
TOKEN = os.environ.get("GITHUB_PAT", "")
if not TOKEN:
    raise ValueError("环境变量 GITHUB_PAT 未设置，请先设置：set GITHUB_PAT=你的Token")


def run(cmd, cwd=REPO_DIR, capture=True):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout + result.stderr, result.returncode


def sync(message=None):
    os.chdir(REPO_DIR)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] 开始同步...")

    # 检查 git status
    status_out, _ = run("git status --porcelain")
    if not status_out.strip():
        print("没有文件变更，跳过。")
        return

    # 获取变更文件列表
    files = [line.strip()[3:] for line in status_out.strip().splitlines()]
    print("变更文件 (%d 个): %s" % (len(files), ", ".join(files[:10]) + (" ..." if len(files) > 10 else "")))

    # git add .
    run("git add -A")

    # 提交
    if message is None:
        message = "Auto-sync %s" % datetime.now().strftime('%Y-%m-%d %H:%M')

    commit_out, code = run('git commit -m "%s"' % message)
    if code != 0:
        print("提交失败: %s" % commit_out)
        return

    print("提交成功: %s" % message)

    # ── push：临时注入 token，完成后立即恢复 ──────────────────────
    # 1. 保存原始 remote URL（不包含 token）
    orig_remote, _ = run("git remote get-url origin")
    orig_remote = orig_remote.strip()

    # 2. 构造含 token 的 push URL
    push_remote = "https://%s@github.com/wwhong-617/Power-AutoTest-Platform.git" % TOKEN

    try:
        # 3. 临时写入含 token 的 remote
        run("git remote set-url origin %s" % push_remote)

        # 4. push
        push_out, code = run("git push origin master")
        if code != 0:
            print("推送失败: %s" % push_out)
            return

        print("推送成功！")

    finally:
        # 5. 无论成功失败，都恢复原始 remote URL（不含 token）
        run("git remote set-url origin %s" % orig_remote)
        print("Remote URL 已恢复为: %s" % orig_remote)

    print("仓库地址: %s" % REPO_URL)


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else None
    sync(msg)
