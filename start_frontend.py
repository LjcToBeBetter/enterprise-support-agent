"""在 PyCharm 中直接运行本文件，启动前端并打开浏览器。"""

from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIRECTORY = PROJECT_ROOT / "frontend"
VITE_SCRIPT = FRONTEND_DIRECTORY / "node_modules" / "vite" / "bin" / "vite.js"
FRONTEND_URL = "http://127.0.0.1:5173"


def frontend_is_running() -> bool:
    """检查这个端口是否已经运行 Vite，避免重复启动前端。"""
    # 只检查本机服务，不让电脑上的代理软件转发这次检查请求。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        # /@vite/client 是 Vite 提供的开发脚本。
        # 普通网页即使也占用了5173端口，也不应被当作已启动的前端。
        with opener.open(f"{FRONTEND_URL}/@vite/client", timeout=1) as response:
            content = response.read().decode("utf-8", errors="replace")
            return response.status == 200 and "createHotContext" in content
    except (OSError, urllib.error.URLError):
        return False


def main() -> None:
    """启动前端开发服务器，等待就绪，再自动打开登录页面。"""
    print("正在检查前端，请稍候……", flush=True)

    if frontend_is_running():
        print(f"前端已经在运行，直接打开：{FRONTEND_URL}", flush=True)
        webbrowser.open(FRONTEND_URL)
        return

    # 前端是 React/TypeScript 程序，需要 Node.js 执行。
    # Python 在这里负责启动它，你不需要手动输入 npm 命令。
    node_executable = shutil.which("node")
    if node_executable is None:
        print("没有找到 Node.js。安装 Node.js 后重新打开 PyCharm，再运行本文件。", flush=True)
        return
    if not VITE_SCRIPT.is_file():
        print("前端依赖尚未安装，缺少 frontend/node_modules。当前电脑已安装依赖时无需重复安装。", flush=True)
        return

    # cwd指定前端所在目录，与PyCharm当前工作目录无关。
    # 直接用Node运行Vite，不另开PowerShell窗口；日志会显示在当前运行窗口。
    process = subprocess.Popen(
        [node_executable, str(VITE_SCRIPT), "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
        cwd=FRONTEND_DIRECTORY,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                print("前端没有启动成功，请查看上方日志；如果端口被其他程序占用，请先关闭该程序。", flush=True)
                return
            if frontend_is_running():
                print(f"前端已启动：{FRONTEND_URL}", flush=True)
                print("后端也需要保持运行；处理文档时还需要运行文档Worker。", flush=True)
                webbrowser.open(FRONTEND_URL)
                # 等待前端进程，不让Python启动文件运行结束后直接退出。
                process.wait()
                return
            time.sleep(0.3)
        print("前端启动等待超时，请查看上方日志。", flush=True)
    except KeyboardInterrupt:
        print("正在停止前端……", flush=True)
    finally:
        # 正常退出或中断时，关闭本次启动的前端进程。
        # 如果前端原本就在运行，上面的复用分支不会进入这里，不会关闭它。
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
