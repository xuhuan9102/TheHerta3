'''
基础信息面板
'''
import bpy

from ..config.main_config import GlobalConfig, LogicName
from ..config.plugin_config import PluginConfig

from ..config.properties_import_model import Properties_ImportModel

from ..utils.translate_utils import TR


class MODEL_OT_SwitchToToolkit(bpy.types.Operator):
    bl_idname = "model.switch_to_toolkit"
    bl_label = "切换到工具集"
    bl_description = "切换到工具集面板"

    def execute(self, context):
        context.scene.herta_show_toolkit = True
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


class MODEL_OT_SwitchToMainPanel(bpy.types.Operator):
    bl_idname = "model.switch_to_main_panel"
    bl_label = "返回主面板"
    bl_description = "切换回主面板"

    def execute(self, context):
        context.scene.herta_show_toolkit = False
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


class PanelBasicInformation(bpy.types.Panel):
    bl_label = TR.translate("基础信息面板")
    bl_idname = "VIEW3D_PT_CATTER_Buttons_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta3'

    @classmethod
    def poll(cls, context):
        return not getattr(context.scene, 'herta_show_toolkit', False)

    def draw(self, context):
        layout = self.layout
        
        row = layout.row()
        row.prop(context.scene, 'herta_show_toolkit', text="工具集模式")
        row.operator("model.switch_to_toolkit", text="", icon='TOOL_SETTINGS')
        layout.separator()
        
        layout.prop(context.scene.properties_import_model,"use_ssmt4")

        if context.scene.properties_import_model.use_ssmt4:
            GlobalConfig.read_from_main_json_ssmt4()
        else:
            GlobalConfig.read_from_main_json()

        self.bl_label =  "TheHerta3 V" +  PluginConfig.get_version_string() + "  SSMT V" + str(GlobalConfig.ssmt_version_number)
        layout.label(text=TR.translate("SSMT缓存文件夹路径: ") + GlobalConfig.dbmtlocation)
        layout.label(text=TR.translate("当前配置名称: ") + GlobalConfig.gamename)


        layout.label(text=TR.translate("当前执行逻辑: ") + GlobalConfig.logic_name)
        layout.label(text=TR.translate("当前工作空间: ") + GlobalConfig.workspacename)

        if PluginConfig.get_min_ssmt_version() > GlobalConfig.ssmt_version_number:
            layout.label(text=TR.translate("当前SSMT版本过低无法适配"),icon='ERROR')

        layout.prop(context.scene.properties_import_model,"use_mirror_workflow",text="使用非镜像工作流")
        
        layout.prop(context.scene.properties_import_model,"use_parallel_export",text="启用并行导出")
        if context.scene.properties_import_model.use_parallel_export:
            from ..config.properties_import_model import Properties_ImportModel
            max_workers = Properties_ImportModel.get_max_parallel_worker_count()
            row = layout.row()
            row.prop(context.scene.properties_import_model,"parallel_worker_count",text=f"进程数(最大{max_workers})")
            layout.prop(context.scene.properties_import_model,"blender_executable_path",text="Blender路径")
            
            is_valid, error_msg = Properties_ImportModel.validate_blender_executable_path()
            if not is_valid:
                layout.label(text=error_msg, icon='ERROR')
            
            if not bpy.data.is_saved:
                layout.label(text="项目未保存，请先保存",icon='ERROR')
            elif bpy.data.is_dirty:
                layout.label(text="项目有未保存的修改",icon='ERROR')
        
        layout.prop(context.scene.properties_import_model,"use_preprocess_cache",text="启用预处理缓存")
        if context.scene.properties_import_model.use_preprocess_cache:
            from ..utils.preprocess_cache import get_cache_manager
            cache_manager = get_cache_manager()
            stats = cache_manager.get_cache_stats()
            row = layout.row()
            row.label(text=f"缓存: {stats['total_entries']}个文件, {stats['total_size_mb']:.1f}MB")
            row.operator("ssmt.clear_preprocess_cache", text="清理缓存", icon='TRASH')
        
        context = bpy.context
        if len(context.selected_objects) != 0:
            obj = context.selected_objects[0]

            gametypename = obj.get("3DMigoto:GameTypeName", "")
            recalculate_tangent = obj.get("3DMigoto:RecalculateTANGENT", False)
            recalculate_color = obj.get("3DMigoto:RecalculateCOLOR", False)

            layout.label(text="GameType: " + gametypename)
            layout.label(text="RecalculateTANGENT: " + str(recalculate_tangent))
            layout.label(text="RecalculateCOLOR: " + str(recalculate_color))
            
        layout.operator("theherta3.open_persistent_blueprint", icon='NODETREE')
        
        layout.operator("ssmt.quick_partial_export", icon='EXPORT')

        layout.operator("import_mesh.migoto_raw_buffers_mmt",icon='IMPORT')

        layout.operator("ssmt.import_all_from_workspace_blueprint",icon='IMPORT')

        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            layout.prop(context.scene.properties_wwmi,"import_merged_vgmap")
            layout.prop(context.scene.properties_wwmi,"import_skip_empty_vertex_groups")

        layout.prop(context.scene.properties_import_model, "use_normal_map")




def register():
    bpy.types.Scene.herta_show_toolkit = bpy.props.BoolProperty(
        name="工具集模式",
        default=False,
    )
    bpy.utils.register_class(MODEL_OT_SwitchToToolkit)
    bpy.utils.register_class(MODEL_OT_SwitchToMainPanel)
    bpy.utils.register_class(PanelBasicInformation)

def unregister():
    bpy.utils.unregister_class(PanelBasicInformation)
    bpy.utils.unregister_class(MODEL_OT_SwitchToMainPanel)
    bpy.utils.unregister_class(MODEL_OT_SwitchToToolkit)
    del bpy.types.Scene.herta_show_toolkit
