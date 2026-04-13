import bpy
import os
import glob
import re
import shutil
from collections import OrderedDict

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_SliderPanel(SSMTNode_PostProcess_Base):
    '''滑块面板后处理节点：扫描INI文件中的形态键强度参数，并为其生成可交互的滑块UI'''
    bl_idname = 'SSMTNode_PostProcess_SliderPanel'
    bl_label = '滑块面板'
    bl_description = '扫描INI文件中的形态键强度参数，并为其生成可交互的滑块UI'

    create_cumulative_backup: bpy.props.BoolProperty(
        name="创建累积备份",
        description="是否在修改前创建备份文件",
        default=True
    )

    # 快捷键属性
    help_key: bpy.props.StringProperty(
        name="帮助键",
        description="用于显示/隐藏帮助面板的快捷键",
        default="home"
    )
    reset_key: bpy.props.StringProperty(
        name="重置位置键",
        description="重置所有滑块位置的快捷键（支持组合键，如 ctrl home）",
        default="ctrl home"
    )
    zoom_in_key: bpy.props.StringProperty(
        name="放大键",
        description="放大UI的快捷键",
        default="up"
    )
    zoom_out_key: bpy.props.StringProperty(
        name="缩小键",
        description="缩小UI的快捷键",
        default="down"
    )
    drag_key: bpy.props.StringProperty(
        name="拖拽键",
        description="用于拖拽滑块的鼠标按键",
        default="VK_LBUTTON"
    )
    auto_play_toggle_key: bpy.props.StringProperty(
        name="自动播放开关键",
        description="用于播放/暂停形态键自动播放的快捷键",
        default="space"
    )

    auto_play_key_global: bpy.props.BoolProperty(
        name="全局生效",
        description="取消勾选后，自动播放快捷键在滑块面板隐藏时也有效（否则仅在滑块显示时生效）",
        default=False
    )

    # 滑块尺寸设置
    slider_width: bpy.props.FloatProperty(
        name="滑块宽度",
        description="每个滑块手柄的宽度（归一化屏幕坐标）",
        default=0.025,
        min=0.001,
        max=1.0,
        precision=4,
        step=0.1
    )
    slider_height: bpy.props.FloatProperty(
        name="滑块高度",
        description="每个滑块手柄的高度（归一化屏幕坐标）",
        default=0.042,
        min=0.001,
        max=1.0,
        precision=4,
        step=0.1
    )
    button_width: bpy.props.FloatProperty(
        name="按钮宽度",
        description="每个滑块左侧按钮的宽度",
        default=0.025,
        min=0.001,
        max=1.0,
        precision=4,
        step=0.1
    )
    button_height: bpy.props.FloatProperty(
        name="按钮高度",
        description="每个滑块左侧按钮的高度",
        default=0.045,
        min=0.001,
        max=1.0,
        precision=4,
        step=0.1
    )
    
    # 新增：角色检测相关属性
    target_object: bpy.props.StringProperty(
        name="目标物体",
        description="选择用于激活滑块面板的物体（用于自动提取哈希值和IndexCount）",
        default="",
        update=lambda self, context: self._update_from_object()
    )
    detect_hash: bpy.props.StringProperty(
        name="哈希值",
        description="用于检测当前角色的哈希值（如 6ec0fbe0）",
        default=""
    )
    detect_index_count: bpy.props.StringProperty(
        name="IndexCount",
        description="用于检测当前角色的 IndexCount 值",
        default=""
    )

    # 自定义图片资源路径
    background_image: bpy.props.StringProperty(
        name="背景图片",
        description="滑块面板的背景图片（将保存为 res/0.png）",
        subtype='FILE_PATH',
        default=""
    )
    slider_handle_image: bpy.props.StringProperty(
        name="滑块图片",
        description="滑块手柄图片（将保存为 res/1.png）",
        subtype='FILE_PATH',
        default=""
    )
    left_bar_image: bpy.props.StringProperty(
        name="左进度条图片",
        description="滑块左侧进度条图片（将保存为 res/2.png）",
        subtype='FILE_PATH',
        default=""
    )
    right_bar_image: bpy.props.StringProperty(
        name="右进度条图片",
        description="滑块右侧进度条图片（将保存为 res/3.png）",
        subtype='FILE_PATH',
        default=""
    )
    # 新增：按钮图片
    button_image: bpy.props.StringProperty(
        name="按钮图片",
        description="滑块左侧按钮图片（将保存为 res/4.png）",
        subtype='FILE_PATH',
        default=""
    )

    def _write_ordered_dict_to_ini(self, sections, ini_file_path, slider_panel_content=""):
        """将 OrderedDict 写回 INI 文件，保留顺序"""
        try:
            with open(ini_file_path, 'w', encoding='utf-8') as f:
                for section_name, lines in sections.items():
                    if section_name.startswith(';;'):
                        f.write(section_name + '\n')
                    else:
                        f.write(section_name + '\n')
                    for line in lines:
                        f.write(line + '\n')
                    f.write('\n')
                if slider_panel_content:
                    f.write('\n')
                    f.write(slider_panel_content)
        except Exception as e:
            print(f"写入INI文件失败: {e}")

    def _update_from_object(self):
        """当选择物体时，自动解析哈希值和IndexCount"""
        obj = bpy.data.objects.get(self.target_object)
        if not obj:
            return
        
        obj_name = obj.name
        # 解析物体名称，支持格式：
        # 1. 哈希-IndexCount-FirstIndex.xxx
        # 2. 哈希-IndexCount
        # 3. 哈希.xxx
        match = re.match(r'^([a-f0-9]{8})-([0-9]+)(?:-([0-9]+))?', obj_name)
        if match:
            self.detect_hash = match.group(1)
            self.detect_index_count = match.group(2)
        else:
            # 只提取哈希
            match2 = re.match(r'^([a-f0-9]{8})', obj_name)
            if match2:
                self.detect_hash = match2.group(1)
                self.detect_index_count = ""
            else:
                print(f"[SliderPanel] 无法从物体名称 '{obj_name}' 解析哈希和IndexCount")
    
    def draw_buttons(self, context, layout):
        layout.prop(self, "create_cumulative_backup")

        # 快捷键设置
        box = layout.box()
        box.label(text="快捷键设置", icon='KEYINGSET')
        box.prop(self, "help_key", text="帮助键")
        box.prop(self, "reset_key", text="重置位置键")
        box.prop(self, "zoom_in_key", text="放大键")
        box.prop(self, "zoom_out_key", text="缩小键")
        box.prop(self, "drag_key", text="拖拽键")
        box.prop(self, "auto_play_toggle_key", text="自动播放开关")
        box.prop(self, "auto_play_key_global", text="全局生效")

        # UI尺寸设置
        box = layout.box()
        box.label(text="UI尺寸设置", icon='PROPERTIES')
        col = box.column(align=True)
        col.prop(self, "slider_width")
        col.prop(self, "slider_height")
        col.separator()
        col.prop(self, "button_width")
        col.prop(self, "button_height")

        # 角色检测设置
        box = layout.box()
        box.label(text="角色检测设置", icon='VIEWZOOM')
        row = box.row(align=True)
        row.prop_search(self, "target_object", bpy.data, "objects", text="物体", icon='OBJECT_DATA')
        # 可选：添加一个按钮来手动触发解析
        row.operator("ssmt.slider_panel_parse_object", text="", icon='FILE_REFRESH').node_name = self.name
        
        box.prop(self, "detect_hash", text="哈希值")
        box.prop(self, "detect_index_count", text="IndexCount")
        box.label(text="提示：选择物体后自动解析哈希和IndexCount，也可手动填写", icon='INFO')

        box = layout.box()
        box.label(text="滑块图片资源（自定义）", icon='TEXTURE')
        box.prop(self, "background_image", text="背景")
        box.prop(self, "slider_handle_image", text="滑块")
        box.prop(self, "left_bar_image", text="左进度条")
        box.prop(self, "right_bar_image", text="右进度条")
        box.prop(self, "button_image", text="按钮")   # 新增：按钮图片设置
        box.label(text="留空则使用插件内置默认图片", icon='INFO')

    def execute_postprocess(self, mod_export_path):
        print(f"滑块面板后处理节点开始执行，Mod导出路径: {mod_export_path}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("路径中未找到任何.ini文件")
            return

        target_ini_file = ini_files[0]

        # 检查是否已经生成过滑块面板，避免重复
        try:
            with open(target_ini_file, 'r', encoding='utf-8') as f:
                if "; --- AUTO-APPENDED SLIDER CONTROL PANEL ---" in f.read():
                    print("滑块面板配置已存在于文件中。请手动删除后再生成。")
                    return
        except Exception as e:
            print(f"读取目标INI文件以进行检查时出错: {e}")
            return

        # 创建备份
        try:
            if self.create_cumulative_backup:
                self._create_cumulative_backup(target_ini_file, mod_export_path)
        except Exception as e:
            print(f"创建备份时出错: {e}")
            return

        # 复制资源文件（图片、shader）
        try:
            addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            source_asset_dir = os.path.join(addon_dir, "Toolset")
            dest_res_dir = os.path.join(mod_export_path, "res")
            os.makedirs(dest_res_dir, exist_ok=True)

            shader_source_path = os.path.join(source_asset_dir, "draw_2d.hlsl")
            shader_dest_path = os.path.join(dest_res_dir, "draw_2d.hlsl")
            if os.path.exists(shader_source_path):
                if not os.path.exists(shader_dest_path):
                    shutil.copy2(shader_source_path, shader_dest_path)
                    print(f"已复制 draw_2d.hlsl 到 {dest_res_dir}")
            else:
                print(f"警告: 未找到 'draw_2d.hlsl' 模板, 滑块UI可能无法显示。")

            # 图片资源映射（标准文件名 -> 自定义路径）【注意：按钮图片不在通用映射中处理，改为批量复制】
            image_mappings = [
                ("0.png", self.background_image),
                ("1.png", self.slider_handle_image),
                ("2.png", self.left_bar_image),
                ("3.png", self.right_bar_image),
                # ("4.png", self.button_image),  # 已移除，按钮图片采用批量复制逻辑
            ]
            for std_name, custom_path in image_mappings:
                dest_path = os.path.join(dest_res_dir, std_name)
                if custom_path and os.path.isfile(custom_path):
                    shutil.copy2(custom_path, dest_path)
                    print(f"已复制自定义图片: {custom_path} -> {std_name}")
                else:
                    self._copy_default_image(std_name, dest_res_dir, source_asset_dir)

            # ---------- 新增：按钮图片批量复制（根据滑块数量） ----------
            # 先读取 INI 以获取滑块数量（需提前解析一次 Constants）
            sections_temp = self._read_ini_to_ordered_dict(target_ini_file)
            if not sections_temp:
                print(f"无法读取INI文件以获取参数数量: {target_ini_file}")
                return

            freq_params_temp = set()
            param_pattern_temp = re.compile(r'^\s*global(?:\s+persist)?\s+(\$Freq_[^\s=]+)')
            if '[Constants]' in sections_temp:
                for line in sections_temp['[Constants]']:
                    match = param_pattern_temp.match(line)
                    if match:
                        freq_params_temp.add(match.group(1))
            num_sliders = len(freq_params_temp)

            if num_sliders == 0:
                print("在INI文件的[Constants]块中未找到任何形态键强度参数，按钮图片无需复制。")
                # 但仍可继续执行后续（不会生成滑块）
            else:
                # 确定按钮图片源路径
                if self.button_image and os.path.isfile(self.button_image):
                    src_button_img = self.button_image
                else:
                    src_button_img = os.path.join(source_asset_dir, "4.png")

                if os.path.exists(src_button_img):
                    for i in range(1, num_sliders + 1):
                        dest_name = f"4_{i}.png"
                        dest_path = os.path.join(dest_res_dir, dest_name)
                        shutil.copy2(src_button_img, dest_path)
                        print(f"已复制按钮图片: {dest_name}")
                else:
                    print(f"警告: 按钮源图片不存在 {src_button_img}，按钮可能无法显示。")
            # --------------------------------------------------------

        except Exception as e:
            print(f"准备和复制资源文件时出错: {e}")
            return

        # 读取现有INI
        sections = self._read_ini_to_ordered_dict(target_ini_file)
        if not sections:
            print(f"无法读取或解析INI文件: {target_ini_file}")
            return

        # 获取形态键强度参数列表
        freq_params = set()
        param_pattern = re.compile(r'^\s*global(?:\s+persist)?\s+(\$Freq_[^\s=]+)')
        if '[Constants]' in sections:
            for line in sections['[Constants]']:
                match = param_pattern.match(line)
                if match:
                    freq_params.add(match.group(1))

        sorted_freq_params = sorted(list(freq_params))
        num_sliders = len(sorted_freq_params)

        if num_sliders == 0:
            print("在INI文件的[Constants]块中未找到任何形态键强度参数 (如 global $Freq_...)")
            return

        print(f"找到 {num_sliders} 个形态键强度参数，开始生成滑块面板...")

        # --------------------------------------------------------------
        # 扫描分组自动播放变量，判断是否为多组独立模式
        # --------------------------------------------------------------
        group_ids = set()
        frame_end_vars = {}
        frame_end_min_vars = {}
        frame_end_max_vars = {}
        multi_group_mode = False

        if '[Constants]' in sections:
            const_lines = sections['[Constants]']
            const_text = "\n".join(const_lines)
            # 匹配 global $auto_play_enabled_group1 = 1 或 global persist $auto_play_enabled_group1 = 1
            for m in re.finditer(r'^\s*global(?:\s+persist)?\s+\$auto_play_enabled_group(\d+)', const_text, re.MULTILINE):
                group_id = int(m.group(1))
                group_ids.add(group_id)
            for m in re.finditer(r'^\s*global(?:\s+persist)?\s+\$frameEnd_group(\d+)', const_text, re.MULTILINE):
                group_id = int(m.group(1))
                frame_end_vars[group_id] = f"$frameEnd_group{group_id}"
            for m in re.finditer(r'^\s*global(?:\s+persist)?\s+\$frameEnd_min_group(\d+)', const_text, re.MULTILINE):
                group_id = int(m.group(1))
                frame_end_min_vars[group_id] = f"$frameEnd_min_group{group_id}"
            for m in re.finditer(r'^\s*global(?:\s+persist)?\s+\$frameEnd_max_group(\d+)', const_text, re.MULTILINE):
                group_id = int(m.group(1))
                frame_end_max_vars[group_id] = f"$frameEnd_max_group{group_id}"

        if group_ids:
            multi_group_mode = True
            group_ids = sorted(group_ids)
            print(f"[SliderPanel] 检测到多组自动播放变量，组号: {group_ids}")
        else:
            print("[SliderPanel] 未检测到分组自动播放变量，使用兼容模式（全局自动播放）")

        # 构建滑块索引到分组编号的映射（仅多组模式下使用）
        slider_to_group = {}
        if multi_group_mode:
            for idx, var_name in enumerate(sorted_freq_params):
                m = re.match(r'\$Freq_group(\d+)', var_name)
                if m:
                    slider_to_group[idx] = int(m.group(1))
                else:
                    print(f"[SliderPanel] 警告：强度变量名 '{var_name}' 无法解析分组编号，该滑块将仅控制强度。")
        # --------------------------------------------------------------

        # 获取用户设置的尺寸
        slider_w = self.slider_width
        slider_h = self.slider_height
        btn_w = self.button_width
        btn_h = self.button_height

        # 计算UI几何
        child_height = slider_h  # 直接使用滑块高度
        top_bottom_padding = 0.03
        spacing = 0.02
        total_slider_height = num_sliders * child_height
        total_spacing_height = max(0, (num_sliders - 1) * spacing)
        parent_height = total_slider_height + total_spacing_height + (top_bottom_padding * 2)

        # 读取用户设置的快捷键
        help_key = self.help_key.strip() or "home"
        reset_key = self.reset_key.strip() or "ctrl home"
        zoom_in_key = self.zoom_in_key.strip() or "up"
        zoom_out_key = self.zoom_out_key.strip() or "down"
        drag_key = self.drag_key.strip() or "VK_LBUTTON"
        auto_play_key = self.auto_play_toggle_key.strip() or "space"
        detect_hash = self.detect_hash.strip()
        detect_index_count = self.detect_index_count.strip()

        # 准备要添加到各个段的内容
        constants_additions = []
        present_additions = []
        other_sections = {}  # 用于存放非 [Constants]/[Present] 的新段

        # 1. 准备 constants 补充内容
        constants_additions.extend([
            "; --- UI 几何与位置配置 (由滑块面板生成) ---",
            "global $base_width0 = 0.34",           # 修改：加宽背景以包含左侧按钮
            f"global $base_height0 = {parent_height:.4f}",
            "global $set_x0 = 0.5", "global $set_y0 = 0.5",
        ])
        for i in range(1, num_sliders + 1):
            current_y_offset = top_bottom_padding + (i - 1) * (child_height + spacing) + (child_height / 2)
            relative_y = current_y_offset / parent_height
            constants_additions.extend([
                f"global $base_width{i} = {slider_w:.4f}",
                f"global $base_height{i} = {slider_h:.4f}",
                f"global $set_rel_x{i} = 0.5",
                f"global $fixed_rel_y{i} = {relative_y:.4f}",
                # 按钮几何变量
                f"global $btn_width{i} = {btn_w:.4f}",
                f"global $btn_height{i} = {btn_h:.4f}",
                f"global $btn_x{i}",
                f"global $btn_y{i}",
                f"global $btn_pressed{i} = 0",
            ])
        constants_additions.extend([
            "global $active", "global $help", "global $max_zoom = 5.0", "global $min_zoom = 0.1",
            "global $dragged_slider = 0",
            "global $mouse_clicked = 0", "global $click_outside = 0", "global $is_dragging = 0",
            "global $drag_x = 0", "global $drag_y = 0",
            "global persist $img0_x = 0", "global persist $img0_y = 0", "global persist $zoom0 = 1.0",
            "global $norm_width0", "global $norm_height0",
            "global $btn_click_processed = 0",   # 修复面板关闭问题
        ])
        # 根据模式决定是否添加全局自动播放变量（兼容模式需要）
        if not multi_group_mode:
            constants_additions.extend([
                "global persist $auto_play_enabled = 1",
                "global persist $frameEnd = 60",
                "global persist $frameEnd_min = 30",
                "global persist $frameEnd_max = 120",
            ])
        for i in range(1, num_sliders + 1):
            constants_additions.extend([
                f"global persist $rel_x{i} = 0", f"global persist $zoom{i} = 1.0",
                f"global $norm_width{i}", f"global $norm_height{i}", f"global $img{i}_x", f"global $img{i}_y",
                f"global $rel_y{i}", f"global $param{i}",
                f"global $left_bar{i}_x", f"global $left_bar{i}_y", f"global $left_bar{i}_width", f"global $left_bar{i}_height",
                f"global $right_bar{i}_x", f"global $right_bar{i}_y", f"global $right_bar{i}_width", f"global $right_bar{i}_height",
                f"global $min_rel_x{i}", f"global $max_rel_x{i}", f"global $range_x{i}", f"global $slider{i}_center_x",
            ])

        # 2. 准备资源检测段
        detect_section = "[TextureOverrideCheckHash]"
        detect_lines = []
        if detect_hash:
            detect_lines.append(f"hash = {detect_hash}")
        else:
            detect_lines.append("hash = ")
        if detect_index_count:
            detect_lines.append(f"match_index_count = {detect_index_count}")
        detect_lines.append("$active = 1")
        other_sections[detect_section] = detect_lines

        # 3. 资源图片段
        other_sections["[ResourceImageToRender0]"] = ["filename = ./res/0.png"]
        other_sections["[ResourceSliderHandle]"] = ["filename = ./res/1.png"]
        other_sections["[ResourceLeftBar]"] = ["filename = ./res/2.png"]
        other_sections["[ResourceRightBar]"] = ["filename = ./res/3.png"]
        # 按钮图片资源：改为按滑块数量生成独立资源段
        for i in range(1, num_sliders + 1):
            other_sections[f"[ResourcePlayPauseButton{i}]"] = [f"filename = ./res/4_{i}.png"]

        # 4. 快捷键和命令列表段
        reset_lines = ["$img0_x = 0", "$img0_y = 0", "$zoom0 = 1.0"]
        for i in range(1, num_sliders + 1):
            reset_lines.extend([f"$rel_x{i} = 0", f"$zoom{i} = 1.0"])
        zoom_in_lines = ["$zoom0 = $zoom0 + 0.05"] + [f"$zoom{i} = $zoom{i} + 0.05" for i in range(1, num_sliders + 1)]
        zoom_out_lines = ["$zoom0 = $zoom0 - 0.05"] + [f"$zoom{i} = $zoom{i} - 0.05" for i in range(1, num_sliders + 1)]

        auto_play_key_lines = []
        if not self.auto_play_key_global:
            auto_play_key_lines.append("condition = $help == 1 && $active == 1")
        auto_play_key_lines.extend([f"key = {auto_play_key}", "type = press", "run = CommandListToggleAutoPlay"])

        other_sections["[KeyHelp]"] = [f"condition = $active == 1", f"key = {help_key}", "type = cycle", "$help = 0,1"]
        other_sections["[KeyResetPosition]"] = [f"condition = $help == 1 && $active == 1", f"key = {reset_key}", "type = cycle"] + reset_lines
        other_sections["[KeyZoomIn]"] = [f"condition = $help == 1 && $active == 1", f"key = {zoom_in_key}", "type = press", "run = CommandListZoomIn"]
        other_sections["[KeyZoomOut]"] = [f"condition = $help == 1 && $active == 1", f"key = {zoom_out_key}", "type = press", "run = CommandListZoomOut"]
        other_sections["[KeyMouseDrag]"] = [f"condition = $help == 1 && $active == 1", f"key = {drag_key}", "type = hold", "$mouse_clicked = 1"]
        other_sections["[KeyToggleAutoPlay]"] = auto_play_key_lines
        other_sections["[CommandListZoomIn]"] = zoom_in_lines
        other_sections["[CommandListZoomOut]"] = zoom_out_lines

        # 自动播放开关命令（多组模式 vs 兼容模式）
        if multi_group_mode:
            toggle_lines = [f"$auto_play_enabled_group{gid} = 1 - $auto_play_enabled_group{gid}" for gid in group_ids]
            other_sections["[CommandListToggleAutoPlay]"] = toggle_lines
            # 为每个分组生成独立的切换命令，供按钮使用
            for gid in group_ids:
                other_sections[f"[CommandListToggleAutoPlayGroup{gid}]"] = [
                    f"$auto_play_enabled_group{gid} = 1 - $auto_play_enabled_group{gid}"
                ]
        else:
            other_sections["[CommandListToggleAutoPlay]"] = ["$auto_play_enabled = 1 - $auto_play_enabled"]

        # 5. 准备滑块逻辑（追加到现有 [Present] 末尾）
        present_additions.append("post $active = 0")
        present_additions.append("if $help == 1 && $active == 1")
        present_additions.append("    ; --- 1. 尺寸计算 ---")
        present_additions.append("    $norm_width0 = $base_width0 * $zoom0")
        present_additions.append("    $norm_height0 = $base_height0 * $zoom0")
        for i in range(1, num_sliders + 1):
            present_additions.append(f"    $norm_width{i} = $base_width{i} * $zoom{i}")
            present_additions.append(f"    $norm_height{i} = $base_height{i} * $zoom{i}")
        present_additions.append("\n    ; --- 2. 计算子级的拖拽边界 ---")
        for i in range(1, num_sliders + 1):
            # 修改：滑块轨道左边界以按钮宽度为基准，使背景能够包含按钮
            present_additions.append(f"    $min_rel_x{i} = $btn_width{i} + 0.02")
            present_additions.append(f"    $max_rel_x{i} = ($norm_width0 * 0.95) - $norm_width{i}")
            present_additions.append(f"    $range_x{i} = $max_rel_x{i} - $min_rel_x{i}")
        present_additions.append("\n    ; --- 3. 位置初始化 ---")
        present_additions.append("    if $img0_x == 0 && $img0_y == 0")
        present_additions.append("        $img0_x = $set_x0 * (1 - $norm_width0)")
        present_additions.append("        $img0_y = $set_y0 * (1 - $norm_height0)")
        present_additions.append("    endif")
        for i in range(1, num_sliders + 1):
            present_additions.append(f"    if $rel_x{i} == 0")
            present_additions.append(f"        $rel_x{i} = $min_rel_x{i} + ($set_rel_x{i} * $range_x{i})")
            present_additions.append("    endif")
        present_additions.append("\n    ; --- 4. 计算滑块和按钮位置 ---")
        for i in range(1, num_sliders + 1):
            present_additions.append(f"    $rel_y{i} = ($fixed_rel_y{i} * $norm_height0) - ($norm_height{i} / 2)")
            present_additions.append(f"    $img{i}_x = $img0_x + $rel_x{i}")
            present_additions.append(f"    $img{i}_y = $img0_y + $rel_y{i}")
            # 按钮位置固定相对于面板，放在滑块轨道最左侧，向左偏移量增加
            present_additions.append(f"    $btn_x{i} = $img0_x + $min_rel_x{i} - $btn_width{i} - 0.01")
            present_additions.append(f"    $btn_y{i} = $img{i}_y + ($norm_height{i} - $btn_height{i}) * 0.5")

        present_additions.append("\n    ; --- 5. 按钮按下/弹起检测（防连击，且不关闭面板） ---")
        present_additions.append("    $btn_click_processed = 0")
        present_additions.append("    if $mouse_clicked && $is_dragging == 0")
        for i in range(1, num_sliders + 1):
            gid = slider_to_group.get(i-1)
            if gid is not None and gid in group_ids:
                present_additions.append(f"        if cursor_x > $btn_x{i} && cursor_x < $btn_x{i} + $btn_width{i} && cursor_y > $btn_y{i} && cursor_y < $btn_y{i} + $btn_height{i}")
                present_additions.append(f"            $btn_pressed{i} = 1")
                present_additions.append(f"            $btn_click_processed = 1")
                present_additions.append(f"        endif")
        present_additions.append("    else")
        present_additions.append("        if $is_dragging == 0")
        for i in range(1, num_sliders + 1):
            gid = slider_to_group.get(i-1)
            if gid is not None and gid in group_ids:
                present_additions.append(f"            if $btn_pressed{i} == 1")
                present_additions.append(f"                if cursor_x > $btn_x{i} && cursor_x < $btn_x{i} + $btn_width{i} && cursor_y > $btn_y{i} && cursor_y < $btn_y{i} + $btn_height{i}")
                present_additions.append(f"                    run = CommandListToggleAutoPlayGroup{gid}")
                present_additions.append(f"                endif")
                present_additions.append(f"                $btn_pressed{i} = 0")
                present_additions.append(f"            endif")
        present_additions.append("        endif")
        present_additions.append("    endif")

        present_additions.append("\n    ; --- 6. 拖拽逻辑与位置更新 ---")
        present_additions.append("    if $mouse_clicked")
        present_additions.append("        if $is_dragging == 0")
        # 滑块拖拽检测
        for i in range(num_sliders, 0, -1):
            prefix = "if" if i == num_sliders else "            else if"
            present_additions.append(f"            {prefix} cursor_x > $img{i}_x && cursor_x < $img{i}_x + $norm_width{i} && cursor_y > $img{i}_y && cursor_y < $img{i}_y + $norm_height{i}")
            present_additions.append(f"                $is_dragging = {i + 1}")
            present_additions.append(f"                $drag_x = cursor_x - $img{i}_x")
        present_additions.append("            else if cursor_x > $img0_x && cursor_x < $img0_x + $norm_width0 && cursor_y > $img0_y && cursor_y < $img0_y + $norm_height0")
        present_additions.append("                $is_dragging = 1")
        present_additions.append("                $drag_x = cursor_x - $img0_x")
        present_additions.append("                $drag_y = cursor_y - $img0_y")
        present_additions.append("            else")
        present_additions.append("                if $btn_click_processed == 0")
        present_additions.append("                    $click_outside = 1")
        present_additions.append("                endif")
        present_additions.append("            endif")
        present_additions.append("        endif")
        present_additions.append("    else")
        present_additions.append("        $is_dragging = 0")
        present_additions.append("    endif")
        present_additions.append("    if $click_outside == 1 && $mouse_clicked == 0")
        present_additions.append("        $help = 0")
        present_additions.append("        $click_outside = 0")
        present_additions.append("    endif")
        present_additions.append("    if $is_dragging == 1")
        present_additions.append("        $img0_x = cursor_x - $drag_x")
        present_additions.append("        $img0_y = cursor_y - $drag_y")
        for i in range(2, num_sliders + 2):
            present_additions.append(f"    else if $is_dragging == {i}")
            present_additions.append(f"        $rel_x{i-1} = (cursor_x - $drag_x) - $img0_x")
            present_additions.append(f"        if $rel_x{i-1} < $min_rel_x{i-1}")
            present_additions.append(f"            $rel_x{i-1} = $min_rel_x{i-1}")
            present_additions.append(f"        endif")
            present_additions.append(f"        if $rel_x{i-1} > $max_rel_x{i-1}")
            present_additions.append(f"            $rel_x{i-1} = $max_rel_x{i-1}")
            present_additions.append(f"        endif")
        present_additions.append("    endif")

        present_additions.append("\n    ; --- 7. 计算进度条的几何信息 ---")
        for i in range(1, num_sliders + 1):
            present_additions.append(f"    $slider{i}_center_x = $img{i}_x + ($norm_width{i} * 0.5)")
            present_additions.append(f"    $left_bar{i}_height = $norm_height{i} * 0.5")
            present_additions.append(f"    $left_bar{i}_y = $img{i}_y + ($norm_height{i} * 0.25)")
            present_additions.append(f"    $left_bar{i}_x = $img0_x + $min_rel_x{i}")
            present_additions.append(f"    $left_bar{i}_width = $slider{i}_center_x - $left_bar{i}_x")
            present_additions.append(f"    $right_bar{i}_height = $left_bar{i}_height")
            present_additions.append(f"    $right_bar{i}_y = $left_bar{i}_y")
            present_additions.append(f"    $right_bar{i}_x = $slider{i}_center_x")
            present_additions.append(f"    $right_bar{i}_width = ($img0_x + $norm_width0 * 0.95) - $right_bar{i}_x")
        present_additions.append("\n    ; --- 8. 计算映射参数并链接到形态键强度或播放速度 ---")
        present_additions.append("    ; 当自动播放开启时，只有当前被拖拽的滑块控制播放速度；关闭时所有滑块控制各自形态键强度")
        present_additions.append("    $dragged_slider = 0")
        present_additions.append("    if $is_dragging >= 2")
        present_additions.append("        $dragged_slider = $is_dragging - 1")
        present_additions.append("    endif")

        # 核心滑块映射逻辑（多组模式 vs 兼容模式）
        if multi_group_mode:
            for i in range(1, num_sliders + 1):
                gid = slider_to_group.get(i - 1)
                present_additions.append(f"    $param{i} = ($rel_x{i} - $min_rel_x{i}) / $range_x{i}")
                if gid is not None:
                    present_additions.append(f"    ; 分组 {gid}")
                    if gid in group_ids:
                        present_additions.append(f"    if ($auto_play_enabled_group{gid} == 1)")
                        present_additions.append(f"        if ($dragged_slider == {i})")
                        present_additions.append(f"            $frameEnd_group{gid} = $frameEnd_max_group{gid} - $param{i} * ($frameEnd_max_group{gid} - $frameEnd_min_group{gid})")
                        present_additions.append(f"        endif")
                        present_additions.append(f"    else")
                        present_additions.append(f"        {sorted_freq_params[i-1]} = $param{i}")
                        present_additions.append(f"    endif")
                    else:
                        present_additions.append(f"    {sorted_freq_params[i-1]} = $param{i}")
                else:
                    present_additions.append(f"    {sorted_freq_params[i-1]} = $param{i}")
        else:
            # 兼容模式：使用全局变量
            for i in range(1, num_sliders + 1):
                present_additions.append(f"    $param{i} = ($rel_x{i} - $min_rel_x{i}) / $range_x{i}")
                present_additions.append(f"    if ($auto_play_enabled == 1)")
                present_additions.append(f"        if ($dragged_slider == {i})")
                present_additions.append(f"            $frameEnd = $frameEnd_max - $param{i} * ($frameEnd_max - $frameEnd_min)")
                present_additions.append(f"        endif")
                present_additions.append(f"    else")
                present_additions.append(f"        {sorted_freq_params[i-1]} = $param{i}")
                present_additions.append(f"    endif")
        # --------------------------------------------------------------

        present_additions.append("\n    ; --- 9. 执行渲染 (按层级) ---")
        present_additions.append("    ; 渲染父级 (最底层)")
        present_additions.append("    ps-t100 = ResourceImageToRender0")
        present_additions.append("    x87 = $norm_width0")
        present_additions.append("    y87 = $norm_height0")
        present_additions.append("    z87 = $img0_x")
        present_additions.append("    w87 = $img0_y")
        present_additions.append("    run = CustomShaderDraw")
        for i in range(1, num_sliders + 1):
            present_additions.append(f"\n    ; 渲染进度条{i}")
            present_additions.append(f"    ps-t100 = ResourceLeftBar")
            present_additions.append(f"    x87 = $left_bar{i}_width")
            present_additions.append(f"    y87 = $left_bar{i}_height")
            present_additions.append(f"    z87 = $left_bar{i}_x")
            present_additions.append(f"    w87 = $left_bar{i}_y")
            present_additions.append(f"    run = CustomShaderDraw")
            present_additions.append(f"    ps-t100 = ResourceRightBar")
            present_additions.append(f"    x87 = $right_bar{i}_width")
            present_additions.append(f"    y87 = $right_bar{i}_height")
            present_additions.append(f"    z87 = $right_bar{i}_x")
            present_additions.append(f"    w87 = $right_bar{i}_y")
            present_additions.append(f"    run = CustomShaderDraw")
        # 渲染按钮（使用独立资源名）
        for i in range(1, num_sliders + 1):
            present_additions.append(f"\n    ; 渲染播放/暂停按钮{i}")
            present_additions.append(f"    ps-t100 = ResourcePlayPauseButton{i}")
            present_additions.append(f"    x87 = $btn_width{i}")
            present_additions.append(f"    y87 = $btn_height{i}")
            present_additions.append(f"    z87 = $btn_x{i}")
            present_additions.append(f"    if $btn_pressed{i} == 1")
            present_additions.append(f"        w87 = $btn_y{i} + 0.002")
            present_additions.append(f"    else")
            present_additions.append(f"        w87 = $btn_y{i}")
            present_additions.append(f"    endif")
            present_additions.append(f"    run = CustomShaderDraw")
        for i in range(1, num_sliders + 1):
            present_additions.append(f"\n    ; 渲染滑块{i} (最顶层)")
            present_additions.append(f"    ps-t100 = ResourceSliderHandle")
            present_additions.append(f"    x87 = $norm_width{i}")
            present_additions.append(f"    y87 = $norm_height{i}")
            present_additions.append(f"    z87 = $img{i}_x")
            present_additions.append(f"    w87 = $img{i}_y")
            present_additions.append(f"    run = CustomShaderDraw")
        present_additions.append("endif")

        # 6. 准备 CustomShaderDraw 段
        shader_def = [
            "hs = null",
            "ds = null",
            "gs = null",
            "cs = null",
            "vs = ./res/draw_2d.hlsl",
            "ps = ./res/draw_2d.hlsl",
            "blend = ADD SRC_ALPHA INV_SRC_ALPHA",
            "cull = none",
            "topology = triangle_strip",
            "o0 = set_viewport bb",
            "Draw = 4,0",
            "clear = ps-t100"
        ]

        # 开始合并到 sections
        # 添加 constants 行（去重）
        if '[Constants]' not in sections:
            sections['[Constants]'] = []
        for line in constants_additions:
            if line not in sections['[Constants]']:
                sections['[Constants]'].append(line)

        # 添加其他新段（如果不存在）
        for sec_name, lines in other_sections.items():
            if sec_name not in sections:
                sections[sec_name] = []
            for line in lines:
                if line not in sections[sec_name]:
                    sections[sec_name].append(line)

        # 添加 CustomShaderDraw 段
        if '[CustomShaderDraw]' not in sections:
            sections['[CustomShaderDraw]'] = []
        for line in shader_def:
            if line not in sections['[CustomShaderDraw]']:
                sections['[CustomShaderDraw]'].append(line)

        # 追加滑块逻辑到 [Present] 末尾
        if '[Present]' not in sections:
            sections['[Present]'] = []
        # 在末尾添加一个空行和标记
        sections['[Present]'].append("")
        sections['[Present]'].append("; ========== SLIDER PANEL LOGIC (appended) ==========")
        sections['[Present]'].extend(present_additions)

        # 写回整个 INI 文件
        try:
            self._write_ordered_dict_to_ini(sections, target_ini_file, "")
            print(f"滑块控制面板配置已合并到: {os.path.basename(target_ini_file)}")
            print(f"共生成 {num_sliders} 个滑块")
            if multi_group_mode:
                print(f"多组自动播放模式已启用，每个滑块左侧已添加独立播放/暂停按钮（固定位置，防连击）")
                print(f"全局快捷键 {auto_play_key} 同时控制所有分组")
            else:
                print(f"自动播放开关快捷键已添加: {auto_play_key} (全局模式)")
        except Exception as e:
            print(f"写入INI文件失败: {e}")
            import traceback
            traceback.print_exc()

    def _copy_default_image(self, std_name, dest_res_dir, source_asset_dir):
        """复制默认图片到目标目录"""
        default_path = os.path.join(source_asset_dir, std_name)
        dest_path = os.path.join(dest_res_dir, std_name)
        if os.path.exists(default_path):
            if not os.path.exists(dest_path):
                shutil.copy2(default_path, dest_path)
                print(f"已复制默认图片: {std_name}")
        else:
            print(f"警告: 默认图片不存在 {default_path}")

    def _read_ini_to_ordered_dict(self, ini_file_path):
        """读取INI文件并返回有序字典"""
        sections = OrderedDict()
        current_section = None
        try:
            with open(ini_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line.startswith('[') and stripped_line.endswith(']') and len(stripped_line) > 2:
                        current_section = stripped_line
                        sections[current_section] = []
                    elif current_section is not None:
                        sections[current_section].append(line.rstrip())
        except FileNotFoundError:
            return None
        return sections


class SSMT_OT_SliderPanelParseObject(bpy.types.Operator):
    """手动触发解析所选物体，更新哈希值和IndexCount"""
    bl_idname = "ssmt.slider_panel_parse_object"
    bl_label = "解析物体"
    bl_description = "根据所选物体的名称解析哈希值和IndexCount"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: bpy.props.StringProperty()

    def execute(self, context):
        # 获取节点
        space_data = getattr(context, "space_data", None)
        if space_data and space_data.type == 'NODE_EDITOR':
            tree = getattr(space_data, "edit_tree", None) or getattr(space_data, "node_tree", None)
            if tree:
                node = tree.nodes.get(self.node_name)
                if node and node.bl_idname == 'SSMTNode_PostProcess_SliderPanel':
                    node._update_from_object()
                    self.report({'INFO'}, f"已解析物体 '{node.target_object}' -> 哈希: {node.detect_hash}, IndexCount: {node.detect_index_count}")
                    return {'FINISHED'}
        self.report({'WARNING'}, "无法找到滑块面板节点")
        return {'CANCELLED'}


classes = (
    SSMTNode_PostProcess_SliderPanel,
    SSMT_OT_SliderPanelParseObject,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)