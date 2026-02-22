#!/usr/bin/env python3
"""
启动脚本 - 自动检查并安装依赖，然后启动主应用
"""

import os
import sys
import subprocess
import platform

# 依赖列表
REQUIREMENTS = [
    "customtkinter>=5.2.0",
    "requests>=2.31.0",
    "flask>=3.1.2",
    "psutil>=5.9.0",
    "pyttsx3>=2.90",
    "websocket-client>=1.8.0",
    "jieba>=0.42.1"
]

# 主应用文件
MAIN_APP = "main.py"

def check_python():
    """检查Python环境"""
    print("检查Python环境...")
    if sys.version_info < (3, 8):
        print(f"错误: Python版本过低 ({sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})")
        print("请安装Python 3.8或更高版本")
        return False
    print(f"Python环境正常: {sys.version}")
    return True

def install_package(package):
    """安装单个包"""
    try:
        print(f"安装 {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        print(f"安装 {package} 失败")
        return False

def check_and_install_dependencies():
    """检查并安装依赖"""
    print("检查依赖...")
    all_installed = True
    
    for package in REQUIREMENTS:
        # 提取包名（去掉版本号）
        package_name = package.split('>')[0].split('=')[0]
        try:
            # 尝试导入包
            __import__(package_name)
            print(f"{package_name} 已安装")
        except ImportError:
            print(f"{package_name} 未安装，正在安装...")
            if not install_package(package):
                all_installed = False
    
    return all_installed

def start_application():
    """启动主应用"""
    print(f"启动应用 {MAIN_APP}...")
    try:
        subprocess.run([sys.executable, MAIN_APP])
    except KeyboardInterrupt:
        print("应用已停止")
    except Exception as e:
        print(f"启动应用失败: {str(e)}")

def main():
    """主函数"""
    print("=====================================")
    print("Ollama Chat Client 启动脚本")
    print("=====================================")
    
    # 检查Python环境
    if not check_python():
        sys.exit(1)
    
    # 检查并安装依赖
    if not check_and_install_dependencies():
        print("部分依赖安装失败，应用可能无法正常运行")
    
    # 启动应用
    start_application()

if __name__ == "__main__":
    main()
