from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pathlib import Path
import logging
from ..storage import ASSETS_DIR, FONTS_DIR

logger = logging.getLogger("astrbot_plugin_custom_menu.renderer")

# --- 常量定义 ---
DEFAULT_WIDTH = 1000
PADDING_X = 40
GROUP_GAP = 30
ITEM_H = 100
ITEM_GAP_X = 15
ITEM_GAP_Y = 15
TITLE_SPACE_H = 50


def load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """尝试加载字体，若失败则返回系统默认字体"""
    font_path = FONTS_DIR / font_name
    try:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), int(size))
        else:
            # 尝试加载备用目录或默认
            return ImageFont.load_default()
    except Exception as e:
        logger.warning(f"无法加载字体 {font_name}: {e}")
        return ImageFont.load_default()


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    try:
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except:
        pass
    return (30, 30, 30)


def draw_glass_rect(base_img: Image.Image, box: tuple, color_hex: str, alpha: int, radius: int, corner_r=15):
    x1, y1, x2, y2 = map(int, box)
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0: return

    img_w, img_h = base_img.size
    if x2 <= 0 or y2 <= 0 or x1 >= img_w or y1 >= img_h: return

    cx1, cy1 = max(0, x1), max(0, y1)
    cx2, cy2 = min(img_w, x2), min(img_h, y2)

    if radius > 0:
        try:
            crop = base_img.crop((cx1, cy1, cx2, cy2))
            crop = crop.filter(ImageFilter.GaussianBlur(radius))
            base_img.paste(crop, (cx1, cy1))
        except:
            pass

    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgb = hex_to_rgb(color_hex)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=corner_r, fill=rgb + (int(alpha),))
    base_img.alpha_composite(overlay)


def draw_text_fit(draw, text, box, font_obj, max_size, color, align='center'):
    center_x, top_y, w_box, h_box = box

    # 简单的文本缩放逻辑
    current_size = max_size
    font = font_obj

    # 如果是默认字体，不尝试重新加载
    if hasattr(font, 'path'):
        font_path = font.path
        while current_size > 10:
            length = font.getlength(text)
            if length <= w_box - 10: break
            current_size -= 2
            try:
                font = ImageFont.truetype(font_path, int(current_size))
            except:
                break

    text_w = font.getlength(text)
    if align == 'center':
        draw_x = center_x - text_w / 2
    elif align == 'left':
        draw_x = center_x - w_box / 2 + 5
    else:
        draw_x = center_x - text_w

    draw.text((draw_x, top_y), text, font=font, fill=color)


