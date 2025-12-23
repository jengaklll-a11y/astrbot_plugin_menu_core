import os
import sys
import asyncio
import traceback
from pathlib import Path
from multiprocessing import Queue
import uuid
import sys
from types import ModuleType

# 确保能找到插件根目录以导入模块
PLUGIN_DIR = Path(__file__).parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))


# --- Queue Logging Adapter ---
class QueueLogger:
    """Redirects logger calls to the multiprocessing queue."""

    def __init__(self, queue):
        self.queue = queue

    def info(self, msg, *args, **kwargs):
        self.queue.put(("INFO", str(msg)))

    def error(self, msg, *args, **kwargs):
        self.queue.put(("ERROR", str(msg)))

    def warning(self, msg, *args, **kwargs):
        self.queue.put(("WARNING", str(msg)))

    def debug(self, msg, *args, **kwargs):
        pass  # Ignore debug in production


def mock_astrbot_logger(queue):
    """
    Mock astrbot.api.logger using sys.modules injection.
    This allows renderer.menu to import astrbot.api.logger seamlessly.
    """
    if "astrbot.api" not in sys.modules:
        m = ModuleType("astrbot.api")
        m.logger = QueueLogger(queue)
        sys.modules["astrbot.api"] = m
        # Also mock submodules if necessary
        import astrbot.api
        astrbot.api.logger = m.logger


def run_server(config_dict, status_queue, log_queue, data_dir=None):
    """Web 服务进程入口"""
    # 1. Setup Mock Logger FIRST
    mock_astrbot_logger(log_queue)

    try:
        # Redirect std streams just in case
        # sys.stdout = ... (Optionally redirect stdout to queue too, but explicit logging is better)

        from quart import Quart, request, render_template, redirect, url_for, session, jsonify, send_from_directory, \
            send_file
        from hypercorn.config import Config
        from hypercorn.asyncio import serve
        from io import BytesIO

        # 2. Initialize storage with explicit path
        try:
            import storage
            if data_dir:
                storage.plugin_storage.init_paths(data_dir)

            from storage import plugin_storage
            from renderer.menu import render_one_menu
        except ImportError:
            from . import storage
            if data_dir:
                storage.plugin_storage.init_paths(data_dir)
            from .storage import plugin_storage
            from .renderer.menu import render_one_menu

        app = Quart(__name__,
                    template_folder=str(PLUGIN_DIR / "templates"),
                    static_folder=str(PLUGIN_DIR / "static"))
        app.secret_key = os.urandom(24)

        @app.before_request
        async def check_auth():
            allow_list = ["login", "static", "serve_bg", "serve_icon", "serve_widget", "serve_fonts"]
            if request.endpoint in allow_list: return
            if not session.get("is_admin"): return redirect(url_for("login"))

        @app.route("/login", methods=["GET", "POST"])
        async def login():
            error = None
            if request.method == "POST":
                form = await request.form
                if form.get("token") == config_dict.get("web_token"):
                    session["is_admin"] = True
                    return redirect(url_for("index"))
                error = "密钥错误"
            return await render_template("login.html", error=error)

        @app.route("/")
        async def index():
            return await render_template("index.html")

        @app.route("/api/config", methods=["GET"])
        async def get_all_config():
            return jsonify(plugin_storage.load_config())

        @app.route("/api/config", methods=["POST"])
        async def save_all_config():
            data = await request.get_json()
            plugin_storage.save_config(data)
            return jsonify({"status": "ok"})

        @app.route("/api/assets", methods=["GET"])
        async def get_assets():
            return jsonify(plugin_storage.get_assets_list())

        @app.route("/api/fonts", methods=["GET"])
        async def get_fonts():
            if not plugin_storage.fonts_dir: return jsonify([])
            fonts = [f.name for f in plugin_storage.fonts_dir.glob("*") if f.suffix.lower() in ['.ttf', '.otf', '.ttc']]
            return jsonify(fonts)

        @app.route("/api/upload", methods=["POST"])
        async def upload_asset():
            files = await request.files
            form = await request.form
            u_type = form.get("type")
            u_file = files.get("file")

            if not u_file: return jsonify({"error": "No file"}), 400

            filename = f"{uuid.uuid4().hex[:8]}_{u_file.filename}"
            target = None

            if u_type == "background":
                target = plugin_storage.bg_dir / filename
            elif u_type == "icon":
                target = plugin_storage.icon_dir / filename
            elif u_type == "widget_img":
                target = plugin_storage.img_dir / filename
            elif u_type == "font":
                target = plugin_storage.fonts_dir / filename

            if target:
                await u_file.save(target)
                return jsonify({"status": "ok", "filename": filename})
            return jsonify({"error": "Unknown type"}), 400

        @app.route("/api/export_image", methods=["POST"])
        async def export_image():
            menu_data = await request.get_json()
            try:
                img = await asyncio.to_thread(render_one_menu, menu_data)
                byte_io = BytesIO()
                img.save(byte_io, 'PNG')
                byte_io.seek(0)
                return await send_file(byte_io, mimetype='image/png', as_attachment=True,
                                       attachment_filename=f"{menu_data.get('name', 'menu')}.png")
            except Exception as e:
                log_queue.put(("ERROR", f"Render Failed: {e}"))
                return jsonify({"error": str(e)}), 500

        @app.route("/raw_assets/backgrounds/<path:path>")
        async def serve_bg(path):
            return await send_from_directory(plugin_storage.bg_dir, path)

        @app.route("/raw_assets/icons/<path:path>")
        async def serve_icon(path):
            return await send_from_directory(plugin_storage.icon_dir, path)

        @app.route("/raw_assets/widgets/<path:path>")
        async def serve_widget(path):
            return await send_from_directory(plugin_storage.img_dir, path)

        @app.route("/fonts/<path:path>")
        async def serve_fonts(path):
            return await send_from_directory(plugin_storage.fonts_dir, path)

        async def start_async():
            port = int(config_dict.get("web_port", 9876))
            host = config_dict.get("web_host", "0.0.0.0")
            cfg = Config()
            cfg.bind = [f"{host}:{port}"]
            cfg.graceful_timeout = 2

            log_queue.put(("INFO", f"Web Interface Started: {host}:{port}"))
            status_queue.put("SUCCESS")
            await serve(app, cfg)

        asyncio.run(start_async())

    except Exception as e:
        err_msg = traceback.format_exc()
        # Use queue instead of stderr/print
        log_queue.put(("ERROR", f"Web Process Crash: {err_msg}"))
        status_queue.put(f"ERROR: {str(e)}")