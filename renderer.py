import asyncio
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random
from astrbot.api import logger
import urllib.request
import traceback

class MenuRenderer:
    def __init__(self, storage_instance):
        self.storage = storage_instance
        # 使用 storage 中统一定义的字体目录
        self.font_dir = self.storage.font_dir
        
        # 字体路径映射
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
        """主入口：Bot调用（异步下载，同步渲染）"""
        if not all(path.exists() for path in self.fonts.values()):
            await self._download_font_async()
        return await asyncio.to_thread(self._render_logic)

    def render_sync_for_web(self, config_data) -> Path:
        """Web入口：直接渲染（同步）"""
        # Web 预览时不强制下载字体，如果不存在会降级
        return self._render_logic(config_data)

    async def _download_font_async(self):
        await asyncio.to_thread(self._ensure_font_exists_sync)

    def _ensure_font_exists_sync(self):
        if not self.font_dir.exists(): 
            self.font_dir.mkdir(parents=True, exist_ok=True)
            
        for style, path in self.fonts.items():
            if not path.exists():
                url = self.urls[style]
                mirror_url = self.mirror_base + url
                logger.info(f"正在下载字体 ({style})...")
                try: urllib.request.urlretrieve(mirror_url, path)
                except:
                    try: urllib.request.urlretrieve(url, path)
                    except: logger.error(f"字体({style})下载失败")

    def _get_font(self, size, weight="regular"):
        """智能字体获取"""
        # 1. 尝试获取指定字重
        target_path = self.fonts.get(weight, self.fonts["regular"])
        if target_path.exists():
            try: return ImageFont.truetype(str(target_path), int(size))
            except: pass
        # 2. 降级到 Regular
        if self.fonts["regular"].exists():
             try: return ImageFont.truetype(str(self.fonts["regular"]), int(size))
             except: pass
        # 3. 系统默认
        return ImageFont.load_default()

    def _draw_text_centered(self, draw, text, font, center_y, width, align='left', color=(255,255,255), padding=90):
        try: text_len = draw.textlength(text, font=font)
        except: text_len = font.getlength(text)
        
        if align == 'center': x = width / 2; anchor = 'mm'
        elif align == 'right': x = width - padding; anchor = 'rm'
        else: x = padding; anchor = 'lm'
        
        draw.text((x, center_y - 8), text, fill=color, font=font, anchor=anchor)

    def _render_logic(self, config_data=None):
        """核心渲染逻辑 (保持原有绘图代码不变)"""
        # 加载配置
        config = config_data if config_data else self.storage.load_config()
        design = config.get("design", {})
        
        # ... (此处省略具体的绘图代码，与原 renderer.py 中 _render_sync 完全一致，只需复制原来的绘图逻辑即可) ...
        # ... 为节省篇幅，这里假设你保留了原来 _render_sync 函数内的所有绘图代码 ...
        
        # 以下是绘图代码的开头部分示例，请确保完整复制原有逻辑：
        global_scale = design.get("global_scale", 1.0)
        SCALE = 3 
        theme = design.get("theme", "dark")
        
        # 颜色定义...
        if theme == 'light':
            BG_COLOR = (255, 255, 255)
            GROUP_BG_COLOR = (242, 242, 247)
            GROUP_BORDER = (229, 229, 234)
            ITEM_BG_COLOR = (0, 0, 0, 10)
            ITEM_BORDER_COLOR = (0, 0, 0, 13)
            TEXT_MAIN = (0, 0, 0)
            TEXT_SUB = (108, 108, 112)
            DIVIDER_COLOR = (229, 229, 234)
        else:
            BG_COLOR = (0, 0, 0)
            GROUP_BG_COLOR = (28, 28, 30)
            GROUP_BORDER = (56, 56, 58)
            ITEM_BG_COLOR = (255, 255, 255, 20)
            ITEM_BORDER_COLOR = (255, 255, 255, 30)
            TEXT_MAIN = (255, 255, 255)
            TEXT_SUB = (142, 142, 147)
            DIVIDER_COLOR = (56, 56, 58)

        # 数据预处理...
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
        
        if not active_groups_info and not config_data: return None

        # 布局计算...
        width = 720 * SCALE
        padding = 30 * SCALE
        gap = 15 * SCALE
        base_title_size = 48 * SCALE * global_scale
        base_sub_size = 24 * SCALE * global_scale
        base_group_size = 28 * SCALE * global_scale
        base_item_size = 24 * SCALE * global_scale
        base_desc_size = 18 * SCALE * global_scale
        
        item_height = 70 * SCALE 
        group_header_height = 50 * SCALE 
        col_count = max(1, min(5, design.get("layout_columns", 2))) 
        title_align = design.get("title_align", "center")

        # 字体...
        font_main = self._get_font(base_title_size, weight="heavy")
        font_sub = self._get_font(base_sub_size, weight="regular")
        font_grp = self._get_font(base_group_size, weight="bold")
        font_item = self._get_font(base_item_size, weight="medium")
        font_desc = self._get_font(base_desc_size, weight="regular")

        # 高度计算...
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
        
        # 绘图...
        img = Image.new('RGBA', (width, int(total_height)), color=(*BG_COLOR, 255))
        draw = ImageDraw.Draw(img)
        
        cursor_y = 40 * SCALE
        
        # 标题绘制...
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
        
        # 分组循环...
        for original_idx, group in active_groups_info:
            menus = group.get("menus", [])
            item_count = len(menus)
            rows = (item_count + col_count - 1) // col_count
            content_h = max(0, rows * (item_height + gap)) - gap
            if content_h < 0: content_h = 0
            
            group_box_h = container_padding * 2 + group_header_height + content_h
            
            # 分组容器
            draw.rounded_rectangle(
                [30*SCALE, cursor_y, width-(30*SCALE), cursor_y + group_box_h],
                radius=18*SCALE, fill=GROUP_BG_COLOR, outline=GROUP_BORDER, width=int(1*SCALE)
            )
            
            inner_cursor_y = cursor_y + container_padding
            grp_center_y = inner_cursor_y + (group_header_height / 2)
            g_align = group.get("align", "left")
            bar_color_rgb = colors[original_idx % len(colors)]
            
            if g_align == 'left':
                bar_top = grp_center_y - (base_group_size / 2)
                draw.rounded_rectangle(
                    [padding + (20*SCALE), bar_top, padding + (26*SCALE), bar_top + base_group_size],
                    radius=3*SCALE, fill=bar_color_rgb
                )
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
                
                # 卡片绘制
                card_img = Image.new('RGBA', (int(card_width), int(item_height)), (0,0,0,0))
                c_draw = ImageDraw.Draw(card_img)
                c_draw.rectangle([0, 0, card_width, item_height], fill=ITEM_BG_COLOR, outline=None)
                c_draw.rectangle([0, 0, 6*SCALE, item_height], fill=bar_color_rgb)
                
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

        # 底部水印
        draw.text((width - (150*SCALE), total_height - (30*SCALE)), "AstrBot Menu", fill=TEXT_SUB, font=self._get_font(12*SCALE))
        
        prefix = "preview_" if config_data else "menu_"
        filename = f"{prefix}{random.randint(1000,9999)}.png"
        
        # 使用 storage.data_dir 来保存生成的图片
        save_path = self.storage.bot_data_root / filename
        
        final_img = Image.new("RGB", img.size, BG_COLOR)
        final_img.paste(img, mask=img.split()[3])
        final_img.save(save_path)
        return save_path