def render_one_menu(menu_data: dict) -> Image.Image:
    # 核心渲染逻辑 (保持原状，增加容错)
    use_canvas_size = menu_data.get("use_canvas_size", False)
    canvas_w_set = int(menu_data.get("canvas_width", 1000))
    canvas_h_set = int(menu_data.get("canvas_height", 2000))
    padding_margin = int(menu_data.get("canvas_padding", 40))
    canvas_color_hex = menu_data.get("canvas_color", "#1e1e1e")

    calc_width = canvas_w_set if use_canvas_size else 1000
    columns = int(menu_data.get("layout_columns") or 3)
    columns = max(1, columns)

    colors = {
        "title": menu_data.get("title_color", "#FFF"),
        "sub": menu_data.get("subtitle_color", "#DDD"),
        "group": menu_data.get("group_title_color", "#FFF"),
        "group_sub": menu_data.get("group_sub_color", "#AAA"),
        "name": menu_data.get("item_name_color", "#FFF"),
        "desc": menu_data.get("item_desc_color", "#AAA"),
    }

    sizes = {
        "title": int(menu_data.get("title_size") or 60),
        "group": int(menu_data.get("group_title_size") or 30),
        "group_sub": int(menu_data.get("group_sub_size") or 18),
        "name": int(menu_data.get("item_name_size") or 26),
        "desc": int(menu_data.get("item_desc_size") or 16)
    }

    fonts = {
        "main": load_font(menu_data.get("title_font", "title.ttf"), sizes["title"]),
        "sub": load_font(menu_data.get("title_font", "title.ttf"), int(sizes["title"] * 0.5)),
        "group": load_font(menu_data.get("group_title_font", "text.ttf"), sizes["group"]),
        "group_sub": load_font(menu_data.get("group_sub_font", "text.ttf"), sizes["group_sub"]),
        "name": load_font(menu_data.get("item_name_font", "title.ttf"), sizes["name"]),
        "desc": load_font(menu_data.get("item_desc_font", "text.ttf"), sizes["desc"])
    }

    header_height = 80 + sizes["title"] + 20 + int(sizes["title"] * 0.5) + 40
    current_y = header_height

    groups = menu_data.get("groups", []) or []
    group_layout_info = []

    for group in groups:
        is_free = group.get("free_mode", False)
        items = group.get("items", []) or []
        group_start_y = current_y
        box_start_y = group_start_y + TITLE_SPACE_H

        if is_free:
            max_item_bottom = 0
            for item in items:
                iy = int(item.get("y", 0))
                ih = int(item.get("h", 100))
                if iy + ih > max_item_bottom: max_item_bottom = iy + ih
            content_h = max(int(group.get("min_height", 100)), max_item_bottom + 20)
        else:
            if items:
                rows = (len(items) + columns - 1) // columns
                content_h = rows * ITEM_H + (rows - 1) * ITEM_GAP_Y + 40
            else:
                content_h = 20

        box_rect = (PADDING_X, box_start_y, calc_width - PADDING_X, box_start_y + content_h)
        group_layout_info.append({
            "data": group,
            "title_y": group_start_y,
            "box_rect": box_rect,
            "is_free": is_free
        })
        current_y = box_start_y + content_h + GROUP_GAP

    content_bottom = current_y + 20
    widgets = menu_data.get("custom_widgets", []) or []
    for w in widgets:
        y = int(w.get('y', 0))
        h = int(w.get('height', 0)) if w.get('type') == 'image' else int(w.get('size', 40))
        if y + h > content_bottom: content_bottom = y + h

    final_w, final_h = (calc_width, content_bottom + padding_margin)
    if use_canvas_size:
        final_w, final_h = canvas_w_set, canvas_h_set

    bg_color_rgb = hex_to_rgb(canvas_color_hex)
    base = Image.new("RGBA", (final_w, final_h), bg_color_rgb + (255,))

    # 背景绘制
    bg_name = menu_data.get("background", "")
    if bg_name:
        bg_path = ASSETS_DIR / "backgrounds" / bg_name
        if bg_path.exists():
            try:
                bg_img = Image.open(bg_path).convert("RGBA")
                fit_mode = menu_data.get("bg_fit_mode", "cover_w")
                if fit_mode == "custom":
                    t_w = int(menu_data.get("bg_custom_width", 1000))
                    t_h = int(menu_data.get("bg_custom_height", 1000))
                else:
                    scale = final_w / bg_img.width
                    t_h = int(bg_img.height * scale)
                    t_w = final_w
                bg_resized = bg_img.resize((t_w, t_h), Image.Resampling.LANCZOS)
                base.paste(bg_resized, ((final_w - t_w) // 2, 0), bg_resized)
            except:
                pass

    g_bg_color = menu_data.get("group_bg_color", "#000000")
    g_bg_alpha = int(menu_data.get("group_bg_alpha", 50))
    g_blur = int(menu_data.get("group_blur_radius", 0))

    for g_info in group_layout_info:
        draw_glass_rect(base, g_info["box_rect"], g_bg_color, g_bg_alpha, g_blur)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)

    # 绘制标题
    title_text = menu_data.get("title", "")
    sub_text = menu_data.get("sub_title", "")
    align = menu_data.get("title_align", "center")

    def get_x_by_align(text, font):
        w = font.getlength(text)
        if align == 'left': return 50
        if align == 'right': return final_w - 50 - w
        return (final_w - w) / 2

    draw_ov.text((get_x_by_align(title_text, fonts["main"]), 80), title_text, font=fonts["main"], fill=colors["title"])
    draw_ov.text((get_x_by_align(sub_text, fonts["sub"]), 80 + sizes["title"] + 10), sub_text, font=fonts["sub"],
                 fill=colors["sub"])

    # 分组项绘制
    i_bg_color = menu_data.get("item_bg_color", "#FFFFFF")
    i_bg_alpha = int(menu_data.get("item_bg_alpha", 20))
    i_blur = int(menu_data.get("item_blur_radius", 0))

    for g_info in group_layout_info:
        group = g_info["data"]
        tx = g_info["box_rect"][0] + 10
        ty = g_info["title_y"] + 10
        draw_ov.text((tx, ty), group.get("title", ""), font=fonts["group"], fill=colors["group"])

        box_x, box_y = g_info["box_rect"][0], g_info["box_rect"][1]
        box_w = g_info["box_rect"][2] - box_x
        item_grid_w = (box_w - 40 - (columns - 1) * ITEM_GAP_X) // columns

        for i, item in enumerate(group.get("items", []) or []):
            if g_info["is_free"]:
                ix, iy = box_x + int(item.get("x", 0)), box_y + int(item.get("y", 0))
                iw, ih = int(item.get("w", 100)), int(item.get("h", 100))
            else:
                row, col = i // columns, i % columns
                ix = box_x + 20 + col * (item_grid_w + ITEM_GAP_X)
                iy = box_y + 20 + row * (ITEM_H + ITEM_GAP_Y)
                iw, ih = item_grid_w, ITEM_H

            draw_glass_rect(base, (ix, iy, ix + iw, iy + ih), i_bg_color, i_bg_alpha, i_blur, corner_r=10)
            render_item_content(draw_ov, item, (ix, iy, ix + iw, iy + ih), fonts, sizes, colors)

    # Widgets
    for wid in widgets:
        try:
            wx, wy = int(wid.get("x", 0)), int(wid.get("y", 0))
            if wid.get("type") == "image":
                path = ASSETS_DIR / "widgets" / wid.get("content", "")
                if path.exists():
                    wi = Image.open(path).convert("RGBA").resize(
                        (int(wid.get("width", 100)), int(wid.get("height", 100))), Image.Resampling.LANCZOS)
                    overlay.paste(wi, (wx, wy), wi)
            else:
                wf = load_font(menu_data.get("title_font", "title.ttf"), int(wid.get("size", 40)))
                draw_ov.text((wx, wy), wid.get("text", ""), font=wf, fill=wid.get("color", "#FFF"))
        except:
            pass

    return Image.alpha_composite(base, overlay)


def render_item_content(draw, item, box, fonts, sizes, colors):
    x, y, x2, y2 = box
    w, h = x2 - x, y2 - y
    center_x = x + w / 2
    name, desc = item.get("name", ""), item.get("desc", "")
    total_h = sizes["name"] + 5 + sizes["desc"]
    start_y = y + (h - total_h) // 2
    draw_text_fit(draw, name, (center_x, start_y, w, sizes["name"]), fonts["name"], sizes["name"], colors["name"])
    draw_text_fit(draw, desc, (center_x, start_y + sizes["name"] + 5, w, sizes["desc"]), fonts["desc"], sizes["desc"],
                  colors["desc"])