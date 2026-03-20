from dataclasses import dataclass, field
from typing import Dict
import bpy
import os


@dataclass
class SubMeshModel:
    drawcall_model_list: list = field(default_factory=list)
    match_draw_ib: str = field(init=False, default="")
    match_first_index: str = field(init=False, default="")
    match_index_count: str = field(init=False, default="")
    unique_str: str = field(init=False, default="")
    vertex_count: int = field(init=False, default=0)
    index_count: int = field(init=False, default=0)
    d3d11_game_type: object = field(init=False, repr=False, default=None)
    ib: list = field(init=False, repr=False, default_factory=list)
    category_buffer_dict: dict = field(init=False, repr=False, default_factory=dict)
    index_vertex_id_dict: dict = field(init=False, repr=False, default_factory=dict)
    _global_config: object = field(init=False, repr=False, default=None)

    def __post_init__(self):
        if len(self.drawcall_model_list) > 0:
            first_model = self.drawcall_model_list[0]
            self.match_draw_ib = getattr(first_model, 'match_draw_ib', '')
            self.match_first_index = getattr(first_model, 'match_first_index', '')
            self.match_index_count = getattr(first_model, 'match_index_count', '')
            if hasattr(first_model, 'get_unique_str'):
                self.unique_str = first_model.get_unique_str()
            else:
                self.unique_str = f"{self.match_draw_ib}-{self.match_first_index}"
        
        self.calc_buffer()

    def _get_global_config(self):
        if self._global_config is None:
            from ...config.main_config import GlobalConfig
            self._global_config = GlobalConfig
        return self._global_config

    def calc_buffer(self):
        from ...utils.obj_utils import ObjUtils
        from ...utils.collection_utils import CollectionUtils
        from ...utils.json_utils import JsonUtils
        from ...base.d3d11_gametype import D3D11GameType
        from ...helper.obj_buffer_helper import ObjBufferHelper
        from ...common.obj_element_model import ObjElementModel
        from ...common.obj_buffer_model_unity import ObjBufferModelUnity
        
        GlobalConfig = self._get_global_config()
        
        folder_name = self.unique_str

        import_json_path = os.path.join(GlobalConfig.path_workspace_folder(), "Import.json")
        import_json = JsonUtils.LoadFromFile(import_json_path)
        gametype_name = import_json.get(folder_name, "")
        
        if gametype_name:
            gametype_foldername = "TYPE_" + gametype_name
            import_folder_path = os.path.join(GlobalConfig.path_workspace_folder(), folder_name)
            game_import_json_path = os.path.join(import_folder_path, gametype_foldername, "import.json")

            if os.path.exists(game_import_json_path):
                self.d3d11_game_type = D3D11GameType(FilePath=game_import_json_path)

                for draw_call_model in self.drawcall_model_list:
                    source_obj = ObjUtils.get_obj_by_name(draw_call_model.obj_name)
                    if source_obj is None:
                        continue
                    ObjBufferHelper.check_and_verify_attributes(obj=source_obj, d3d11_game_type=self.d3d11_game_type)
        
        index_offset = 0
        submesh_temp_obj_list = []
        temp_collection = None
        
        for draw_call_model in self.drawcall_model_list:
            source_obj = ObjUtils.get_obj_by_name(draw_call_model.obj_name)
            if source_obj is None:
                continue

            if temp_collection is None:
                temp_collection = CollectionUtils.create_new_collection("TEMP_SUBMESH_COLLECTION_" + self.unique_str)
                bpy.context.scene.collection.children.link(temp_collection)

            temp_obj = ObjUtils.copy_object(
                context=bpy.context,
                obj=source_obj,
                name=source_obj.name + "_temp",
                collection=temp_collection
            )

            ObjUtils.triangulate_object(bpy.context, temp_obj)

            draw_call_model.vertex_count = len(temp_obj.data.vertices)
            draw_call_model.index_count = len(temp_obj.data.polygons) * 3
            draw_call_model.index_offset = index_offset

            index_offset += draw_call_model.index_count

            self.vertex_count += draw_call_model.vertex_count
            self.index_count += draw_call_model.index_count

            submesh_temp_obj_list.append(temp_obj)

        if not submesh_temp_obj_list:
            return

        if submesh_temp_obj_list:
            bpy.ops.object.select_all(action='DESELECT')
            target_active = submesh_temp_obj_list[0]
            target_active.select_set(True)
            bpy.context.view_layer.objects.active = target_active

        ObjUtils.join_objects(bpy.context, submesh_temp_obj_list)

        submesh_merged_obj = submesh_temp_obj_list[0]
        merged_obj_name = "TEMP_SUBMESH_MERGED_" + self.unique_str
        ObjUtils.rename_object(submesh_merged_obj, merged_obj_name)

        if self.d3d11_game_type:
            obj_element_model = ObjElementModel(d3d11_game_type=self.d3d11_game_type, obj_name=submesh_merged_obj.name)

            obj_element_model.element_vertex_ndarray = ObjBufferHelper.convert_to_element_vertex_ndarray(
                original_elementname_data_dict=obj_element_model.original_elementname_data_dict,
                final_elementname_data_dict={},
                mesh=obj_element_model.mesh,
                d3d11_game_type=self.d3d11_game_type
            )

            obj_buffer_model = ObjBufferModelUnity(obj=submesh_merged_obj, d3d11_game_type=self.d3d11_game_type)
            self.ib = obj_buffer_model.ib
            self.category_buffer_dict = obj_buffer_model.category_buffer_dict
            self.index_vertex_id_dict = obj_buffer_model.index_loop_id_dict

        bpy.data.objects.remove(submesh_merged_obj, do_unlink=True)

        if temp_collection:
            bpy.context.scene.collection.children.unlink(temp_collection)
            bpy.data.collections.remove(temp_collection)

        print("SubMeshModel: " + self.unique_str + " 计算完成，临时对象已删除")
