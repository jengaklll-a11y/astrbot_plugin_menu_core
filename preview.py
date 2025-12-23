from pathlib import Path
from .renderer.menu import render_menu
from .storage import DATA_DIR # Fix: Use corrected storage path

PREVIEW_FILE = DATA_DIR / "preview.png" # Fix: Hardcoded path removed

def rebuild_preview():
    """触发渲染逻辑"""
    render_menu(PREVIEW_FILE)

def get_latest_preview():
    if not PREVIEW_FILE.exists():
        try:
            rebuild_preview()
        except Exception as e:
            print(f"Render Error: {e}")
            return None
    return PREVIEW_FILE