"""
GitHub 自动同步脚本
每2小时自动执行：git add → git commit → git push
同时也支持手动调用：python sync_to_github.py "提交信息"
"""
import subprocess
import sys
import os
from datetime import datetime

REPO_DIR = r"D:\injoinic--job\自动化测试平台开发\自动化测试平台"
TOKEN = os.environ.get("GITHUB_PAT", "")
if not TOKEN:
    raise ValueError("环境变量 GITHUB_PAT 未设置，请先设置：set GITHUB_PAT=你的Token")
REMOTE = f"https://{TOKEN}@github.com/wwhong-617/Power-AutoTest-Platform.git"


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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始同步...")

    # 检查 git status
    status_out, _ = run("git status --porcelain")
    if not status_out.strip():
        print("没有文件变更，跳过。")
        return

    # 获取变更文件列表
    files = [line.strip()[3:] for line in status_out.strip().splitlines()]
    print(f"变更文件 ({len(files)} 个): {', '.join(files[:10])}" + (" ..." if len(files) > 10 else ""))

    # git add .
    run("git add -A")

    # 提交
    if message is None:
        message = f"Auto-sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    commit_out, code = run(f'git commit -m "{message}"')
    if code != 0:
        print(f"提交失败: {commit_out}")
        return

    print(f"提交成功: {message}")

    # 设置 remote（含 token）
    run(f'git remote set-url origin {REMOTE}')

    # push
    push_out, code = run("git push origin master")
    if code != 0:
        print(f"推送失败: {push_out}")
        return

    print("推送成功！")
    print(f"仓库地址: https://github.com/wwhong-617/Power-AutoTest-Platform")


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else None
    sync(msg)
