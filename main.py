import asyncio
import traceback
from astrbot.api.star import Context, Star, register
from astrbot.api import event, logger
from astrbot.api.event import filter

# 引入分层模块
from . import storage
from .renderer import MenuRenderer
from .web_server import WebManager
from .utils import MENU_REGEX_PATTERN

# 修改：添加了 Repo URL 参数，使其与 metadata.yaml 保持一致
@register("astrbot_plugin_menu_core", "jengaklll-a11y", "自定义菜单(Core)", "1.0.0", "https://github.com/jengaklll-a11y/astrbot_plugin_menu_core")
class CustomMenuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.cfg = config
        
        # 1. 初始化数据层
        self.storage = storage.PluginStorage(config)
        
        # 2. 初始化 Web 管理层 (此时还不需要 Renderer)
        self.web_manager = WebManager(config, self.storage)
        
        # 3. 初始化渲染层
        self.renderer = MenuRenderer(self.storage)
        
        # 4. 依赖注入：将渲染器交给 Web 管理器 (用于预览功能)
        self.web_manager.set_renderer(self.renderer)
        
        self.admins_id = context.get_config().get("admins_id", [])
        
        # 异步初始化任务
        self._init_task = asyncio.create_task(self._async_init())

    async def _async_init(self):
        try:
            logger.info("[CustomMenuPlugin] 正在初始化资源...")
            self.storage.init_paths()
            
            # 检查 Pillow
            try: import PIL
            except ImportError: raise ImportError("缺少 Pillow 库")
            
            logger.info("✅ [CustomMenuPlugin] 初始化完成")
        except Exception as e:
            logger.error(f"❌ 初始化失败: {traceback.format_exc()}")
            self.web_manager.set_error(str(e))

    async def on_unload(self):
        await self.web_manager.stop()

    def is_admin(self, event_obj: event.AstrMessageEvent) -> bool:
        if not self.admins_id: return True
        return str(event_obj.get_sender_id()) in [str(uid) for uid in self.admins_id]

    async def _generate_menu(self, event_obj: event.AstrMessageEvent):
        # 等待初始化
        if not self._init_task.done():
            await asyncio.wait([self._init_task], timeout=5.0)

        if self.web_manager.has_error:
            yield event_obj.plain_result(f"❌ 插件错误: {self.web_manager.error_msg}")
            return

        try:
            image_path = await self.renderer.render_menu_image()
            if image_path:
                yield event_obj.image_result(str(image_path))
            else:
                yield event_obj.plain_result("⚠️ 暂无菜单配置。")
        except Exception as e:
            logger.error(f"生成菜单失败: {traceback.format_exc()}")
            yield event_obj.plain_result(f"❌ 渲染错误: {e}")

    # --- 事件处理 ---

    @filter.regex(MENU_REGEX_PATTERN)
    async def menu_regex_cmd(self, event: event.AstrMessageEvent):
        async for result in self._generate_menu(event):
            yield result

    @filter.llm_tool(name="show_graphical_menu")
    async def show_menu_tool(self, event: event.AstrMessageEvent):
        """展示图形化菜单"""
        async for result in self._generate_menu(event):
            await event.send(result)
        return "已发送菜单图片。"

    @filter.command("开启后台")
    async def start_web_cmd(self, event: event.AstrMessageEvent):
        if not self.is_admin(event):
            yield event.plain_result("❌ 权限不足")
            return
        
        yield event.plain_result("🚀 正在启动 Web 后台...")
        result_msg = await self.web_manager.start()
        yield event.plain_result(result_msg)

    @filter.command("关闭后台")
    async def stop_web_cmd(self, event: event.AstrMessageEvent):
        if not self.is_admin(event): return
        await self.web_manager.stop()
        yield event.plain_result("✅ 后台已关闭")