import os
import sys
import asyncio
import traceback
from pathlib import Path
from multiprocessing import Queue
import uuid

# 确保能找到插件根目录以导入模块
PLUGIN_DIR = Path(__file__).parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))


def run_server(config_dict, status_queue):
    """Web 服务进程入口"""
    try:
        # 重定向输出流，防止日志丢失
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)

        from quart import Quart, request, render_template, redirect, url_for, session, jsonify, send_from_directory, \
            send_file
        from hypercorn.config import Config
        from hypercorn.asyncio import serve
        from io import BytesIO

        # 导入 storage，确保读写的是持久化目录
        try:
            from storage import load_config, save_config, get_assets_list, ASSETS_DIR, FONTS_DIR, BG_DIR, ICON_DIR, \
                IMG_DIR
            from renderer.menu import render_one_menu
        except ImportError:
            # 兼容不同运行环境的导入
            from .storage import load_config, save_config, get_assets_list, ASSETS_DIR, FONTS_DIR, BG_DIR, ICON_DIR, \
                IMG_DIR
            from .renderer.menu import render_one_menu

        app = Quart(__name__,
                    template_folder=str(PLUGIN_DIR / "templates"),
                    static_folder=str(PLUGIN_DIR / "static"))
        app.secret_key = os.urandom(24)

        # --- 中间件：鉴权 ---
        @app.before_request
        async def check_auth():
            # 放行登录页、静态资源、API资源
            allow_list = ["login", "static", "serve_bg", "serve_icon", "serve_widget", "serve_fonts"]
            if request.endpoint in allow_list: return
            if not session.get("is_admin"): return redirect(url_for("login"))

        # --- 页面路由 ---
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

        # --- API：配置管理 ---
        @app.route("/api/config", methods=["GET"])
        async def get_all_config():
            return jsonify(load_config())

        @app.route("/api/config", methods=["POST"])
        async def save_all_config():
            data = await request.get_json()
            save_config(data)  # 写入 data/plugin_data/...
            return jsonify({"status": "ok"})

        # --- API：资源列表 ---
        @app.route("/api/assets", methods=["GET"])
        async def get_assets():
            return jsonify(get_assets_list())

        @app.route("/api/fonts", methods=["GET"])
        async def get_fonts():
            # 列出持久化目录下的字体
            fonts = [f.name for f in FONTS_DIR.glob("*") if f.suffix.lower() in ['.ttf', '.otf', '.ttc']]
            return jsonify(fonts)

        # --- API：文件上传 ---
        @app.route("/api/upload", methods=["POST"])
        async def upload_asset():
            files = await request.files
            form = await request.form
            u_type = form.get("type")
            u_file = files.get("file")

            if not u_file: return jsonify({"error": "No file"}), 400

            # 生成安全文件名
            filename = f"{uuid.uuid4().hex[:8]}_{u_file.filename}"

            # 根据类型存入不同的持久化子目录
            if u_type == "background":
                target = BG_DIR / filename
            elif u_type == "icon":
                target = ICON_DIR / filename
            elif u_type == "widget_img":
                target = IMG_DIR / filename
            elif u_type == "font":
                target = FONTS_DIR / filename
            else:
                return jsonify({"error": "Unknown type"}), 400

            await u_file.save(target)
            return jsonify({"status": "ok", "filename": filename})

        # --- API：导出/预览图片 ---
        @app.route("/api/export_image", methods=["POST"])
        async def export_image():
            menu_data = await request.get_json()
            try:
                # 调用后端渲染器生成图片流
                img = await asyncio.to_thread(render_one_menu, menu_data)
                byte_io = BytesIO()
                img.save(byte_io, 'PNG')
                byte_io.seek(0)
                return await send_file(byte_io, mimetype='image/png', as_attachment=True,
                                       attachment_filename=f"{menu_data.get('name', 'menu')}.png")
            except Exception as e:
                print(f"Web预览渲染失败: {e}")
                traceback.print_exc()
                return jsonify({"error": str(e)}), 500

        # --- 静态资源服务 (指向持久化目录) ---
        @app.route("/raw_assets/backgrounds/<path:path>")
        async def serve_bg(path):
            return await send_from_directory(BG_DIR, path)

        @app.route("/raw_assets/icons/<path:path>")
        async def serve_icon(path):
            return await send_from_directory(ICON_DIR, path)

        @app.route("/raw_assets/widgets/<path:path>")
        async def serve_widget(path):
            return await send_from_directory(IMG_DIR, path)

        @app.route("/fonts/<path:path>")
        async def serve_fonts(path):
            return await send_from_directory(FONTS_DIR, path)

        # --- 启动服务 ---
        async def start_async():
            port = int(config_dict.get("web_port", 9876))
            host = config_dict.get("web_host", "0.0.0.0")

            cfg = Config()
            cfg.bind = [f"{host}:{port}"]
            cfg.graceful_timeout = 2

            print(f"✅ [Web进程] 启动监听: {host}:{port}")
            status_queue.put("SUCCESS")
            await serve(app, cfg)

        asyncio.run(start_async())

    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"❌ [Web进程崩溃] {err_msg}", file=sys.stderr)
        status_queue.put(f"ERROR: {str(e)}")