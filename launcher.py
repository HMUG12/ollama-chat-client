#!/usr/bin/env python3
"""
Ollama Chat Launcher
启动器脚本，用于检查和启动Ollama服务
"""

import subprocess
import sys
import os
import time
import threading
import webbrowser
from pathlib import Path


def check_ollama_running():
    """检查Ollama是否在运行"""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def start_ollama_service():
    """启动Ollama服务"""
    print("正在启动Ollama服务...")

    # 尝试不同的启动方式
    startup_commands = [
        ["ollama", "serve"],  # 标准方式
        ["ollama", "run", "llama2"],  # 另一种方式
    ]

    for cmd in startup_commands:
        try:
            # 在后台启动Ollama
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            print(f"已启动命令: {' '.join(cmd)}")
            time.sleep(3)  # 等待服务启动
            return process
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"启动失败: {e}")
            continue

    return None


def open_browser_if_needed():
    """如果需要，打开浏览器到Ollama WebUI"""
    try:
        webbrowser.open("http://localhost:11434")
    except:
        pass


def check_dependencies():
    """检查依赖"""
    required_packages = ["customtkinter", "requests", "pillow"]
    missing = []

    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    return missing


def install_dependencies(missing_packages):
    """安装缺失的依赖"""
    if not missing_packages:
        return True

    print(f"缺少依赖: {missing_packages}")
    response = input("是否自动安装？(y/n): ")

    if response.lower() == 'y':
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            print("依赖安装完成！")
            return True
        except subprocess.CalledProcessError:
            print("安装失败，请手动运行:")
            print(f"pip install {' '.join(missing_packages)}")
            return False
    else:
        print("请手动安装依赖:")
        print(f"pip install {' '.join(missing_packages)}")
        return False


def create_shortcut():
    """创建快捷方式（可选）"""
    if sys.platform == "win32":
        try:
            import winshell
            from win32com.client import Dispatch

            desktop = winshell.desktop()
            path = os.path.join(desktop, "Ollama Chat.lnk")

            target = sys.executable
            wDir = os.path.dirname(os.path.abspath(__file__))
            icon = os.path.join(wDir, "assets", "icon.ico") if os.path.exists(
                os.path.join(wDir, "assets", "icon.ico")) else None

            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.Arguments = f'"{os.path.join(wDir, "launcher.py")}"'
            shortcut.WorkingDirectory = wDir
            if icon:
                shortcut.IconLocation = icon
            shortcut.save()

            print(f"已在桌面创建快捷方式")
        except:
            pass  # 忽略创建快捷方式失败


def main():
    """主函数"""
    print("=" * 50)
    print("Ollama Chat 启动器")
    print("=" * 50)

    # 检查依赖
    missing = check_dependencies()
    if missing:
        if not install_dependencies(missing):
            input("按Enter键退出...")
            return

    # 检查Ollama是否运行
    if not check_ollama_running():
        print("⚠️  Ollama服务未运行")
        response = input("是否尝试启动Ollama服务？(y/n): ")

        if response.lower() == 'y':
            ollama_process = start_ollama_service()

            if ollama_process:
                print("等待Ollama服务启动...")
                for i in range(10):  # 等待最多10秒
                    time.sleep(1)
                    if check_ollama_running():
                        print("✅ Ollama服务已启动")
                        break
                    print(f"等待中... ({i + 1}/10)")
            else:
                print("❌ 无法启动Ollama服务")
                print("请确保已安装Ollama:")
                print("1. 访问 https://ollama.com 下载安装")
                print("2. 在终端运行: ollama serve")
                open_browser_if_needed()
        else:
            print("请手动启动Ollama:")
            print("1. 打开终端/命令提示符")
            print("2. 运行: ollama serve")
            open_browser_if_needed()
    else:
        print("✅ Ollama服务已在运行")

    # 启动主程序
    print("\n启动聊天界面...")

    try:
        # 导入并运行主程序
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from main import OllamaChatGUI

        app = OllamaChatGUI()
        app.run()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按Enter键退出...")


if __name__ == "__main__":
    # 创建快捷方式（首次运行时）
    if not os.path.exists(os.path.join(os.path.dirname(__file__), ".shortcut_created")):
        create_shortcut()
        with open(os.path.join(os.path.dirname(__file__), ".shortcut_created"), "w") as f:
            f.write("1")

    main()