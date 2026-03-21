
'''
导入模型配置面板
'''
import os
import bpy

from bpy_extras.io_utils import ImportHelper

from ..utils.obj_utils import ObjUtils 

from ..utils.json_utils import JsonUtils
from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import CollectionColor, CollectionUtils
from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR

from ..config.main_config import GlobalConfig, LogicName

from ..importer.mesh_importer import MeshImporter,MigotoBinaryFile
from ..importer.migoto_binary_file import ConfigTabsHelper
from ..base.drawib_pair import DrawIBPair


class Import3DMigotoRaw(bpy.types.Operator, ImportHelper):
    """Import raw 3Dmigoto vertex and index buffers"""
    bl_idname = "import_mesh.migoto_raw_buffers_mmt"
    bl_label = TR.translate("导入.fmt .ib .vb格式模型")
    bl_description = "导入3Dmigoto格式的 .ib .vb .fmt文件，只需选择.fmt文件即可"
    bl_options = {'REGISTER','UNDO'}

    filename_ext = '.fmt'

    filter_glob: bpy.props.StringProperty(
        default='*.fmt',
        options={'HIDDEN'},
    ) # type: ignore

    files: bpy.props.CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    ) # type: ignore

    def execute(self, context):
        dirname = os.path.dirname(self.filepath)

        collection_name = os.path.basename(dirname)
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)

        import_filename_list = []
        if len(self.files) == 1:
            if str(self.filepath).endswith(".fmt"):
                import_filename_list.append(self.filepath)
            else:
                for filename in os.listdir(self.filepath):
                    if filename.endswith(".fmt"):
                        import_filename_list.append(filename)
        else:
            for fmt_file in self.files:
                import_filename_list.append(fmt_file.name)

        ConfigTabsHelper.reset()
        workspace_path = GlobalConfig.path_workspace_folder()
        ConfigTabsHelper.load_tabs_config(workspace_path)

        imported_objects_info = []

        for fmt_file_name in import_filename_list:
            fmt_file_path = os.path.join(dirname, fmt_file_name)
            mbf = MigotoBinaryFile(fmt_path=fmt_file_path)
            
            obj = MeshImporter.create_mesh_obj_from_mbf(mbf=mbf, import_collection=collection)
            
            if obj:
                draw_ib = self._extract_draw_ib_from_mesh_name(mbf.mesh_name)
                imported_objects_info.append({
                    "obj": obj,
                    "draw_ib": draw_ib,
                    "mesh_name": mbf.mesh_name
                })

        self._organize_objects_by_tabs(collection, imported_objects_info)

        CollectionUtils.select_collection_objects(collection)

        return {'FINISHED'}

    def _extract_draw_ib_from_mesh_name(self, mesh_name: str) -> str:
        if not mesh_name:
            return ""
        if "-" in mesh_name:
            return mesh_name.split("-")[0]
        return mesh_name

    def _organize_objects_by_tabs(self, parent_collection, imported_objects_info: list):
        tabs_config = ConfigTabsHelper.get_drawib_tabs_config()
        
        print(f"[Import3DMigotoRaw] 导入物体数量: {len(imported_objects_info)}")
        for obj_info in imported_objects_info:
            print(f"[Import3DMigotoRaw] 物体: {obj_info['mesh_name']}, draw_ib: {obj_info['draw_ib']}")
        
        if not tabs_config:
            print("[Import3DMigotoRaw] 未找到有效的分组配置，跳过分组")
            return

        workspace_collection = self._find_workspace_collection(parent_collection)
        if not workspace_collection:
            workspace_collection = parent_collection
        print(f"[Import3DMigotoRaw] 使用父集合: {workspace_collection.name}")

        for tab_config in tabs_config:
            tab_name = tab_config["tab_name"]
            draw_ib_to_alias = tab_config["draw_ib_to_alias"]
            print(f"[Import3DMigotoRaw] 处理分组配置: {tab_name}, IB列表: {list(draw_ib_to_alias.keys())}")

            tab_collection = bpy.data.collections.new(tab_name)
            workspace_collection.children.link(tab_collection)
            tab_collection.color_tag = CollectionColor.Green

            ib_to_objects = {}
            for obj_info in imported_objects_info:
                obj = obj_info["obj"]
                draw_ib = obj_info["draw_ib"]
                
                if draw_ib in draw_ib_to_alias:
                    if draw_ib not in ib_to_objects:
                        ib_to_objects[draw_ib] = []
                    ib_to_objects[draw_ib].append(obj)
                    print(f"[Import3DMigotoRaw] 物体 {obj.name} 匹配到 IB {draw_ib}")

            for draw_ib, objects in ib_to_objects.items():
                if len(objects) == 0:
                    continue

                alias_name = draw_ib_to_alias.get(draw_ib, draw_ib)
                ib_collection_name = f"{draw_ib}_{alias_name}"
                ib_collection = bpy.data.collections.new(ib_collection_name)
                tab_collection.children.link(ib_collection)
                ib_collection.color_tag = CollectionColor.Blue

                for obj in objects:
                    parent_collection.objects.unlink(obj)
                    ib_collection.objects.link(obj)

            print(f"[Import3DMigotoRaw] 创建分组 '{tab_name}', 包含 {len(ib_to_objects)} 个 IB 子分组")

    def _find_workspace_collection(self, collection):
        for col in bpy.data.collections:
            if col.name.startswith(GlobalConfig.workspacename):
                return col
        return None

def register():
    bpy.utils.register_class(Import3DMigotoRaw)

def unregister():
    bpy.utils.unregister_class(Import3DMigotoRaw)
