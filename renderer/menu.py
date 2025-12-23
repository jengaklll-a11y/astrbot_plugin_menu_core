from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pathlib import Path
import logging
from ..storage import ASSETS_DIR, FONTS_DIR, ICON_DIR, BG_DIR

logger = logging.getLogger("astrbot_plugin_custom_menu.renderer")

# --- 常量定义 ---
PADDING_X = 40
GROUP_GAP = 30
ITEM_H = 100
ITEM_GAP_X = 15
ITEM_GAP_Y = 15
TITLE_SPACE_H = 50


def load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    if not font_name:
        try:
            return ImageFont.load_default(size=int(size))
        except AttributeError:
            return ImageFont.load_default()

    font_path = FONTS_DIR / font_name
    try:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), int(size))
        return ImageFont.load_default()
    except Exception:
        try:
            return ImageFont.load_default(size=int(size))
        except AttributeError:
            return ImageFont.load_default()


def hex_to_rgb(hex_color):
    hex_color = (hex_color or "#000000").lstrip('#')
    try:
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        pass
    return 30, 30, 30


def draw_glass_rect(base_img: Image.Image, box: tuple, color_hex: str, alpha: int, radius: int, corner_r=15):
    x1, y1, x2, y2 = map(int, box)
    if x2 - x1 <= 0 or y2 - y1 <= 0: return

    if radius > 0:
        try:
            crop = base_img.crop(box).filter(ImageFilter.GaussianBlur(radius))
            base_img.paste(crop, box)
        except Exception:
            pass

    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(box, radius=corner_r, fill=hex_to_rgb(color_hex) + (int(alpha),))
    base_img.alpha_composite(overlay)


def render_item_content(overlay_img, draw, item, box, fonts_map):
    x, y, x2, y2 = box
    w, h = x2 - x, y2 - y

    icon_name = item.get("icon", "")
    text_start_x = x + 15  # 默认文字左边距

    if icon_name:
        icon_path = ICON_DIR / icon_name
        if icon_path.exists():
            try:
                with Image.open(icon_path).convert("RGBA") as icon_img:
                    # --- 核心修复 1: 精确图标缩放 ---
                    custom_icon_size = item.get("icon_size")
                    if custom_icon_size and int(custom_icon_size) > 0:
                        target_h = int(custom_icon_size)
                    else:
                        target_h = int(h * 0.6)

                    # 根据目标高度，计算等比宽度
                    aspect_ratio = icon_img.width / icon_img.height
                    target_w = int(target_h * aspect_ratio)

                    # 使用 resize 进行精确缩放
                    icon_resized = icon_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                    icon_x = x + 15  # 图标左边距
                    icon_y = y + (h - icon_resized.height) // 2

                    overlay_img.paste(icon_resized, (icon_x, icon_y), icon_resized)
                    text_start_x = icon_x + icon_resized.width + 12  # 更新文字起始 X
            except Exception as e:
                logger.error(f"加载或缩放图标失败 {icon_name}: {e}")

    name = item.get("name", "")
    desc = item.get("desc", "")
    name_font = fonts_map["name"]
    desc_font = fonts_map["desc"]
    name_color = fonts_map["name_color"]
    desc_color = fonts_map["desc_color"]
    line_spacing = 4

    # --- 核心修复 2: 支持换行并精确计算高度 ---
    try:  # Pillow >= 10.0.0, 使用更精确的 textbbox
        name_h = name_font.getbbox(name)[3] - name_font.getbbox(name)[1] if name else 0
        desc_bbox = draw.multiline_textbbox((0, 0), desc, font=desc_font, spacing=line_spacing) if desc else (0, 0, 0,
                                                                                                              0)
        desc_h = desc_bbox[3] - desc_bbox[1]
    except Exception:  # 兼容旧版 Pillow
        name_h = name_font.getsize(name)[1] if name else 0
        desc_h = 0
        if desc:
            lines = desc.split('\n')
            desc_h = sum(desc_font.getsize(line)[1] for line in lines) + (len(lines) - 1) * line_spacing

    total_text_height = name_h + (desc_h + 5 if desc else 0)  # 5是名字和描述间的间隙
    text_start_y = y + (h - total_text_height) / 2

    if name:
        draw.text((text_start_x, text_start_y), name, font=name_font, fill=name_color)
    if desc:
        # 使用 multiline_text 绘制换行文本
        draw.multiline_text(
            (text_start_x, text_start_y + name_h + 5),
            desc,
            font=desc_font,
            fill=desc_color,
            spacing=line_spacing
        )


