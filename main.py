import asyncio
import socket
import json
import multiprocessing
import traceback
import copy
import threading
from pathlib import Path

# AstrBot API
from astrbot.api.star import Context, Star, register
from astrbot.api import event
from astrbot.api.event import filter
from astrbot.api import logger

HAS_DEPS = False


def _get_local_ip_sync():
    """Gets local IP with a timeout to prevent long blocking"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2.0)  # Add timeout
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


async def get_local_ip():
    return await asyncio.to_thread(_get_local_ip_sync)


@register(
    "astrbot_plugin_custom_menu",
    author="shskjw",
    desc="Web可视化菜单编辑器(支持LLM智能回复)",
    version="1.5.4"
)
class CustomMenuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)
        self.cfg = config
        self.web_process = None
        self.log_queue = None
        self._log_consumer_task = None
        self.admins_id = context.get_config().get("admins_id", [])

    async def on_load(self):
        global HAS_DEPS
        try:
            from . import storage
            # Initialize storage paths explicitly
            storage.plugin_storage.init_paths()

            # Run migration in thread to avoid blocking loop
            await asyncio.to_thread(storage.plugin_storage.migrate_data)

            from .renderer.menu import render_one_menu
            HAS_DEPS = True
            logger.info("✅ 菜单插件加载完毕 (LLM Tool: show_graphical_menu 已注册)")
        except ImportError as e:
            logger.error(f"❌ 依赖缺失: {e}")
            HAS_DEPS = False

    async def on_unload(self):
        if self.web_process and self.web_process.is_alive():
            self.web_process.terminate()
            logger.info("后台 Web 服务已关闭")
        # Stop log consumer is handled implicitly as main process shuts down,
        # but cleaner to have a stop flag if this was a long running thread in plugin.
        # Since plugins unload usually ends the process or reloading, queue GC is fine.

    def is_admin(self, event: event.AstrMessageEvent) -> bool:
        if not self.admins_id: return True
        sender_id = str(event.get_sender_id())
        return sender_id in [str(uid) for uid in self.admins_id]

    def _consume_logs(self):
        """Background thread to consume logs from subprocess"""
        while self.web_process and self.web_process.is_alive():
            try:
                # Blocking get with timeout to check for process liveness
                level, msg = self.log_queue.get(timeout=1.0)
                if level == "ERROR":
                    logger.error(f"[Web] {msg}")
                elif level == "WARNING":
                    logger.warning(f"[Web] {msg}")
                else:
                    logger.info(f"[Web] {msg}")
            except:
                continue

    async def _generate_menu_chain(self, event_obj):
        if not HAS_DEPS:
            yield event_obj.plain_result("❌ 插件文件不完整，无法渲染。")
            return

        try:
            from .storage import plugin_storage
            from .renderer.menu import render_one_menu

            logger.info("正在渲染菜单...")
            root_config = plugin_storage.load_config()
            menus = root_config.get("menus", [])
            active_menus = [m for m in menus if m.get("enabled", True)]

            if not active_menus:
                yield event_obj.plain_result("⚠️ 当前没有启用的菜单，请在后台开启。")
                return

            for menu_data in active_menus:
                logger.info(f"正在渲染菜单: {menu_data.get('name')}")

                try:
                    img = await asyncio.to_thread(render_one_menu, menu_data)
                except Exception as e:
                    logger.error(f"渲染失败: {traceback.format_exc()}")
                    yield event_obj.plain_result(f"❌ 渲染错误 [{menu_data.get('name')}]: {e}")
                    continue

                temp_filename = f"temp_render_{menu_data.get('id')}.png"
                temp_path = (plugin_storage.data_dir / temp_filename).absolute()
                img.save(temp_path)

                logger.info(f"渲染完成，发送图片: {temp_path}")
                yield event_obj.image_result(str(temp_path))

        except Exception as e:
            logger.error(f"生成菜单流程异常: {e}")
            yield event_obj.plain_result(f"❌ 系统内部错误: {e}")

    @filter.command("菜单")
    async def menu_cmd(self, event: event.AstrMessageEvent):
        async for result in self._generate_menu_chain(event):
            yield result

    @filter.llm_tool(name="show_graphical_menu")
    async def show_menu_tool(self, event: event.AstrMessageEvent):
        logger.info(f"🧠 LLM 触发了菜单工具 (User: {event.get_sender_name()})")
        async for result in self._generate_menu_chain(event):
            yield result
        yield event.plain_result("已发送功能菜单图片。")

    @filter.command("开启后台")
    async def start_web_cmd(self, event: event.AstrMessageEvent):
        if not self.is_admin(event):
            yield event.plain_result("❌ 权限不足")
            return
        if not HAS_DEPS:
            yield event.plain_result("❌ 缺少依赖")
            return
        if self.web_process and self.web_process.is_alive():
            yield event.plain_result("⚠️ 后台已在运行")
            return

        yield event.plain_result("🚀 正在启动后台...")

        ctx = multiprocessing.get_context('spawn')
        status_queue = ctx.Queue()
        self.log_queue = ctx.Queue()

        try:
            # Fix: Use deepcopy instead of json load/dump
            clean_config = copy.deepcopy(self.cfg)

            # Pass absolute path string to subprocess
            from .storage import plugin_storage
            if not plugin_storage.data_dir:
                yield event.plain_result("❌ 存储路径未初始化")
                return

            data_dir_str = str(plugin_storage.data_dir.absolute())

            # Import run_server here
            from .web_server import run_server

            self.web_process = ctx.Process(
                target=run_server,
                args=(clean_config, status_queue, self.log_queue, data_dir_str),
                daemon=True
            )
            self.web_process.start()

            # Start log consumer thread
            self._log_consumer_task = threading.Thread(target=self._consume_logs, daemon=True)
            self._log_consumer_task.start()

            try:
                msg = await asyncio.to_thread(status_queue.get, True, 10)
            except:
                msg = "TIMEOUT"

            if msg == "SUCCESS":
                host_conf = self.cfg.get("web_host", "0.0.0.0")
                port = self.cfg.get("web_port", 9876)
                token = self.cfg.get("web_token", "astrbot123")
                show_ip = "127.0.0.1" if host_conf == "127.0.0.1" else await get_local_ip()
                yield event.plain_result(f"✅ 启动成功！\n地址: http://{show_ip}:{port}/\n密钥: {token}")
            else:
                if self.web_process.is_alive(): self.web_process.terminate()
                yield event.plain_result(f"❌ 启动失败: {msg}")

        except Exception as e:
            logger.error(f"启动异常: {e}")
            yield event.plain_result(f"❌ 启动异常: {e}")

    @filter.command("关闭后台")
    async def stop_web_cmd(self, event: event.AstrMessageEvent):
        if not self.is_admin(event): return
        if not self.web_process or not self.web_process.is_alive():
            yield event.plain_result("⚠️ 后台未运行")
            return
        self.web_process.terminate()
        self.web_process.join()
        self.web_process = None
        self.log_queue = None
        yield event.plain_result("✅ 后台已关闭")