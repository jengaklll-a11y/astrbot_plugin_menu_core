import threading
import json
import socket
import logging
import traceback
from astrbot.api import logger

# 尝试导入 Flask
try:
    from flask import Flask, jsonify, request, send_file
    from werkzeug.serving import make_server
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

class WebManager:
    def __init__(self, config, storage_instance):
        self.cfg = config
        self.storage = storage_instance
        self.server_thread = None
        self.server = None 
        
        # 延迟导入 renderer 以避免循环依赖或初始化过早
        self.renderer = None
        
        self.has_error = False
        self.error_msg = None
        if not HAS_FLASK: 
            self.has_error = True
            self.error_msg = "缺少 Flask 库，请 pip install flask"

    def set_renderer(self, renderer_instance):
        """注入渲染器实例"""
        self.renderer = renderer_instance

    def _create_app(self):
        app = Flask(__name__)
        # 禁用 Flask 默认日志
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        @app.route('/')
        def index():
            # 从 storage 读取分离出去的 HTML 文件
            return self.storage.get_html_content()

        @app.route('/api/config', methods=['GET', 'POST'])
        def handle_config():
            if request.method == 'GET':
                return jsonify(self.storage.load_config())
            elif request.method == 'POST':
                try:
                    self.storage.save_config(request.json)
                    return jsonify({"status": "ok"})
                except Exception as e:
                    return jsonify({"msg": str(e)}), 500

        @app.route('/api/preview', methods=['POST'])
        def preview():
            if not self.renderer:
                return jsonify({"error": "渲染器未初始化"}), 500
            try:
                # 调用渲染器生成图片
                path = self.renderer.render_sync_for_web(config_data=request.json)
                return send_file(str(path), mimetype='image/png')
            except Exception as e:
                logger.error(f"Preview Error: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500
                
        return app

    async def start(self):
        if self.server_thread and self.server_thread.is_alive():
            return "⚠️ 后台已在运行中"
        if not HAS_FLASK:
            return "❌ 缺少 Flask 库"
            
        try:
            host = self.cfg.get("web_host", "0.0.0.0")
            port = self.cfg.get("web_port", 9876)
            
            app = self._create_app()
            self.server = make_server(host, port, app)
            
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            return f"✅ 菜单编辑器已启动: http://{self._get_local_ip()}:{port}/"
        except Exception as e:
            return f"❌ 启动失败: {e}"

    async def stop(self):
        if self.server:
            self.server.shutdown()
            self.server = None

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
