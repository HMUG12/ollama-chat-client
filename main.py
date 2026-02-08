import customtkinter as ctk
import threading
import json
import time
from tkinter import scrolledtext
import requests
from typing import List, Dict


class OllamaChatGUI:
    def __init__(self):
        # 初始化窗口
        ctk.set_appearance_mode("dark")  # 深色模式
        ctk.set_default_color_theme("blue")  # 蓝色主题

        self.window = ctk.CTk()
        self.window.title("Ollama Chat Client - 本地AI助手")
        self.window.geometry("1000x700")

        # Ollama配置
        self.base_url = "http://localhost:11434"  # Ollama默认地址
        self.current_model = self.get_available_models()[0] if self.get_available_models() else ""

        # 对话历史
        self.conversation_history: List[Dict] = []

        self.setup_ui()
        self.test_connection()

    def setup_ui(self):
        """设置用户界面"""
        # 创建网格布局
        self.window.grid_columnconfigure(1, weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        # 左侧边栏
        sidebar_frame = ctk.CTkFrame(self.window, width=200, corner_radius=0)
        sidebar_frame.grid(row=0, column=0, sticky="nsew")
        sidebar_frame.grid_rowconfigure(4, weight=1)

        # 标题
        title_label = ctk.CTkLabel(
            sidebar_frame,
            text="Ollama Chat",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=20)

        # 模型选择
        model_label = ctk.CTkLabel(sidebar_frame, text="选择模型:")
        model_label.grid(row=1, column=0, padx=20, pady=(10, 0))

        self.model_var = ctk.StringVar(value=self.current_model)
        self.model_dropdown = ctk.CTkComboBox(
            sidebar_frame,
            values=self.get_available_models(),
            variable=self.model_var,
            command=self.change_model
        )
        self.model_dropdown.grid(row=2, column=0, padx=20, pady=(0, 10))

        # 刷新模型按钮
        refresh_btn = ctk.CTkButton(
            sidebar_frame,
            text="刷新模型列表",
            command=self.refresh_models
        )
        refresh_btn.grid(row=3, column=0, padx=20, pady=10)

        # 清除对话按钮
        clear_btn = ctk.CTkButton(
            sidebar_frame,
            text="清除对话",
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
            command=self.clear_conversation
        )
        clear_btn.grid(row=4, column=0, padx=20, pady=10)

        # 退出按钮
        exit_btn = ctk.CTkButton(
            sidebar_frame,
            text="退出",
            command=self.window.quit,
            fg_color="#FF5555",
            hover_color="#FF3333"
        )
        exit_btn.grid(row=6, column=0, padx=20, pady=20)

        # 状态标签
        self.status_label = ctk.CTkLabel(sidebar_frame, text="状态: 等待连接")
        self.status_label.grid(row=5, column=0, padx=20, pady=20)

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

        # 底部输入区域
        bottom_frame = ctk.CTkFrame(main_frame)
        bottom_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom_frame.grid_columnconfigure(0, weight=1)

        # 输入框
        self.input_text = ctk.CTkTextbox(bottom_frame, height=80)
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # 发送按钮
        send_btn = ctk.CTkButton(
            bottom_frame,
            text="发送",
            width=100,
            command=self.send_message
        )
        send_btn.grid(row=0, column=1)

        # 绑定回车键发送
        self.input_text.bind("<Return>", lambda e: "break")  # 禁用默认回车行为
        self.input_text.bind("<Control-Return>", self.send_message_event)

    def get_available_models(self):
        """获取可用的Ollama模型"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [model["name"] for model in models]
        except:
            pass
        return ["llama2", "mistral", "codellama"]  # 默认模型列表

    def test_connection(self):
        """测试Ollama连接"""

        def test():
            try:
                response = requests.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    self.status_label.configure(
                        text="状态: 已连接 ✅",
                        text_color="lightgreen"
                    )
                    self.add_message("system", "系统", "已连接到Ollama，可以开始对话了！")
                else:
                    self.status_label.configure(
                        text="状态: 连接失败 ❌",
                        text_color="red"
                    )
            except Exception as e:
                self.status_label.configure(
                    text="状态: Ollama未运行 ❌",
                    text_color="red"
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
        self.model_dropdown.configure(values=models)
        if models:
            self.model_dropdown.set(models[0])
            self.current_model = models[0]

    def clear_conversation(self):
        """清除对话历史"""
        self.conversation_history = []
        self.conversation_text.configure(state="normal")
        self.conversation_text.delete(1.0, "end")
        self.conversation_text.configure(state="disabled")
        self.add_message("system", "系统", "对话历史已清除")

    def send_message_event(self, event=None):
        """事件绑定的发送消息"""
        self.send_message()
        return "break"  # 阻止默认行为

    def send_message(self):
        """发送消息"""
        message = self.input_text.get("1.0", "end-1c").strip()
        if not message or not self.current_model:
            return

        # 清空输入框
        self.input_text.delete("1.0", "end")

        # 显示用户消息
        self.add_message("user", "你", message)

        # 发送到Ollama
        threading.Thread(target=self.get_ai_response, args=(message,), daemon=True).start()

    def get_ai_response(self, message):
        """获取AI响应"""
        try:
            # 准备请求数据
            data = {
                "model": self.current_model,
                "prompt": message,
                "stream": False,
                "context": self.get_context()
            }

            # 发送请求
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=data,
                timeout=300
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result.get("response", "")

                # 保存到历史
                self.conversation_history.append({
                    "role": "user",
                    "content": message
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": ai_response
                })

                # 显示AI响应
                self.add_message("assistant", "AI", ai_response)
            else:
                self.add_message("system", "系统", f"错误: {response.status_code}")

        except Exception as e:
            self.add_message("system", "系统", f"请求失败: {str(e)}")

    def get_context(self):
        """获取对话上下文（简化版本）"""
        # 在实际使用中，这里应该返回对话历史
        # 为了简化，返回空列表
        return []

    def add_message(self, sender, name, message):
        """添加消息到对话框"""
        self.window.after(0, self._add_message_gui, sender, name, message)

    def _add_message_gui(self, sender, name, message):
        """在GUI线程中添加消息"""
        self.conversation_text.configure(state="normal")

        # 添加时间戳
        timestamp = time.strftime("%H:%M:%S")

        # 设置颜色和格式
        if sender == "user":
            tag_color = "#4CAF50"  # 绿色
            prefix = "👤"
        elif sender == "assistant":
            tag_color = "#2196F3"  # 蓝色
            prefix = "🤖"
        else:
            tag_color = "#FF9800"  # 橙色
            prefix = "⚙️"

        # 插入消息
        self.conversation_text.insert("end", f"\n[{timestamp}] {prefix} {name}:\n", f"timestamp_{sender}")
        self.conversation_text.insert("end", f"{message}\n", f"message_{sender}")
        self.conversation_text.insert("end", "-" * 50 + "\n")

        # 滚动到底部
        self.conversation_text.see("end")
        self.conversation_text.configure(state="disabled")

        # 配置标签
        self.conversation_text.tag_config(f"timestamp_{sender}", foreground=tag_color, font=("Arial", 10, "bold"))
        self.conversation_text.tag_config(f"message_{sender}", foreground="white", font=("Microsoft YaHei", 11))

    def run(self):
        """运行应用"""
        self.window.mainloop()


if __name__ == "__main__":
    app = OllamaChatGUI()
    app.run()