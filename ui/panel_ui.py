import bpy
import blf
import os
import sys

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_global import Properties_Global
from ..utils.translate_utils import TR
from ..config.plugin_config import PluginConfig


# 3Dmigoto属性绘制
def draw_migoto_overlay():
    """在 3D 视图左下角绘制自定义信息"""
    context = bpy.context  # 直接使用 bpy.context 获取完整上下文
    if len(context.selected_objects) == 0:
        return
    
    if not Properties_Global.show_obj_attributes():
        return

    obj = context.selected_objects[0]
    region = context.region
    font_id = 0  # 默认字体

    # 设置绘制位置（左上角，稍微偏移避免遮挡默认信息）
    x = 70
    y = 60  # 从顶部往下偏移

    # 获取自定义属性
    gametypename = obj.get("3DMigoto:GameTypeName", None)
    recalculate_tangent = obj.get("3DMigoto:RecalculateTANGENT", None)
    recalculate_color = obj.get("3DMigoto:RecalculateCOLOR", None)

    # 设置字体样式（可选）
    blf.size(font_id, 24)  # 12pt 大小
    blf.color(font_id, 1, 1, 1, 1)  # 白色

    # 绘制文本
    if gametypename:
        y += 20
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, f"GameType: {gametypename}")

        y += 20
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, f"Recalculate TANGENT: {recalculate_tangent}")
        

        y += 20
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, f"Recalculate COLOR: {recalculate_color}")

# 存储 draw_handler 引用，方便后续移除
migoto_draw_handler = None





class PanelBasicInformation(bpy.types.Panel):
    bl_label = TR.translate("基础信息面板")
    bl_idname = "VIEW3D_PT_CATTER_Buttons_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta'

    def draw(self, context):
        layout = self.layout

        GlobalConfig.read_from_main_json()

        layout.label(text="当前插件版本: " + PluginConfig.get_version_string())
        layout.label(text="SSMT缓存文件夹路径: " + GlobalConfig.dbmtlocation)
        layout.label(text=TR.translate("当前游戏: ") + GlobalConfig.gamename)
        layout.label(text=TR.translate("当前逻辑: ") + GlobalConfig.logic_name)
        layout.label(text=TR.translate("当前工作空间: ") + GlobalConfig.workspacename)

        # layout.prop(context.scene.properties_import_model,"use_mirror_workflow",text="使用非镜像工作流")

        layout.prop(context.scene.properties_global,"show_obj_attributes")

        context = bpy.context  # 直接使用 bpy.context 获取完整上下文
        if len(context.selected_objects) != 0:
            if Properties_Global.show_obj_attributes():
                obj = context.selected_objects[0]

                # 获取自定义属性
                gametypename = obj.get("3DMigoto:GameTypeName", None)
                recalculate_tangent = obj.get("3DMigoto:RecalculateTANGENT", None)
                recalculate_color = obj.get("3DMigoto:RecalculateCOLOR", None)

                layout.label(text="GameType: " + gametypename)
                layout.label(text="RecalculateTANGENT: " + str(recalculate_tangent))
                layout.label(text="RecalculateCOLOR: " + str(recalculate_color))

        



    