# blueprint_node_postprocess_shapekey_anim_control.py
import bpy
import os
import glob
import re
from collections import OrderedDict

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_ShapeKeyAnimControl(SSMTNode_PostProcess_Base):
    """形态键播放控制节点：为指定的形态键变量生成自动播放/手动控制双模式配置"""
    bl_idname = 'SSMTNode_PostProcess_ShapeKeyAnimControl'
    bl_label = '形态键播放控制'
    bl_description = '为形态键变量生成自动播放与手动控制的双模式配置'

    # 基本设置
    shapekey_var: bpy.props.StringProperty(
        name="形态键变量",
        description="需要控制的形态键强度变量名（例如 $Freq__1）",
        default="$Freq__1",
        update=lambda self, ctx: self.update_node_width([self.shapekey_var])
    )

    # 自动播放设置
    auto_enabled: bpy.props.BoolProperty(
        name="启用自动播放",
        description="启用自动播放模式",
        default=True
    )
    default_playing: bpy.props.BoolProperty(
        name="默认播放",
        description="自动播放默认状态（播放/暂停）",
        default=True
    )
    play_speed: bpy.props.FloatProperty(
        name="播放速率",
        description="每秒循环次数（速率）",
        default=1.0,
        min=0.1,
        max=10.0,
        step=0.1,
        precision=1
    )

    play_order_items = [
        ('FORWARD', '正序', '从0到1循环'),
        ('REVERSE', '倒序', '从1到0循环'),
    ]
    play_order: bpy.props.EnumProperty(
        name="播放顺序",
        description="形态键强度的变化顺序",
        items=play_order_items,
        default='FORWARD'
    )

    loop_mode_items = [
        ('FORWARD', '正向循环', '0→1→0→1...（锯齿波）'),
        ('PINGPONG', '往返循环', '0→1→0→1...（三角波）'),
        ('REVERSE', '逆向循环', '1→0→1→0...（反锯齿）'),
    ]
    loop_mode: bpy.props.EnumProperty(
        name="循环模式",
        description="形态键强度的波形",
        items=loop_mode_items,
        default='FORWARD'
    )

    # 手动控制设置
    manual_enabled: bpy.props.BoolProperty(
        name="启用手动模式",
        description="启用手动控制模式（需配合滑块面板）",
        default=True
    )
    slider_enabled: bpy.props.BoolProperty(
        name="启用滑块面板",
        description="为手动模式生成滑块UI",
        default=True
    )

    # 模式切换快捷键
    toggle_key: bpy.props.StringProperty(
        name="模式切换键",
        description="切换自动/手动模式的快捷键（例如 No_Modifiers 0）",
        default="No_Modifiers 0"
    )
    auto_key: bpy.props.StringProperty(
        name="自动播放开关键",
        description="自动模式下暂停/继续的快捷键（例如 No_Modifiers 1）",
        default="No_Modifiers 1"
    )

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="形态键变量", icon='SHAPEKEY_DATA')
        box.prop(self, "shapekey_var", text="")

        box = layout.box()
        box.label(text="自动播放设置", icon='PLAY')
        box.prop(self, "auto_enabled")
        if self.auto_enabled:
            row = box.row()
            row.prop(self, "default_playing", text="默认播放")
            row.prop(self, "play_speed", text="速率")
            row = box.row()
            row.prop(self, "play_order", text="顺序")
            row.prop(self, "loop_mode", text="循环")

        box = layout.box()
        box.label(text="手动控制设置", icon='HAND')
        box.prop(self, "manual_enabled")
        if self.manual_enabled:
            box.prop(self, "slider_enabled", text="生成滑块面板")

        box = layout.box()
        box.label(text="快捷键", icon='KEYINGSET')
        box.prop(self, "toggle_key", text="模式切换")
        if self.auto_enabled:
            box.prop(self, "auto_key", text="播放/暂停")

    def execute_postprocess(self, mod_export_path):
        print(f"[ShapeKeyAnimControl] 开始执行，Mod导出路径: {mod_export_path}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("[ShapeKeyAnimControl] 未找到任何 .ini 文件，跳过")
            return

        target_ini = ini_files[0]
        # 检查是否已存在标记，避免重复追加
        marker = "; --- AUTO-APPENDED SHAPEKEY ANIM CONTROL ---"
        try:
            with open(target_ini, 'r', encoding='utf-8') as f:
                if marker in f.read():
                    print("[ShapeKeyAnimControl] 配置已存在，跳过")
                    return
        except Exception:
            pass

        # 备份原文件
        self._create_cumulative_backup(target_ini, mod_export_path)

        # 生成配置块
        config_block = self._generate_config_block()
        if not config_block:
            print("[ShapeKeyAnimControl] 生成配置失败")
            return

        # 追加到文件末尾
        with open(target_ini, 'a', encoding='utf-8') as f:
            f.write("\n\n")
            f.write("; ==============================================================================\n")
            f.write("; --- AUTO-APPENDED SHAPEKEY ANIM CONTROL ---\n")
            f.write("; ==============================================================================\n\n")
            f.write(config_block)

        print(f"[ShapeKeyAnimControl] 已追加配置到 {os.path.basename(target_ini)}")

    def _generate_config_block(self):
        lines = []

        # ----- 1. 定义全局变量 -----
        var = self.shapekey_var.strip()
        if not var.startswith('$'):
            self.report({'ERROR'}, f"形态键变量必须以 $ 开头: {var}")
            return None

        lines.append("[Constants]")
        # 速度变量
        lines.append(f"global $anim_speed = {self.play_speed:.2f}")
        # 播放状态（0=暂停，1=播放）
        lines.append(f"global $anim_playing = {1 if self.default_playing else 0}")
        # 模式变量（0=自动，1=手动）
        lines.append(f"global $anim_mode = 0")
        # 帧计数器
        lines.append("global $auxTime = 0")
        lines.append("")

        # ----- 2. 快捷键定义 -----
        if self.auto_enabled and self.auto_key:
            lines.append(f"[KeyToggleAutoPlay]")
            lines.append(f"key = {self.auto_key}")
            lines.append("type = cycle")
            lines.append("$anim_playing = 0,1")
            lines.append("")

        if self.manual_enabled and self.toggle_key:
            lines.append(f"[KeyToggleMode]")
            lines.append(f"key = {self.toggle_key}")
            lines.append("type = cycle")
            lines.append("$anim_mode = 0,1")
            lines.append("")

        # ----- 3. 自动播放核心逻辑（Present 部分）-----
        lines.append("[Present]")
        lines.append("post $auxTime = $auxTime + 1")
        lines.append("")

        # 自动模式计算
        if self.auto_enabled:
            # 根据循环模式和顺序计算强度值
            if self.loop_mode == 'FORWARD':
                # 正向循环：0→1→0→1...
                lines.append("if $anim_mode == 0")
                lines.append("    if $anim_playing == 1")
                lines.append(f"        $t = $auxTime * $anim_speed")
                lines.append("        $frac = $t - floor($t)")
                if self.play_order == 'FORWARD':
                    lines.append(f"        {var} = $frac")
                else:
                    lines.append(f"        {var} = 1 - $frac")
                lines.append("    endif")
                lines.append("endif")
            elif self.loop_mode == 'PINGPONG':
                # 往返循环（三角波）
                lines.append("if $anim_mode == 0")
                lines.append("    if $anim_playing == 1")
                lines.append(f"        $t = $auxTime * $anim_speed")
                lines.append("        $frac = $t - floor($t)")
                if self.play_order == 'FORWARD':
                    lines.append(f"        {var} = 2 * (0.5 - abs($frac - 0.5))")
                else:
                    lines.append(f"        {var} = 1 - 2 * (0.5 - abs($frac - 0.5))")
                lines.append("    endif")
                lines.append("endif")
            else:  # REVERSE 逆向循环（1→0→1→0...）
                lines.append("if $anim_mode == 0")
                lines.append("    if $anim_playing == 1")
                lines.append(f"        $t = $auxTime * $anim_speed")
                lines.append("        $frac = $t - floor($t)")
                lines.append(f"        {var} = 1 - $frac")
                lines.append("    endif")
                lines.append("endif")
        else:
            # 自动模式未启用，手动模式接管（无自动逻辑）
            pass

        # ----- 4. 手动模式滑块面板（如果启用）-----
        if self.manual_enabled and self.slider_enabled:
            slider_block = self._generate_slider_panel(var)
            if slider_block:
                lines.extend(slider_block)

        # 确保形态键着色器被调用（假设已有的形态键配置会调用 CustomShader）
        # 但我们需要在 Present 末尾调用形态键着色器？不一定需要，因为已有的形态键配置会在 Present 中调用 run。
        # 为了不干扰，我们不在本块中重复调用。只需保证变量被正确赋值即可。

        return "\n".join(lines)

    def _generate_slider_panel(self, var):
        """生成单个滑块的UI代码（简化版，仅针对一个形态键）"""
        lines = []
        lines.append("")
        lines.append("; --- 手动模式滑块 UI ---")
        lines.append("[ResourceImageToRender0]")
        lines.append("filename = ./res/0.png")
        lines.append("[ResourceSliderHandle]")
        lines.append("filename = ./res/1.png")
        lines.append("[ResourceLeftBar]")
        lines.append("filename = ./res/2.png")
        lines.append("[ResourceRightBar]")
        lines.append("filename = ./res/3.png")
        lines.append("")

        # 检测哈希的节点（需要用户配置，此处使用一个通用模板，用户可能需要手动修改）
        lines.append("[TextureOverrideCheckHash]")
        lines.append("hash = ")  # 留空，用户自己填
        lines.append("$active = 1")
        lines.append("")

        lines.append("[KeyHelp]")
        lines.append("condition = $active == 1")
        lines.append("key = home")
        lines.append("type = cycle")
        lines.append("$help = 0,1")
        lines.append("")

        lines.append("[KeyResetPosition]")
        lines.append("condition = $help == 1 && $active == 1")
        lines.append("key = ctrl home")
        lines.append("type = cycle")
        lines.append("$img0_x = 0")
        lines.append("$img0_y = 0")
        lines.append("$zoom0 = 1.0")
        lines.append("$rel_x1 = 0")
        lines.append("$zoom1 = 1.0")
        lines.append("")

        lines.append("[KeyZoomIn]")
        lines.append("condition = $help == 1 && $active == 1")
        lines.append("key = up")
        lines.append("type = press")
        lines.append("run = CommandListZoomIn")
        lines.append("")

        lines.append("[KeyZoomOut]")
        lines.append("condition = $help == 1 && $active == 1")
        lines.append("key = down")
        lines.append("type = press")
        lines.append("run = CommandListZoomOut")
        lines.append("")

        lines.append("[KeyMouseDrag]")
        lines.append("condition = $help == 1 && $active == 1")
        lines.append("key = VK_LBUTTON")
        lines.append("type = hold")
        lines.append("$mouse_clicked = 1")
        lines.append("")

        lines.append("[CommandListZoomIn]")
        lines.append("$zoom0 = $zoom0 + 0.05")
        lines.append("$zoom1 = $zoom1 + 0.05")
        lines.append("")

        lines.append("[CommandListZoomOut]")
        lines.append("$zoom0 = $zoom0 - 0.05")
        lines.append("$zoom1 = $zoom1 - 0.05")
        lines.append("")

        # UI 几何变量
        lines.append("[Constants]")
        lines.append("global $base_width0 = 0.3")
        lines.append("global $base_height0 = 0.0900")
        lines.append("global $set_x0 = 0.5")
        lines.append("global $set_y0 = 0.5")
        lines.append("global $base_width1 = 0.02")
        lines.append("global $base_height1 = 0.03")
        lines.append("global $set_rel_x1 = 0.5")
        lines.append("global $fixed_rel_y1 = 0.5000")
        lines.append("global $active")
        lines.append("global $help")
        lines.append("global $mouse_clicked = 0")
        lines.append("global $click_outside = 0")
        lines.append("global $is_dragging = 0")
        lines.append("global $drag_x = 0")
        lines.append("global $drag_y = 0")
        lines.append("global persist $img0_x = 0")
        lines.append("global persist $img0_y = 0")
        lines.append("global persist $zoom0 = 1.0")
        lines.append("global $norm_width0")
        lines.append("global $norm_height0")
        lines.append("global persist $rel_x1 = 0")
        lines.append("global persist $zoom1 = 1.0")
        lines.append("global $norm_width1")
        lines.append("global $norm_height1")
        lines.append("global $img1_x")
        lines.append("global $img1_y")
        lines.append("global $rel_y1")
        lines.append("global $param1")
        lines.append("global $left_bar1_x")
        lines.append("global $left_bar1_y")
        lines.append("global $left_bar1_width")
        lines.append("global $left_bar1_height")
        lines.append("global $right_bar1_x")
        lines.append("global $right_bar1_y")
        lines.append("global $right_bar1_width")
        lines.append("global $right_bar1_height")
        lines.append("global $min_rel_x1")
        lines.append("global $max_rel_x1")
        lines.append("global $range_x1")
        lines.append("global $slider1_center_x")
        lines.append("")

        # Present 中的 UI 渲染（手动模式下覆盖形态键值）
        lines.append("[Present]")
        lines.append("post $active = 0")
        lines.append("if $help == 1 && $active == 1")
        lines.append("    $norm_width0 = $base_width0 * $zoom0")
        lines.append("    $norm_height0 = $base_height0 * $zoom0")
        lines.append("    $norm_width1 = $base_width1 * $zoom1")
        lines.append("    $norm_height1 = $base_height1 * $zoom1")
        lines.append("    $min_rel_x1 = $norm_width0 * 0.05")
        lines.append("    $max_rel_x1 = ($norm_width0 * 0.95) - $norm_width1")
        lines.append("    $range_x1 = $max_rel_x1 - $min_rel_x1")
        lines.append("    if $img0_x == 0 && $img0_y == 0")
        lines.append("        $img0_x = $set_x0 * (1 - $norm_width0)")
        lines.append("        $img0_y = $set_y0 * (1 - $norm_height0)")
        lines.append("    endif")
        lines.append("    if $rel_x1 == 0")
        lines.append("        $rel_x1 = $min_rel_x1 + ($set_rel_x1 * $range_x1)")
        lines.append("    endif")
        lines.append("    if $mouse_clicked")
        lines.append("        if $is_dragging == 0")
        lines.append("            if cursor_x > $img1_x && cursor_x < $img1_x + $norm_width1 && cursor_y > $img1_y && cursor_y < $img1_y + $norm_height1")
        lines.append("                $is_dragging = 2")
        lines.append("                $drag_x = cursor_x - $img1_x")
        lines.append("            else if cursor_x > $img0_x && cursor_x < $img0_x + $norm_width0 && cursor_y > $img0_y && cursor_y < $img0_y + $norm_height0")
        lines.append("                $is_dragging = 1")
        lines.append("                $drag_x = cursor_x - $img0_x")
        lines.append("                $drag_y = cursor_y - $img0_y")
        lines.append("            else")
        lines.append("                $click_outside = 1")
        lines.append("            endif")
        lines.append("        endif")
        lines.append("    else")
        lines.append("        $is_dragging = 0")
        lines.append("    endif")
        lines.append("    if $click_outside == 1 && $mouse_clicked == 0")
        lines.append("        $help = 0")
        lines.append("        $click_outside = 0")
        lines.append("    endif")
        lines.append("    if $is_dragging == 1")
        lines.append("        $img0_x = cursor_x - $drag_x")
        lines.append("        $img0_y = cursor_y - $drag_y")
        lines.append("    else if $is_dragging == 2")
        lines.append("        $rel_x1 = (cursor_x - $drag_x) - $img0_x")
        lines.append("        if $rel_x1 < $min_rel_x1")
        lines.append("            $rel_x1 = $min_rel_x1")
        lines.append("        endif")
        lines.append("        if $rel_x1 > $max_rel_x1")
        lines.append("            $rel_x1 = $max_rel_x1")
        lines.append("        endif")
        lines.append("    endif")
        lines.append("    $rel_y1 = ($fixed_rel_y1 * $norm_height0) - ($norm_height1 / 2)")
        lines.append("    $img1_x = $img0_x + $rel_x1")
        lines.append("    $img1_y = $img0_y + $rel_y1")
        lines.append("    $slider1_center_x = $img1_x + ($norm_width1 * 0.5)")
        lines.append("    $left_bar1_height = $norm_height1 * 0.5")
        lines.append("    $left_bar1_y = $img1_y + ($norm_height1 * 0.25)")
        lines.append("    $left_bar1_x = $img0_x + $min_rel_x1")
        lines.append("    $left_bar1_width = $slider1_center_x - $left_bar1_x")
        lines.append("    $right_bar1_height = $left_bar1_height")
        lines.append("    $right_bar1_y = $left_bar1_y")
        lines.append("    $right_bar1_x = $slider1_center_x")
        lines.append("    $right_bar1_width = ($img0_x + $norm_width0 * 0.95) - $right_bar1_x")
        lines.append("    $param1 = ($rel_x1 - $min_rel_x1) / $range_x1")
        lines.append(f"    if $anim_mode == 1")
        lines.append(f"        {var} = $param1")
        lines.append(f"    endif")
        lines.append("    ps-t100 = ResourceImageToRender0")
        lines.append("    x87 = $norm_width0")
        lines.append("    y87 = $norm_height0")
        lines.append("    z87 = $img0_x")
        lines.append("    w87 = $img0_y")
        lines.append("    run = CustomShaderDraw")
        lines.append("    ps-t100 = ResourceLeftBar")
        lines.append("    x87 = $left_bar1_width")
        lines.append("    y87 = $left_bar1_height")
        lines.append("    z87 = $left_bar1_x")
        lines.append("    w87 = $left_bar1_y")
        lines.append("    run = CustomShaderDraw")
        lines.append("    ps-t100 = ResourceRightBar")
        lines.append("    x87 = $right_bar1_width")
        lines.append("    y87 = $right_bar1_height")
        lines.append("    z87 = $right_bar1_x")
        lines.append("    w87 = $right_bar1_y")
        lines.append("    run = CustomShaderDraw")
        lines.append("    ps-t100 = ResourceSliderHandle")
        lines.append("    x87 = $norm_width1")
        lines.append("    y87 = $norm_height1")
        lines.append("    z87 = $img1_x")
        lines.append("    w87 = $img1_y")
        lines.append("    run = CustomShaderDraw")
        lines.append("endif")
        lines.append("")

        # 渲染着色器
        lines.append("[CustomShaderDraw]")
        lines.append("hs = null")
        lines.append("ds = null")
        lines.append("gs = null")
        lines.append("cs = null")
        lines.append("vs = ./res/draw_2d.hlsl")
        lines.append("ps = ./res/draw_2d.hlsl")
        lines.append("blend = ADD SRC_ALPHA INV_SRC_ALPHA")
        lines.append("cull = none")
        lines.append("topology = triangle_strip")
        lines.append("o0 = set_viewport bb")
        lines.append("Draw = 4,0")
        lines.append("clear = ps-t100")
        lines.append("")

        return lines


# 注册
classes = (
    SSMTNode_PostProcess_ShapeKeyAnimControl,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)