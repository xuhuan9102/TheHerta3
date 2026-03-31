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
        submesh_obj_list = []
        processed_obj_names = {}
        
        for draw_call_model in self.drawcall_model_list:
            source_obj = ObjUtils.get_obj_by_name(draw_call_model.obj_name)
            if source_obj is None:
                continue

            draw_call_model.vertex_count = len(source_obj.data.vertices)
            draw_call_model.index_count = len(source_obj.data.polygons) * 3
            
            if draw_call_model.obj_name in processed_obj_names:
                draw_call_model.index_offset = processed_obj_names[draw_call_model.obj_name]
            else:
                draw_call_model.index_offset = index_offset
                processed_obj_names[draw_call_model.obj_name] = index_offset
                index_offset += draw_call_model.index_count
                submesh_obj_list.append(source_obj)

            self.vertex_count += draw_call_model.vertex_count
            self.index_count += draw_call_model.index_count

        if not submesh_obj_list:
            return

        mesh_objects = [obj for obj in submesh_obj_list if obj and obj.type == 'MESH']
        if not mesh_objects:
            print(f"SubMeshModel 警告: {self.unique_str} 没有网格对象可处理")
            return

        should_delete_merged = False
        submesh_merged_obj = None
        temp_obj_copies = []
        
        if len(mesh_objects) == 1:
            submesh_merged_obj = mesh_objects[0]
        else:
            for obj in mesh_objects:
                temp_copy = obj.copy()
                temp_copy.data = obj.data.copy()
                bpy.context.scene.collection.objects.link(temp_copy)
                temp_copy.hide_set(False)
                temp_copy.hide_viewport = False
                temp_obj_copies.append(temp_copy)
            
            first_temp = temp_obj_copies[0]
            
            bpy.ops.object.select_all(action='DESELECT')
            for temp_obj in temp_obj_copies:
                temp_obj.select_set(True)
            bpy.context.view_layer.objects.active = first_temp

            ObjUtils.join_objects(bpy.context, temp_obj_copies)

            submesh_merged_obj = bpy.data.objects.get(first_temp.name)
            if submesh_merged_obj is None:
                print(f"SubMeshModel 错误: 合并后找不到临时对象 {first_temp.name}")
                for tc in temp_obj_copies:
                    try:
                        if tc.name in bpy.data.objects:
                            bpy.data.objects.remove(tc, do_unlink=True)
                    except:
                        pass
                return
            should_delete_merged = True

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

        if should_delete_merged:
            bpy.data.objects.remove(submesh_merged_obj, do_unlink=True)
            print("SubMeshModel: " + self.unique_str + " 计算完成，合并临时对象已删除")
        else:
            print("SubMeshModel: " + self.unique_str + " 计算完成，单对象保留由清理流程处理")
