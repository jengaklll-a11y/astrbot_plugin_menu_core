import json
import os
from pathlib import Path
from astrbot.api import logger

class PluginStorage:
    def __init__(self, config):
        # 1. 定位插件根目录 (即 storage.py 所在的目录)
        self.plugin_root = Path(__file__).resolve().parent
        
        # 2. 定位 Bot 数据目录
        # 使用 metadata.yaml 中的 name 作为目录名，确保一致性
        self.bot_data_root = self.plugin_root.parent.parent / "data" / "plugins" / "astrbot_plugin_menu_core"
        
        # 3. 配置文件路径
        self.config_file = self.bot_data_root / "menu_config.json"
        
        # 4. 静态资源路径 (指向插件目录下的 templates)
        self.template_dir = self.plugin_root / "templates"
        self.html_file = self.template_dir / "index.html"

        # 5. 字体资源目录 (放在 data 目录下，避免更新插件丢失)
        self.font_dir = self.bot_data_root / "fonts"

        logger.info(f"[Menu] 数据目录: {self.bot_data_root}")
        logger.info(f"[Menu] 模板文件: {self.html_file}")

        # 【修改点】补全了 design 字段的默认值
        self.default_config = {
            "title": "我的机器人菜单",
            "subtitle": "发送指令使用功能",
            "design": {
                "layout_columns": 2,
                "title_align": "center",
                "theme": "dark"
            },
            "menus": [
                {"id": 1, "name": "帮助", "desc": "查看使用说明", "enabled": True},
                {"id": 2, "name": "关于", "desc": "关于作者", "enabled": True}
            ]
        }

    def init_paths(self):
        """初始化必要的文件夹"""
        # 创建数据目录
        if not self.bot_data_root.exists():
            self.bot_data_root.mkdir(parents=True, exist_ok=True)
        
        # 创建字体目录
        if not self.font_dir.exists():
            self.font_dir.mkdir(parents=True, exist_ok=True)

        # 初始化配置
        if not self.config_file.exists():
            self.save_config(self.default_config)

    def load_config(self) -> dict:
        if not self.config_file.exists():
            return self.default_config
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 简单的合并策略：如果读取的配置缺字段，尽量用默认补全（可选）
                if "design" not in data:
                    data["design"] = self.default_config["design"]
                return data
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self.default_config

    def save_config(self, data: dict):
        if not self.bot_data_root.exists():
            self.bot_data_root.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_html_content(self) -> str:
        """读取 HTML 模板内容"""
        if not self.html_file.exists():
            return "<h1>Error: Template file not found via storage path.</h1>"
        with open(self.html_file, 'r', encoding='utf-8') as f:
            return f.read()
