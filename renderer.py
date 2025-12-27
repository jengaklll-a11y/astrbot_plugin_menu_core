import asyncio
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random
import math
import urllib.request
import traceback

class MenuRenderer:
    def __init__(self, storage_instance):
        self.storage = storage_instance
        self.font_dir = self.storage.font_dir
        self.fonts = {
            "heavy":   self.font_dir / "font_heavy.otf",
            "bold":    self.font_dir / "font_bold.otf",
            "medium":  self.font_dir / "font_medium.otf",
            "regular": self.font_dir / "font_regular.otf"
        }
        self.urls = {
            "heavy":   "https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Heavy.otf",
            "bold":    "https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf",
            "medium":  "https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Medium.otf",
            "regular": "https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Regular.otf"
        }
        self.mirror_base = "https://ghproxy.net/"

    async def render_menu_image(self) -> Path:
        if not all(path.exists() for path in self.fonts.values()):
            await self._download_font_async()
        return await asyncio.to_thread(self._render_logic)

    def render_sync_for_web(self, config_data) -> Path:
        return self._render_logic(config_data)

    async def _download_font_async(self):
        await asyncio.to_thread(self._ensure_font_exists_sync)

    def _ensure_font_exists_sync(self):
        if not self.font_dir.exists(): 
            self.font_dir.mkdir(parents=True, exist_ok=True)
        for style, path in self.fonts.items():
            if not path.exists():
                try: urllib.request.urlretrieve(self.mirror_base + self.urls[style], path)
                except: pass

    def _get_font(self, size, weight="regular"):
        target_path = self.fonts.get(weight, self.fonts["regular"])
        if target_path.exists():
            return ImageFont.truetype(str(target_path), int(size))
        return ImageFont.load_default()

    def _draw_text_centered(self, draw, text, font, center_y, width, align='left', color=(255,255,255), padding=90):
        try: text_len = draw.textlength(text, font=font)
        except: text_len = font.getlength(text)
        
        if align == 'center': x = width / 2; anchor = 'mm'
        elif align == 'right': x = width - padding; anchor = 'rm'
        else: x = padding; anchor = 'lm'
        
        draw.text((x, center_y - 8), text, fill=color, font=font, anchor=anchor)

    def _render_logic(self, config_data=None):
        config = config_data if config_data else self.storage.load_config()
        mode = config.get("design", {}).get("layout_mode", "list")
        
        if mode == "grid":
            return self._render_grid_mode(config)
        else:
            return self._render_list_mode(config)

    def _render_list_mode(self, config):
        design = config.get("design", {})
        global_scale = design.get("global_scale", 1.0)
        SCALE = 3 
        theme = design.get("theme", "dark")
        
        if theme == 'light':
            BG_COLOR = (255, 255, 255); GROUP_BG_COLOR = (242, 242, 247); GROUP_BORDER = (229, 229, 234)
            ITEM_BG_COLOR = (0, 0, 0, 10); ITEM_BORDER_COLOR = (0, 0, 0, 13)
            TEXT_MAIN = (0, 0, 0); TEXT_SUB = (108, 108, 112); DIVIDER_COLOR = (229, 229, 234)
        else:
            BG_COLOR = (0, 0, 0); GROUP_BG_COLOR = (28, 28, 30); GROUP_BORDER = (56, 56, 58)
            ITEM_BG_COLOR = (255, 255, 255, 20); ITEM_BORDER_COLOR = (255, 255, 255, 30)
            TEXT_MAIN = (255, 255, 255); TEXT_SUB = (142, 142, 147); DIVIDER_COLOR = (56, 56, 58)

        groups = config.get("groups", [])
        if not groups and config.get("menus"): groups = [{"title": "列表", "enabled":True, "menus": config.get("menus")}]
        
        active_groups_info = [] 
        for i, g in enumerate(groups):
            if g.get("enabled", True) is False: continue
            active_items = [m for m in g.get("menus", []) if m.get("enabled", True)]
            if active_items:
                new_g = g.copy()
                new_g["menus"] = active_items
                active_groups_info.append((i, new_g))
        
        if not active_groups_info and not config: return None

        width = 800 * SCALE
        
        padding = 30 * SCALE
        gap = 15 * SCALE
        base_title_size = 48 * SCALE * global_scale
        base_sub_size = 24 * SCALE * global_scale
        base_group_size = 28 * SCALE * global_scale
        base_item_size = 18 * SCALE * global_scale
        base_desc_size = 14 * SCALE * global_scale
        
        item_height = 70 * SCALE 
        group_header_height = 50 * SCALE 
        col_count = max(1, min(5, design.get("layout_columns", 2))) 
        title_align = design.get("title_align", "center")

        font_main = self._get_font(base_title_size, weight="heavy")
        font_sub = self._get_font(base_sub_size, weight="regular")
        font_grp = self._get_font(base_group_size, weight="bold")
        font_item = self._get_font(base_item_size, weight="medium")
        font_desc = self._get_font(base_desc_size, weight="regular")

        container_padding = 20 * SCALE
        current_y = (40 * SCALE) + base_title_size + (10 * SCALE)
        subtitle = config.get("subtitle", "")
        if subtitle: current_y += base_sub_size + (10 * SCALE)
        current_y += (20 * SCALE)
        
        for _, group in active_groups_info:
            group_h = container_padding * 2 + group_header_height
            menus = group.get("menus", [])
            rows = (len(menus) + col_count - 1) // col_count
            content_h = max(0, rows * (item_height + gap)) - gap
            if content_h < 0: content_h = 0
            group_h += content_h
            current_y += group_h + (20 * SCALE)
            
        total_height = max(current_y + (40 * SCALE), 300 * SCALE)
        
        img = Image.new('RGBA', (width, int(total_height)), color=(*BG_COLOR, 255))
        draw = ImageDraw.Draw(img)
        
        cursor_y = 40 * SCALE
        title_padding = 30 * SCALE
        self._draw_text_centered(draw, config.get("title", "Menu"), font_main, cursor_y + (base_title_size/2), width, title_align, TEXT_MAIN, padding=title_padding)
        cursor_y += base_title_size + (10 * SCALE)
        
        if subtitle:
            self._draw_text_centered(draw, subtitle, font_sub, cursor_y + (base_sub_size/2), width, title_align, TEXT_SUB, padding=title_padding)
            cursor_y += base_sub_size + (10 * SCALE)
            
        line_y = cursor_y + (10 * SCALE)
        draw.line([(30*SCALE, line_y), (width-(30*SCALE), line_y)], fill=DIVIDER_COLOR, width=int(1*SCALE))
        cursor_y = line_y + (20 * SCALE)
        
        colors = [(10, 132, 255), (48, 209, 88), (255, 159, 10), (255, 69, 58), (191, 90, 242), (100, 210, 255)]
        
        for original_idx, group in active_groups_info:
            menus = group.get("menus", [])
            item_count = len(menus)
            rows = (item_count + col_count - 1) // col_count
            content_h = max(0, rows * (item_height + gap)) - gap
            if content_h < 0: content_h = 0
            
            group_box_h = container_padding * 2 + group_header_height + content_h
            draw.rounded_rectangle([30*SCALE, cursor_y, width-(30*SCALE), cursor_y + group_box_h], radius=18*SCALE, fill=GROUP_BG_COLOR, outline=GROUP_BORDER, width=int(1*SCALE))
            
            inner_cursor_y = cursor_y + container_padding
            grp_center_y = inner_cursor_y + (group_header_height / 2)
            g_align = group.get("align", "left")
            bar_color_rgb = colors[original_idx % len(colors)]
            
            if g_align == 'left':
                bar_top = grp_center_y - (base_group_size / 2)
                draw.rounded_rectangle([padding + (20*SCALE), bar_top, padding + (26*SCALE), bar_top + base_group_size], radius=3*SCALE, fill=bar_color_rgb)
                text_padding = padding + (35*SCALE)
            else:
                text_padding = padding + (20*SCALE)
            
            self._draw_text_centered(draw, group.get("title", "分组"), font_grp, grp_center_y, width, g_align, TEXT_MAIN, padding=text_padding)
            inner_cursor_y += group_header_height
            
            inner_width = width - (60*SCALE) - (40*SCALE)
            card_width = (inner_width - (col_count - 1) * gap) / col_count
            start_x_abs = 50 * SCALE
            
            for i, menu in enumerate(menus):
                col = i % col_count
                if col == 0 and i > 0: inner_cursor_y += (item_height + gap)
                x = start_x_abs + col * (card_width + gap)
                y = inner_cursor_y
                
                card_img = Image.new('RGBA', (int(card_width), int(item_height)), (0,0,0,0))
                c_draw = ImageDraw.Draw(card_img)
                c_draw.rectangle([0, 0, card_width, item_height], fill=ITEM_BG_COLOR, outline=None)
                
                mask = Image.new('L', (int(card_width), int(item_height)), 0)
                m_draw = ImageDraw.Draw(mask)
                m_draw.rounded_rectangle([0, 0, card_width, item_height], radius=12*SCALE, fill=255)
                
                border_img = Image.new('RGBA', (int(card_width), int(item_height)), (0,0,0,0))
                b_draw = ImageDraw.Draw(border_img)
                b_draw.rounded_rectangle([0, 0, card_width, item_height], radius=12*SCALE, outline=ITEM_BORDER_COLOR, width=int(1*SCALE))
                
                img.paste(card_img, (int(x), int(y)), mask)
                img.alpha_composite(border_img, (int(x), int(y)))
                
                text_x = x + (15*SCALE)
                name = menu.get("name", "")
                desc = menu.get("desc", "")
                
                h_title = base_item_size * 1.1 
                h_desc = base_desc_size * 1.1
                h_gap = 4 * SCALE
                
                has_desc = bool(desc)
                total_text_h = (h_title + h_gap + h_desc) if has_desc else h_title
                block_top_y = y + (item_height - total_text_h) / 2
                visual_fix = -3 * SCALE * global_scale 

                target_y_title = block_top_y + (h_title / 2) + visual_fix
                draw.text((text_x, target_y_title), name, fill=TEXT_MAIN, font=font_item, anchor='lm')
                
                if has_desc:
                    target_y_desc = block_top_y + h_title + h_gap + (h_desc / 2) + visual_fix
                    limit = int(card_width / (base_desc_size/2)) - 2
                    if len(desc) > limit: desc = desc[:limit] + ".."
                    draw.text((text_x, target_y_desc), desc, fill=TEXT_SUB, font=font_desc, anchor='lm')
            
            cursor_y += group_box_h + (20 * SCALE)

        draw.text((width - (150*SCALE), total_height - (30*SCALE)), "AstrBot Menu", fill=TEXT_SUB, font=self._get_font(12*SCALE))
        return self._save_image(img, config)

    def _render_grid_mode(self, config):
        design = config.get("design", {})
        SCALE = 2 
        canvas_width = 800 * SCALE
        padding = 30 * SCALE
        gap = 20 * SCALE
        
        theme = design.get("theme", "dark")
        grid_cols = design.get("grid_columns", 4)
        title_align = design.get("title_align", "center") 
        
        font_title = self._get_font(40 * SCALE, "heavy")
        font_sub = self._get_font(20 * SCALE, "regular")
        font_w_title = self._get_font(24 * SCALE, "bold")
        font_item = self._get_font(20 * SCALE, "medium")
        
        is_light = theme == 'light'
        bg_color = (242, 242, 247) if is_light else (0, 0, 0)
        widget_bg = (255, 255, 255) if is_light else (28, 28, 30)
        text_main = (0, 0, 0) if is_light else (255, 255, 255)
        text_sub = (100, 100, 100) if is_light else (150, 150, 150)
        deco_colors = [(10, 132, 255), (48, 209, 88), (255, 159, 10), (255, 69, 58), (191, 90, 242)]

        available_width = canvas_width - (padding * 2)
        col_unit_width = (available_width - (gap * (grid_cols - 1))) / grid_cols
        
        cursor_y = padding + (80 * SCALE)
        current_x = padding
        current_row_max_h = 0
        
        layout_items = []
        
        groups = config.get("groups", [])
        for idx, group in enumerate(groups):
            if not group.get("enabled", True): continue
            
            span = min(group.get("span", 2), grid_cols)
            inner_cols = group.get("cols", 1)
            menus = [m for m in group.get("menus", []) if m.get("enabled", True)]
            
            if not menus: continue
            
            widget_w = (col_unit_width * span) + (gap * (span - 1))
            
            header_h = 40 * SCALE
            item_h = 50 * SCALE
            rows = math.ceil(len(menus) / inner_cols)
            content_h = (rows * item_h) + ((rows - 1) * 10 * SCALE) if rows > 0 else 0
            widget_h = header_h + content_h + (30 * SCALE)
            
            if current_x + widget_w > canvas_width - padding + 5: 
                cursor_y += current_row_max_h + gap
                current_x = padding
                current_row_max_h = 0
            
            layout_items.append({
                "x": current_x, "y": cursor_y, "w": widget_w, "h": widget_h,
                "data": group, "idx": idx, "menus": menus, "inner_cols": inner_cols
            })
            
            current_x += widget_w + gap
            current_row_max_h = max(current_row_max_h, widget_h)
            
        total_height = cursor_y + current_row_max_h + padding
        
        img = Image.new('RGB', (int(canvas_width), int(total_height)), bg_color)
        draw = ImageDraw.Draw(img)
        
        self._draw_text_centered(draw, config.get("title", "Menu"), font_title, padding + 20*SCALE, canvas_width, title_align, text_main, padding=padding)
        if config.get("subtitle"):
            self._draw_text_centered(draw, config.get("subtitle"), font_sub, padding + 55*SCALE, canvas_width, title_align, text_sub, padding=padding)

        for item in layout_items:
            x, y, w, h = item["x"], item["y"], item["w"], item["h"]
            draw.rounded_rectangle([x, y, x+w, y+h], radius=16*SCALE, fill=widget_bg)
            
            color = deco_colors[item["idx"] % len(deco_colors)]
            
            draw.rounded_rectangle([x+15*SCALE, y+20*SCALE, x+20*SCALE, y+44*SCALE], radius=2*SCALE, fill=color)
            draw.text((x + 30*SCALE, y+20*SCALE), item["data"].get("title", "分组"), fill=text_main, font=font_w_title)
            
            start_cx = x + 15*SCALE
            start_cy = y + 60*SCALE
            inner_cols = item["inner_cols"]
            content_w = w - 30*SCALE
            cell_w = (content_w - (10*SCALE * (inner_cols-1))) / inner_cols
            cell_h = 50 * SCALE
            
            for m_i, menu in enumerate(item["menus"]):
                r = m_i // inner_cols
                c = m_i % inner_cols
                cx = start_cx + c * (cell_w + 10*SCALE)
                cy = start_cy + r * (cell_h + 10*SCALE)
                
                draw.rounded_rectangle([cx, cy, cx+cell_w, cy+cell_h], radius=8*SCALE, fill=bg_color)
                
                name = menu.get("name", "")
                try: tw = draw.textlength(name, font_item)
                except: tw = font_item.getlength(name)
                
                if tw > cell_w - 10*SCALE: 
                    name = name[:4] + ".."
                    try: tw = draw.textlength(name, font_item)
                    except: tw = font_item.getlength(name)
                    
                draw.text((cx + (cell_w-tw)/2, cy + (cell_h-20*SCALE)/2 - 4*SCALE), name, fill=text_main, font=font_item)

        return self._save_image(img, config)

    def _save_image(self, img, config):
        prefix = "preview_" if config.get("is_preview") else "menu_"
        filename = f"{prefix}{random.randint(1000,9999)}.png"
        save_path = self.storage.bot_data_root / filename
        
        if img.mode == 'RGBA':
            final_img = Image.new("RGB", img.size, (255, 255, 255))
            final_img.paste(img, mask=img.split()[3])
        else:
            final_img = img
            
        final_img.save(save_path)
        return save_path