def get_style(obj: dict, menu: dict, key: str, fallback_key: str, default=None):
    val = obj.get(key)
    if val is not None and val != "":
        return val
    return menu.get(fallback_key, default)


def render_one_menu(menu_data: dict) -> Image.Image:
    use_canvas_size = menu_data.get("use_canvas_size", False)
    canvas_w_set = int(menu_data.get("canvas_width", 1000))
    canvas_h_set = int(menu_data.get("canvas_height", 2000))
    canvas_color_hex = menu_data.get("canvas_color", "#1e1e1e")
    final_w = canvas_w_set if use_canvas_size else 1000
    columns = max(1, int(menu_data.get("layout_columns") or 3))

    # --- 布局计算 ---
    title_size = int(menu_data.get("title_size") or 60)
    header_height = 80 + title_size + 10 + int(title_size * 0.5) + 40
    current_y = header_height
    group_layout_info = []

    for group in menu_data.get("groups", []):
        is_free = group.get("free_mode", False)
        items = group.get("items", [])
        g_cols = group.get("layout_columns") or columns
        box_start_y = current_y + TITLE_SPACE_H
        content_h = 0
        if is_free:
            max_bottom = max((int(item.get("y", 0)) + int(item.get("h", 100)) for item in items), default=0)
            content_h = max(int(group.get("min_height", 100)), max_bottom + 20)
        elif items:
            rows = (len(items) + g_cols - 1) // g_cols
            content_h = rows * ITEM_H + (rows - 1) * ITEM_GAP_Y + 40

        box_rect = (PADDING_X, box_start_y, final_w - PADDING_X, box_start_y + content_h)
        group_layout_info.append(
            {"data": group, "title_y": current_y, "box_rect": box_rect, "is_free": is_free, "columns": g_cols})
        current_y = box_start_y + content_h + GROUP_GAP

    final_h = current_y if not use_canvas_size else canvas_h_set
    if not use_canvas_size and (bg_name := menu_data.get("background")):
        if (bg_path := BG_DIR / bg_name).exists():
            try:
                with Image.open(bg_path) as bg_img:
                    aspect_ratio = bg_img.height / bg_img.width
                    bg_fit_h = int(final_w * aspect_ratio)
                    final_h = max(current_y, bg_fit_h)
            except Exception as e:
                logger.error(f"计算背景图高度失败: {e}")

    # --- 绘图 ---
    base = Image.new("RGBA", (final_w, final_h), hex_to_rgb(canvas_color_hex))
    if bg_name := menu_data.get("background"):
        if (bg_path := BG_DIR / bg_name).exists():
            try:
                with Image.open(bg_path).convert("RGBA") as bg_img:
                    scale = final_w / bg_img.width
                    bg_resized = bg_img.resize((final_w, int(bg_img.height * scale)), Image.Resampling.LANCZOS)
                    base.paste(bg_resized, (0, 0), bg_resized)
            except Exception as e:
                logger.error(f"粘贴背景图失败: {e}")

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)

    # 绘制总标题
    title_font = load_font(menu_data.get("title_font", "title.ttf"), title_size)
    sub_title_font = load_font(menu_data.get("title_font", "title.ttf"), int(title_size * 0.5))
    align = menu_data.get("title_align", "center")
    title_x = {"left": PADDING_X, "right": final_w - PADDING_X, "center": final_w / 2}
    anchor = {"left": "lt", "right": "rt", "center": "mt"}
    draw_ov.text((title_x[align], 80), menu_data.get("title", ""), font=title_font,
                 fill=hex_to_rgb(menu_data.get("title_color")), anchor=anchor[align])
    draw_ov.text((title_x[align], 80 + title_size + 10), menu_data.get("sub_title", ""), font=sub_title_font,
                 fill=hex_to_rgb(menu_data.get("subtitle_color")), anchor=anchor[align])

    # 绘制分组和项目
    for g_info in group_layout_info:
        group = g_info["data"]
        box_x, box_y, box_x2, box_y2 = g_info["box_rect"]
        box_w = box_x2 - box_x

        g_bg_color = get_style(group, menu_data, 'bg_color', 'group_bg_color', '#000000')
        g_bg_alpha = get_style(group, menu_data, 'bg_alpha', 'group_bg_alpha', 50)
        g_blur = menu_data.get("group_blur_radius", 0)
        draw_glass_rect(base, g_info["box_rect"], g_bg_color, g_bg_alpha, g_blur)

        g_title_size = get_style(group, menu_data, 'title_size', 'group_title_size', 30)
        g_sub_size = get_style(group, menu_data, 'sub_size', 'group_sub_size', 18)
        g_title_font = load_font(get_style(group, menu_data, 'title_font', 'group_title_font', 'text.ttf'),
                                 g_title_size)
        g_sub_font = load_font(get_style(group, menu_data, 'sub_font', 'group_sub_font', 'text.ttf'), g_sub_size)
        g_title_color = hex_to_rgb(get_style(group, menu_data, 'title_color', 'group_title_color', '#FFFFFF'))
        g_sub_color = hex_to_rgb(get_style(group, menu_data, 'sub_color', 'group_sub_color', '#AAAAAA'))

        draw_ov.text((box_x + 10, g_info["title_y"] + 10), group.get("title", ""), font=g_title_font,
                     fill=g_title_color)
        if group.get("subtitle"):
            try:
                title_w = draw_ov.textlength(group.get("title", ""), font=g_title_font)
            except:
                title_w = g_title_font.getsize(group.get("title", ""))[0]
            draw_ov.text((box_x + 10 + title_w + 10, g_info["title_y"] + 10), group.get("subtitle"), font=g_sub_font,
                         fill=g_sub_color)

        item_grid_w = (box_w - 40 - (g_info["columns"] - 1) * ITEM_GAP_X) // g_info["columns"]
        for i, item in enumerate(group.get("items", [])):
            if g_info["is_free"]:
                ix, iy = box_x + int(item.get("x", 0)), box_y + int(item.get("y", 0))
                iw, ih = int(item.get("w", 100)), int(item.get("h", 100))
            else:
                row, col = i // g_info["columns"], i % g_info["columns"]
                ix = box_x + 20 + col * (item_grid_w + ITEM_GAP_X)
                iy = box_y + 20 + row * (ITEM_H + ITEM_GAP_Y)
                iw, ih = item_grid_w, ITEM_H

            i_bg_color = get_style(item, menu_data, 'bg_color', 'item_bg_color', '#FFFFFF')
            i_bg_alpha = get_style(item, menu_data, 'bg_alpha', 'item_bg_alpha', 20)
            i_blur = menu_data.get("item_blur_radius", 0)
            draw_glass_rect(base, (ix, iy, ix + iw, iy + ih), i_bg_color, i_bg_alpha, i_blur, corner_r=10)

            item_fonts_map = {
                "name": load_font(get_style(item, menu_data, 'name_font', 'item_name_font', 'title.ttf'),
                                  get_style(item, menu_data, 'name_size', 'item_name_size', 26)),
                "desc": load_font(get_style(item, menu_data, 'desc_font', 'item_desc_font', 'text.ttf'),
                                  get_style(item, menu_data, 'desc_size', 'item_desc_size', 16)),
                "name_color": hex_to_rgb(get_style(item, menu_data, 'name_color', 'item_name_color', '#FFFFFF')),
                "desc_color": hex_to_rgb(get_style(item, menu_data, 'desc_color', 'item_desc_color', '#AAAAAA')),
            }
            render_item_content(overlay, draw_ov, item, (ix, iy, ix + iw, iy + ih), item_fonts_map)

    return Image.alpha_composite(base, overlay)