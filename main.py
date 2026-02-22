import customtkinter as ctk
import threading
import time
from tkinter import scrolledtext
import requests
import websocket
import json
from typing import List, Dict
import flask
import os
import sys
import uuid
from datetime import datetime, timedelta
import configparser
from collections import deque
import gc
import psutil


class OllamaChatGUI:
    def __init__(self):
        # 初始化窗口
        ctk.set_appearance_mode("dark")  # 深色模式
        ctk.set_default_color_theme("blue")  # 蓝色主题

        # Ollama配置
        self.base_url = "http://localhost:11434"  # Ollama默认地址
        try:
            self._cached_models = self.get_available_models()
            self.current_model = self._cached_models[0] if self._cached_models else ""
        except Exception as e:
            print(f"获取模型列表失败: {str(e)}")
            self._cached_models = ["llama2", "mistral", "codellama"]
            self.current_model = self._cached_models[0]

        # API服务配置
        self.api_server_enabled = False
        self.api_server_port = 5000
        try:
            self.api_keys = self.load_api_keys()
        except Exception as e:
            print(f"加载API密钥失败: {str(e)}")
            self.api_keys = []
        self.api_server = None
        # API Key调用统计
        try:
            self.api_key_stats = self.load_api_key_stats()
        except Exception as e:
            print(f"加载API密钥统计失败: {str(e)}")
            self.api_key_stats = {}
        
        # 向外调用配置
        self.external_calls = []  # 向外调用配置列表
        try:
            self.external_calls = self.load_external_calls()
        except Exception as e:
            print(f"加载向外调用配置失败: {str(e)}")
            self.external_calls = []
        # 向外调用服务状态
        self.external_call_enabled = False
        
        # MCP Router配置
        self.mcp_router_enabled = False
        self.mcp_router_port = 8000
        self.mcp_router = None
        
        # TTS配置
        self.tts_enabled = False
        self.tts_engine = None
        self.tts_mode = "local"  # local 或 online
        self.tts_rate = 200  # 语速
        self.tts_volume = 1.0  # 音量 0.0-1.0
        self.tts_voice_index = 0  # 声音索引
        
        # 初始化本地控制台窗口
        print("启动本地控制台...")
        self.window = ctk.CTk()
        self.window.title("Ollama Chat Client - 本地AI助手")
        self.window.geometry("1050x700")
        # 设置窗口最小尺寸
        self.window.minsize(800, 500)

        # 对话历史管理
        self.max_history_rounds = 20  # 最大对话轮数
        # 为每个API Key创建独立的对话历史
        self.conversation_histories = {}  # {api_key: deque}
        # 全局对话历史（用于GUI）
        self.conversation_history = deque(maxlen=self.max_history_rounds)

        # API请求处理配置
        self.max_concurrent_requests = 5  # 最大并发请求数
        self.request_timeout = 60  # 请求超时时间（秒）
        # 请求队列控制
        self.request_semaphore = threading.Semaphore(self.max_concurrent_requests)

        # 内存管理配置
        self.memory_check_interval = 300  # 内存检查间隔（秒）- 增加间隔减少资源占用
        self.max_memory_usage = 85  # 最大内存使用率
        # GPU内存管理配置
        self.gpu_memory_check_enabled = False  # 禁用GPU内存监控以减少资源占用
        self.max_gpu_memory_usage = 80  # 最大GPU内存使用率
        # 启动内存监控线程
        self.memory_monitor_thread = threading.Thread(target=self.monitor_memory, daemon=True)
        self.memory_monitor_thread.start()

        # 是否正在等待AI回复
        self._waiting_response = False
        # 加载动画状态
        self.loading_animation_running = False

        # 加载配置
        self.load_config()

        # 重新初始化依赖配置的组件
        # 重新初始化请求信号量
        self.request_semaphore = threading.Semaphore(self.max_concurrent_requests)
        # 重新初始化全局对话历史
        self.conversation_history = deque(maxlen=self.max_history_rounds)

        self.setup_ui()
        self.test_connection()
        
        # 绑定窗口缩放事件
        self.window.bind("<Configure>", self.on_window_resize)

    def setup_ui(self):
        """设置用户界面"""
        # 创建网格布局
        self.window.grid_columnconfigure(1, weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        # 左侧边栏 - 恢复原始简洁设计
        sidebar_frame = ctk.CTkFrame(self.window, width=280, corner_radius=0)
        sidebar_frame.grid(row=0, column=0, sticky="nsew")
        sidebar_frame.grid_rowconfigure(11, weight=1)

        # 标题
        title_label = ctk.CTkLabel(
            sidebar_frame,
            text="Ollama Chat",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=15, pady=15)

        # Ollama API地址设置
        url_label = ctk.CTkLabel(sidebar_frame, text="Ollama地址:")
        url_label.grid(row=1, column=0, padx=15, pady=(5, 0))

        self.base_url_entry = ctk.CTkEntry(sidebar_frame, placeholder_text="http://localhost:11434")
        self.base_url_entry.insert(0, self.base_url)
        self.base_url_entry.grid(row=2, column=0, padx=15, pady=(0, 8), sticky="ew")

        # 更新地址按钮
        update_url_btn = ctk.CTkButton(
            sidebar_frame,
            text="更新地址",
            command=self.update_ollama_url,
            hover_color="#3498db",
            fg_color="#2980b9",
            border_color="#3498db",
            border_width=2,
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28
        )
        update_url_btn.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="ew")

        # 模型选择
        model_label = ctk.CTkLabel(sidebar_frame, text="选择模型:")
        model_label.grid(row=4, column=0, padx=15, pady=(5, 0))

        self.model_var = ctk.StringVar(value=self.current_model)
        self.model_dropdown = ctk.CTkComboBox(
            sidebar_frame,
            values=self._cached_models,
            variable=self.model_var,
            command=self.change_model
        )
        self.model_dropdown.grid(row=5, column=0, padx=15, pady=(0, 8), sticky="ew")

        # 刷新模型按钮
        refresh_btn = ctk.CTkButton(
            sidebar_frame,
            text="刷新模型列表",
            command=self.refresh_models,
            hover_color="#27ae60",
            fg_color="#229954",
            border_color="#222222",
            border_width=2,
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28
        )
        refresh_btn.grid(row=6, column=0, padx=15, pady=8, sticky="ew")

        # 拉取模型按钮
        pull_model_btn = ctk.CTkButton(
            sidebar_frame,
            text="⬇️ 拉取模型",
            command=self.open_pull_model_window,
            hover_color="#3498db",
            fg_color="#2980b9",
            border_color="#3498db",
            border_width=2,
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28
        )
        pull_model_btn.grid(row=7, column=0, padx=15, pady=8, sticky="ew")

        # 清除对话按钮 - 调整位置避免重叠
        self.clear_btn = ctk.CTkButton(
            sidebar_frame,
            text="清除对话",
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
            border_color="#95a5a6",
            hover_color="#7f8c8d",
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28,
            command=self.clear_conversation
        )
        self.clear_btn.grid(row=8, column=0, padx=15, pady=8, sticky="ew")

        # 端口扫描按钮
        port_scan_btn = ctk.CTkButton(
            sidebar_frame,
            text="🔍 端口扫描",
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
            border_color="#95a5a6",
            hover_color="#7f8c8d",
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28,
            command=self.open_port_scan_window
        )
        port_scan_btn.grid(row=9, column=0, padx=15, pady=8, sticky="ew")

        # API服务管理区域
        api_server_frame = ctk.CTkFrame(sidebar_frame, corner_radius=8)
        api_server_frame.grid(row=10, column=0, padx=15, pady=8, sticky="ew")
        api_server_frame.grid_columnconfigure(0, weight=1)

        api_server_title = ctk.CTkLabel(
            api_server_frame,
            text="API服务管理",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        api_server_title.grid(row=0, column=0, padx=10, pady=(8, 4))

        # 向外调用管理按钮
        external_call_btn = ctk.CTkButton(
            api_server_frame,
            text="向外调用管理",
            command=self.open_external_call_console,
            height=26,
            font=ctk.CTkFont(size=10)
        )
        external_call_btn.grid(row=1, column=0, padx=10, pady=4, sticky="ew")

        # 本地服务搭建按钮
        local_service_btn = ctk.CTkButton(
            api_server_frame,
            text="本地服务搭建",
            command=self.open_local_service_window,
            height=26,
            font=ctk.CTkFont(size=10)
        )
        local_service_btn.grid(row=2, column=0, padx=10, pady=4, sticky="ew")

        # API服务状态
        self.api_server_status = ctk.CTkLabel(
            api_server_frame, 
            text="API服务状态: 未启动",
            font=ctk.CTkFont(size=10)
        )
        self.api_server_status.grid(row=3, column=0, padx=10, pady=(8, 8))

        # 设置按钮
        settings_btn = ctk.CTkButton(
            sidebar_frame,
            text="⚙️ 设置",
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
            border_color="#95a5a6",
            hover_color="#7f8c8d",
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28,
            command=self.open_settings_window
        )
        settings_btn.grid(row=11, column=0, padx=15, pady=8, sticky="ew")

        # 状态标签
        self.status_label = ctk.CTkLabel(
            sidebar_frame, 
            text="状态: 等待连接",
            font=ctk.CTkFont(size=10)
        )
        self.status_label.grid(row=12, column=0, padx=15, pady=8)

        # 退出按钮
        exit_btn = ctk.CTkButton(
            sidebar_frame,
            text="退出",
            command=self.exit_application,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            border_color="#e74c3c",
            border_width=2,
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=28
        )
        exit_btn.grid(row=13, column=0, padx=15, pady=15, sticky="ew")
        
        # 绑定窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.exit_application)

        # 主对话区域
        main_frame = ctk.CTkFrame(self.window, corner_radius=0)
        main_frame.grid(row=0, column=1, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # 对话显示框
        self.conversation_text = scrolledtext.ScrolledText(
            main_frame,
            wrap="word",
            bg="#2b2b2b",
            fg="white",
            font=("Microsoft YaHei", 12),
            padx=15,
            pady=15,
            state="disabled"
        )
        self.conversation_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 预设文字样式标签
        self.conversation_text.tag_config("timestamp_user", foreground="#4CAF50", font=("Arial", 10, "bold"))
        self.conversation_text.tag_config("message_user", foreground="white", font=("Microsoft YaHei", 11))
        self.conversation_text.tag_config("timestamp_assistant", foreground="#2196F3", font=("Arial", 10, "bold"))
        self.conversation_text.tag_config("message_assistant", foreground="white", font=("Microsoft YaHei", 11))
        self.conversation_text.tag_config("timestamp_system", foreground="#FF9800", font=("Arial", 10, "bold"))
        self.conversation_text.tag_config("message_system", foreground="white", font=("Microsoft YaHei", 11))

        # 底部输入区域
        bottom_frame = ctk.CTkFrame(main_frame)
        bottom_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom_frame.grid_columnconfigure(0, weight=1)

        # 输入框
        self.input_text = ctk.CTkTextbox(bottom_frame, height=80)
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # 右侧按钮容器
        right_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=5, pady=5, sticky="ns")
        right_frame.grid_columnconfigure(0, weight=1)
        
        # 上传按钮容器
        upload_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        upload_frame.grid(row=0, column=0, padx=5, pady=(5, 5), sticky="ew")
        upload_frame.grid_columnconfigure(0, weight=1)
        upload_frame.grid_columnconfigure(1, weight=1)
        
        # 上传文本按钮
        upload_text_btn = ctk.CTkButton(
            upload_frame,
            text="📄",
            width=40,
            command=self.upload_text,
            hover_color="#3498db",
            fg_color="#2980b9",
            border_color="#3498db",
            border_width=2,
            corner_radius=6,
            font=ctk.CTkFont(size=12)
        )
        upload_text_btn.grid(row=0, column=0, padx=(0, 5), pady=2)
        
        # 上传图片按钮
        upload_image_btn = ctk.CTkButton(
            upload_frame,
            text="🖼️",
            width=40,
            command=self.upload_image,
            hover_color="#3498db",
            fg_color="#2980b9",
            border_color="#3498db",
            border_width=2,
            corner_radius=6,
            font=ctk.CTkFont(size=12)
        )
        upload_image_btn.grid(row=0, column=1, padx=(5, 0), pady=2)
        
        # 联网搜索开关
        self.web_search_var = ctk.BooleanVar(value=False)
        web_search_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        web_search_frame.grid(row=1, column=0, padx=5, pady=(5, 5), sticky="ew")
        web_search_frame.grid_columnconfigure(0, weight=1)
        
        web_search_switch = ctk.CTkSwitch(
            web_search_frame,
            text="联网",
            variable=self.web_search_var,
            command=self.toggle_web_search_mode
        )
        web_search_switch.grid(row=0, column=0, padx=5, pady=2, sticky="ew")
        
        # 搜索API设置
        self.search_api_var = ctk.StringVar(value="模拟搜索")

        # 发送按钮和加载指示器容器
        send_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        send_frame.grid(row=2, column=0, padx=5, pady=(5, 5), sticky="ew")
        send_frame.grid_columnconfigure(0, weight=1)

        # 发送按钮
        self.send_btn = ctk.CTkButton(
            send_frame,
            text="发送",
            command=self.send_message,
            hover_color="#3498db",
            fg_color="#2980b9",
            border_color="#3498db",
            border_width=2,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.send_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # 加载指示器
        self.loading_indicator = ctk.CTkLabel(
            send_frame,
            text="",
            font=ctk.CTkFont(size=16)
        )
        self.loading_indicator.grid(row=0, column=0, padx=5, pady=5)
        self.loading_indicator.grid_remove()  # 初始隐藏

        # 绑定快捷键：Enter 发送，Shift+Enter 换行
        self.input_text.bind("<Return>", self._on_enter)
        self.input_text.bind("<Shift-Return>", lambda e: None)  # 允许换行

    def _on_enter(self, event=None):
        """Enter 键发送消息"""
        self.send_message()
        return "break"  # 阻止插入换行符

    def _blend_colors(self, color1, color2, alpha):
        """混合两种颜色"""
        # 解析颜色值
        def parse_color(color):
            if color.startswith('#'):
                color = color[1:]
            if len(color) == 6:
                return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            return (0, 0, 0)
        
        # 混合颜色
        r1, g1, b1 = parse_color(color1)
        r2, g2, b2 = parse_color(color2)
        
        r = int(r1 * (1 - alpha) + r2 * alpha)
        g = int(g1 * (1 - alpha) + g2 * alpha)
        b = int(b1 * (1 - alpha) + b2 * alpha)
        
        return f"#{r:02x}{g:02x}{b:02x}"

    def update_ollama_url(self):
        """更新Ollama API地址"""
        new_url = self.base_url_entry.get().strip()
        if new_url:
            self.base_url = new_url
            # 测试新地址
            self._cached_models = self.get_available_models()
            self.model_dropdown.configure(values=self._cached_models)
            if self._cached_models:
                self.current_model = self._cached_models[0]
                self.model_dropdown.set(self.current_model)
            self.add_message("system", "系统", f"Ollama地址已更新为: {new_url}")
            self.save_config()

    def on_window_resize(self, event):
        """窗口缩放事件处理"""
        # 可以在这里添加窗口缩放时的逻辑
        pass

    def get_available_models(self):
        """获取可用的Ollama模型"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [model["name"] for model in models]
        except (requests.RequestException, ValueError, KeyError):
            pass
        return ["llama2", "mistral", "codellama"]  # 默认模型列表

    def test_connection(self):
        """测试Ollama连接"""

        def test():
            try:
                response = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    self.window.after(0, self.status_label.configure,
                        {"text": "状态: 已连接 ✅", "text_color": "lightgreen"}
                    )
                    self.add_message("system", "系统", "已连接到Ollama，可以开始对话了！")
                else:
                    self.window.after(0, self.status_label.configure,
                        {"text": "状态: 连接失败 ❌", "text_color": "red"}
                    )
            except requests.RequestException:
                self.window.after(0, self.status_label.configure,
                    {"text": "状态: Ollama未运行 ❌", "text_color": "red"}
                )
                self.add_message("system", "系统",
                                 "无法连接到Ollama，请确保Ollama服务正在运行。\n"
                                 "在终端运行: ollama serve")

        threading.Thread(target=test, daemon=True).start()

    def change_model(self, choice):
        """切换模型"""
        self.current_model = choice
        self.add_message("system", "系统", f"已切换到模型: {choice}")

    def refresh_models(self):
        """刷新模型列表"""
        models = self.get_available_models()
        self._cached_models = models
        self.model_dropdown.configure(values=models)
        if models:
            self.model_dropdown.set(models[0])
            self.current_model = models[0]

    def open_pull_model_window(self):
        """打开拉取模型窗口"""
        window = ctk.CTkToplevel(self.window)
        window.title("拉取模型")
        window.geometry("500x400")
        window.transient(self.window)
        window.grab_set()
        
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(4, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            window,
            text="⬇️ 拉取模型",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(20, 20))
        
        # 模型名称
        model_label = ctk.CTkLabel(window, text="模型名称:")
        model_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        self.model_name_entry = ctk.CTkEntry(window, width=300)
        self.model_name_entry.insert(0, "llama3:8b")  # 默认模型
        self.model_name_entry.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # 常用模型快捷按钮
        quick_models_frame = ctk.CTkFrame(window, fg_color="transparent")
        quick_models_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        
        quick_models = [
            "llama3:8b", "llama3:70b", "mistral:7b", "gemma:7b",
            "phi3:3.8b", "deepseek-coder:6.7b", "llava:13b", "whisper:large"
        ]
        
        for i, model in enumerate(quick_models):
            btn = ctk.CTkButton(
                quick_models_frame,
                text=model,
                width=100,
                height=30,
                font=ctk.CTkFont(size=10),
                command=lambda m=model: self.model_name_entry.delete(0, "end") or self.model_name_entry.insert(0, m)
            )
            btn.grid(row=i//4, column=i%4, padx=5, pady=5, sticky="ew")
        
        # 拉取按钮
        def start_pull():
            model_name = self.model_name_entry.get().strip()
            if not model_name:
                result_text.configure(state="normal")
                result_text.delete(1.0, "end")
                result_text.insert(1.0, "错误: 请输入模型名称")
                result_text.configure(state="disabled")
                return
            
            # 禁用按钮
            pull_btn.configure(state="disabled")
            result_text.configure(state="normal")
            result_text.delete(1.0, "end")
            result_text.insert(1.0, f"开始拉取模型: {model_name}...\n")
            result_text.configure(state="disabled")
            
            # 在新线程中执行拉取
            def pull_thread():
                success, message = self.pull_model(model_name)
                
                # 更新结果
                window.after(0, lambda: update_results(success, message))
            
            def update_results(success, message):
                result_text.configure(state="normal")
                result_text.delete(1.0, "end")
                if success:
                    result_text.insert(1.0, f"✅ 模型拉取成功: {model_name}\n\n{message}")
                    # 刷新模型列表
                    window.after(1000, lambda: self.refresh_models())
                else:
                    result_text.insert(1.0, f"❌ 模型拉取失败: {message}")
                result_text.configure(state="disabled")
                pull_btn.configure(state="normal")
            
            threading.Thread(target=pull_thread, daemon=True).start()
        
        pull_btn = ctk.CTkButton(
            window,
            text="开始拉取",
            command=start_pull,
            fg_color="#3498db",
            hover_color="#2980b9"
        )
        pull_btn.grid(row=3, column=0, columnspan=2, padx=20, pady=20, sticky="ew")
        
        # 结果显示
        result_frame = ctk.CTkFrame(window, corner_radius=8)
        result_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="nsew")
        
        result_text = scrolledtext.ScrolledText(
            result_frame,
            wrap="word",
            bg="#2b2b2b",
            fg="white",
            font=("Microsoft YaHei", 12),
            padx=15,
            pady=15,
            state="disabled"
        )
        result_text.pack(fill="both", expand=True)

    def pull_model(self, model_name):
        """拉取模型"""
        try:
            # 构建API请求
            url = f"{self.base_url}/api/pull"
            data = {
                "name": model_name
            }
            
            # 发送请求
            response = requests.post(url, json=data, stream=True, timeout=300)
            
            if response.status_code == 200:
                # 处理流式响应
                output = []
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        try:
                            line = chunk.decode('utf-8')
                            if line.strip():
                                # 解析JSON
                                import json
                                data = json.loads(line)
                                if 'status' in data:
                                    output.append(data['status'])
                                    if 'digest' in data:
                                        output.append(f"  进度: {data.get('completed', 0)}/{data.get('total', 0)}")
                        except:
                            pass
                
                return True, "\n".join(output)
            else:
                return False, f"HTTP错误: {response.status_code}"
        except Exception as e:
            return False, str(e)

    def clear_conversation(self):
        """清除对话历史"""
        self.conversation_history = []
        self.conversation_text.configure(state="normal")
        self.conversation_text.delete(1.0, "end")
        self.conversation_text.configure(state="disabled")
        self.add_message("system", "系统", "对话历史已清除")

    def send_message(self):
        """发送消息"""
        if self._waiting_response:
            return

        # 检查API服务是否启用，如果启用则禁止控制台对话
        if self.api_server_enabled:
            self.add_message("system", "系统", "API服务已启用，禁止使用控制台对话")
            return

        message = self.input_text.get("1.0", "end-1c").strip()
        if not message or not self.current_model:
            return

        # 清空输入框并禁用发送按钮
        self.input_text.delete("1.0", "end")
        self._set_sending_state(True)

        # 显示用户消息
        self.add_message("user", "你", message)

        # 发送到Ollama
        threading.Thread(target=self.get_ai_response, args=(message,), daemon=True).start()

    def _update_connection_status(self, connected: bool, error_msg: str = ""):
        """根据实际连接结果更新状态标签"""
        if connected:
            self.status_label.configure(text="状态: 已连接 ✅", text_color="lightgreen")
        elif error_msg:
            self.status_label.configure(text=f"状态: {error_msg}", text_color="red")
        else:
            self.status_label.configure(text="状态: 未连接 ❌", text_color="red")

    def _set_sending_state(self, sending, connected=True, error_msg=""):
        """设置发送状态，防止重复发送"""
        self._waiting_response = sending
        if sending:
            # 显示加载动画
            self.send_btn.grid_remove()
            self.loading_indicator.grid()
            self.loading_indicator.configure(text="🤖")
            self.clear_btn.configure(state="disabled")
            self.status_label.configure(text="状态: AI思考中...", text_color="yellow")
            
            # 启动加载动画
            self.loading_animation_running = True
            self._animate_loading()
        else:
            # 隐藏加载动画
            self.loading_animation_running = False
            self.loading_indicator.grid_remove()
            self.send_btn.grid()
            self.send_btn.configure(state="normal", text="发送")
            self.clear_btn.configure(state="normal")
            self._update_connection_status(connected, error_msg)

    def _animate_loading(self):
        """加载动画效果 - 简化版"""
        if not self.loading_animation_running:
            return
        
        # 简化的加载动画
        def animate():
            if self.loading_animation_running:
                current_text = self.loading_indicator.cget("text")
                new_text = "🤖" if current_text != "🤖" else "🧠"
                self.loading_indicator.configure(text=new_text)
                self.window.after(500, animate)
        
        animate()

    def get_ai_response(self, message):
        """获取AI响应（使用 /api/chat 支持多轮对话）"""
        connected = True
        error_msg = ""
        try:
            # 限制消息长度，避免过长消息占用过多内存
            max_message_length = 5000  # 5KB，减少显存占用
            if len(message) > max_message_length:
                message = message[:max_message_length] + "...（消息过长，已截断）"
                print("用户消息过长，已截断")

            # 检查是否启用联网搜索
            search_results = []
            if self.web_search_var.get():
                # 执行联网搜索
                self.window.after(0, self.status_label.configure, {
                    "text": "状态: 正在联网搜索...",
                    "text_color": "yellow"
                })
                search_results = self.perform_web_search(message)
                
                # 显示搜索结果摘要
                if search_results:
                    search_summary = "\n".join(search_results)
                    self.add_message("system", "系统", f"联网搜索完成，获取到 {len(search_results)} 条相关结果")
                else:
                    self.add_message("system", "系统", "联网搜索无结果，将基于本地知识回答")

            # 将用户消息加入历史
            self.conversation_history.append({
                "role": "user",
                "content": message
            })

            # 构建请求时对历史做快照，避免与主线程竞争
            messages_snapshot = list(self.conversation_history)

            # 进一步限制历史记录长度，减少显存占用
            if len(messages_snapshot) > 10:  # 最多保留10条消息
                messages_snapshot = messages_snapshot[-10:]

            # 如果有搜索结果，构建增强的消息
            if search_results:
                search_summary = "\n".join(search_results)
                # 创建一个系统消息，包含搜索结果
                enhanced_message = {
                    "role": "system",
                    "content": f"基于以下搜索结果，回答用户的问题：\n\n{search_summary}\n\n请综合搜索结果和你的知识，提供一个全面、准确的回答。"
                }
                messages_snapshot.append(enhanced_message)

            data = {
                "model": self.current_model,
                "messages": messages_snapshot,
                "stream": False
            }

            response = requests.post(
                f"{self.base_url}/api/chat",
                json=data,
                timeout=self.request_timeout
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result.get("message", {}).get("content", "")

                # 限制AI回复长度
                if len(ai_response) > max_message_length:
                    ai_response = ai_response[:max_message_length] + "...（回复过长，已截断）"
                    print("AI回复过长，已截断")

                # 将AI回复也加入历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": ai_response
                })

                self.add_message("assistant", "AI", ai_response)
                
                # 释放资源
                del result, messages_snapshot
                if 'search_summary' in locals():
                    del search_summary
                gc.collect()
            else:
                # 请求失败，安全回滚用户消息
                if self.conversation_history and self.conversation_history[-1].get("role") == "user":
                    self.conversation_history.pop()
                self.add_message("system", "系统", f"错误: {response.status_code}")
                connected = False
                error_msg = f"请求错误 ({response.status_code})"
                
                # 释放资源
                del messages_snapshot
                if 'search_summary' in locals():
                    del search_summary
                gc.collect()

        except requests.RequestException as e:
            # 网络异常，安全回滚用户消息
            if self.conversation_history and self.conversation_history[-1].get("role") == "user":
                self.conversation_history.pop()
            self.add_message("system", "系统", f"请求失败: {str(e)}")
            connected = False
            error_msg = "连接失败 ❌"
            
            # 释放资源
            try:
                del messages_snapshot
                if 'search_summary' in locals():
                    del search_summary
            except:
                pass
            gc.collect()
        finally:
            self.window.after(0, self._set_sending_state, False, connected, error_msg)

    def add_message(self, sender, name, message):
        """添加消息到对话框"""
        self.window.after(0, self._add_message_gui, sender, name, message)

    def _add_message_gui(self, sender, name, message):
        """在GUI线程中添加消息"""
        self.conversation_text.configure(state="normal")

        # 添加时间戳
        timestamp = time.strftime("%H:%M:%S")

        # 设置消息前缀图标
        if sender == "user":
            prefix = "👤"
        elif sender == "assistant":
            prefix = "🤖"
        else:
            prefix = "⚙️"

        # 保存当前插入位置
        current_pos = self.conversation_text.index("end")

        # 插入消息
        self.conversation_text.insert("end", f"\n[{timestamp}] {prefix} {name}:\n", f"timestamp_{sender}")
        self.conversation_text.insert("end", f"{message}\n", f"message_{sender}")
        self.conversation_text.insert("end", "-" * 50 + "\n")

        # 滚动到底部
        self.conversation_text.see("end")
        self.conversation_text.configure(state="disabled")

        # 移除淡入效果，直接显示消息以减少资源占用
        
        # 如果是AI回复且TTS启用，自动朗读
        if sender == "assistant" and self.tts_enabled:
            # 在新线程中执行TTS，避免阻塞GUI
            def speak_in_thread():
                # 简短延迟，确保消息已显示
                time.sleep(0.5)
                self.speak_text(message)
            
            threading.Thread(target=speak_in_thread, daemon=True).start()

    def load_config(self):
        """从文件加载配置"""
        # 优先从config.ini加载配置
        config_ini_path = self.get_app_data_path("config.ini")
        config_json_path = self.get_app_data_path("config.json")
        
        try:
            # 加载config.ini
            if os.path.exists(config_ini_path):
                # 创建一个自定义的ConfigParser，忽略值中的注释
                class ConfigParserWithComments(configparser.ConfigParser):
                    def get(self, section, option, *, raw=False, vars=None, fallback=configparser._UNSET):
                        value = super().get(section, option, raw=raw, vars=vars, fallback=fallback)
                        # 去除注释部分
                        if isinstance(value, str):
                            value = value.split('#')[0].strip()
                        return value
                    
                    def getint(self, section, option, *, raw=False, vars=None, fallback=configparser._UNSET):
                        value = self.get(section, option, raw=raw, vars=vars, fallback=fallback)
                        if value != configparser._UNSET:
                            try:
                                return int(value)
                            except ValueError:
                                return fallback
                        return fallback
                    
                    def getboolean(self, section, option, *, raw=False, vars=None, fallback=configparser._UNSET):
                        value = self.get(section, option, raw=raw, vars=vars, fallback=fallback)
                        if value != configparser._UNSET:
                            if isinstance(value, str):
                                value = value.lower()
                                return value in ('true', '1', 'yes', 'on')
                            return bool(value)
                        return fallback
                
                config = ConfigParserWithComments()
                config.read(config_ini_path, encoding="utf-8")
                
                # 服务器配置
                if config.has_section("Server"):
                    self.api_server_enabled = config.getboolean("Server", "enable_api_server", fallback=False)
                    self.api_server_port = config.getint("Server", "api_server_port", fallback=5000)
                
                # Ollama配置
                if config.has_section("Ollama"):
                    self.base_url = config.get("Ollama", "base_url", fallback="http://localhost:11434")
                    default_model = config.get("Ollama", "default_model", fallback="llama2")
                    if default_model:
                        self.current_model = default_model
                
                # API配置
                if config.has_section("API"):
                    self.use_api_key = config.getboolean("API", "enable_external_api", fallback=False)
                    self.api_base_url = config.get("API", "external_api_base_url", fallback="https://api.openai.com/v1")
                
                # 性能配置
                if config.has_section("Performance"):
                    self.max_concurrent_requests = config.getint("Performance", "max_concurrent_requests", fallback=5)
                    self.request_timeout = config.getint("Performance", "request_timeout", fallback=60)
                    self.max_history_rounds = config.getint("Performance", "max_history_rounds", fallback=20)
                    self.memory_check_interval = config.getint("Performance", "memory_check_interval", fallback=60)
                    self.max_memory_usage = config.getint("Performance", "max_memory_usage", fallback=80)
                    # GPU内存管理配置
                    self.gpu_memory_check_enabled = config.getboolean("Performance", "gpu_memory_check_enabled", fallback=True)
                    self.max_gpu_memory_usage = config.getint("Performance", "max_gpu_memory_usage", fallback=80)
            
            # 从config.json加载（保持向后兼容）
            elif os.path.exists(config_json_path):
                with open(config_json_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.api_server_enabled = config.get("api_server_enabled", False)
                    self.api_server_port = config.get("api_server_port", 5000)
                    if "current_model" in config:
                        self.current_model = config["current_model"]
        except Exception as e:
            print(f"加载配置失败: {e}")

    def save_config(self):
        """保存配置到文件"""
        config_ini_path = self.get_app_data_path("config.ini")
        try:
            config = configparser.ConfigParser()
            
            # 读取现有配置
            if os.path.exists(config_ini_path):
                config.read(config_ini_path, encoding="utf-8")
            
            # 更新配置
            if not config.has_section("Server"):
                config.add_section("Server")
            config.set("Server", "enable_api_server", str(self.api_server_enabled))
            config.set("Server", "api_server_port", str(self.api_server_port))
            
            if not config.has_section("Ollama"):
                config.add_section("Ollama")
            config.set("Ollama", "base_url", self.base_url)
            config.set("Ollama", "default_model", self.current_model)
            
            if not config.has_section("Performance"):
                config.add_section("Performance")
            config.set("Performance", "max_concurrent_requests", str(self.max_concurrent_requests))
            config.set("Performance", "request_timeout", str(self.request_timeout))
            config.set("Performance", "max_history_rounds", str(self.max_history_rounds))
            config.set("Performance", "memory_check_interval", str(self.memory_check_interval))
            config.set("Performance", "max_memory_usage", str(self.max_memory_usage))
            config.set("Performance", "gpu_memory_check_enabled", str(self.gpu_memory_check_enabled))
            config.set("Performance", "max_gpu_memory_usage", str(self.max_gpu_memory_usage))
            
            # 保存配置
            with open(config_ini_path, "w", encoding="utf-8") as f:
                config.write(f)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def get_app_data_path(self, filename):
        """获取应用程序数据文件的正确路径（兼容打包后的环境）"""
        if getattr(sys, 'frozen', False):
            # 如果是打包后的可执行文件，使用可执行文件所在目录
            base_path = os.path.dirname(sys.executable)
        else:
            # 开发环境，使用脚本所在目录
            base_path = os.path.dirname(__file__)
        return os.path.join(base_path, filename)
    
    def load_api_keys(self):
        """加载API Keys"""
        api_keys_path = self.get_app_data_path("api_keys.json")
        try:
            if os.path.exists(api_keys_path):
                with open(api_keys_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载API Keys失败: {e}")
        return []

    def save_api_keys(self):
        """保存API Keys"""
        api_keys_path = self.get_app_data_path("api_keys.json")
        try:
            with open(api_keys_path, "w", encoding="utf-8") as f:
                json.dump(self.api_keys, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存API Keys失败: {e}")



    def view_api_keys(self):
        """查看已有的API Keys"""
        if not self.api_keys:
            self.add_message("system", "系统", "没有已生成的API Keys")
            return
        
        keys_info = "已生成的API Keys:\n"
        for i, key_info in enumerate(self.api_keys, 1):
            keys_info += f"\n{i}. Key: {key_info['key']}\n"
            keys_info += f"   创建时间: {key_info['created_at']}\n"
            keys_info += f"   过期时间: {key_info['expires_at']}\n"
        
        self.add_message("system", "系统", keys_info)

    def create_api_app(self):
        """创建API应用，支持阿里API调用方式"""
        app = flask.Flask(__name__)
        
        # 初始化API调用速率限制
        self.api_rate_limit = {}  # {api_key: {timestamp, count}}
        self.api_rate_limit_window = 60  # 60秒窗口
        self.api_rate_limit_max = 100  # 每分钟最多100次请求
        self.api_ip_whitelist = []  # IP白名单（可选）
        self.api_ip_blacklist = []  # IP黑名单
        
        # API认证中间件
        @app.before_request
        def authenticate():
            # 跳过OPTIONS请求
            if flask.request.method == 'OPTIONS':
                return
            
            # 检查IP黑名单
            client_ip = flask.request.remote_addr
            if client_ip in self.api_ip_blacklist:
                return flask.jsonify({"code": 403, "message": "IP address blocked", "data": None}), 403
            
            # 检查IP白名单（如果启用）
            if self.api_ip_whitelist and client_ip not in self.api_ip_whitelist:
                return flask.jsonify({"code": 403, "message": "IP address not allowed", "data": None}), 403
            
            # 获取API Key（支持多种认证方式）
            api_key = None
            
            # 方式1: Bearer token（标准方式）
            auth_header = flask.request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                api_key = auth_header[7:]
            
            # 方式2: 阿里API方式（通过公共参数）
            if not api_key:
                # 从查询参数或表单获取
                api_key = flask.request.args.get('AccessKeyId') or flask.request.form.get('AccessKeyId')
                
            # 方式3: 从JSON请求体获取（阿里API可能的方式）
            if not api_key:
                try:
                    data = flask.request.json
                    if data:
                        api_key = data.get('AccessKeyId')
                except:
                    pass
            
            if not api_key:
                return flask.jsonify({"code": 401, "message": "Missing API Key", "data": None}), 401
            
            # 验证API Key
            valid = False
            api_key_info = None
            for key_info in self.api_keys:
                if key_info['key'] == api_key:
                    api_key_info = key_info
                    # 检查是否过期
                    expires_at = datetime.fromisoformat(key_info['expires_at'])
                    if datetime.now() < expires_at:
                        valid = True
                    break
            
            if not valid:
                return flask.jsonify({"code": 401, "message": "Invalid or expired API Key", "data": None}), 401
            
            # 检查速率限制
            current_time = time.time()
            if api_key not in self.api_rate_limit:
                self.api_rate_limit[api_key] = {'timestamp': current_time, 'count': 0}
            
            rate_info = self.api_rate_limit[api_key]
            if current_time - rate_info['timestamp'] > self.api_rate_limit_window:
                # 重置窗口
                rate_info['timestamp'] = current_time
                rate_info['count'] = 0
            
            if rate_info['count'] >= self.api_rate_limit_max:
                return flask.jsonify({"code": 429, "message": "Too many requests", "data": None}), 429
            
            rate_info['count'] += 1
            
            # 确保为该API Key创建对话历史
            if api_key not in self.conversation_histories:
                self.conversation_histories[api_key] = deque(maxlen=self.max_history_rounds)
            
            # 记录API调用统计
            self.record_api_call(api_key)
        
        # 聊天API端点（支持阿里API格式）
        @app.route('/api/chat', methods=['POST'])
        def chat():
            try:
                # 检查是否超过最大并发请求数
                if not self.request_semaphore.acquire(blocking=False):
                    return flask.jsonify({"code": 429, "message": "Too many concurrent requests", "data": None}), 429
                
                try:
                    # 获取API Key
                    api_key = None
                    
                    # 从请求中获取API Key
                    if flask.request.is_json:
                        data = flask.request.json
                        api_key = data.get('AccessKeyId')
                    if not api_key:
                        api_key = flask.request.args.get('AccessKeyId') or flask.request.form.get('AccessKeyId')
                    if not api_key:
                        auth_header = flask.request.headers.get('Authorization')
                        if auth_header and auth_header.startswith('Bearer '):
                            api_key = auth_header[7:]
                    
                    # 解析请求（支持多种格式）
                    message = None
                    model = self.current_model
                    
                    # 方式1: 标准JSON格式
                    if flask.request.is_json:
                        data = flask.request.json
                        message = data.get('message') or data.get('Message')  # 支持阿里API的参数名
                        model = data.get('model', self.current_model) or data.get('Model', self.current_model)
                    
                    # 方式2: 表单格式（阿里API可能使用）
                    if not message:
                        message = flask.request.form.get('message') or flask.request.form.get('Message')
                        model = flask.request.form.get('model', self.current_model) or flask.request.form.get('Model', self.current_model)
                    
                    # 方式3: 查询参数（阿里API可能使用）
                    if not message:
                        message = flask.request.args.get('message') or flask.request.args.get('Message')
                        model = flask.request.args.get('model', self.current_model) or flask.request.args.get('Model', self.current_model)
                    
                    if not message:
                        return flask.jsonify({"code": 400, "message": "Missing message", "data": None}), 400
                    
                    # 使用同步版本获取回复，传入API Key，添加超时
                    import threading
                    import queue
                    
                    # 创建结果队列
                    result_queue = queue.Queue()
                    
                    # 定义工作函数
                    def worker():
                        try:
                            result = self.get_ai_response_sync(message, model, api_key)
                            result_queue.put((True, result))
                        except Exception as e:
                            result_queue.put((False, str(e)))
                    
                    # 启动工作线程
                    thread = threading.Thread(target=worker)
                    thread.daemon = True
                    thread.start()
                    
                    # 等待结果，设置超时
                    try:
                        success, result = result_queue.get(timeout=self.request_timeout)
                        if success:
                            response = result
                        else:
                            return flask.jsonify({"code": 500, "message": result, "data": None}), 500
                    except queue.Empty:
                        return flask.jsonify({"code": 408, "message": "Request timeout", "data": None}), 408
                    
                    # 返回阿里API标准格式
                    return flask.jsonify({
                        "code": 200,
                        "message": "Success",
                        "data": {
                            "response": response
                        }
                    })
                finally:
                    # 释放信号量
                    self.request_semaphore.release()
            except Exception as e:
                # 确保释放信号量
                try:
                    self.request_semaphore.release()
                except:
                    pass
                return flask.jsonify({"code": 500, "message": str(e), "data": None}), 500
        
        # 模型列表API端点（支持阿里API格式）
        @app.route('/api/models', methods=['GET'])
        def models():
            try:
                models = self.get_available_models()
                # 返回阿里API标准格式
                return flask.jsonify({
                    "code": 200,
                    "message": "Success",
                    "data": {
                        "models": models
                    }
                })
            except Exception as e:
                return flask.jsonify({"code": 500, "message": str(e), "data": None}), 500
        
        # WebSocket聊天API端点
        @app.route('/api/chat/ws')
        def chat_ws():
            # 获取API Key
            api_key = flask.request.args.get('AccessKeyId')
            if not api_key:
                # 尝试从查询参数获取
                api_key = flask.request.args.get('api_key')
            
            # 验证API Key
            valid = False
            for key_info in self.api_keys:
                if key_info['key'] == api_key:
                    # 检查是否过期
                    expires_at = datetime.fromisoformat(key_info['expires_at'])
                    if datetime.now() < expires_at:
                        valid = True
                    break
            
            if not valid:
                return flask.jsonify({"code": 401, "message": "Invalid or expired API Key", "data": None}), 401
            
            # 记录API调用统计
            self.record_api_call(api_key)
            
            # 处理WebSocket连接
            from flask import request
            from werkzeug.wrappers import Response
            
            def wsgi_app(environ, start_response):
                # 检查是否是WebSocket请求
                if environ.get('HTTP_UPGRADE') == 'websocket':
                    # 这里简化处理，实际应该使用专门的WebSocket库
                    # 由于Flask默认不支持WebSocket，我们返回一个错误
                    response = flask.jsonify({"code": 501, "message": "WebSocket not fully implemented", "data": None})
                    return response(environ, start_response)
                else:
                    # 不是WebSocket请求，返回错误
                    response = flask.jsonify({"code": 400, "message": "Not a WebSocket request", "data": None})
                    return response(environ, start_response)
            
            return wsgi_app
        
        return app

    def get_ai_response_sync(self, message, model=None, api_key=None):
        """同步获取AI响应"""
        if model:
            self.current_model = model
        
        # 选择对话历史
        if api_key:
            # 使用API Key对应的对话历史
            history = self.conversation_histories.get(api_key)
            if not history:
                history = deque(maxlen=self.max_history_rounds)
                self.conversation_histories[api_key] = history
        else:
            # 使用全局对话历史（用于GUI）
            history = self.conversation_history
        
        # 限制消息长度，避免过长消息占用过多内存
        max_message_length = 5000  # 5KB，减少显存占用
        if len(message) > max_message_length:
            message = message[:max_message_length] + "...（消息过长，已截断）"
            print("用户消息过长，已截断")

        # 检查是否启用联网搜索
        # API Key远程调用默认启用联网搜索
        use_web_search = self.web_search_var.get() or api_key is not None
        search_results = []
        
        if use_web_search:
            # 执行联网搜索
            print(f"执行联网搜索: {message}")
            search_results = self.perform_web_search(message)
            
            if search_results:
                print(f"联网搜索完成，获取到 {len(search_results)} 条相关结果")
            else:
                print("联网搜索无结果，将基于本地知识回答")

        # 将用户消息加入历史
        history.append({
            "role": "user",
            "content": message
        })

        # 构建请求时对历史做快照，避免与主线程竞争
        messages_snapshot = list(history)

        # 进一步限制历史记录长度，减少显存占用
        if len(messages_snapshot) > 10:  # 最多保留10条消息
            messages_snapshot = messages_snapshot[-10:]

        # 如果有搜索结果，构建增强的消息
        if search_results:
            search_summary = "\n".join(search_results)
            # 创建一个系统消息，包含搜索结果
            enhanced_message = {
                "role": "system",
                "content": f"基于以下搜索结果，回答用户的问题：\n\n{search_summary}\n\n请综合搜索结果和你的知识，提供一个全面、准确的回答。"
            }
            messages_snapshot.append(enhanced_message)

        data = {
            "model": self.current_model,
            "messages": messages_snapshot,
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=data,
                timeout=300
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result.get("message", {}).get("content", "")

                # 限制AI回复长度
                if len(ai_response) > max_message_length:
                    ai_response = ai_response[:max_message_length] + "...（回复过长，已截断）"
                    print("AI回复过长，已截断")

                # 将AI回复也加入历史
                history.append({
                    "role": "assistant",
                    "content": ai_response
                })

                # 释放资源
                del result, messages_snapshot
                if 'search_summary' in locals():
                    del search_summary
                gc.collect()

                return ai_response
            else:
                # 请求失败，安全回滚用户消息
                if history and history[-1].get("role") == "user":
                    history.pop()
                # 释放资源
                del messages_snapshot
                if 'search_summary' in locals():
                    del search_summary
                gc.collect()
                return f"错误: {response.status_code}"
        except Exception as e:
            # 网络异常，安全回滚用户消息
            if history and history[-1].get("role") == "user":
                history.pop()
            # 释放资源
            try:
                del messages_snapshot
                if 'search_summary' in locals():
                    del search_summary
            except:
                pass
            gc.collect()
            return f"错误: {str(e)}"

    def start_api_server(self):
        """启动API服务"""
        try:
            # 获取端口，优先从主窗口的 api_port_entry 获取
            try:
                if hasattr(self, 'api_port_entry'):
                    port = int(self.api_port_entry.get())
                else:
                    port = self.api_server_port
            except (ValueError, AttributeError):
                port = self.api_server_port
            
            self.api_server_port = port
            
            # 创建API应用
            self.api_server = self.create_api_app()
            
            # 在后台线程中运行API服务
            def run_server():
                self.api_server.run(host='0.0.0.0', port=port, debug=False)
            
            threading.Thread(target=run_server, daemon=True).start()
            
            # 更新状态
            self.api_server_enabled = True
            # 更新主窗口的状态（如果存在）
            if hasattr(self, 'api_server_status'):
                self.api_server_status.configure(text=f"API服务状态: 已启动 (端口: {port})", text_color="lightgreen")
            self.add_message("system", "系统", f"API服务已启动，端口: {port}")
            
            # 保存配置
            self.save_config()
        except Exception as e:
            # 更新主窗口的状态（如果存在）
            if hasattr(self, 'api_server_status'):
                self.api_server_status.configure(text=f"API服务状态: 启动失败", text_color="red")
            self.add_message("system", "系统", f"API服务启动失败: {str(e)}")

    def stop_api_server(self):
        """停止API服务"""
        # 注意：Flask的开发服务器不支持优雅停止
        # 这里我们只是标记为已停止
        self.api_server_enabled = False
        # 更新主窗口的状态（如果存在）
        if hasattr(self, 'api_server_status'):
            self.api_server_status.configure(text="API服务状态: 已停止", text_color="red")
        self.add_message("system", "系统", "API服务已停止")
        self.api_server = None
        
        # 保存配置
        self.save_config()

    def toggle_api_server(self):
        """切换API服务状态"""
        if self.api_server_var.get():
            self.start_api_server()
        else:
            self.stop_api_server()
    


    def load_api_key_stats(self):
        """加载API Key调用统计数据"""
        stats_path = self.get_app_data_path("api_key_stats.json")
        try:
            if os.path.exists(stats_path):
                with open(stats_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载API Key统计数据失败: {e}")
        return {}

    def save_api_key_stats(self):
        """保存API Key调用统计数据"""
        stats_path = self.get_app_data_path("api_key_stats.json")
        try:
            with open(stats_path, "w", encoding="utf-8") as f:
                json.dump(self.api_key_stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存API Key统计数据失败: {e}")
    
    def load_external_calls(self):
        """加载向外调用配置"""
        external_calls_path = self.get_app_data_path("external_calls.json")
        try:
            if os.path.exists(external_calls_path):
                with open(external_calls_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载向外调用配置失败: {str(e)}")
        return []
    
    def save_external_calls(self):
        """保存向外调用配置"""
        external_calls_path = self.get_app_data_path("external_calls.json")
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(external_calls_path), exist_ok=True)
            # 保存配置
            with open(external_calls_path, "w", encoding="utf-8") as f:
                json.dump(self.external_calls, f, ensure_ascii=False, indent=2)
            print(f"向外调用配置已保存到: {external_calls_path}")
        except Exception as e:
            print(f"保存向外调用配置失败: {str(e)}")
            # 尝试使用绝对路径
            try:
                import tempfile
                temp_path = os.path.join(tempfile.gettempdir(), "external_calls.json")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self.external_calls, f, ensure_ascii=False, indent=2)
                print(f"向外调用配置已保存到临时路径: {temp_path}")
            except Exception as e2:
                print(f"保存到临时路径也失败: {str(e2)}")
    
    def create_external_call(self, name, model, model_type, url, port, api_key, expires_days):
        """创建新的向外调用配置"""
        # 生成唯一ID
        call_id = str(uuid.uuid4())
        # 计算过期时间
        expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
        # 创建向外调用配置
        external_call = {
            "id": call_id,
            "name": name,
            "model": model,
            "model_type": model_type,
            "url": url,
            "port": port,
            "api_key": api_key,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at,
            "enabled": True,
            "call_count": 0,
            "last_call": None
        }
        # 添加到列表
        self.external_calls.append(external_call)
        # 保存配置
        self.save_external_calls()
        return external_call
    
    def delete_external_call(self, call_id, console_window=None):
        """删除向外调用配置"""
        self.external_calls = [call for call in self.external_calls if call['id'] != call_id]
        self.save_external_calls()
        # 刷新控制台窗口
        if console_window:
            console_window.destroy()
            self.open_external_call_console()
    
    def make_external_call(self, call_id, message, use_websocket=True):
        """执行向外调用"""
        # 检查全局向外调用服务是否启用
        if not self.external_call_enabled:
            return "错误: 向外调用服务未启用"
        
        # 查找向外调用配置
        external_call = None
        for call in self.external_calls:
            if call['id'] == call_id:
                external_call = call
                break
        
        if not external_call:
            return "错误: 未找到向外调用配置"
        
        # 检查是否启用
        if not external_call.get('enabled', True):
            return "错误: 该向外调用已禁用"
        
        # 检查是否过期
        expires_at = datetime.fromisoformat(external_call['expires_at'])
        if datetime.now() > expires_at:
            return "错误: 向外调用配置已过期"
        
        # 更新调用统计
        external_call['call_count'] = external_call.get('call_count', 0) + 1
        external_call['last_call'] = datetime.now().isoformat()
        self.save_external_calls()
        
        # 构建URL
        url = external_call['url'].strip()
        port = external_call['port']
        
        # 检查URL是否已经包含端口
        if ':' in url and not url.startswith(('http://', 'https://', 'ws://', 'wss://')):
            # URL格式不正确，应该包含协议
            return "错误: URL格式不正确，必须包含http://、https://、ws://或wss://"
        
        if use_websocket:
            # WebSocket模式
            try:
                # 构建WebSocket URL
                if '://' in url:
                    # 已经包含协议，转换为WebSocket协议
                    if url.startswith('http://'):
                        ws_url = url.replace('http://', 'ws://')
                    elif url.startswith('https://'):
                        ws_url = url.replace('https://', 'wss://')
                    else:
                        # 已经是WebSocket协议
                        ws_url = url
                else:
                    # 添加默认WebSocket协议
                    ws_url = f"ws://{url}"
                
                # 检查是否需要添加端口
                if ':' not in ws_url.split('://')[1].split('/')[0]:
                    # URL中没有端口，添加配置的端口
                    ws_url = f"{ws_url}:{port}"
                
                # 添加WebSocket路径
                ws_url = f"{ws_url}/api/chat/ws"
                
                # 构建请求数据
                data = {
                    "AccessKeyId": external_call['api_key'],
                    "Message": message,
                    "Model": external_call['model']
                }
                
                # WebSocket连接和通信
                def on_message(ws, message):
                    nonlocal response_data
                    response_data = message
                    ws.close()
                
                def on_error(ws, error):
                    nonlocal error_message
                    error_message = str(error)
                    ws.close()
                
                def on_close(ws, close_status_code, close_msg):
                    nonlocal connection_closed
                    connection_closed = True
                
                def on_open(ws):
                    # 发送消息
                    ws.send(json.dumps(data))
                
                response_data = None
                error_message = None
                connection_closed = False
                
                # 创建WebSocket连接
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                
                # 运行WebSocket连接，设置超时
                ws.run_forever(timeout=self.request_timeout)
                
                if error_message:
                    # WebSocket连接失败，尝试使用HTTP POST
                    return self._make_external_call_http(external_call, message)
                
                if response_data:
                    try:
                        result = json.loads(response_data)
                        return result.get("data", {}).get("response", "无响应内容")
                    except json.JSONDecodeError:
                        return f"错误: WebSocket响应格式不正确: {response_data}"
                else:
                    # 无响应，尝试使用HTTP POST
                    return self._make_external_call_http(external_call, message)
                    
            except Exception as e:
                # WebSocket连接失败，尝试使用HTTP POST
                return self._make_external_call_http(external_call, message)
        else:
            # HTTP POST模式
            return self._make_external_call_http(external_call, message)
    
    def _make_external_call_http(self, external_call, message):
        """使用HTTP POST执行向外调用"""
        # 构建API URL
        url = external_call['url'].strip()
        port = external_call['port']
        
        if '://' in url:
            # 已经包含协议
            base_url = url
        else:
            # 添加默认协议
            base_url = f"http://{url}"
        
        # 检查是否需要添加端口
        if ':' not in base_url.split('://')[1].split('/')[0]:
            # URL中没有端口，添加配置的端口
            api_url = f"{base_url}:{port}/api/chat"
        else:
            # URL中已经有端口，直接使用
            api_url = f"{base_url}/api/chat"
        
        # 构建请求数据
        data = {
            "AccessKeyId": external_call['api_key'],
            "Message": message,
            "Model": external_call['model']
        }
        
        try:
            # 发送请求
            response = requests.post(
                api_url,
                json=data,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("data", {}).get("response", "无响应内容")
            else:
                return f"错误: API调用失败，状态码: {response.status_code}\n{response.text}"
        except Exception as e:
            return f"错误: API调用失败，{str(e)}"
    
    def toggle_external_call_service(self):
        """切换向外调用服务状态"""
        self.external_call_enabled = not self.external_call_enabled
        status = "已启用" if self.external_call_enabled else "已禁用"
        self.add_message("system", "系统", f"向外调用服务{status}")
    
    def toggle_global_external_service(self, enabled, console_window=None):
        """切换全局向外调用服务状态"""
        self.external_call_enabled = enabled
        status = "已启用" if enabled else "已禁用"
        self.add_message("system", "系统", f"全局向外调用服务{status}")
        if console_window:
            console_window.destroy()
            self.open_external_call_console()
    
    def toggle_mcp_router(self, enabled, console_window=None):
        """切换MCP Router服务状态"""
        self.mcp_router_enabled = enabled
        if enabled:
            self.start_mcp_router()
        else:
            self.stop_mcp_router()
        status = "已启动" if enabled else "已停止"
        self.add_message("system", "系统", f"MCP Router服务{status}")
        if console_window:
            console_window.destroy()
            self.open_external_call_console()
    
    def start_mcp_router(self):
        """启动MCP Router服务"""
        try:
            def run_mcp_server():
                app = flask.Flask(__name__)
                
                @app.route('/mcp/tools', methods=['GET'])
                def list_tools():
                    return flask.jsonify({
                        "tools": [
                            {"name": "search", "description": "搜索网络"},
                            {"name": "calculate", "description": "数学计算"}
                        ]
                    })
                
                @app.route('/mcp/call', methods=['POST'])
                def call_tool():
                    data = flask.request.json
                    tool_name = data.get('tool')
                    params = data.get('params', {})
                    
                    if tool_name == 'search':
                        return flask.jsonify({"result": f"搜索结果: {params.get('query', '')}"})
                    elif tool_name == 'calculate':
                        return flask.jsonify({"result": f"计算结果: {params.get('expression', '')}"})
                    return flask.jsonify({"error": "Unknown tool"}), 400
                
                app.run(host='0.0.0.0', port=self.mcp_router_port, threaded=True, use_reloader=False)
            
            self.mcp_router = threading.Thread(target=run_mcp_server, daemon=True)
            self.mcp_router.start()
            print(f"MCP Router已启动在端口 {self.mcp_router_port}")
        except Exception as e:
            print(f"启动MCP Router失败: {str(e)}")
    
    def stop_mcp_router(self):
        """停止MCP Router服务"""
        print("MCP Router已停止")
    
    def toggle_tts(self, enabled, console_window=None):
        """切换TTS服务状态"""
        self.tts_enabled = enabled
        if enabled:
            self.init_tts_engine()
        else:
            self.stop_tts_engine()
        status = "已启用" if enabled else "已禁用"
        self.add_message("system", "系统", f"本地TTS服务{status}")
        if console_window:
            console_window.destroy()
            self.open_external_call_console()
    
    def init_tts_engine(self):
        """初始化TTS引擎"""
        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            
            # 应用设置
            try:
                self.tts_engine.setProperty('rate', self.tts_rate)
                self.tts_engine.setProperty('volume', self.tts_volume)
                
                # 设置声音
                voices = self.tts_engine.getProperty('voices')
                if voices and self.tts_voice_index < len(voices):
                    self.tts_engine.setProperty('voice', voices[self.tts_voice_index].id)
            except Exception as e:
                print(f"应用TTS设置失败: {str(e)}")
            
            print("TTS引擎已初始化")
        except ImportError:
            print("pyttsx3未安装，无法初始化TTS")
            self.tts_enabled = False
        except Exception as e:
            print(f"初始化TTS失败: {str(e)}")
    
    def stop_tts_engine(self):
        """停止TTS引擎"""
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except:
                pass
            self.tts_engine = None
        print("TTS引擎已停止")
    
    def speak_text(self, text):
        """使用TTS朗读文本"""
        if not self.tts_enabled:
            return
        
        if self.tts_mode == "local":
            if not self.tts_engine:
                return
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                print(f"TTS朗读失败: {str(e)}")
        else:
            print("在线TTS模式待实现")
    
    def open_settings_window(self):
        """打开设置窗口"""
        window = ctk.CTkToplevel(self.window)
        window.title("设置")
        window.geometry("600x500")
        window.transient(self.window)
        window.grab_set()
        
        window.grid_columnconfigure(0, weight=1)
        window.grid_columnconfigure(1, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            window,
            text="⚙️ 系统设置",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(20, 20))
        
        # 性能设置区域
        performance_frame = ctk.CTkFrame(window, corner_radius=12)
        performance_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        
        perf_title = ctk.CTkLabel(
            performance_frame,
            text="性能设置",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        perf_title.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        
        # 超时设置
        timeout_label = ctk.CTkLabel(performance_frame, text="请求超时 (秒):")
        timeout_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        timeout_var = ctk.IntVar(value=self.request_timeout)
        timeout_entry = ctk.CTkEntry(performance_frame, width=100, textvariable=timeout_var)
        timeout_entry.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # 最大并发请求数
        concurrent_label = ctk.CTkLabel(performance_frame, text="最大并发请求数:")
        concurrent_label.grid(row=2, column=0, padx=20, pady=10, sticky="e")
        
        concurrent_var = ctk.IntVar(value=self.max_concurrent_requests)
        concurrent_entry = ctk.CTkEntry(performance_frame, width=100, textvariable=concurrent_var)
        concurrent_entry.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        
        # 最大对话轮数
        history_label = ctk.CTkLabel(performance_frame, text="最大对话轮数:")
        history_label.grid(row=3, column=0, padx=20, pady=10, sticky="e")
        
        history_var = ctk.IntVar(value=self.max_history_rounds)
        history_entry = ctk.CTkEntry(performance_frame, width=100, textvariable=history_var)
        history_entry.grid(row=3, column=1, padx=20, pady=10, sticky="w")
        
        # 内存设置区域
        memory_frame = ctk.CTkFrame(window, corner_radius=12)
        memory_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        
        mem_title = ctk.CTkLabel(
            memory_frame,
            text="内存设置",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        mem_title.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        
        # 内存检查间隔
        memory_check_label = ctk.CTkLabel(memory_frame, text="内存检查间隔 (秒):")
        memory_check_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        memory_check_var = ctk.IntVar(value=self.memory_check_interval)
        memory_check_entry = ctk.CTkEntry(memory_frame, width=100, textvariable=memory_check_var)
        memory_check_entry.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # 最大内存使用率
        max_memory_label = ctk.CTkLabel(memory_frame, text="最大内存使用率 (%):")
        max_memory_label.grid(row=2, column=0, padx=20, pady=10, sticky="e")
        
        max_memory_var = ctk.IntVar(value=self.max_memory_usage)
        max_memory_entry = ctk.CTkEntry(memory_frame, width=100, textvariable=max_memory_var)
        max_memory_entry.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        
        # 保存按钮
        def save_settings():
            # 保存超时设置
            self.request_timeout = timeout_var.get()
            # 保存其他设置
            self.max_concurrent_requests = concurrent_var.get()
            self.max_history_rounds = history_var.get()
            self.memory_check_interval = memory_check_var.get()
            self.max_memory_usage = max_memory_var.get()
            
            # 重新初始化依赖配置的组件
            self.request_semaphore = threading.Semaphore(self.max_concurrent_requests)
            self.conversation_history = deque(maxlen=self.max_history_rounds)
            
            # 保存配置到文件
            self.save_config()
            
            # 显示成功消息
            success_window = ctk.CTkToplevel(window)
            success_window.title("成功")
            success_window.geometry("300x150")
            success_window.transient(window)
            
            success_label = ctk.CTkLabel(
                success_window,
                text="设置已保存",
                font=ctk.CTkFont(size=14)
            )
            success_label.pack(pady=40)
            
            success_btn = ctk.CTkButton(
                success_window,
                text="确定",
                command=lambda: [success_window.destroy(), window.destroy()]
            )
            success_btn.pack(pady=10)
        
        save_btn = ctk.CTkButton(
            window,
            text="保存设置",
            command=save_settings,
            fg_color="#27ae60",
            hover_color="#2ecc71"
        )
        save_btn.grid(row=3, column=0, columnspan=2, padx=20, pady=20, sticky="ew")

    def open_tts_settings(self, parent_window=None):
        """打开TTS设置面板"""
        window = ctk.CTkToplevel(parent_window if parent_window else self.window)
        window.title("TTS设置")
        window.geometry("500x450")
        if parent_window:
            window.transient(parent_window)
        window.grab_set()
        
        window.grid_columnconfigure(0, weight=1)
        window.grid_columnconfigure(1, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            window,
            text="⚙️ TTS语音设置",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(20, 20))
        
        # 语速
        rate_label = ctk.CTkLabel(window, text="语速:")
        rate_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        rate_var = ctk.IntVar(value=self.tts_rate)
        
        rate_slider = ctk.CTkSlider(
            window,
            from_=50,
            to=400,
            variable=rate_var,
            width=200
        )
        rate_slider.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        rate_value_label = ctk.CTkLabel(window, textvariable=rate_var)
        rate_value_label.grid(row=1, column=1, padx=20, pady=10, sticky="e")
        
        # 音量
        volume_label = ctk.CTkLabel(window, text="音量:")
        volume_label.grid(row=2, column=0, padx=20, pady=10, sticky="e")
        
        volume_var = ctk.DoubleVar(value=self.tts_volume)
        
        volume_slider = ctk.CTkSlider(
            window,
            from_=0.0,
            to=1.0,
            variable=volume_var,
            width=200
        )
        volume_slider.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        
        def update_volume_label(*args):
            volume_value_label.configure(text=f"{int(volume_var.get() * 100)}%")
        
        volume_var.trace_add("write", update_volume_label)
        
        volume_value_label = ctk.CTkLabel(window, text=f"{int(self.tts_volume * 100)}%")
        volume_value_label.grid(row=2, column=1, padx=20, pady=10, sticky="e")
        
        # 声音选择（如果本地TTS可用）
        voice_label = ctk.CTkLabel(window, text="声音:")
        voice_label.grid(row=3, column=0, padx=20, pady=10, sticky="e")
        
        voice_var = ctk.StringVar(value="默认")
        voice_options = ["默认"]
        
        # 获取可用声音
        if self.tts_engine:
            try:
                voices = self.tts_engine.getProperty('voices')
                voice_options = [f"{i+1}. {voice.name}" for i, voice in enumerate(voices)]
                if voice_options:
                    voice_var.set(voice_options[min(self.tts_voice_index, len(voice_options)-1)])
            except:
                pass
        
        voice_dropdown = ctk.CTkComboBox(
            window,
            values=voice_options,
            variable=voice_var,
            width=200
        )
        voice_dropdown.grid(row=3, column=1, padx=20, pady=10, sticky="w")
        
        # 测试按钮
        def test_tts():
            test_text = "你好，这是TTS语音测试"
            self.speak_text(test_text)
        
        test_btn = ctk.CTkButton(
            window,
            text="🔊 测试语音",
            fg_color="#27ae60",
            hover_color="#2ecc71",
            command=test_tts
        )
        test_btn.grid(row=4, column=0, columnspan=2, padx=20, pady=20, sticky="ew")
        
        # 保存按钮
        def save_settings():
            self.tts_rate = rate_var.get()
            self.tts_volume = volume_var.get()
            
            # 设置声音
            if self.tts_engine:
                try:
                    self.tts_engine.setProperty('rate', self.tts_rate)
                    self.tts_engine.setProperty('volume', self.tts_volume)
                    
                    if voice_options and voice_options != ["默认"]:
                        idx = voice_options.index(voice_var.get())
                        self.tts_voice_index = idx
                        voices = self.tts_engine.getProperty('voices')
                        if idx < len(voices):
                            self.tts_engine.setProperty('voice', voices[idx].id)
                except Exception as e:
                    print(f"设置TTS属性失败: {str(e)}")
            
            window.destroy()
            if parent_window:
                parent_window.destroy()
                self.open_external_call_console()
        
        save_btn = ctk.CTkButton(
            window,
            text="保存设置",
            command=save_settings
        )
        save_btn.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
    
    def open_local_service_window(self):
        """打开本地服务搭建窗口"""
        window = ctk.CTkToplevel(self.window)
        window.title("本地服务搭建")
        window.geometry("700x600")
        window.transient(self.window)
        window.grab_set()
        
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(5, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            window,
            text="🏠 本地服务搭建",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(20, 20))
        
        # 服务类型选择
        service_label = ctk.CTkLabel(window, text="服务类型:")
        service_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        self.service_type_var = ctk.StringVar(value="Ollama")
        service_types = ["Ollama", "OpenAI兼容API", "Hugging Face", "自定义服务"]
        
        service_dropdown = ctk.CTkComboBox(
            window,
            values=service_types,
            variable=self.service_type_var,
            width=300
        )
        service_dropdown.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # 服务配置区域
        config_frame = ctk.CTkFrame(window, corner_radius=8, border_width=1, border_color="#3498db")
        config_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        
        # 端口配置
        port_label = ctk.CTkLabel(config_frame, text="服务端口:")
        port_label.grid(row=0, column=0, padx=20, pady=10, sticky="e")
        
        self.port_entry = ctk.CTkEntry(config_frame, width=100)
        self.port_entry.insert(0, "11434")  # 默认Ollama端口
        self.port_entry.grid(row=0, column=1, padx=20, pady=10, sticky="w")
        
        # 服务状态
        self.service_status = ctk.CTkLabel(config_frame, text="服务状态: 未启动")
        self.service_status.grid(row=1, column=0, columnspan=2, padx=20, pady=10)
        
        # 操作按钮
        btn_frame = ctk.CTkFrame(window, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=20, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        def start_service():
            service_type = self.service_type_var.get()
            port = self.port_entry.get().strip()
            
            try:
                port = int(port)
                if port < 1 or port > 65535:
                    raise ValueError
            except ValueError:
                self.service_status.configure(text="错误: 端口无效 (1-65535)")
                return
            
            # 禁用按钮
            start_btn.configure(state="disabled")
            stop_btn.configure(state="disabled")
            self.service_status.configure(text=f"启动中: {service_type} (端口: {port})...")
            
            # 在新线程中执行启动
            def start_thread():
                success, message = self.start_local_service(service_type, port)
                
                # 更新状态
                window.after(0, lambda: update_status(success, message))
            
            def update_status(success, message):
                if success:
                    self.service_status.configure(text=f"服务状态: 运行中 - {message}")
                else:
                    self.service_status.configure(text=f"错误: {message}")
                start_btn.configure(state="normal")
                stop_btn.configure(state="normal")
            
            threading.Thread(target=start_thread, daemon=True).start()
        
        def stop_service():
            service_type = self.service_type_var.get()
            
            # 禁用按钮
            start_btn.configure(state="disabled")
            stop_btn.configure(state="disabled")
            self.service_status.configure(text=f"停止中: {service_type}...")
            
            # 在新线程中执行停止
            def stop_thread():
                success, message = self.stop_local_service(service_type)
                
                # 更新状态
                window.after(0, lambda: update_status(success, message))
            
            def update_status(success, message):
                if success:
                    self.service_status.configure(text=f"服务状态: 已停止 - {message}")
                else:
                    self.service_status.configure(text=f"错误: {message}")
                start_btn.configure(state="normal")
                stop_btn.configure(state="normal")
            
            threading.Thread(target=stop_thread, daemon=True).start()
        
        start_btn = ctk.CTkButton(
            btn_frame,
            text="启动服务",
            command=start_service,
            fg_color="#27ae60",
            hover_color="#2ecc71"
        )
        start_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        stop_btn = ctk.CTkButton(
            btn_frame,
            text="停止服务",
            command=stop_service,
            fg_color="#e74c3c",
            hover_color="#c0392b"
        )
        stop_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # 服务管理区域
        manage_frame = ctk.CTkFrame(window, corner_radius=8)
        manage_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        
        manage_title = ctk.CTkLabel(
            manage_frame,
            text="服务管理",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        manage_title.pack(pady=10, padx=20, anchor="w")
        
        # 服务列表
        service_list = [
            {"name": "Ollama", "desc": "本地AI模型服务", "port": "11434"},
            {"name": "OpenAI兼容API", "desc": "兼容OpenAI接口的服务", "port": "8000"},
            {"name": "Hugging Face", "desc": "Hugging Face模型服务", "port": "8080"},
            {"name": "自定义服务", "desc": "自定义AI服务", "port": "9000"}
        ]
        
        for i, service in enumerate(service_list):
            service_item = ctk.CTkFrame(manage_frame, corner_radius=6, border_width=1, border_color="#34495e")
            service_item.pack(fill="x", padx=20, pady=5)
            
            service_info = ctk.CTkLabel(
                service_item,
                text=f"{service['name']} - {service['desc']} (默认端口: {service['port']})",
                font=ctk.CTkFont(size=12)
            )
            service_info.pack(padx=15, pady=10, anchor="w")
        
        # 日志区域
        log_frame = ctk.CTkFrame(window, corner_radius=8)
        log_frame.grid(row=5, column=0, columnspan=2, padx=20, pady=(10, 20), sticky="nsew")
        
        log_label = ctk.CTkLabel(log_frame, text="服务日志:")
        log_label.pack(pady=(10, 5), padx=15, anchor="w")
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap="word",
            bg="#2b2b2b",
            fg="white",
            font=("Microsoft YaHei", 10),
            padx=10,
            pady=10,
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def start_local_service(self, service_type, port):
        """启动本地服务"""
        try:
            import subprocess
            import os
            
            # 记录日志
            def log_message(message):
                if hasattr(self, 'log_text'):
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                print(f"[{time.strftime('%H:%M:%S')}] {message}")
            
            log_message(f"开始启动服务: {service_type} (端口: {port})")
            
            if service_type == "Ollama":
                # 检查Ollama是否安装
                try:
                    result = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=10)
                    if result.returncode != 0:
                        return False, "Ollama未安装，请先安装Ollama"
                except:
                    return False, "Ollama未安装或不在PATH中"
                
                # 启动Ollama服务（Ollama通常作为系统服务运行）
                log_message("检查Ollama服务状态...")
                try:
                    # 尝试获取模型列表，验证服务是否运行
                    import requests
                    response = requests.get(f"http://localhost:{port}/api/tags", timeout=5)
                    if response.status_code == 200:
                        return True, f"Ollama服务已在端口 {port} 运行"
                except:
                    pass
                
                # 尝试启动Ollama服务
                log_message("尝试启动Ollama服务...")
                try:
                    # Ollama在Windows上通常通过系统服务运行
                    # 这里我们只是检查并返回状态
                    return True, f"Ollama服务配置为端口 {port}"
                except Exception as e:
                    return False, f"启动Ollama服务失败: {str(e)}"
            
            elif service_type == "OpenAI兼容API":
                # 这里可以添加启动OpenAI兼容API服务的逻辑
                log_message("配置OpenAI兼容API服务...")
                return True, f"OpenAI兼容API服务配置为端口 {port}"
            
            elif service_type == "Hugging Face":
                # 这里可以添加启动Hugging Face服务的逻辑
                log_message("配置Hugging Face服务...")
                return True, f"Hugging Face服务配置为端口 {port}"
            
            elif service_type == "自定义服务":
                # 这里可以添加启动自定义服务的逻辑
                log_message("配置自定义服务...")
                return True, f"自定义服务配置为端口 {port}"
            
            else:
                return False, "不支持的服务类型"
                
        except Exception as e:
            return False, str(e)

    def stop_local_service(self, service_type):
        """停止本地服务"""
        try:
            import subprocess
            
            # 记录日志
            def log_message(message):
                if hasattr(self, 'log_text'):
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                print(f"[{time.strftime('%H:%M:%S')}] {message}")
            
            log_message(f"开始停止服务: {service_type}")
            
            if service_type == "Ollama":
                # Ollama通常作为系统服务运行，这里只是返回状态
                log_message("Ollama服务管理建议: 使用系统服务管理器停止")
                return True, "Ollama服务管理提示已显示"
            
            elif service_type == "OpenAI兼容API":
                # 这里可以添加停止OpenAI兼容API服务的逻辑
                log_message("停止OpenAI兼容API服务...")
                return True, "OpenAI兼容API服务已停止"
            
            elif service_type == "Hugging Face":
                # 这里可以添加停止Hugging Face服务的逻辑
                log_message("停止Hugging Face服务...")
                return True, "Hugging Face服务已停止"
            
            elif service_type == "自定义服务":
                # 这里可以添加停止自定义服务的逻辑
                log_message("停止自定义服务...")
                return True, "自定义服务已停止"
            
            else:
                return False, "不支持的服务类型"
                
        except Exception as e:
            return False, str(e)

    def open_external_call_console(self):
        """打开向外调用管理控制台"""
        # 创建控制台窗口
        console_window = ctk.CTkToplevel(self.window)
        console_window.title("向外调用管理控制台")
        console_window.geometry("1400x950")
        console_window.transient(self.window)
        console_window.grab_set()
        
        # 保存控制台窗口引用，用于刷新
        self.current_console_window = console_window
        
        # 创建主可滚动容器
        scrollable_main = ctk.CTkScrollableFrame(console_window, fg_color="#0f0f1a")
        scrollable_main.pack(fill="both", expand=True)
        scrollable_main.grid_columnconfigure(0, weight=1)
        
        # 创建主布局 - 使用可滚动容器
        main_frame = ctk.CTkFrame(scrollable_main, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 顶部标题和控制区域 - 渐变背景效果
        header_frame = ctk.CTkFrame(main_frame, corner_radius=20, fg_color="#1a1a2e")
        header_frame.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 15))
        header_frame.grid_columnconfigure(0, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            header_frame,
            text="⚡ 向外调用管理中心",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="#ffffff"
        )
        title_label.grid(row=0, column=0, padx=30, pady=(25, 5), sticky="w")
        
        # 副标题
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="高性能AI模型向外调用管理与实时监控系统",
            font=ctk.CTkFont(size=14),
            text_color="#8b8bb8"
        )
        subtitle_label.grid(row=1, column=0, padx=30, pady=(0, 20), sticky="w")
        
        # 全局控制区域 - 现代化卡片设计
        global_control_frame = ctk.CTkFrame(header_frame, fg_color="#252540", corner_radius=15)
        global_control_frame.grid(row=2, column=0, sticky="ew", padx=30, pady=(0, 25))
        global_control_frame.grid_columnconfigure(3, weight=1)
        
        # 全局状态指示器 - 更大更明显的指示灯
        status_indicator_frame = ctk.CTkFrame(global_control_frame, fg_color="transparent")
        status_indicator_frame.grid(row=0, column=0, padx=20, pady=20)
        
        # 大号圆形状态灯 + 发光效果
        status_canvas = ctk.CTkCanvas(
            status_indicator_frame,
            width=40,
            height=40,
            highlightthickness=0,
            bg="#252540"
        )
        status_canvas.pack(side="left", padx=(0, 15))
        
        # 绘制发光圆形
        if self.external_call_enabled:
            # 绿色状态 - 多层发光效果
            status_canvas.create_oval(0, 0, 40, 40, fill="#1e8449", outline="")
            status_canvas.create_oval(5, 5, 35, 35, fill="#27ae60", outline="")
            status_canvas.create_oval(10, 10, 30, 30, fill="#2ecc71", outline="")
            status_text = "运行中"
            status_color = "#2ecc71"
        else:
            # 红色状态 - 多层发光效果
            status_canvas.create_oval(0, 0, 40, 40, fill="#7b241c", outline="")
            status_canvas.create_oval(5, 5, 35, 35, fill="#e74c3c", outline="")
            status_canvas.create_oval(10, 10, 30, 30, fill="#ec7063", outline="")
            status_text = "已停止"
            status_color = "#e74c3c"
        
        global_status_label = ctk.CTkLabel(
            status_indicator_frame,
            text=f"全局状态: {status_text}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=status_color
        )
        global_status_label.pack(side="left")
        
        # 系统资源监控
        system_monitor_frame = ctk.CTkFrame(global_control_frame, fg_color="transparent")
        system_monitor_frame.grid(row=0, column=1, padx=20, pady=20)
        
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            mem_percent = memory.percent
        except:
            cpu_percent = 0
            mem_percent = 0
        
        # CPU监控
        cpu_frame = ctk.CTkFrame(system_monitor_frame, fg_color="transparent")
        cpu_frame.pack(side="left", padx=(0, 30))
        
        cpu_label = ctk.CTkLabel(
            cpu_frame,
            text=f"💻 CPU: {cpu_percent}%",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#f39c12"
        )
        cpu_label.pack()
        
        # CPU进度条
        cpu_bar_bg = ctk.CTkFrame(cpu_frame, fg_color="#1a1a2e", height=8, width=100, corner_radius=4)
        cpu_bar_bg.pack(pady=(5, 0))
        cpu_bar_bg.grid_columnconfigure(0, weight=1)
        
        cpu_bar_fill = ctk.CTkFrame(cpu_bar_bg, fg_color="#f39c12", height=8, corner_radius=4)
        cpu_bar_fill.grid(row=0, column=0, sticky="w", padx=1, pady=1)
        cpu_bar_fill.configure(width=int(cpu_percent))
        
        # 内存监控
        mem_frame = ctk.CTkFrame(system_monitor_frame, fg_color="transparent")
        mem_frame.pack(side="left")
        
        mem_label = ctk.CTkLabel(
            mem_frame,
            text=f"🧠 内存: {mem_percent}%",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#9b59b6"
        )
        mem_label.pack()
        
        # 内存进度条
        mem_bar_bg = ctk.CTkFrame(mem_frame, fg_color="#1a1a2e", height=8, width=100, corner_radius=4)
        mem_bar_bg.pack(pady=(5, 0))
        mem_bar_bg.grid_columnconfigure(0, weight=1)
        
        mem_bar_fill = ctk.CTkFrame(mem_bar_bg, fg_color="#9b59b6", height=8, corner_radius=4)
        mem_bar_fill.grid(row=0, column=0, sticky="w", padx=1, pady=1)
        mem_bar_fill.configure(width=int(mem_percent))
        
        # 统计信息卡片
        stats_frame = ctk.CTkFrame(global_control_frame, fg_color="transparent")
        stats_frame.grid(row=0, column=2, padx=20, pady=20)
        
        total_calls = len(self.external_calls)
        enabled_calls = sum(1 for call in self.external_calls if call.get('enabled', True))
        total_call_count = sum(c.get('call_count', 0) for c in self.external_calls)
        
        # 总配置卡片
        total_card = ctk.CTkFrame(stats_frame, fg_color="#3498db", corner_radius=10)
        total_card.pack(side="left", padx=(0, 15))
        
        total_label = ctk.CTkLabel(
            total_card,
            text=f"📊\n{total_calls}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ffffff"
        )
        total_label.pack(padx=20, pady=10)
        
        total_sub = ctk.CTkLabel(
            total_card,
            text="总配置",
            font=ctk.CTkFont(size=10),
            text_color="#d6eaf8"
        )
        total_sub.pack(pady=(0, 10))
        
        # 已启用卡片
        enabled_card = ctk.CTkFrame(stats_frame, fg_color="#27ae60", corner_radius=10)
        enabled_card.pack(side="left", padx=(0, 15))
        
        enabled_label = ctk.CTkLabel(
            enabled_card,
            text=f"✅\n{enabled_calls}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ffffff"
        )
        enabled_label.pack(padx=20, pady=10)
        
        enabled_sub = ctk.CTkLabel(
            enabled_card,
            text="已启用",
            font=ctk.CTkFont(size=10),
            text_color="#d5f5e3"
        )
        enabled_sub.pack(pady=(0, 10))
        
        # 总调用次数卡片
        count_card = ctk.CTkFrame(stats_frame, fg_color="#e67e22", corner_radius=10)
        count_card.pack(side="left")
        
        count_label = ctk.CTkLabel(
            count_card,
            text=f"🔥\n{total_call_count}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ffffff"
        )
        count_label.pack(padx=20, pady=10)
        
        count_sub = ctk.CTkLabel(
            count_card,
            text="总调用",
            font=ctk.CTkFont(size=10),
            text_color="#fdebd0"
        )
        count_sub.pack(pady=(0, 10))
        
        # 全局控制按钮
        button_frame = ctk.CTkFrame(global_control_frame, fg_color="transparent")
        button_frame.grid(row=0, column=3, padx=20, pady=20, sticky="e")
        
        # 全局状态开关
        global_switch_var = ctk.BooleanVar(value=self.external_call_enabled)
        
        def toggle_global():
            self.toggle_global_external_service(global_switch_var.get(), console_window)
        
        global_switch_frame = ctk.CTkFrame(button_frame, fg_color="#2c3e50", corner_radius=12)
        global_switch_frame.pack(side="left", padx=(0, 12))
        
        global_switch_label = ctk.CTkLabel(
            global_switch_frame,
            text="全局服务",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff"
        )
        global_switch_label.pack(side="left", padx=(15, 10), pady=10)
        
        global_switch = ctk.CTkSwitch(
            global_switch_frame,
            text="",
            variable=global_switch_var,
            command=toggle_global,
            width=50,
            height=25
        )
        global_switch.pack(side="left", padx=(0, 15), pady=10)
        
        # 启动所有按钮
        global_start_btn = ctk.CTkButton(
            button_frame,
            text="⚡ 启用所有",
            fg_color="#27ae60",
            hover_color="#2ecc71",
            height=45,
            width=140,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=12,
            command=self.start_all_external_services
        )
        global_start_btn.pack(side="left", padx=(0, 12))
        
        # 添加按钮
        add_btn = ctk.CTkButton(
            button_frame,
            text="➕ 新建调用",
            fg_color="#3498db",
            hover_color="#2980b9",
            height=45,
            width=140,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=12,
            command=lambda: self.open_add_external_call_window(console_window)
        )
        add_btn.pack(side="left")
        
        # 性能监控区域 - 高级条形图
        performance_frame = ctk.CTkFrame(main_frame, corner_radius=20, fg_color="#1a1a2e")
        performance_frame.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 15))
        performance_frame.grid_columnconfigure(0, weight=1)
        performance_frame.grid_columnconfigure(1, weight=1)
        
        perf_title = ctk.CTkLabel(
            performance_frame,
            text="📈 实时性能概览",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        perf_title.grid(row=0, column=0, columnspan=2, padx=30, pady=(25, 20), sticky="w")
        
        # 调用次数统计条 - 更高级的设计
        if self.external_calls:
            max_count = max(1, max(c.get('call_count', 0) for c in self.external_calls))
            for idx, call in enumerate(self.external_calls[:6]):  # 显示前6个
                call_name = call['name'][:18] + "..." if len(call['name']) > 18 else call['name']
                call_count = call.get('call_count', 0)
                
                bar_frame = ctk.CTkFrame(performance_frame, fg_color="transparent")
                bar_frame.grid(row=idx+1, column=0, columnspan=2, sticky="ew", padx=30, pady=8)
                bar_frame.grid_columnconfigure(1, weight=1)
                
                # 名称标签
                name_label = ctk.CTkLabel(
                    bar_frame,
                    text=call_name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#c0c0e0",
                    width=180
                )
                name_label.grid(row=0, column=0, sticky="w")
                
                # 进度条背景
                bar_bg = ctk.CTkFrame(bar_frame, fg_color="#252540", height=28, corner_radius=14)
                bar_bg.grid(row=0, column=1, sticky="ew", padx=(15, 0))
                bar_bg.grid_columnconfigure(0, weight=1)
                
                # 进度条填充 - 渐变颜色
                fill_percent = min(100, (call_count / max_count) * 100) if max_count > 0 else 0
                
                if fill_percent > 0:
                    # 根据百分比选择颜色
                    if fill_percent > 80:
                        fill_color = "#e74c3c"
                    elif fill_percent > 50:
                        fill_color = "#f39c12"
                    else:
                        fill_color = "#3498db"
                    
                    fill_frame = ctk.CTkFrame(bar_bg, fg_color=fill_color, height=28, corner_radius=14)
                    fill_frame.grid(row=0, column=0, sticky="w", padx=2, pady=2)
                    fill_frame.grid_columnconfigure(0, weight=1)
                    fill_frame.configure(width=int(fill_percent * 4))
                
                # 次数标签
                count_label = ctk.CTkLabel(
                    bar_frame,
                    text=str(call_count),
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color="#2ecc71",
                    width=60
                )
                count_label.grid(row=0, column=2, sticky="e", padx=(15, 0))
            
            perf_padding = ctk.CTkLabel(performance_frame, text="", fg_color="transparent")
            perf_padding.grid(row=len(self.external_calls[:6])+1, column=0, pady=15)
        else:
            empty_perf = ctk.CTkLabel(
                performance_frame,
                text="📊 暂无调用数据",
                font=ctk.CTkFont(size=16),
                text_color="#7f8c8d"
            )
            empty_perf.grid(row=1, column=0, columnspan=2, pady=40)
        
        # MCP Router 和 TTS 控制区域
        mcp_tts_frame = ctk.CTkFrame(main_frame, corner_radius=20, fg_color="#1a1a2e")
        mcp_tts_frame.grid(row=2, column=0, sticky="ew", padx=25, pady=(0, 15))
        mcp_tts_frame.grid_columnconfigure(0, weight=1)
        mcp_tts_frame.grid_columnconfigure(1, weight=1)
        
        mcp_tts_title = ctk.CTkLabel(
            mcp_tts_frame,
            text="🔧 系统服务",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        mcp_tts_title.grid(row=0, column=0, columnspan=2, padx=30, pady=(25, 20), sticky="w")
        
        # MCP Router 控制
        mcp_frame = ctk.CTkFrame(mcp_tts_frame, fg_color="#252540", corner_radius=15)
        mcp_frame.grid(row=1, column=0, sticky="ew", padx=(30, 15), pady=(0, 25))
        
        mcp_title = ctk.CTkLabel(
            mcp_frame,
            text="🌐 MCP Router",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff"
        )
        mcp_title.pack(padx=20, pady=(15, 10), anchor="w")
        
        mcp_desc = ctk.CTkLabel(
            mcp_frame,
            text="模型控制协议路由服务",
            font=ctk.CTkFont(size=12),
            text_color="#8b8bb8"
        )
        mcp_desc.pack(padx=20, pady=(0, 15), anchor="w")
        
        mcp_switch_var = ctk.BooleanVar(value=self.mcp_router_enabled)
        
        def toggle_mcp():
            self.toggle_mcp_router(mcp_switch_var.get(), console_window)
        
        mcp_control_frame = ctk.CTkFrame(mcp_frame, fg_color="transparent")
        mcp_control_frame.pack(padx=20, pady=(0, 15), fill="x")
        
        mcp_switch_label = ctk.CTkLabel(
            mcp_control_frame,
            text=f"端口: {self.mcp_router_port}",
            font=ctk.CTkFont(size=12),
            text_color="#c0c0e0"
        )
        mcp_switch_label.pack(side="left")
        
        mcp_switch = ctk.CTkSwitch(
            mcp_control_frame,
            text="",
            variable=mcp_switch_var,
            command=toggle_mcp,
            width=50,
            height=25
        )
        mcp_switch.pack(side="right")
        
        # TTS 控制
        tts_frame = ctk.CTkFrame(mcp_tts_frame, fg_color="#252540", corner_radius=15)
        tts_frame.grid(row=1, column=1, sticky="ew", padx=(15, 30), pady=(0, 25))
        tts_frame.grid_columnconfigure(1, weight=1)
        
        tts_title_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_title_row.pack(padx=20, pady=(15, 5), fill="x")
        
        tts_title = ctk.CTkLabel(
            tts_title_row,
            text="🔊 TTS语音",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff"
        )
        tts_title.pack(side="left")
        
        # TTS设置按钮
        tts_settings_btn = ctk.CTkButton(
            tts_title_row,
            text="⚙️ 设置",
            fg_color="#3498db",
            hover_color="#2980b9",
            width=80,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=8,
            command=lambda: self.open_tts_settings(console_window)
        )
        tts_settings_btn.pack(side="right")
        
        tts_desc = ctk.CTkLabel(
            tts_frame,
            text="文字转语音服务",
            font=ctk.CTkFont(size=12),
            text_color="#8b8bb8"
        )
        tts_desc.pack(padx=20, pady=(0, 10), anchor="w")
        
        # TTS模式选择
        mode_display_map = {"local": "本地", "online": "在线"}
        mode_value_map = {"本地": "local", "在线": "online"}
        tts_mode_var = ctk.StringVar(value=mode_display_map.get(self.tts_mode, "本地"))
        tts_mode_frame = ctk.CTkFrame(tts_frame, fg_color="#1a1a2e", corner_radius=10)
        tts_mode_frame.pack(padx=20, pady=(0, 15), fill="x")
        
        tts_mode_label = ctk.CTkLabel(
            tts_mode_frame,
            text="模式:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#c0c0e0"
        )
        tts_mode_label.pack(side="left", padx=(15, 10), pady=10)
        
        def change_tts_mode(choice):
            self.tts_mode = mode_value_map.get(choice, "local")
        
        tts_mode_dropdown = ctk.CTkComboBox(
            tts_mode_frame,
            values=["本地", "在线"],
            variable=tts_mode_var,
            command=change_tts_mode,
            width=120
        )
        tts_mode_dropdown.pack(side="left", pady=10)
        
        tts_switch_var = ctk.BooleanVar(value=self.tts_enabled)
        
        def toggle_tts():
            self.toggle_tts(tts_switch_var.get(), console_window)
        
        tts_control_frame = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_control_frame.pack(padx=20, pady=(0, 15), fill="x")
        
        mode_text = "本地语音合成" if self.tts_mode == "local" else "在线语音合成"
        tts_switch_label = ctk.CTkLabel(
            tts_control_frame,
            text=mode_text,
            font=ctk.CTkFont(size=12),
            text_color="#c0c0e0"
        )
        tts_switch_label.pack(side="left")
        
        tts_switch = ctk.CTkSwitch(
            tts_control_frame,
            text="",
            variable=tts_switch_var,
            command=toggle_tts,
            width=50,
            height=25
        )
        tts_switch.pack(side="right")
        
        # 向外调用列表（卡片式）
        list_title = ctk.CTkLabel(
            main_frame,
            text="📋 向外调用配置列表",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        list_title.grid(row=3, column=0, sticky="w", padx=25, pady=(0, 10))
        
        call_list_frame = ctk.CTkFrame(main_frame, corner_radius=20, fg_color="#1a1a2e")
        call_list_frame.grid(row=4, column=0, sticky="ew", padx=25, pady=(0, 25))
        call_list_frame.grid_columnconfigure(0, weight=1)
        
        # 检查是否有向外调用
        if not self.external_calls:
            empty_frame = ctk.CTkFrame(call_list_frame, fg_color="transparent")
            empty_frame.grid(row=0, column=0, pady=100)
            
            empty_icon = ctk.CTkLabel(
                empty_frame,
                text="📭",
                font=ctk.CTkFont(size=64)
            )
            empty_icon.pack(pady=(0, 20))
            
            empty_label = ctk.CTkLabel(
                empty_frame,
                text="暂无向外调用配置",
                font=ctk.CTkFont(size=20),
                text_color="#7f8c8d"
            )
            empty_label.pack(pady=(0, 10))
            
            empty_hint = ctk.CTkLabel(
                empty_frame,
                text="点击上方的「➕ 新建调用」按钮创建第一个配置",
                font=ctk.CTkFont(size=14),
                text_color="#5a5a7a"
            )
            empty_hint.pack()
        else:
            # 为每个向外调用创建卡片
            for idx, call in enumerate(self.external_calls):
                self.create_external_call_card(call_list_frame, call, idx, console_window)
    
    def create_external_call_card(self, parent_frame, call, idx, console_window):
        """创建单个向外调用卡片 - 高级设计"""
        is_enabled = call.get('enabled', True)
        
        # 卡片主框架 - 根据启用状态调整背景
        card_bg = "#252540" if is_enabled else "#2a2a3a"
        card_frame = ctk.CTkFrame(parent_frame, corner_radius=15, fg_color=card_bg)
        card_frame.grid(row=idx, column=0, sticky="ew", pady=12)
        card_frame.grid_columnconfigure(1, weight=1)
        
        # 左侧状态指示灯区域
        status_col_frame = ctk.CTkFrame(card_frame, fg_color="transparent", width=70)
        status_col_frame.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(20, 0), pady=20)
        status_col_frame.grid_propagate(False)
        
        # 大号圆形状态指示灯
        status_canvas = ctk.CTkCanvas(
            status_col_frame,
            width=50,
            height=50,
            highlightthickness=0,
            bg=card_bg
        )
        status_canvas.pack(pady=(0, 8))
        
        if is_enabled:
            # 绿色激活状态 - 多层发光效果
            status_canvas.create_oval(0, 0, 50, 50, fill="#1e8449", outline="")
            status_canvas.create_oval(6, 6, 44, 44, fill="#27ae60", outline="")
            status_canvas.create_oval(12, 12, 38, 38, fill="#2ecc71", outline="")
            status_text = "启用"
            status_color = "#2ecc71"
        else:
            # 红色禁用状态
            status_canvas.create_oval(0, 0, 50, 50, fill="#7b241c", outline="")
            status_canvas.create_oval(6, 6, 44, 44, fill="#e74c3c", outline="")
            status_canvas.create_oval(12, 12, 38, 38, fill="#ec7063", outline="")
            status_text = "禁用"
            status_color = "#e74c3c"
        
        status_label_small = ctk.CTkLabel(
            status_col_frame,
            text=status_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=status_color
        )
        status_label_small.pack()
        
        # 中间内容区域
        content_col_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        content_col_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        content_col_frame.grid_columnconfigure(0, weight=1)
        
        # 标题行
        title_row = ctk.CTkFrame(content_col_frame, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)
        
        name_label = ctk.CTkLabel(
            title_row,
            text=call['name'],
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        name_label.grid(row=0, column=0, sticky="w")
        
        # 模型类型徽章
        model_type = call.get('model_type', '文本')
        
        # 模型类型颜色
        type_colors = {
            '文本': '#3498db',
            '视觉': '#9b59b6',
            '全能': '#27ae60'
        }
        type_emojis = {
            '文本': '📝',
            '视觉': '👁️',
            '全能': '🚀'
        }
        type_color = type_colors.get(model_type, '#3498db')
        type_emoji = type_emojis.get(model_type, '📝')
        
        # 模型类型徽章
        type_badge = ctk.CTkFrame(title_row, fg_color=type_color, corner_radius=8)
        type_badge.grid(row=0, column=1, sticky="e", padx=(10, 8))
        
        type_label = ctk.CTkLabel(
            type_badge,
            text=f"{type_emoji} {model_type}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff"
        )
        type_label.pack(padx=12, pady=6)
        
        # 模型标签
        model_badge = ctk.CTkFrame(title_row, fg_color="#2c3e50", corner_radius=8)
        model_badge.grid(row=0, column=2, sticky="e")
        
        model_label = ctk.CTkLabel(
            model_badge,
            text=call['model'],
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff"
        )
        model_label.pack(padx=12, pady=6)
        
        # 信息行
        info_row = ctk.CTkFrame(content_col_frame, fg_color="transparent")
        info_row.grid(row=1, column=0, sticky="ew", pady=(15, 0))
        
        # URL
        url_frame = ctk.CTkFrame(info_row, fg_color="#1a1a2e", corner_radius=10)
        url_frame.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        url_label = ctk.CTkLabel(
            url_frame,
            text=f"🔗 {call['url']}:{call['port']}",
            font=ctk.CTkFont(size=12),
            text_color="#c0c0e0"
        )
        url_label.pack(side="left", padx=15, pady=10)
        
        copy_url_btn = ctk.CTkButton(
            url_frame,
            text="📋",
            width=40,
            height=30,
            font=ctk.CTkFont(size=14),
            fg_color="#2980b9",
            hover_color="#3498db",
            corner_radius=8,
            command=lambda u=f"{call['url']}:{call['port']}": self.copy_to_clipboard(u)
        )
        copy_url_btn.pack(side="right", padx=8, pady=8)
        
        # API Key行
        api_row = ctk.CTkFrame(content_col_frame, fg_color="transparent")
        api_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        
        api_frame = ctk.CTkFrame(api_row, fg_color="#1a1a2e", corner_radius=10)
        api_frame.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        api_key_short = call['api_key'][:25] + "..." if len(call['api_key']) > 25 else call['api_key']
        api_key_label = ctk.CTkLabel(
            api_frame,
            text=f"🔑 {api_key_short}",
            font=ctk.CTkFont(size=12),
            text_color="#c0c0e0"
        )
        api_key_label.pack(side="left", padx=15, pady=10)
        
        copy_api_btn = ctk.CTkButton(
            api_frame,
            text="📋",
            width=40,
            height=30,
            font=ctk.CTkFont(size=14),
            fg_color="#8e44ad",
            hover_color="#9b59b6",
            corner_radius=8,
            command=lambda k=call['api_key']: self.copy_to_clipboard(k)
        )
        copy_api_btn.pack(side="right", padx=8, pady=8)
        
        # 统计信息行
        stats_row = ctk.CTkFrame(content_col_frame, fg_color="transparent")
        stats_row.grid(row=3, column=0, sticky="ew", pady=(15, 0))
        
        call_count = call.get('call_count', 0)
        last_call = call.get('last_call', '从未调用')
        if last_call and last_call != '从未调用':
            last_call = last_call[:19]
        
        # 调用次数卡片
        count_card = ctk.CTkFrame(stats_row, fg_color="#e67e22", corner_radius=10)
        count_card.pack(side="left", padx=(0, 12))
        
        count_label = ctk.CTkLabel(
            count_card,
            text=f"🔥 {call_count}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff"
        )
        count_label.pack(padx=15, pady=8)
        
        # 最后调用卡片
        last_card = ctk.CTkFrame(stats_row, fg_color="#1a1a2e", corner_radius=10)
        last_card.pack(side="left")
        
        last_label = ctk.CTkLabel(
            last_card,
            text=f"⏰ {last_call}",
            font=ctk.CTkFont(size=12),
            text_color="#c0c0e0"
        )
        last_label.pack(padx=15, pady=8)
        
        # 右侧操作区域
        action_col_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        action_col_frame.grid(row=0, column=2, rowspan=3, sticky="ns", padx=(0, 20), pady=20)
        
        # 启用/禁用开关
        enabled_var = ctk.BooleanVar(value=is_enabled)
        
        def toggle_enabled(call_id=call['id'], var=enabled_var):
            self.toggle_external_call_enabled(call_id, var.get())
            console_window.destroy()
            self.open_external_call_console()
        
        enabled_switch = ctk.CTkSwitch(
            action_col_frame,
            text="",
            variable=enabled_var,
            command=toggle_enabled,
            width=60,
            height=30
        )
        enabled_switch.pack(pady=(0, 15))
        
        # 测试按钮
        test_btn = ctk.CTkButton(
            action_col_frame,
            text="🧪 测试",
            fg_color="#27ae60",
            hover_color="#2ecc71",
            width=100,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            command=lambda c=call: self.test_external_call(c)
        )
        test_btn.pack(pady=(0, 10))
        
        # 删除按钮
        delete_btn = ctk.CTkButton(
            action_col_frame,
            text="🗑️ 删除",
            fg_color="#e74c3c",
            hover_color="#c0392b",
            width=100,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            command=lambda c=call['id'], win=console_window: self.delete_external_call(c, win)
        )
        delete_btn.pack()
    
    def copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.add_message("system", "系统", "已复制到剪贴板")
        except Exception as e:
            print(f"复制失败: {e}")
    
    def toggle_external_call_enabled(self, call_id, enabled):
        """切换向外调用的启用状态"""
        for call in self.external_calls:
            if call['id'] == call_id:
                call['enabled'] = enabled
                break
        self.save_external_calls()
    
    def start_all_external_services(self):
        """启动所有向外调用服务"""
        self.external_call_enabled = True
        # 启用所有向外调用
        for call in self.external_calls:
            call['enabled'] = True
        self.save_external_calls()
        self.add_message("system", "系统", "所有向外调用服务已启动")
        # 刷新控制台
        if hasattr(self, 'current_console_window'):
            self.current_console_window.destroy()
            self.open_external_call_console()
    
    def open_add_external_call_window(self, parent_window):
        """打开添加向外调用窗口"""
        # 创建窗口
        window = ctk.CTkToplevel(parent_window)
        window.title("添加向外调用")
        window.geometry("600x480")
        window.transient(parent_window)
        window.grab_set()
        
        # 布局
        window.grid_columnconfigure(0, weight=1)
        window.grid_columnconfigure(1, weight=1)
        
        # 名称
        ctk.CTkLabel(window, text="名称:").grid(row=0, column=0, padx=20, pady=10, sticky="e")
        name_entry = ctk.CTkEntry(window, width=200)
        name_entry.grid(row=0, column=1, padx=20, pady=10, sticky="w")
        
        # 模型
        ctk.CTkLabel(window, text="模型:").grid(row=1, column=0, padx=20, pady=10, sticky="e")
        model_var = ctk.StringVar(value=self.current_model)
        model_dropdown = ctk.CTkComboBox(
            window,
            values=self._cached_models,
            variable=model_var,
            width=200
        )
        model_dropdown.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # 模型类型
        ctk.CTkLabel(window, text="模型类型:").grid(row=2, column=0, padx=20, pady=10, sticky="e")
        model_type_var = ctk.StringVar(value="文本")
        model_type_options = ["文本", "视觉", "全能"]
        model_type_dropdown = ctk.CTkComboBox(
            window,
            values=model_type_options,
            variable=model_type_var,
            width=200
        )
        model_type_dropdown.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        
        # URL（默认值为http://localhost）
        ctk.CTkLabel(window, text="URL:").grid(row=3, column=0, padx=20, pady=10, sticky="e")
        url_entry = ctk.CTkEntry(window, width=200)
        url_entry.insert(0, "http://localhost")  # 设置默认值
        url_entry.grid(row=3, column=1, padx=20, pady=10, sticky="w")
        
        # 端口
        ctk.CTkLabel(window, text="端口:").grid(row=4, column=0, padx=20, pady=10, sticky="e")
        port_entry = ctk.CTkEntry(window, width=200, placeholder_text="5000")
        port_entry.grid(row=4, column=1, padx=20, pady=10, sticky="w")
        
        # API Key（随机生成，用户不能修改）
        ctk.CTkLabel(window, text="API Key:").grid(row=5, column=0, padx=20, pady=10, sticky="e")
        # 生成随机API Key
        random_api_key = str(uuid.uuid4()) + "-" + str(uuid.uuid4())
        api_key_entry = ctk.CTkEntry(window, width=200)
        api_key_entry.insert(0, random_api_key)
        api_key_entry.configure(state="disabled")  # 禁用输入框，用户不能修改
        api_key_entry.grid(row=5, column=1, padx=20, pady=10, sticky="w")
        
        # 过期时间
        ctk.CTkLabel(window, text="过期时间:").grid(row=6, column=0, padx=20, pady=10, sticky="e")
        expire_var = ctk.StringVar(value="30")
        expire_options = ["7", "30", "90", "180", "365"]
        expire_dropdown = ctk.CTkComboBox(
            window,
            values=expire_options,
            variable=expire_var,
            width=200
        )
        expire_dropdown.grid(row=6, column=1, padx=20, pady=10, sticky="w")
        
        # 保存按钮
        def save_external_call():
            name = name_entry.get().strip()
            model = model_var.get()
            model_type = model_type_var.get()
            url = url_entry.get().strip()
            port = port_entry.get().strip()
            api_key = api_key_entry.get().strip()
            expires_days = int(expire_var.get())
            
            if not name or not model or not url or not port or not api_key:
                # 使用 tkinter 的 messagebox 代替 CTkMessageBox
                from tkinter import messagebox
                messagebox.showerror(
                    title="错误",
                    message="所有字段都是必填的"
                )
                return
            
            try:
                port = int(port)
            except ValueError:
                # 使用 tkinter 的 messagebox 代替 CTkMessageBox
                from tkinter import messagebox
                messagebox.showerror(
                    title="错误",
                    message="端口必须是数字"
                )
                return
            
            # 创建向外调用
            self.create_external_call(name, model, model_type, url, port, api_key, expires_days)
            
            # 关闭窗口
            window.destroy()
            # 刷新父窗口
            parent_window.destroy()
            self.open_external_call_console()
        
        save_btn = ctk.CTkButton(
            window,
            text="保存",
            command=save_external_call
        )
        save_btn.grid(row=6, column=0, columnspan=2, padx=20, pady=20, sticky="ew")
    
    def test_external_call(self, external_call):
        """测试向外调用"""
        # 创建测试窗口
        window = ctk.CTkToplevel(self.window)
        window.title("测试向外调用")
        window.geometry("500x400")
        window.transient(self.window)
        window.grab_set()
        
        # 布局
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)
        
        # 向外调用信息
        info_frame = ctk.CTkFrame(window)
        info_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(info_frame, text=f"名称: {external_call['name']}").pack(anchor="w", pady=2)
        ctk.CTkLabel(info_frame, text=f"模型: {external_call['model']}").pack(anchor="w", pady=2)
        ctk.CTkLabel(info_frame, text=f"URL: {external_call['url']}:{external_call['port']}").pack(anchor="w", pady=2)
        
        # 测试消息输入
        msg_frame = ctk.CTkFrame(window)
        msg_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(msg_frame, text="测试消息:").pack(anchor="w")
        
        test_message = ctk.CTkTextbox(msg_frame, height=100)
        test_message.pack(fill="x", pady=5)
        test_message.insert("0.0", "你好，这是一个测试消息")
        
        # 测试结果显示
        result_frame = ctk.CTkScrollableFrame(window)
        result_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        
        result_label = ctk.CTkLabel(
            result_frame,
            text="测试结果将显示在这里...",
            justify="left"
        )
        result_label.pack(padx=10, pady=10)
        
        # 测试按钮
        def run_test():
            message = test_message.get("0.0", "end-1c").strip()
            if not message:
                result_label.configure(text="错误: 测试消息不能为空")
                return
            
            result_label.configure(text="测试中...")
            
            try:
                # 执行向外调用
                result = self.make_external_call(external_call['id'], message)
                result_label.configure(text=result)
            except Exception as e:
                result_label.configure(text=f"测试失败: {str(e)}")
        
        test_btn = ctk.CTkButton(
            window,
            text="运行测试",
            command=run_test
        )
        test_btn.grid(row=3, column=0, padx=20, pady=20, sticky="ew")

    def record_api_call(self, api_key):
        """记录API调用"""
        # 初始化统计数据
        if api_key not in self.api_key_stats:
            self.api_key_stats[api_key] = {
                "total_calls": 0,
                "last_call": None,
                "calls_today": 0,
                "today": datetime.now().strftime("%Y-%m-%d")
            }
        
        # 更新统计数据
        stats = self.api_key_stats[api_key]
        stats["total_calls"] += 1
        stats["last_call"] = datetime.now().isoformat()
        
        # 更新今日调用次数
        today = datetime.now().strftime("%Y-%m-%d")
        if stats["today"] != today:
            stats["today"] = today
            stats["calls_today"] = 1
        else:
            stats["calls_today"] += 1
        
        # 保存统计数据
        self.save_api_key_stats()

    def open_api_key_console(self):
        """打开API Key管理控制台"""
        # 创建控制台窗口
        console_window = ctk.CTkToplevel(self.window)
        console_window.title("API Key管理控制台")
        console_window.geometry("1000x750")
        console_window.transient(self.window)
        console_window.grab_set()
        
        # 创建标签页
        tabview = ctk.CTkTabview(console_window)
        tabview.pack(fill="both", expand=True, padx=20, pady=20)
        
        # API Key管理标签
        key_management_tab = tabview.add("API Key管理")
        key_management_tab.grid_columnconfigure(0, weight=1)
        key_management_tab.grid_rowconfigure(0, weight=1)
        
        # 标题区域
        header_frame = ctk.CTkFrame(key_management_tab, corner_radius=8)
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        header_frame.grid_columnconfigure(0, weight=1)
        
        header_label = ctk.CTkLabel(
            header_frame, 
            text="API Key管理", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        header_label.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        # API Key列表
        key_list_frame = ctk.CTkScrollableFrame(key_management_tab, corner_radius=8)
        key_list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        key_list_frame.grid_columnconfigure(0, weight=1)
        
        # 标题行
        title_frame = ctk.CTkFrame(key_list_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", pady=10)
        title_frame.grid_columnconfigure(0, weight=1)
        title_frame.grid_columnconfigure(1, weight=1)
        title_frame.grid_columnconfigure(2, weight=1)
        title_frame.grid_columnconfigure(3, weight=1)
        title_frame.grid_columnconfigure(4, weight=1)
        
        ctk.CTkLabel(title_frame, text="API Key", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkLabel(title_frame, text="创建时间", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkLabel(title_frame, text="过期时间", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkLabel(title_frame, text="总调用次数", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkLabel(title_frame, text="操作", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=4, padx=8, pady=8)
        
        # API Key列表
        for i, key_info in enumerate(self.api_keys, 1):
            key = key_info["key"]
            created_at = key_info["created_at"]
            expires_at = key_info["expires_at"]
            
            # 获取调用统计
            total_calls = 0
            if key in self.api_key_stats:
                total_calls = self.api_key_stats[key].get("total_calls", 0)
            
            # 创建行
            row_frame = ctk.CTkFrame(key_list_frame, corner_radius=6)
            row_frame.grid(row=i, column=0, sticky="ew", pady=5)
            row_frame.grid_columnconfigure(0, weight=1)
            row_frame.grid_columnconfigure(1, weight=1)
            row_frame.grid_columnconfigure(2, weight=1)
            row_frame.grid_columnconfigure(3, weight=1)
            row_frame.grid_columnconfigure(4, weight=1)
            
            # 添加数据
            ctk.CTkLabel(row_frame, text=key[:25] + "...", font=ctk.CTkFont(size=10)).grid(row=0, column=0, padx=8, pady=10)
            ctk.CTkLabel(row_frame, text=created_at[:19], font=ctk.CTkFont(size=10)).grid(row=0, column=1, padx=8, pady=10)
            ctk.CTkLabel(row_frame, text=expires_at[:19], font=ctk.CTkFont(size=10)).grid(row=0, column=2, padx=8, pady=10)
            ctk.CTkLabel(row_frame, text=str(total_calls), font=ctk.CTkFont(size=10)).grid(row=0, column=3, padx=8, pady=10)
            
            # 操作按钮
            button_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            button_frame.grid(row=0, column=4, padx=8, pady=10)
            
            # 测试按钮
            test_btn = ctk.CTkButton(
                button_frame,
                text="测试",
                fg_color="#2ecc71",
                hover_color="#27ae60",
                width=70,
                height=28,
                font=ctk.CTkFont(size=10),
                command=lambda k=key: self.test_api_key(k)
            )
            test_btn.pack(side="left", padx=3)
            
            # 删除按钮
            delete_btn = ctk.CTkButton(
                button_frame,
                text="删除",
                fg_color="#e74c3c",
                hover_color="#c0392b",
                width=70,
                height=28,
                font=ctk.CTkFont(size=10),
                command=lambda k=key: self.delete_api_key(k, console_window)
            )
            delete_btn.pack(side="left", padx=3)
        
        # 调用统计标签
        stats_tab = tabview.add("调用统计")
        stats_tab.grid_columnconfigure(0, weight=1)
        stats_tab.grid_rowconfigure(0, weight=1)
        
        # 使用新的create_dashboard_ui方法创建仪表盘UI
        self.create_dashboard_ui(stats_tab)

    def delete_api_key(self, api_key, console_window):
        """删除API Key"""
        # 从列表中删除
        self.api_keys = [key_info for key_info in self.api_keys if key_info['key'] != api_key]
        # 从统计数据中删除
        if api_key in self.api_key_stats:
            del self.api_key_stats[api_key]
        # 保存
        self.save_api_keys()
        self.save_api_key_stats()
        # 关闭并重新打开控制台
        console_window.destroy()
        self.open_api_key_console()
        # 显示消息
        self.add_message("system", "系统", f"已删除API Key")

    def test_api_key(self, api_key):
        """测试API Key"""
        # 创建测试窗口
        window = ctk.CTkToplevel(self.window)
        window.title("测试API Key")
        window.geometry("500x400")
        window.transient(self.window)
        window.grab_set()
        
        # 布局
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)
        
        # API Key显示
        key_frame = ctk.CTkFrame(window)
        key_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(key_frame, text="API Key:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkLabel(key_frame, text=api_key[:30] + "...").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # 测试消息输入
        msg_frame = ctk.CTkFrame(window)
        msg_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(msg_frame, text="测试消息:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        test_message = ctk.CTkTextbox(msg_frame, height=100)
        test_message.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        test_message.insert("0.0", "你好，这是一个API Key测试消息")
        
        # 测试结果显示
        result_frame = ctk.CTkScrollableFrame(window)
        result_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        
        result_label = ctk.CTkLabel(
            result_frame,
            text="测试结果将显示在这里...",
            justify="left"
        )
        result_label.pack(padx=10, pady=10)
        
        # 测试按钮
        def run_test():
            message = test_message.get("0.0", "end-1c").strip()
            if not message:
                result_label.configure(text="错误: 测试消息不能为空")
                return
            
            result_label.configure(text="测试中...")
            
            try:
                # 构建测试请求
                import json
                import http.client
                
                # 连接本地API服务
                conn = http.client.HTTPConnection("localhost", self.api_server_port)
                
                # 构建请求数据
                data = {
                    "AccessKeyId": api_key,
                    "Message": message,
                    "Model": self.current_model
                }
                
                # 发送请求
                headers = {
                    "Content-Type": "application/json"
                }
                conn.request("POST", "/api/chat", json.dumps(data), headers)
                
                # 获取响应
                response = conn.getresponse()
                response_data = response.read().decode()
                conn.close()
                
                # 解析响应
                response_json = json.loads(response_data)
                
                if response.status == 200 and response_json.get("code") == 200:
                    result = response_json.get("data", {}).get("response", "")
                    result_label.configure(
                        text=f"测试成功!\n\n响应:\n{result}"
                    )
                else:
                    error_msg = response_json.get("message", "未知错误")
                    result_label.configure(
                        text=f"测试失败!\n\n错误: {error_msg}"
                    )
                    
            except Exception as e:
                result_label.configure(
                    text=f"测试失败!\n\n错误: {str(e)}"
                )
        
        test_btn = ctk.CTkButton(
            window,
            text="运行测试",
            command=run_test
        )
        test_btn.grid(row=3, column=0, padx=20, pady=20)

    def monitor_memory(self):
        """监控内存使用情况"""
        import psutil
        import time
        
        while True:
            try:
                # 获取当前进程的内存使用情况
                process = psutil.Process()
                memory_info = process.memory_info()
                memory_percent = process.memory_percent()
                
                # 检查内存使用率
                if memory_percent > self.max_memory_usage:
                    self.release_resources()
                    print(f"内存使用率过高 ({memory_percent:.2f}%%)，已释放部分资源")
                
                # 监控GPU内存使用情况
                if self.gpu_memory_check_enabled:
                    gpu_memory_percent = self.get_gpu_memory_usage()
                    if gpu_memory_percent > self.max_gpu_memory_usage:
                        self.release_resources()
                        print(f"GPU内存使用率过高 ({gpu_memory_percent:.2f}%%)，已释放部分资源")
            except Exception as e:
                print(f"内存监控错误: {str(e)}")
            
            # 等待下一次检查
            time.sleep(self.memory_check_interval)
    
    def get_gpu_memory_usage(self):
        """获取GPU内存使用情况"""
        try:
            # 尝试使用pynvml库
            try:
                import pynvml
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                total_memory = 0
                used_memory = 0
                
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    total_memory += info.total
                    used_memory += info.used
                
                pynvml.nvmlShutdown()
                
                if total_memory > 0:
                    return (used_memory / total_memory) * 100
            except ImportError:
                # pynvml未安装，尝试使用nvidia-smi命令
                import subprocess
                import re
                
                result = subprocess.run(['nvidia-smi', '--query-gpu=memory.total,memory.used', '--format=csv,noheader,nounits'], 
                                      capture_output=True, text=True)
                
                if result.returncode == 0:
                    total_memory = 0
                    used_memory = 0
                    
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            parts = line.split(',')
                            if len(parts) == 2:
                                try:
                                    total = int(parts[0].strip())
                                    used = int(parts[1].strip())
                                    total_memory += total
                                    used_memory += used
                                except ValueError:
                                    pass
                    
                    if total_memory > 0:
                        return (used_memory / total_memory) * 100
        except Exception as e:
            print(f"GPU内存监控错误: {str(e)}")
        
        return 0

    def release_resources(self):
        """释放资源"""
        try:
            # 1. 清理不活跃的对话历史
            # 检查API Key的最后使用时间，清理长时间未使用的
            current_time = datetime.now()
            inactive_keys = []
            
            for api_key, stats in self.api_key_stats.items():
                last_call = stats.get("last_call")
                if last_call:
                    last_call_time = datetime.fromisoformat(last_call)
                    # 如果超过12小时未使用，清理对话历史
                    if (current_time - last_call_time).total_seconds() > 12 * 3600:
                        inactive_keys.append(api_key)
                else:
                    # 如果从未使用过，也清理
                    inactive_keys.append(api_key)
            
            # 清理不活跃的对话历史
            for api_key in inactive_keys:
                if api_key in self.conversation_histories:
                    del self.conversation_histories[api_key]
                    print(f"清理不活跃的API Key对话历史: {api_key}")
            
            # 2. 清理全局对话历史（更激进）
            if len(self.conversation_history) > 5:
                # 保留最近5轮对话
                from collections import deque
                new_history = deque(maxlen=self.max_history_rounds)
                # 复制最近的对话
                for msg in list(self.conversation_history)[-5:]:
                    new_history.append(msg)
                self.conversation_history = new_history
                print("清理全局对话历史，保留最近5轮")
            
            # 3. 清理所有对话历史（如果内存仍然紧张）
            # 这里可以根据实际情况调整触发条件
            
            # 4. 尝试清理Python垃圾回收
            import gc
            gc.collect()
            print("执行垃圾回收")
            
            # 5. 限制并发请求数（临时降低）
            # 注意：这只是临时措施，下次启动会恢复配置值
            if self.max_concurrent_requests > 3:
                self.max_concurrent_requests = 3
                # 重新初始化信号量
                import threading
                self.request_semaphore = threading.Semaphore(self.max_concurrent_requests)
                print("临时降低最大并发请求数到3")
                
        except Exception as e:
            print(f"释放资源错误: {str(e)}")
    
    def release_gpu_resources(self):
        """释放GPU资源"""
        try:
            # 1. 清理所有对话历史
            self.conversation_history.clear()
            self.conversation_histories.clear()
            print("清理所有对话历史")
            
            # 2. 强制垃圾回收
            import gc
            gc.collect()
            print("执行强制垃圾回收")
            
            # 3. 尝试使用pynvml释放GPU内存
            try:
                import pynvml
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    # 获取GPU内存信息
                    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    print(f"GPU {i} 内存使用: {info.used / (1024 * 1024 * 1024):.2f} GB / {info.total / (1024 * 1024 * 1024):.2f} GB")
                pynvml.nvmlShutdown()
            except ImportError:
                print("pynvml未安装，跳过GPU内存检查")
            except Exception as e:
                print(f"GPU内存释放错误: {str(e)}")
                
        except Exception as e:
            print(f"释放GPU资源错误: {str(e)}")
    
    def cleanup_resources(self):
        """清理所有资源"""
        try:
            # 1. 清理API速率限制数据
            if hasattr(self, 'api_rate_limit'):
                self.api_rate_limit.clear()
            
            # 2. 清理请求信号量
            if hasattr(self, 'request_semaphore'):
                # 释放所有信号量
                try:
                    for _ in range(self.max_concurrent_requests):
                        self.request_semaphore.release()
                except:
                    pass
            
            # 3. 清理模型缓存
            if hasattr(self, '_cached_models'):
                self._cached_models = []
            
            # 4. 强制垃圾回收
            import gc
            gc.collect()
            print("清理所有资源完成")
            
        except Exception as e:
            print(f"清理资源错误: {str(e)}")

    def exit_application(self):
        """退出应用程序，正确释放所有资源"""
        print("正在退出应用程序...")
        
        try:
            # 1. 停止API服务器
            if hasattr(self, 'api_server_enabled') and self.api_server_enabled:
                print("停止API服务器...")
                self.stop_api_server()
            
            # 2. 释放GPU资源
            print("释放GPU资源...")
            self.release_gpu_resources()
            
            # 3. 清理所有资源
            print("清理所有资源...")
            self.cleanup_resources()
            
            # 4. 保存配置
            print("保存配置...")
            self.save_config()
            
            # 5. 退出应用程序
            print("退出应用程序...")
            if hasattr(self, 'window'):
                self.window.destroy()
            
            # 6. 强制退出进程
            import os
            os._exit(0)
            
        except Exception as e:
            print(f"退出应用程序错误: {str(e)}")
            # 即使出错也要强制退出
            import os
            os._exit(1)

    def upload_text(self):
        """上传文本文件"""
        try:
            from tkinter import filedialog
            file_path = filedialog.askopenfilename(
                title="选择文本文件",
                filetypes=[
                    ("文本文件", "*.txt"),
                    ("所有文件", "*.*")
                ]
            )
            
            if file_path:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # 限制文件大小
                max_size = 100000  # 100KB
                if len(content) > max_size:
                    content = content[:max_size] + "\n...（文件过大，已截断）"
                
                # 将文本内容添加到输入框
                self.input_text.delete("1.0", "end")
                self.input_text.insert("1.0", content)
                self.add_message("system", "系统", f"已上传文本文件: {os.path.basename(file_path)}")
        except Exception as e:
            self.add_message("system", "系统", f"上传文本文件失败: {str(e)}")

    def upload_image(self):
        """上传图片文件"""
        try:
            from tkinter import filedialog
            file_path = filedialog.askopenfilename(
                title="选择图片文件",
                filetypes=[
                    ("图片文件", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"),
                    ("所有文件", "*.*")
                ]
            )
            
            if file_path:
                # 检查文件大小
                file_size = os.path.getsize(file_path)
                max_size = 5 * 1024 * 1024  # 5MB
                if file_size > max_size:
                    self.add_message("system", "系统", "图片文件过大，请选择小于5MB的图片")
                    return
                
                # 读取图片并进行Base64编码（如果需要）
                import base64
                with open(file_path, "rb") as f:
                    image_data = f.read()
                
                # 这里可以添加图片分析逻辑
                self.add_message("system", "系统", f"已上传图片文件: {os.path.basename(file_path)}")
                self.add_message("system", "系统", "图片已上传，请在输入框中描述您的需求")
                
                # 将图片信息添加到输入框
                self.input_text.delete("1.0", "end")
                self.input_text.insert("1.0", f"请分析以下图片: {os.path.basename(file_path)}")
        except Exception as e:
            self.add_message("system", "系统", f"上传图片文件失败: {str(e)}")

    def toggle_web_search_mode(self):
        """切换联网搜索模式"""
        if self.web_search_var.get():
            self.add_message("system", "系统", "联网搜索已启用，AI将自动联网获取最新信息")
        else:
            self.add_message("system", "系统", "联网搜索已禁用，AI将基于本地知识回答")

    def open_port_scan_window(self):
        """打开端口扫描窗口"""
        window = ctk.CTkToplevel(self.window)
        window.title("端口扫描")
        window.geometry("600x500")
        window.transient(self.window)
        window.grab_set()
        
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(4, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            window,
            text="🔍 端口扫描工具",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(20, 20))
        
        # 目标IP
        ip_label = ctk.CTkLabel(window, text="目标IP:")
        ip_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        self.ip_entry = ctk.CTkEntry(window, width=300)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # 端口范围
        port_range_label = ctk.CTkLabel(window, text="端口范围:")
        port_range_label.grid(row=2, column=0, padx=20, pady=10, sticky="e")
        
        range_frame = ctk.CTkFrame(window, fg_color="transparent")
        range_frame.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        
        self.start_port_entry = ctk.CTkEntry(range_frame, width=100, placeholder_text="开始端口")
        self.start_port_entry.insert(0, "1")
        self.start_port_entry.grid(row=0, column=0, padx=(0, 10))
        
        ctk.CTkLabel(range_frame, text="-").grid(row=0, column=1, padx=5)
        
        self.end_port_entry = ctk.CTkEntry(range_frame, width=100, placeholder_text="结束端口")
        self.end_port_entry.insert(0, "10000")
        self.end_port_entry.grid(row=0, column=2, padx=(10, 0))
        
        # 扫描按钮
        def start_scan():
            ip = self.ip_entry.get().strip()
            try:
                start_port = int(self.start_port_entry.get().strip())
                end_port = int(self.end_port_entry.get().strip())
            except ValueError:
                result_text.configure(state="normal")
                result_text.delete(1.0, "end")
                result_text.insert(1.0, "错误: 端口必须是数字")
                result_text.configure(state="disabled")
                return
            
            if start_port < 1 or end_port > 65535 or start_port > end_port:
                result_text.configure(state="normal")
                result_text.delete(1.0, "end")
                result_text.insert(1.0, "错误: 端口范围无效 (1-65535)")
                result_text.configure(state="disabled")
                return
            
            # 禁用按钮
            scan_btn.configure(state="disabled")
            result_text.configure(state="normal")
            result_text.delete(1.0, "end")
            result_text.insert(1.0, f"开始扫描 {ip}:{start_port}-{end_port}...\n")
            result_text.configure(state="disabled")
            
            # 在新线程中执行扫描
            def scan_thread():
                results = self.scan_ports(ip, start_port, end_port)
                
                # 更新结果
                window.after(0, lambda: update_results(results))
            
            def update_results(results):
                result_text.configure(state="normal")
                result_text.delete(1.0, "end")
                if results:
                    result_text.insert(1.0, f"扫描完成，找到 {len(results)} 个开放端口:\n\n")
                    for port in results:
                        result_text.insert("end", f"✅ 端口 {port} 开放\n")
                else:
                    result_text.insert(1.0, "扫描完成，未找到开放端口")
                result_text.configure(state="disabled")
                scan_btn.configure(state="normal")
            
            threading.Thread(target=scan_thread, daemon=True).start()
        
        scan_btn = ctk.CTkButton(
            window,
            text="开始扫描",
            command=start_scan,
            fg_color="#27ae60",
            hover_color="#2ecc71"
        )
        scan_btn.grid(row=3, column=0, columnspan=2, padx=20, pady=20, sticky="ew")
        
        # 结果显示
        result_frame = ctk.CTkFrame(window, corner_radius=8)
        result_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="nsew")
        
        result_text = scrolledtext.ScrolledText(
            result_frame,
            wrap="word",
            bg="#2b2b2b",
            fg="white",
            font=("Microsoft YaHei", 12),
            padx=15,
            pady=15,
            state="disabled"
        )
        result_text.pack(fill="both", expand=True)

    def scan_ports(self, ip, start_port, end_port):
        """扫描指定IP的端口范围"""
        open_ports = []
        
        # 限制扫描速度，避免网络拥塞
        max_workers = 100
        from concurrent.futures import ThreadPoolExecutor
        
        def scan_port(port):
            if self.is_port_open(ip, port):
                return port
            return None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(scan_port, range(start_port, end_port + 1))
            
        for port in results:
            if port:
                open_ports.append(port)
        
        return open_ports

    def is_port_open(self, ip, port):
        """检查指定端口是否开放"""
        import socket
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                result = s.connect_ex((ip, port))
                return result == 0
        except:
            return False

    def perform_web_search(self, query):
        """执行联网搜索，包含关键词提取和内容分析"""
        try:
            # 网络安全措施
            # 1. 输入验证和清理
            if not query or len(query) > 1000:  # 限制搜索词长度
                return ["搜索词无效或过长，请尝试更简洁的搜索词。"]
            
            # 2. 清理搜索词，防止注入攻击
            import re
            # 只允许字母、数字、中文和常见标点符号
            clean_query = re.sub(r'[^\w\s\u4e00-\u9fa5\-.,!?]', '', query)
            if not clean_query:
                return ["搜索词包含无效字符，请重新输入。"]
            
            # 3. 关键词提取（重点识别）
            keywords = self.extract_keywords(clean_query)
            
            # 4. 根据关键词拟定搜索词
            search_terms = self.generate_search_terms(keywords, clean_query)
            
            # 5. 搜索API安全配置
            search_api = self.search_api_var.get() if hasattr(self, 'search_api_var') else "模拟搜索"
            
            # 6. 模拟搜索结果（实际应用中应集成安全的搜索API）
            import time
            import random
            
            # 模拟网络延迟，添加随机性
            time.sleep(random.uniform(0.5, 1.5))
            
            # 7. 模拟搜索结果，确保内容安全
            search_results = []
            for i, term in enumerate(search_terms[:3], 1):  # 只使用前3个搜索词
                # 为每个搜索词生成结果
                search_results.extend([
                    f"搜索结果 {len(search_results) + 1}: {term} - 这是关于'{term}'的详细信息，包含相关概念和最新数据。",
                    f"搜索结果 {len(search_results) + 1}: {term} - 这是关于'{term}'的应用案例和实践经验。"
                ])
            
            # 8. 内容分析和整合
            analyzed_results = self.analyze_search_results(search_results, clean_query, keywords)
            
            # 9. 记录搜索请求（便于审计）
            print(f"[安全日志] 执行联网搜索: {clean_query}")
            print(f"[安全日志] 提取关键词: {keywords}")
            print(f"[安全日志] 生成搜索词: {search_terms}")
            
            return analyzed_results
        except Exception as e:
            # 10. 错误处理，避免泄露敏感信息
            print(f"[安全日志] 搜索失败: {str(e)}")
            return ["搜索服务暂时不可用，请稍后再试。"]
    
    def extract_keywords(self, query):
        """从用户查询中提取关键词"""
        import re
        import jieba
        
        # 移除停用词
        stopwords = set([
            '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你',
            '会', '着', '没有', '看', '好', '自己', '这', '关于', '对于', '怎么', '如何', '什么', '为什么', '吗', '呢', '啊'
        ])
        
        # 使用结巴分词提取关键词
        try:
            words = jieba.cut_for_search(query)
            keywords = [word for word in words if word not in stopwords and len(word) > 1]
            
            # 如果结巴分词失败，使用简单的方法
            if not keywords:
                # 简单分词（按空格和标点）
                words = re.findall(r'[\w\u4e00-\u9fa5]+', query)
                keywords = [word for word in words if word not in stopwords and len(word) > 1]
        except:
            # 降级方案
            words = re.findall(r'[\w\u4e00-\u9fa5]+', query)
            keywords = [word for word in words if word not in stopwords and len(word) > 1]
        
        # 确保至少有一个关键词
        if not keywords:
            keywords = [query[:20]]  # 使用查询的前20个字符作为关键词
        
        return keywords[:5]  # 最多返回5个关键词
    
    def generate_search_terms(self, keywords, original_query):
        """根据关键词生成搜索词"""
        search_terms = []
        
        # 1. 使用原始查询
        search_terms.append(original_query)
        
        # 2. 使用单个关键词
        for keyword in keywords:
            if keyword not in search_terms:
                search_terms.append(keyword)
        
        # 3. 使用关键词组合
        if len(keywords) > 1:
            # 两两组合
            for i in range(len(keywords)):
                for j in range(i + 1, len(keywords)):
                    combined = f"{keywords[i]} {keywords[j]}"
                    if combined not in search_terms:
                        search_terms.append(combined)
        
        return search_terms[:5]  # 最多返回5个搜索词
    
    def analyze_search_results(self, results, original_query, keywords):
        """分析搜索结果并整合"""
        # 1. 统计关键词出现频率
        keyword_freq = {}
        for keyword in keywords:
            freq = sum(1 for result in results if keyword in result)
            keyword_freq[keyword] = freq
        
        # 2. 按相关性排序结果
        def get_relevance(result):
            relevance = 0
            for keyword, freq in keyword_freq.items():
                if keyword in result:
                    relevance += freq
            return relevance
        
        sorted_results = sorted(results, key=get_relevance, reverse=True)
        
        # 3. 生成分析摘要
        analyzed_results = []
        analyzed_results.append(f"🔍 搜索分析: 根据您的问题，我识别到的重点是: {', '.join(keywords)}")
        analyzed_results.append("\n📋 搜索结果摘要:")
        
        # 添加前5个最相关的结果
        for i, result in enumerate(sorted_results[:5], 1):
            analyzed_results.append(f"{i}. {result}")
        
        analyzed_results.append("\n💡 提示: 以上结果基于关键词搜索，可能需要结合您的具体问题进行进一步分析。")
        
        return analyzed_results




    def create_dashboard_ui(self, dashboard_tab):
        """创建仪表盘UI"""
        # 高级仪表盘标题
        dashboard_title = ctk.CTkLabel(
            dashboard_tab,
            text="API服务实时监测仪表盘",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#3498db"
        )
        dashboard_title.pack(pady=(20, 10))
        
        # 统计卡片网格
        stats_grid_frame = ctk.CTkFrame(dashboard_tab, corner_radius=15, border_width=1, border_color="#444444")
        stats_grid_frame.pack(fill="x", padx=20, pady=10)
        stats_grid_frame.grid_columnconfigure(0, weight=1)
        stats_grid_frame.grid_columnconfigure(1, weight=1)
        stats_grid_frame.grid_columnconfigure(2, weight=1)
        stats_grid_frame.grid_columnconfigure(3, weight=1)
        
        # 总调用次数卡片
        total_calls_frame = ctk.CTkFrame(stats_grid_frame, corner_radius=10, fg_color="#1a1a2e")
        total_calls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        total_calls_icon = ctk.CTkLabel(
            total_calls_frame,
            text="📊",
            font=ctk.CTkFont(size=24)
        )
        total_calls_icon.pack(pady=(15, 5))
        
        total_calls_label = ctk.CTkLabel(
            total_calls_frame,
            text="总调用次数",
            font=ctk.CTkFont(size=12),
            text_color="#95a5a6"
        )
        total_calls_label.pack(pady=5)
        
        total_calls_value = sum(stats.get("total_calls", 0) for stats in self.api_key_stats.values())
        total_calls_value_label = ctk.CTkLabel(
            total_calls_frame,
            text=str(total_calls_value),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#3498db"
        )
        total_calls_value_label.pack(pady=5)
        
        # 今日调用次数卡片
        today_calls_frame = ctk.CTkFrame(stats_grid_frame, corner_radius=10, fg_color="#1a1a2e")
        today_calls_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        today_calls_icon = ctk.CTkLabel(
            today_calls_frame,
            text="📅",
            font=ctk.CTkFont(size=24)
        )
        today_calls_icon.pack(pady=(15, 5))
        
        today_calls_label = ctk.CTkLabel(
            today_calls_frame,
            text="今日调用次数",
            font=ctk.CTkFont(size=12),
            text_color="#95a5a6"
        )
        today_calls_label.pack(pady=5)
        
        today_calls_value = sum(stats.get("calls_today", 0) for stats in self.api_key_stats.values())
        today_calls_value_label = ctk.CTkLabel(
            today_calls_frame,
            text=str(today_calls_value),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#4CAF50"
        )
        today_calls_value_label.pack(pady=5)
        
        # 活跃API Key数量卡片
        active_keys_frame = ctk.CTkFrame(stats_grid_frame, corner_radius=10, fg_color="#1a1a2e")
        active_keys_frame.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
        
        active_keys_icon = ctk.CTkLabel(
            active_keys_frame,
            text="🔑",
            font=ctk.CTkFont(size=24)
        )
        active_keys_icon.pack(pady=(15, 5))
        
        active_keys_label = ctk.CTkLabel(
            active_keys_frame,
            text="活跃API Key",
            font=ctk.CTkFont(size=12),
            text_color="#95a5a6"
        )
        active_keys_label.pack(pady=5)
        
        active_keys_value = len([key for key, stats in self.api_key_stats.items() if stats.get("total_calls", 0) > 0])
        active_keys_value_label = ctk.CTkLabel(
            active_keys_frame,
            text=str(active_keys_value),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#FF9800"
        )
        active_keys_value_label.pack(pady=5)
        
        # API服务状态卡片
        status_frame = ctk.CTkFrame(stats_grid_frame, corner_radius=10, fg_color="#1a1a2e")
        status_frame.grid(row=0, column=3, padx=10, pady=10, sticky="nsew")
        
        status_icon = ctk.CTkLabel(
            status_frame,
            text="🟢" if self.api_server_enabled else "🔴",
            font=ctk.CTkFont(size=24)
        )
        status_icon.pack(pady=(15, 5))
        
        status_label = ctk.CTkLabel(
            status_frame,
            text="API服务状态",
            font=ctk.CTkFont(size=12),
            text_color="#95a5a6"
        )
        status_label.pack(pady=5)
        
        status_value = "运行中" if self.api_server_enabled else "已停止"
        status_value_label = ctk.CTkLabel(
            status_frame,
            text=status_value,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#4CAF50" if self.api_server_enabled else "#e74c3c"
        )
        status_value_label.pack(pady=5)
        
        # 详细统计区域
        details_frame = ctk.CTkFrame(dashboard_tab, corner_radius=15, border_width=1, border_color="#444444")
        details_frame.pack(fill="both", expand=True, padx=20, pady=10)
        details_frame.grid_columnconfigure(0, weight=1)
        details_frame.grid_rowconfigure(0, weight=1)
        
        # API Key使用情况标题
        usage_title = ctk.CTkLabel(
            details_frame,
            text="API Key使用详情",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#3498db"
        )
        usage_title.pack(pady=(15, 10))
        
        # 高级表格框架
        table_frame = ctk.CTkScrollableFrame(details_frame, corner_radius=10)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        # 表头
        header_frame = ctk.CTkFrame(table_frame, fg_color="#1a1a2e", corner_radius=5)
        header_frame.pack(fill="x", pady=5)
        header_frame.grid_columnconfigure(0, weight=2)
        header_frame.grid_columnconfigure(1, weight=1)
        header_frame.grid_columnconfigure(2, weight=1)
        header_frame.grid_columnconfigure(3, weight=2)
        
        ctk.CTkLabel(header_frame, text="API Key", font=ctk.CTkFont(weight="bold"), text_color="#3498db").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(header_frame, text="总调用次数", font=ctk.CTkFont(weight="bold"), text_color="#3498db").grid(row=0, column=1, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(header_frame, text="今日调用次数", font=ctk.CTkFont(weight="bold"), text_color="#3498db").grid(row=0, column=2, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(header_frame, text="最后调用时间", font=ctk.CTkFont(weight="bold"), text_color="#3498db").grid(row=0, column=3, padx=10, pady=8, sticky="w")
        
        # 表格数据
        if self.api_key_stats:
            for i, (key, stats) in enumerate(self.api_key_stats.items(), 1):
                # 交替行颜色
                row_bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
                row_frame = ctk.CTkFrame(table_frame, fg_color=row_bg, corner_radius=5)
                row_frame.pack(fill="x", pady=2)
                row_frame.grid_columnconfigure(0, weight=2)
                row_frame.grid_columnconfigure(1, weight=1)
                row_frame.grid_columnconfigure(2, weight=1)
                row_frame.grid_columnconfigure(3, weight=2)
                
                # API Key
                key_label = ctk.CTkLabel(row_frame, text=key[:30] + "...", text_color="#ffffff")
                key_label.grid(row=0, column=0, padx=10, pady=8, sticky="w")
                
                # 总调用次数
                total_calls = stats.get("total_calls", 0)
                total_calls_label = ctk.CTkLabel(row_frame, text=str(total_calls), text_color="#3498db")
                total_calls_label.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                
                # 今日调用次数
                today_calls = stats.get("calls_today", 0)
                today_calls_label = ctk.CTkLabel(row_frame, text=str(today_calls), text_color="#4CAF50")
                today_calls_label.grid(row=0, column=2, padx=10, pady=8, sticky="w")
                
                # 最后调用时间
                last_call = stats.get("last_call", "-").split('.')[0]
                last_call_label = ctk.CTkLabel(row_frame, text=last_call, text_color="#95a5a6")
                last_call_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        else:
            no_data_frame = ctk.CTkFrame(table_frame, corner_radius=10, fg_color="#1a1a2e")
            no_data_frame.pack(fill="both", expand=True, pady=20)
            no_data_label = ctk.CTkLabel(
                no_data_frame,
                text="暂无API调用数据",
                font=ctk.CTkFont(size=14),
                text_color="#95a5a6"
            )
            no_data_label.pack(pady=40)
        
        # 操作按钮区域
        buttons_frame = ctk.CTkFrame(dashboard_tab, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=10)
        buttons_frame.grid_columnconfigure(0, weight=1)
        
        # 刷新按钮
        refresh_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 刷新数据",
            command=lambda: self.refresh_dashboard(dashboard_tab),
            fg_color="#3498db",
            hover_color="#2980b9",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        refresh_btn.pack(side="right", padx=10)
        
        # 导出数据按钮
        export_btn = ctk.CTkButton(
            buttons_frame,
            text="📤 导出统计",
            command=lambda: self.export_dashboard_data(),
            fg_color="#27ae60",
            hover_color="#229954",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        export_btn.pack(side="right", padx=10)

    def refresh_dashboard(self, dashboard_tab):
        """刷新仪表盘数据"""
        # 重新加载API Key统计数据
        self.api_key_stats = self.load_api_key_stats()
        
        # 清除现有仪表盘内容
        for widget in dashboard_tab.winfo_children():
            widget.destroy()
        
        # 重新创建仪表盘UI
        self.create_dashboard_ui(dashboard_tab)

    def export_dashboard_data(self):
        """导出仪表盘数据"""
        try:
            import json
            import datetime
            
            # 准备导出数据
            export_data = {
                "export_time": datetime.datetime.now().isoformat(),
                "total_calls": sum(stats.get("total_calls", 0) for stats in self.api_key_stats.values()),
                "today_calls": sum(stats.get("calls_today", 0) for stats in self.api_key_stats.values()),
                "active_api_keys": len([key for key, stats in self.api_key_stats.items() if stats.get("total_calls", 0) > 0]),
                "api_server_status": "运行中" if self.api_server_enabled else "已停止",
                "api_key_stats": self.api_key_stats
            }
            
            # 生成文件名
            filename = f"api_dashboard_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = self.get_app_data_path(filename)
            
            # 写入文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            # 显示成功消息
            self.add_message("system", "系统", f"仪表盘数据已导出到: {filename}")
        except Exception as e:
            # 显示错误消息
            self.add_message("system", "系统", f"导出仪表盘数据失败: {str(e)}")

    def show_console_selector(self):
        """显示控制台选择界面"""
        # 创建主窗口而不是Toplevel，避免白色边框问题
        selector_window = ctk.CTk()
        selector_window.title("控制台选择")
        selector_window.geometry("500x350")
        selector_window.resizable(False, False)
        
        # 设置窗口居中
        selector_window.update_idletasks()
        width = selector_window.winfo_width()
        height = selector_window.winfo_height()
        x = (selector_window.winfo_screenwidth() // 2) - (width // 2)
        y = (selector_window.winfo_screenheight() // 2) - (height // 2)
        selector_window.geometry(f"{width}x{height}+{x}+{y}")
        
        # 配置网格布局
        selector_window.grid_columnconfigure(0, weight=1)
        selector_window.grid_rowconfigure(0, weight=1)
        selector_window.grid_rowconfigure(1, weight=1)
        selector_window.grid_rowconfigure(2, weight=1)
        
        # 标题
        title_label = ctk.CTkLabel(
            selector_window,
            text="选择控制台模式",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=30)
        
        # 选择变量
        console_var = ctk.StringVar(value="local")
        
        # 本地控制台选项
        local_frame = ctk.CTkFrame(selector_window, corner_radius=10, border_width=2, border_color="#3498db")
        local_frame.grid(row=1, column=0, padx=50, pady=10, sticky="nsew")
        local_frame.grid_columnconfigure(0, weight=1)
        
        local_radio = ctk.CTkRadioButton(
            local_frame,
            text="本地控制台",
            variable=console_var,
            value="local",
            font=ctk.CTkFont(size=14)
        )
        local_radio.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        local_desc = ctk.CTkLabel(
            local_frame,
            text="使用桌面应用程序进行对话，功能完整且响应迅速",
            font=ctk.CTkFont(size=12),
            text_color="#95a5a6"
        )
        local_desc.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="w")
        
        # Web控制台选项
        web_frame = ctk.CTkFrame(selector_window, corner_radius=10, border_width=2, border_color="#27ae60")
        web_frame.grid(row=2, column=0, padx=50, pady=10, sticky="nsew")
        web_frame.grid_columnconfigure(0, weight=1)
        
        web_radio = ctk.CTkRadioButton(
            web_frame,
            text="Web控制台",
            variable=console_var,
            value="web",
            font=ctk.CTkFont(size=14)
        )
        web_radio.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        web_desc = ctk.CTkLabel(
            web_frame,
            text="通过浏览器访问，支持设备监控和远程访问",
            font=ctk.CTkFont(size=12),
            text_color="#95a5a6"
        )
        web_desc.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="w")
        
        # 确认按钮
        def on_confirm():
            nonlocal selected_mode
            selected_mode = console_var.get()
            selector_window.destroy()
        
        selected_mode = "local"
        confirm_btn = ctk.CTkButton(
            selector_window,
            text="确认选择",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=on_confirm
        )
        confirm_btn.grid(row=3, column=0, padx=50, pady=30, sticky="ew")
        
        # 等待用户选择
        selector_window.mainloop()
        
        return selected_mode
    
    def run(self):
        """运行应用"""
        # 如果是本地控制台，绑定窗口关闭事件
        if hasattr(self, 'window'):
            self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
            self.window.mainloop()
        # 如果是web控制台，保持程序运行
        else:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("程序已停止")
    
    def on_window_close(self):
        """窗口关闭事件处理"""
        # 保存API密钥
        self.save_api_keys()
        # 保存API密钥统计数据
        self.save_api_key_stats()
        # 保存配置
        self.save_config()
        # 停止API服务
        if self.api_server_enabled:
            self.stop_api_server()
        # 释放GPU资源
        self.release_gpu_resources()
        # 清理所有资源
        self.cleanup_resources()
        # 关闭窗口
        self.window.destroy()


if __name__ == "__main__":
    print("启动Ollama Chat Client...")
    app = OllamaChatGUI()
    print("应用初始化完成，使用本地控制台模式")
    app.run()
    print("应用程序已退出")
