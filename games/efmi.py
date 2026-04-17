import bpy
import math
import os
import shutil

from ..config.main_config import GlobalConfig,LogicName
from ..common.draw_ib_model import DrawIBModel

from ..base.m_global_key_counter import M_GlobalKeyCounter
from ..blueprint.blueprint_model import BluePrintModel
from ..blueprint.blueprint_export_helper import BlueprintExportHelper

from ..common.m_ini_builder import M_IniBuilder,M_IniSection,M_SectionType
from ..config.properties_generate_mod import Properties_GenerateMod
from ..common.m_ini_helper import M_IniHelper,M_IniHelper
from ..common.m_ini_helper_gui import M_IniHelperGUI


class DrawIBModelAdapter:
    '''
    SSMT4 DrawIBModel 适配器
    将 SubMeshModel 适配为 DrawIBModel 接口
    '''
    def __init__(self, submesh_model, branch_model_v4):
        from ..base.m_draw_indexed import M_DrawIndexed
        from ..config.import_config import ImportConfig
        
        self.draw_ib = submesh_model.match_draw_ib
        self.draw_ib_alias = submesh_model.match_draw_ib
        self.d3d11GameType = submesh_model.d3d11_game_type
        self.draw_number = submesh_model.vertex_count
        self.unique_str = submesh_model.unique_str
        
        unique_str = submesh_model.unique_str
        
        self.PartName_IBResourceName_Dict = {
            "1": f"Resource_{unique_str.replace('-', '_')}_Index"
        }
        self.PartName_IBBufferFileName_Dict = {
            "1": f"{unique_str}-Index.buf"
        }
        self.componentname_ibbuf_dict = {
            "Component 1": submesh_model.ib
        }
        
        self.category_hash_dict = {}
        if submesh_model.d3d11_game_type:
            self.category_hash_dict = getattr(submesh_model.d3d11_game_type, 'CategoryHashDict', {})
        
        # 初始化 import_config
        # 传递 unique_str 以支持 SSMT4 命名格式
        self.import_config = ImportConfig(draw_ib=self.draw_ib, unique_str=unique_str)
        
        drawcall_model_list = submesh_model.drawcall_model_list
        for drawcall_model in drawcall_model_list:
            drawcall_model.drawindexed_obj = M_DrawIndexed()
            drawcall_model.drawindexed_obj.DrawNumber = str(drawcall_model.index_count)
            drawcall_model.drawindexed_obj.DrawOffsetIndex = str(drawcall_model.index_offset)
            drawcall_model.drawindexed_obj.UniqueVertexCount = drawcall_model.vertex_count
        
        self._component_model = ComponentModelAdapter(drawcall_model_list)
        self.component_name_component_model_dict = {
            "Component 1": self._component_model
        }
        
        self.key_number = len(branch_model_v4.keyname_mkey_dict) if branch_model_v4 else 0


class ComponentModelAdapter:
    '''
    SSMT4 ComponentModel 适配器
    '''
    def __init__(self, drawcall_model_list):
        self.component_name = "Component 1"
        self.final_ordered_draw_obj_model_list = drawcall_model_list


class ModModelEFMI:
    def __init__(self, skip_buffer_export:bool = False, use_ssmt4:bool = False):
        self.use_ssmt4 = use_ssmt4
        
        if use_ssmt4:
            from ..common.export.blueprint_model_v4 import BluePrintModel_V4
            from ..common.export.submesh_model import SubMeshModel
            
            self.branch_model = BluePrintModel_V4()
            tree = BlueprintExportHelper.get_current_blueprint_tree()
            if tree:
                self.branch_model.initialize_from_tree(tree)
                print(f"ModModelEFMI SSMT4: 解析完成，共收集 {len(self.branch_model.ordered_draw_obj_data_model_list)} 个物体")
            
            self.drawib_drawibmodel_dict: dict = {}
            self._submesh_model_list: list = []
            self._init_submesh_models(skip_buffer_export)
        else:
            self.branch_model = BluePrintModel()
            self.drawib_drawibmodel_dict: dict[str, DrawIBModel] = {}
            self.parse_draw_ib_draw_ib_model_dict(skip_buffer_export)

        self.vlr_filter_index_indent = ""
        self.texture_hash_filter_index_dict = {}
        
        self.cross_ib_info_dict = self.branch_model.cross_ib_info_dict
        self.cross_ib_method_dict = getattr(self.branch_model, 'cross_ib_method_dict', {})
        self.has_cross_ib = len(self.cross_ib_info_dict) > 0
        self.cross_ib_mapping_objects = getattr(self.branch_model, 'cross_ib_mapping_objects', {})
        self.cross_ib_vb_condition_mapping = getattr(self.branch_model, 'cross_ib_vb_condition_mapping', {})
        self.cross_ib_source_to_target_dict = getattr(self.branch_model, 'cross_ib_source_to_target_dict', {})
        self.cross_ib_object_vb_condition = getattr(self.branch_model, 'cross_ib_object_vb_condition', {})
        
        if use_ssmt4:
            self.cross_ib_target_info = getattr(self.branch_model, 'cross_ib_target_info', {})
            self.cross_ib_match_mode = getattr(self.branch_model, 'cross_ib_match_mode', 'IB_HASH')
            print(f"[CrossIB EFMI] SSMT4 模式，match_mode={self.cross_ib_match_mode}")
            print(f"[CrossIB EFMI] cross_ib_info_dict={self.cross_ib_info_dict}")
            print(f"[CrossIB EFMI] cross_ib_target_info={self.cross_ib_target_info}")
            print(f"[CrossIB EFMI] cross_ib_object_names={self.branch_model.cross_ib_object_names}")
            print(f"[CrossIB EFMI] cross_ib_mapping_objects={self.cross_ib_mapping_objects}")
            print(f"[CrossIB EFMI] cross_ib_vb_condition_mapping={self.cross_ib_vb_condition_mapping}")
        else:
            self.cross_ib_target_info = {}
            self.cross_ib_match_mode = 'IB_HASH'
    
    def _get_vb_condition_for_mapping(self, source_ib_key: str, target_ib_key: str, condition_type: str = 'source') -> str:
        mapping_key = (source_ib_key, target_ib_key)
        condition_info = self.cross_ib_vb_condition_mapping.get(mapping_key, {})
        if condition_type == 'source':
            return condition_info.get('source', "if vs == 200 || vs == 201 || vs == 204")
        else:
            return condition_info.get('target', "if vs == 202 || vs == 203")
    
    def _get_vb_condition_for_object(self, obj_name: str, source_ib_key: str, target_ib_key: str, condition_type: str = 'source') -> str:
        object_mapping_key = (obj_name, source_ib_key, target_ib_key)
        condition_info = self.cross_ib_object_vb_condition.get(object_mapping_key, {})
        if condition_type == 'source':
            return condition_info.get('source', "if vs == 200 || vs == 201 || vs == 204")
        else:
            return condition_info.get('target', "if vs == 202 || vs == 203")
    
    def _group_objects_by_vb_condition(self, objects, source_ib_key: str, target_ib_key: str, condition_type: str = 'source') -> dict:
        grouped = {}
        print(f"[CrossIB EFMI] _group_objects_by_vb_condition: source_ib_key={source_ib_key}, target_ib_key={target_ib_key}")
        print(f"[CrossIB EFMI] cross_ib_object_vb_condition keys: {self.cross_ib_object_vb_condition.keys()}")
        for obj in objects:
            obj_name = obj.obj_name if hasattr(obj, 'obj_name') else str(obj)
            vb_condition = self._get_vb_condition_for_object(obj_name, source_ib_key, target_ib_key, condition_type)
            print(f"[CrossIB EFMI] 检查物体: {obj_name}, VB条件: {vb_condition}")
            if vb_condition not in grouped:
                grouped[vb_condition] = []
            grouped[vb_condition].append(obj)
        return grouped

    def _group_objects_by_cross_ib_target(self, objects, source_ib_key: str, target_ib_keys: list) -> dict:
        """
        按目标 IB 和 VB 条件对物体进行分组
        返回: {(target_ib_key, vb_condition): [objects]}
        """
        grouped = {}
        cross_ib_mapping_objects = self.cross_ib_mapping_objects
        
        for obj in objects:
            obj_name = obj.obj_name if hasattr(obj, 'obj_name') else str(obj)
            
            for target_ib_key in target_ib_keys:
                mapping_key = (source_ib_key, target_ib_key)
                if mapping_key in cross_ib_mapping_objects:
                    if obj_name in cross_ib_mapping_objects[mapping_key]:
                        vb_condition = self._get_vb_condition_for_object(obj_name, source_ib_key, target_ib_key, 'source')
                        group_key = (target_ib_key, vb_condition)
                        if group_key not in grouped:
                            grouped[group_key] = []
                        grouped[group_key].append(obj)
                        break
        
        return grouped

    def _init_submesh_models(self, skip_buffer_export: bool = False):
        from ..common.export.submesh_model import SubMeshModel
        
        draw_call_model_dict: dict = {}
        
        for draw_call_model in self.branch_model.ordered_draw_obj_data_model_list:
            unique_str = draw_call_model.get_unique_str()
            draw_call_model_list = draw_call_model_dict.get(unique_str, [])
            draw_call_model_list.append(draw_call_model)
            draw_call_model_dict[unique_str] = draw_call_model_list

        for unique_str, draw_call_model_list in draw_call_model_dict.items():
            has_multifile = len(self.branch_model.multifile_export_nodes) > 0
            submesh_model = SubMeshModel(drawcall_model_list=draw_call_model_list, use_temp_copy_for_merge=has_multifile)
            self._submesh_model_list.append(submesh_model)
            
            adapter = DrawIBModelAdapter(submesh_model, self.branch_model)
            adapter_key = f"{adapter.draw_ib}_{submesh_model.match_index_count}"
            self.drawib_drawibmodel_dict[adapter_key] = adapter
        
        if not skip_buffer_export:
            self._export_buffers()
    
    def _export_buffers(self):
        import struct
        
        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()

        for submesh_model in self._submesh_model_list:
            if len(submesh_model.ib) > 0:
                ib_filename = submesh_model.unique_str + "-Index.buf"
                ib_filepath = os.path.join(buf_output_folder, ib_filename)
                packed_data = struct.pack(f'<{len(submesh_model.ib)}I', *submesh_model.ib)
                with open(ib_filepath, 'wb') as ibf:
                    ibf.write(packed_data)

            for category, category_buf in submesh_model.category_buffer_dict.items():
                category_buf_filename = submesh_model.unique_str + "-" + category + ".buf"
                category_buf_filepath = os.path.join(buf_output_folder, category_buf_filename)
                with open(category_buf_filepath, 'wb') as f:
                    category_buf.tofile(f)

    def parse_draw_ib_draw_ib_model_dict(self, skip_buffer_export:bool = False):
        for draw_ib in self.branch_model.draw_ib__component_count_list__dict.keys():
            draw_ib_model = DrawIBModel(draw_ib=draw_ib,branch_model=self.branch_model, skip_buffer_export=skip_buffer_export)
            self.drawib_drawibmodel_dict[draw_ib] = draw_ib_model

    def add_cross_ib_present_section(self, ini_builder:M_IniBuilder):
        if not self.has_cross_ib:
            return
        
        present_section = M_IniSection(M_SectionType.CrossIBPresent)
        present_section.append(";特殊追加固定区域")
        present_section.append("[Present]")
        present_section.append("ResourcePrev_SRV = ResourceFakeT0_SRV")
        present_section.new_line()
        
        present_section.append("[ResourceDumpedCB1_UAV]")
        present_section.append("type = RWStructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceDumpedCB1_SRV]")
        present_section.append("type = Buffer")
        present_section.append("stride = 16")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceFakeCB1_UAV]")
        present_section.append("type = RWStructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceFakeCB1]")
        present_section.append("type = Buffer")
        present_section.append("stride = 16")
        present_section.append("format = R32G32B32A32_UINT")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceFakeT0_UAV]")
        present_section.append("type = RWStructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 200000")
        present_section.new_line()
        
        present_section.append("[ResourceFakeT0_SRV]")
        present_section.append("type = StructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 200000")
        present_section.new_line()
        
        present_section.append("[ResourcePrev_SRV]")
        present_section.append("type = StructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 200000")
        present_section.new_line()
        
        present_section.append("[CustomShader_ExtractCB1]")
        present_section.append("vs = ./res/extract_cb1_vs.hlsl")
        present_section.append("ps = ./res/extract_cb1_ps.hlsl")
        present_section.append("ps-u7 = ResourceDumpedCB1_UAV")
        present_section.append("depth_enable = false")
        present_section.append("blend = ADD SRC_ALPHA INV_SRC_ALPHA")
        present_section.append("cull = none")
        present_section.append("topology = point_list")
        present_section.append("draw = 4096, 0")
        present_section.append("ps-u7 = null")
        present_section.append("ResourceDumpedCB1_SRV = copy ResourceDumpedCB1_UAV")
        present_section.new_line()
        
        present_section.append("[CustomShader_RecordBones]")
        present_section.append("cs = ./res/record_bones_cs.hlsl")
        present_section.append("cs-t0 = vs-t0")
        present_section.append("cs-t1 = ResourceDumpedCB1_SRV")
        present_section.append("cs-u1 = ResourceFakeT0_UAV")
        present_section.append("dispatch = 12, 1, 1")
        present_section.append("cs-u1 = null")
        present_section.append("cs-t0 = null")
        present_section.append("cs-t1 = null")
        present_section.append("ResourceFakeT0_SRV = copy ResourceFakeT0_UAV")
        present_section.new_line()
        
        present_section.append("[CustomShader_RedirectCB1]")
        present_section.append("cs = ./res/redirect_cb1_cs.hlsl")
        present_section.append("cs-t0 = ResourceDumpedCB1_SRV")
        present_section.append("ResourceFakeCB1_UAV = copy ResourceDumpedCB1_SRV")
        present_section.append("cs-u0 = ResourceFakeCB1_UAV")
        present_section.append("dispatch = 4, 1, 1")
        present_section.append("cs-u0 = null")
        present_section.append("cs-t0 = null")
        present_section.append("ResourceFakeCB1 = copy ResourceFakeCB1_UAV")
        present_section.new_line()
        
        shader_overrides = [
            ("ShaderOverridevs1000", "241383a9d64b4978", "200"),
            ("ShaderOverridevs1001", "6733250da4e23fd6", "200"),
            ("ShaderOverridevs1002", "9bac7486f7930a24", "201"),
            ("ShaderOverridevs1003", "b30cc5ad521e0700", "202"),
            ("ShaderOverridevs1004", "4921f64a7c74226d", "203"),
            ("ShaderOverridevs1005", "1b835d0e8dbbfb8f", "203"),
            ("ShaderOverridevs1006", "06c94dd56f447210", "204"),
            ("ShaderOverridevs1007", "f47b1f797f5831d0", "204"),
        ]
        
        
        for name, hash_val, filter_idx in shader_overrides:
            present_section.append(f"[{name}]")
            present_section.append(f"hash = {hash_val}")
            present_section.append(f"filter_index = {filter_idx}")
            present_section.new_line()
        
        ini_builder.append_section(present_section)

    def add_cross_ib_resource_id_sections(self, ini_builder:M_IniBuilder):
        if not self.has_cross_ib:
            return
        
        resource_id_section = M_IniSection(M_SectionType.ResourceID)
        resource_id_section.append(";特殊追加身份证区域")
        
        all_identifiers = set()
        
        if self.use_ssmt4 and self.cross_ib_match_mode == 'INDEX_COUNT':
            for source_key, target_key_list in self.cross_ib_info_dict.items():
                if source_key.startswith('indexcount_'):
                    index_count = source_key.replace('indexcount_', '')
                    all_identifiers.add(index_count)
                for target_key in target_key_list:
                    if target_key.startswith('indexcount_'):
                        index_count = target_key.replace('indexcount_', '')
                        all_identifiers.add(index_count)
            
            for submesh_model in self._submesh_model_list:
                if submesh_model.match_index_count:
                    all_identifiers.add(submesh_model.match_index_count)
        else:
            for source_ib, target_ib_list in self.cross_ib_info_dict.items():
                source_hash = source_ib.split("_")[0]
                all_identifiers.add(source_hash)
                for target_ib in target_ib_list:
                    target_hash = target_ib.split("_")[0]
                    all_identifiers.add(target_hash)
            
            for adapter_key in self.drawib_drawibmodel_dict.keys():
                draw_ib = adapter_key.split("_")[0]
                all_identifiers.add(draw_ib)
        
        sorted_identifiers = sorted(list(all_identifiers))
        
        for idx, identifier in enumerate(sorted_identifiers):
            resource_id_section.append(f"[ResourceID_{identifier}]")
            resource_id_section.append("type = Buffer")
            resource_id_section.append("format = R32_FLOAT")
            resource_id_section.append(f"data = {idx * 1000}.0")
            resource_id_section.new_line()
        
        ini_builder.append_section(resource_id_section)

    def get_cross_ib_objects_for_source(self, source_ib):
        cross_ib_objects = []
        
        for obj_model in self.branch_model.ordered_draw_obj_data_model_list:
            if self.use_ssmt4:
                if hasattr(obj_model, 'match_draw_ib') and obj_model.match_draw_ib == source_ib:
                    cross_ib_objects.append(obj_model)
            else:
                if obj_model.draw_ib == source_ib:
                    cross_ib_objects.append(obj_model)
        
        return cross_ib_objects

    def _split_objects_by_cross_ib(self, obj_model_list, source_ib_key=None, target_ib_key=None):
        cross_ib_objects = []
        non_cross_ib_objects = []
        
        cross_ib_object_names = self.branch_model.cross_ib_object_names
        cross_ib_mapping_objects = self.cross_ib_mapping_objects
        
        if source_ib_key:
            specific_cross_ib_objects = set()
            
            if target_ib_key:
                mapping_key = (source_ib_key, target_ib_key)
                specific_cross_ib_objects = cross_ib_mapping_objects.get(mapping_key, set())
            else:
                for (src_key, tgt_key), obj_names in cross_ib_mapping_objects.items():
                    if src_key == source_ib_key:
                        specific_cross_ib_objects.update(obj_names)
            
            for obj_model in obj_model_list:
                obj_name = obj_model.obj_name if hasattr(obj_model, 'obj_name') else getattr(obj_model, 'obj_name', '')
                if obj_name in specific_cross_ib_objects:
                    cross_ib_objects.append(obj_model)
                else:
                    non_cross_ib_objects.append(obj_model)
        else:
            for obj_model in obj_model_list:
                obj_name = obj_model.obj_name if hasattr(obj_model, 'obj_name') else getattr(obj_model, 'obj_name', '')
                if obj_name in cross_ib_object_names:
                    cross_ib_objects.append(obj_model)
                else:
                    non_cross_ib_objects.append(obj_model)
        
        return cross_ib_objects, non_cross_ib_objects

    def generate_cross_ib_block_for_source(self, source_identifier, component_model, source_ib_key=None, target_ib_key=None):
        lines = []
        
        cross_ib_objects, non_cross_ib_objects = self._split_objects_by_cross_ib(
            component_model.final_ordered_draw_obj_model_list,
            source_ib_key=source_ib_key
        )
        
        target_ib_keys = self.cross_ib_source_to_target_dict.get(source_ib_key, [])
        if target_ib_key and target_ib_key not in target_ib_keys:
            target_ib_keys.append(target_ib_key)
        
        grouped_objects = self._group_objects_by_cross_ib_target(cross_ib_objects, source_ib_key, target_ib_keys)
        
        for (tgt_ib_key, vb_condition), objects in grouped_objects.items():
            if not objects:
                continue
            
            lines.append(";跨 iB 区域")
            lines.append(vb_condition)
            lines.append("    run = CustomShader_ExtractCB1")
            lines.append(f"    cs-t2 = ResourceID_{source_identifier}")
            lines.append("    run = CustomShader_RecordBones")
            lines.append("    run = CustomShader_RedirectCB1")
            lines.append("    vs-t0 = ResourceFakeT0_SRV")
            lines.append("    vs-cb1 = ResourceFakeCB1")
            lines.append(";所有需要跨 Ib 的物体引用")
            
            drawindexed_str_list = self._get_drawindexed_str_list(objects)
            for drawindexed_str in drawindexed_str_list:
                if drawindexed_str.strip():
                    lines.append(drawindexed_str)
            
            lines.append("endif")
        
        lines.append(";不需要跨 Ib 的物体引用")
        
        if non_cross_ib_objects:
            drawindexed_str_list = self._get_drawindexed_str_list(non_cross_ib_objects)
            for drawindexed_str in drawindexed_str_list:
                if drawindexed_str.strip():
                    lines.append(drawindexed_str)
        
        lines.append("")
        lines.append("post vs-cb1 = null")
        lines.append("post vs-t0 = null")
        lines.append("post cs-t2 = null")
        
        return lines
    
    def _get_drawindexed_str_list(self, obj_model_list):
        if self.use_ssmt4:
            return self._get_drawindexed_str_list_v4(obj_model_list)
        else:
            return M_IniHelper.get_drawindexed_instanced_str_list(obj_model_list)
    
    def _get_drawindexed_str_list_v4(self, drawcall_model_list):
        from ..base.m_draw_indexed import M_DrawIndexedInstanced
        
        condition_str_obj_list_dict: dict = {}
        for drawcall_model in drawcall_model_list:
            condition_str = ""
            if hasattr(drawcall_model, 'condition') and drawcall_model.condition:
                condition_str = getattr(drawcall_model.condition, 'condition_str', '')
            
            obj_list = condition_str_obj_list_dict.get(condition_str, [])
            obj_list.append(drawcall_model)
            condition_str_obj_list_dict[condition_str] = obj_list
        
        drawindexed_str_list = []
        for condition_str, obj_list in condition_str_obj_list_dict.items():
            if condition_str != "":
                drawindexed_str_list.append(f"if {condition_str}")
                for drawcall_model in obj_list:
                    display_name = getattr(drawcall_model, 'display_name', drawcall_model.obj_name)
                    vertex_count = getattr(drawcall_model, 'vertex_count', 0)
                    drawindexed_str_list.append(f"  ; [mesh:{display_name}] [vertex_count:{vertex_count}]")
                    
                    drawindexed_instanced = M_DrawIndexedInstanced()
                    drawindexed_instanced.IndexCountPerInstance = drawcall_model.index_count
                    drawindexed_instanced.StartIndexLocation = drawcall_model.index_offset
                    drawindexed_str_list.append("  " + drawindexed_instanced.get_draw_str())
                drawindexed_str_list.append("endif")
            else:
                for drawcall_model in obj_list:
                    display_name = getattr(drawcall_model, 'display_name', drawcall_model.obj_name)
                    vertex_count = getattr(drawcall_model, 'vertex_count', 0)
                    drawindexed_str_list.append(f"; [mesh:{display_name}] [vertex_count:{vertex_count}]")
                    
                    drawindexed_instanced = M_DrawIndexedInstanced()
                    drawindexed_instanced.IndexCountPerInstance = drawcall_model.index_count
                    drawindexed_instanced.StartIndexLocation = drawcall_model.index_offset
                    drawindexed_str_list.append(drawindexed_instanced.get_draw_str())
            drawindexed_str_list.append("")
        
        return drawindexed_str_list

    def add_unity_vs_texture_override_ib_sections(self, config_ini_builder:M_IniBuilder, commandlist_ini_builder:M_IniBuilder, draw_ib_model, is_cross_ib_source=False, is_cross_ib_target=False, source_ib_list_for_target=None, part_name=None, match_first_index="0", match_index_count=0, current_identifier=None):
        if source_ib_list_for_target is None:
            source_ib_list_for_target = []
        
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib
        
        if current_identifier is None:
            if self.use_ssmt4 and self.cross_ib_match_mode == 'INDEX_COUNT':
                current_identifier = str(match_index_count) if match_index_count > 0 else draw_ib
            else:
                current_identifier = draw_ib
        
        d3d11GameType = draw_ib_model.d3d11GameType

        if self.use_ssmt4:
            texture_override_name_suffix = draw_ib + "_" + str(match_index_count) + "_" + str(match_first_index)
        else:
            style_part_name = "Component" + part_name
            texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name

        ib_resource_name = ""
        if self.use_ssmt4:
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get("1", "")
        else:
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(part_name, None)

        texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
        texture_override_ib_section.append("hash = " + draw_ib)
        texture_override_ib_section.append("match_first_index = " + match_first_index)
        
        if self.use_ssmt4 and match_index_count > 0:
            texture_override_ib_section.append("match_index_count = " + str(match_index_count))

        if self.vlr_filter_index_indent != "":
            texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

        texture_override_ib_section.append(self.vlr_filter_index_indent + "handling = skip")
        
        if is_cross_ib_target:
            texture_override_ib_section.append(self.vlr_filter_index_indent + "analyse_options = deferred_ctx_immediate dump_rt dump_cb dump_vb dump_ib buf txt dds dump_tex dds symlink")

        component_name = "Component 1" if self.use_ssmt4 else "Component " + part_name
        ib_buf = draw_ib_model.componentname_ibbuf_dict.get(component_name, None)
        if ib_buf is None or len(ib_buf) == 0:
            texture_override_ib_section.append("ib = null")
            texture_override_ib_section.new_line()
            config_ini_builder.append_section(texture_override_ib_section)
            return

        texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CommandList\\EFMIv1\\OverrideTextures")

        # 槽位贴图生成逻辑（SSMT3 和 SSMT4 模式都支持）
        if not Properties_GenerateMod.forbid_auto_texture_ini():
            # SSMT4 模式下使用 unique_str 作为 part_name，SSMT3 模式下使用 part_name
            texture_part_name = draw_ib_model.unique_str if self.use_ssmt4 else part_name
            print(f"调试: 查找贴图标记，texture_part_name = {texture_part_name}")
            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(texture_part_name, None)
            print(f"调试: 找到的贴图标记数量 = {len(texture_markup_info_list) if texture_markup_info_list else 0}")
            
            if texture_markup_info_list is not None:
                if Properties_GenerateMod.use_rabbitfx_slot():
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            if texture_markup_info.mark_name == "DiffuseMap":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\Diffuse = ref " + texture_markup_info.get_resource_name())
                            elif texture_markup_info.mark_name == "LightMap":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\LightMap = ref " + texture_markup_info.get_resource_name())
                            elif texture_markup_info.mark_name == "NormalMap":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\NormalMap = ref " + texture_markup_info.get_resource_name())
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CommandList\\RabbitFx\\SetTextures")
                    
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            if texture_markup_info.mark_name in ["DiffuseMap", "LightMap", "NormalMap"]:
                                pass
                            else:
                                texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())
                else:
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

        texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = ref " + ib_resource_name)

        if d3d11GameType:
            if self.use_ssmt4:
                unique_str = draw_ib_model.unique_str
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb0 = ref Resource_" + unique_str.replace('-', '_') + "_Position")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb1 = ref Resource_" + unique_str.replace('-', '_') + "_Texcoord")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb2 = ref Resource_" + unique_str.replace('-', '_') + "_Blend")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb3 = ref Resource_" + unique_str.replace('-', '_') + "_Position")
            else:
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb0 = ref Resource" + draw_ib + "Position")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb1 = ref Resource" + draw_ib + "Texcoord")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb2 = ref Resource" + draw_ib + "Blend")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb3 = ref Resource" + draw_ib + "Position")

        if self.has_cross_ib and (is_cross_ib_source or is_cross_ib_target):
            texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_ExtractCB1")
            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    cs-t2 = ResourceID_{current_identifier}")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RecordBones")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RedirectCB1")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "    vs-t0 = ResourceFakeT0_SRV")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "    vs-cb1 = ResourceFakeCB1")

        component_model = draw_ib_model.component_name_component_model_dict.get(component_name)
        if component_model is None:
            component_model = draw_ib_model.component_name_component_model_dict.get("Component 1")

        if self.use_ssmt4 and self.cross_ib_match_mode == 'INDEX_COUNT':
            current_ib_key = f"indexcount_{current_identifier}" if str(current_identifier).isdigit() else current_identifier
        else:
            current_ib_key = f"{current_identifier}_1"
        
        is_both_source_and_target = is_cross_ib_source and is_cross_ib_target and self.has_cross_ib
        
        if is_both_source_and_target:
            cross_ib_objects_from_source, non_cross_ib_objects = self._split_objects_by_cross_ib(
                component_model.final_ordered_draw_obj_model_list,
                source_ib_key=current_ib_key
            )
            
            target_ib_keys = self.cross_ib_source_to_target_dict.get(current_ib_key, [])
            grouped_source_objects = self._group_objects_by_cross_ib_target(cross_ib_objects_from_source, current_ib_key, target_ib_keys)
            
            for (target_ib_key, vb_condition), objects in grouped_source_objects.items():
                if not objects:
                    continue
                
                texture_override_ib_section.append(self.vlr_filter_index_indent + ";跨 iB 区域")
                texture_override_ib_section.append(self.vlr_filter_index_indent + vb_condition)
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_ExtractCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + f"    cs-t2 = ResourceID_{current_identifier}")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RecordBones")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RedirectCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    vs-t0 = ResourceFakeT0_SRV")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    vs-cb1 = ResourceFakeCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + ";所有需要跨 Ib 的物体引用")
                
                drawindexed_str_list = self._get_drawindexed_str_list(objects)
                for drawindexed_str in drawindexed_str_list:
                    if drawindexed_str.strip():
                        texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
                
                texture_override_ib_section.append(self.vlr_filter_index_indent + "endif")
            
            texture_override_ib_section.append(self.vlr_filter_index_indent + ";不需要跨 Ib 的物体引用")
            
            if non_cross_ib_objects:
                drawindexed_str_list = self._get_drawindexed_str_list(non_cross_ib_objects)
                for drawindexed_str in drawindexed_str_list:
                    if drawindexed_str.strip():
                        texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
            
            if is_cross_ib_target and source_ib_list_for_target:
                for source_ib in source_ib_list_for_target:
                    if self.use_ssmt4 and self.cross_ib_match_mode == 'INDEX_COUNT':
                        source_identifier = source_ib.replace('indexcount_', '') if source_ib.startswith('indexcount_') else source_ib.split("_")[0]
                        source_adapter_key = None
                        source_ib_model = None
                        for key, adapter in self.drawib_drawibmodel_dict.items():
                            if key.endswith(f"_{source_identifier}"):
                                source_adapter_key = key
                                source_ib_model = adapter
                                break
                        if source_adapter_key is None:
                            continue
                        source_hash = source_adapter_key.split("_")[0]
                    else:
                        source_hash, source_component_index = source_ib.split("_")
                        source_component_index = int(source_component_index)
                        source_identifier = source_hash
                        source_ib_model = self.drawib_drawibmodel_dict.get(source_hash)
                    
                    source_component_model = None
                    if source_ib_model:
                        src_component_name = "Component 1" if self.use_ssmt4 else f"Component {source_component_index}"
                        source_component_model = source_ib_model.component_name_component_model_dict.get(src_component_name)
                    
                    cross_objs, _ = self._split_objects_by_cross_ib(
                        source_component_model.final_ordered_draw_obj_model_list if source_component_model else [],
                        source_ib_key=source_ib,
                        target_ib_key=current_ib_key
                    )
                    
                    if not cross_objs:
                        continue
                    
                    grouped_cross_objs = self._group_objects_by_vb_condition(cross_objs, source_ib, current_ib_key, 'target')
                    
                    for vb_condition_target, objects in grouped_cross_objs.items():
                        if not objects:
                            continue
                        
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f";跨 IB 身份块,绘制 {source_identifier} 需要跨 Ib 的物体引用")
                        if vb_condition_target:
                            texture_override_ib_section.append(self.vlr_filter_index_indent + vb_condition_target)
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    cs-t2 = ResourceID_{source_identifier}")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RedirectCB1")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + "    ;跨 IB 块数据区域")
                        
                        if self.use_ssmt4 and source_ib_model:
                            source_unique_str = source_ib_model.unique_str
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb0 = Resource_{source_unique_str.replace('-', '_')}_Position")
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb1 = Resource_{source_unique_str.replace('-', '_')}_Texcoord")
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb2 = Resource_{source_unique_str.replace('-', '_')}_Blend")
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb3 = Resource_{source_unique_str.replace('-', '_')}_Position")
                            src_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get("1")
                            if src_ib_resource_name:
                                texture_override_ib_section.append(self.vlr_filter_index_indent + f"    ib = {src_ib_resource_name}")
                        else:
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb0 = Resource{source_hash}Position")
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb1 = Resource{source_hash}Texcoord")
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb2 = Resource{source_hash}Blend")
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb3 = Resource{source_hash}Position")
                            if source_ib_model:
                                src_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get("1")
                                if src_ib_resource_name:
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    ib = {src_ib_resource_name}")
                        
                        texture_override_ib_section.append(self.vlr_filter_index_indent + ";所有需要跨 Ib 的物体引用")
                        
                        drawindexed_str_list = self._get_drawindexed_str_list(objects)
                        for drawindexed_str in drawindexed_str_list:
                            if drawindexed_str.strip():
                                texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
                        
                        texture_override_ib_section.append(self.vlr_filter_index_indent + "endif")
            
            texture_override_ib_section.append(self.vlr_filter_index_indent + "")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "post vs-cb1 = null")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "post vs-t0 = null")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "post cs-t2 = null")
        
        elif is_cross_ib_source and self.has_cross_ib:
            target_ib_keys = self.cross_ib_source_to_target_dict.get(current_ib_key, [])
            target_ib_key = target_ib_keys[0] if target_ib_keys else None
            cross_ib_lines = self.generate_cross_ib_block_for_source(current_identifier, component_model, source_ib_key=current_ib_key, target_ib_key=target_ib_key)
            for line in cross_ib_lines:
                texture_override_ib_section.append(self.vlr_filter_index_indent + line)
        
        elif is_cross_ib_target and self.has_cross_ib and source_ib_list_for_target:
            all_target_objects = component_model.final_ordered_draw_obj_model_list if component_model else []
            if all_target_objects:
                drawindexed_str_list = self._get_drawindexed_str_list(all_target_objects)
                for drawindexed_str in drawindexed_str_list:
                    if drawindexed_str.strip():
                        texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
            
            for source_ib in source_ib_list_for_target:
                if self.use_ssmt4 and self.cross_ib_match_mode == 'INDEX_COUNT':
                    source_identifier = source_ib.replace('indexcount_', '') if source_ib.startswith('indexcount_') else source_ib.split("_")[0]
                    source_adapter_key = None
                    source_ib_model = None
                    for key, adapter in self.drawib_drawibmodel_dict.items():
                        if key.endswith(f"_{source_identifier}"):
                            source_adapter_key = key
                            source_ib_model = adapter
                            break
                    if source_adapter_key is None:
                        continue
                    source_hash = source_adapter_key.split("_")[0]
                else:
                    source_hash, source_component_index = source_ib.split("_")
                    source_component_index = int(source_component_index)
                    source_identifier = source_hash
                    source_ib_model = self.drawib_drawibmodel_dict.get(source_hash)
                
                source_component_model = None
                if source_ib_model:
                    src_component_name = "Component 1" if self.use_ssmt4 else f"Component {source_component_index}"
                    source_component_model = source_ib_model.component_name_component_model_dict.get(src_component_name)
                
                cross_objs, _ = self._split_objects_by_cross_ib(
                    source_component_model.final_ordered_draw_obj_model_list if source_component_model else [],
                    source_ib_key=source_ib,
                    target_ib_key=current_ib_key
                )
                
                if not cross_objs:
                    continue
                
                grouped_cross_objs = self._group_objects_by_vb_condition(cross_objs, source_ib, current_ib_key, 'target')
                
                for vb_condition_target, objects in grouped_cross_objs.items():
                    if not objects:
                        continue
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f";跨 IB 身份块,绘制 {source_identifier} 需要跨 Ib 的物体引用")
                    if vb_condition_target:
                        texture_override_ib_section.append(self.vlr_filter_index_indent + vb_condition_target)
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    cs-t2 = ResourceID_{source_identifier}")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RedirectCB1")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "    ;跨 IB 块数据区域")
                    
                    if self.use_ssmt4 and source_ib_model:
                        source_unique_str = source_ib_model.unique_str
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb0 = Resource_{source_unique_str.replace('-', '_')}_Position")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb1 = Resource_{source_unique_str.replace('-', '_')}_Texcoord")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb2 = Resource_{source_unique_str.replace('-', '_')}_Blend")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb3 = Resource_{source_unique_str.replace('-', '_')}_Position")
                        src_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get("1")
                        if src_ib_resource_name:
                            texture_override_ib_section.append(self.vlr_filter_index_indent + f"    ib = {src_ib_resource_name}")
                    else:
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb0 = Resource{source_hash}Position")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb1 = Resource{source_hash}Texcoord")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb2 = Resource{source_hash}Blend")
                        texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb3 = Resource{source_hash}Position")
                        if source_ib_model:
                            src_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get("1")
                            if src_ib_resource_name:
                                texture_override_ib_section.append(self.vlr_filter_index_indent + f"    ib = {src_ib_resource_name}")
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + ";所有需要跨 Ib 的物体引用")
                    
                    drawindexed_str_list = self._get_drawindexed_str_list(objects)
                    for drawindexed_str in drawindexed_str_list:
                        if drawindexed_str.strip():
                            texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "endif")
            
            texture_override_ib_section.append(self.vlr_filter_index_indent + "")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "post vs-cb1 = null")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "post vs-t0 = null")
            texture_override_ib_section.append(self.vlr_filter_index_indent + "post cs-t2 = null")
        
        else:
            if component_model:
                drawindexed_str_list = self._get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                for drawindexed_str in drawindexed_str_list:
                    if drawindexed_str.strip():
                        texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
        
        if self.vlr_filter_index_indent:
            texture_override_ib_section.append("endif")
            texture_override_ib_section.new_line()
        
        if len(self.branch_model.keyname_mkey_dict.keys()) != 0:
            texture_override_ib_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")
            
            if Properties_GenerateMod.generate_branch_mod_gui():
                texture_override_ib_section.append("$ActiveCharacter = 1")
            
        config_ini_builder.append_section(texture_override_ib_section)


    def add_unity_vs_resource_vb_sections(self, ini_builder, draw_ib_model, unique_str=None):
        resource_vb_section = M_IniSection(M_SectionType.ResourceBuffer)
        
        if self.use_ssmt4 and unique_str:
            for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
                resource_name = f"Resource_{unique_str.replace('-', '_')}_{category_name}"
                resource_vb_section.append(f"[{resource_name}]")
                resource_vb_section.append("type = Buffer")
                resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
                buffer_folder_name = GlobalConfig.get_buffer_folder_name()
                resource_vb_section.append("filename = " + buffer_folder_name + "/" + unique_str + "-" + category_name + ".buf")
                resource_vb_section.new_line()
        else:
            for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
                resource_vb_section.append("[Resource" + draw_ib_model.draw_ib + category_name + "]")
                resource_vb_section.append("type = Buffer")
                resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
                buffer_folder_name = GlobalConfig.get_buffer_folder_name()
                resource_vb_section.append("filename = " + buffer_folder_name + "/" + draw_ib_model.draw_ib + "-" + category_name + ".buf")
                resource_vb_section.new_line()

        for partname, ib_filename in draw_ib_model.PartName_IBBufferFileName_Dict.items():
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(partname, None)
            resource_vb_section.append("[" + ib_resource_name + "]")
            resource_vb_section.append("type = Buffer")
            resource_vb_section.append("format = DXGI_FORMAT_R32_UINT")
            buffer_folder_name = GlobalConfig.get_buffer_folder_name()
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + ib_filename)
            resource_vb_section.new_line()

        ini_builder.append_section(resource_vb_section)


    def add_resource_texture_sections(self, ini_builder, draw_ib_model):
        if Properties_GenerateMod.forbid_auto_texture_ini():
            return 
        
        # SSMT4 模式下也支持槽位贴图生成
        resource_texture_section = M_IniSection(M_SectionType.ResourceTexture)
        for partname, texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.items():
            for texture_markup_info in texture_markup_info_list:
                if texture_markup_info.mark_type == "Slot":
                    resource_texture_section.append("[" + texture_markup_info.get_resource_name() + "]")
                    resource_texture_section.append("filename = Texture/" + texture_markup_info.mark_filename)
                    resource_texture_section.new_line()

        ini_builder.append_section(resource_texture_section)


    def add_unity_cs_texture_override_vb_sections(self, config_ini_builder:M_IniBuilder, commandlist_ini_builder:M_IniBuilder, draw_ib_model):
        if self.use_ssmt4:
            return
        
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        if d3d11GameType.GPU_PreSkinning:
            texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
            texture_override_vb_section.append("; " + draw_ib)
            for category_name in d3d11GameType.OrderedCategoryNameList:
                category_hash = draw_ib_model.category_hash_dict[category_name]
                category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]
                texture_override_vb_namesuffix = "VB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + category_name

                if GlobalConfig.logic_name == LogicName.SRMI:
                    if category_name == "Position":
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "_VertexLimitRaise]")
                        texture_override_vb_section.append("override_byte_stride = " + str(d3d11GameType.CategoryStrideDict["Position"]))
                        texture_override_vb_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))
                        texture_override_vb_section.append("uav_byte_stride = 4")
                    else:
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                else:
                    texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                texture_override_vb_section.append("hash = " + category_hash)

                filterindex_indent_prefix = ""
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                    if category_name == draw_category_name:
                        if original_category_name == "Position":
                            texture_override_vb_section.append("cs-cb0 = Resource_" + draw_ib + "_VertexLimit")

                            position_category_slot = d3d11GameType.CategoryExtractSlotDict["Position"]
                            blend_category_slot = d3d11GameType.CategoryExtractSlotDict["Blend"]

                            texture_override_vb_section.append(position_category_slot + " = Resource" + draw_ib + "Position")
                            texture_override_vb_section.append(blend_category_slot + " = Resource" + draw_ib + "Blend")

                            texture_override_vb_section.append("handling = skip")

                            dispatch_number = int(math.ceil(draw_ib_model.draw_number / 64)) + 1
                            texture_override_vb_section.append("dispatch = " + str(dispatch_number) + ",1,1")
                        elif original_category_name != "Blend":
                            category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                            texture_override_vb_section.append(filterindex_indent_prefix  + category_original_slot + " = Resource" + draw_ib + original_category_name)

                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("endif")
                
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Position"]:
                    if draw_ib_model.key_number != 0:
                        texture_override_vb_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")

                texture_override_vb_section.new_line()
            config_ini_builder.append_section(texture_override_vb_section)



    def generate_unity_vs_config_ini(self):
        config_ini_builder = M_IniBuilder()
        
        if self.has_cross_ib:
            for node_name, cross_ib_method in self.cross_ib_method_dict.items():
                if cross_ib_method != 'END_FIELD':
                    print(f"[CrossIB] 警告: 节点 {node_name} 使用的跨 IB 方式 '{cross_ib_method}' 不适用于 EFMI 模式")
                    print(f"[CrossIB] EFMI 模式只支持 'END_FIELD' (终末地跨 IB) 方式")
                    self.has_cross_ib = False
                    break

        if self.has_cross_ib:
            self.add_cross_ib_present_section(config_ini_builder)
            self.add_cross_ib_resource_id_sections(config_ini_builder)

        if not self.use_ssmt4:
            M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder, drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        
        print("Length: " + str(len(self.drawib_drawibmodel_dict.items())))

        if self.use_ssmt4:
            for submesh_model in self._submesh_model_list:
                if len(submesh_model.ib) == 0:
                    continue
                
                draw_ib = submesh_model.match_draw_ib
                adapter_key = f"{draw_ib}_{submesh_model.match_index_count}"
                draw_ib_model = self.drawib_drawibmodel_dict.get(adapter_key)
                
                if draw_ib_model is None:
                    print(f"[CrossIB EFMI] 警告: 未找到 adapter_key={adapter_key}")
                    continue
                
                if self.cross_ib_match_mode == 'INDEX_COUNT':
                    current_ib_key = f"indexcount_{submesh_model.match_index_count}"
                else:
                    current_ib_key = f"{draw_ib}_1"
                
                is_source_ib = current_ib_key in self.cross_ib_info_dict
                source_ib_list_for_target = self.cross_ib_target_info.get(current_ib_key, [])
                is_target_ib = len(source_ib_list_for_target) > 0
                
                if self.cross_ib_match_mode == 'INDEX_COUNT':
                    current_identifier = submesh_model.match_index_count
                else:
                    current_identifier = draw_ib
                
                print(f"[CrossIB EFMI] submesh: {submesh_model.unique_str}, match_index_count={submesh_model.match_index_count}, current_ib_key={current_ib_key}")
                print(f"[CrossIB EFMI] is_source_ib={is_source_ib}, is_target_ib={is_target_ib}, current_identifier={current_identifier}")

                self.add_unity_vs_texture_override_ib_sections(
                    config_ini_builder=config_ini_builder,
                    commandlist_ini_builder=config_ini_builder,
                    draw_ib_model=draw_ib_model,
                    is_cross_ib_source=is_source_ib,
                    is_cross_ib_target=is_target_ib,
                    source_ib_list_for_target=source_ib_list_for_target,
                    part_name="1",
                    match_first_index=submesh_model.match_first_index,
                    match_index_count=int(submesh_model.match_index_count) if submesh_model.match_index_count else 0,
                    current_identifier=current_identifier
                )
                
                self.add_unity_vs_resource_vb_sections(
                    ini_builder=config_ini_builder,
                    draw_ib_model=draw_ib_model,
                    unique_str=submesh_model.unique_str
                )
                
                # SSMT4 模式下也需要生成资源纹理部分和移动槽位风格纹理
                self.add_resource_texture_sections(ini_builder=config_ini_builder, draw_ib_model=draw_ib_model)
                M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)
                
                M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1
        else:
            for draw_ib, draw_ib_model in self.drawib_drawibmodel_dict.items():
                print("Generating Config INI for DrawIB: " + draw_ib)

                for count_i, part_name in enumerate(draw_ib_model.import_config.part_name_list):
                    component_index = count_i + 1
                    current_ib_key = f"{draw_ib}_{component_index}"
                    
                    is_source_ib = current_ib_key in self.cross_ib_info_dict
                    
                    source_ib_list_for_target = []
                    for source_ib, target_ib_list in self.cross_ib_info_dict.items():
                        if current_ib_key in target_ib_list:
                            source_ib_list_for_target.append(source_ib)
                    
                    is_target_ib = len(source_ib_list_for_target) > 0
                    
                    match_first_index = draw_ib_model.import_config.match_first_index_list[draw_ib_model.import_config.part_name_list.index(part_name)]

                    self.add_unity_vs_texture_override_ib_sections(
                        config_ini_builder=config_ini_builder,
                        commandlist_ini_builder=config_ini_builder,
                        draw_ib_model=draw_ib_model,
                        is_cross_ib_source=is_source_ib,
                        is_cross_ib_target=is_target_ib,
                        source_ib_list_for_target=source_ib_list_for_target,
                        part_name=part_name,
                        match_first_index=match_first_index,
                        match_index_count=0
                    )
                
                self.add_unity_vs_resource_vb_sections(ini_builder=config_ini_builder, draw_ib_model=draw_ib_model)
                self.add_resource_texture_sections(ini_builder=config_ini_builder, draw_ib_model=draw_ib_model)

                M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)

                M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        
        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder, key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        
        if not self.use_ssmt4:
            M_IniHelper.add_shapekey_ini_sections(ini_builder=config_ini_builder, drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        
        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder, key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")

        if self.has_cross_ib:
            self.copy_cross_ib_hlsl_files()

    def copy_cross_ib_hlsl_files(self):
        addon_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        source_dir = os.path.join(addon_dir, "Toolset")
        
        if not os.path.exists(source_dir):
            print(f"[CrossIB] 警告: Toolset目录不存在: {source_dir}")
            return
        
        hlsl_files = [
            'extract_cb1_ps.hlsl',
            'extract_cb1_vs.hlsl',
            'record_bones_cs.hlsl',
            'redirect_cb1_cs.hlsl'
        ]
        
        mod_export_path = GlobalConfig.path_generate_mod_folder()
        res_dir = os.path.join(mod_export_path, "res")
        os.makedirs(res_dir, exist_ok=True)
        
        copied_count = 0
        for hlsl_file in hlsl_files:
            source_file = os.path.join(source_dir, hlsl_file)
            target_file = os.path.join(res_dir, hlsl_file)
            
            if os.path.exists(source_file):
                if not os.path.exists(target_file):
                    shutil.copy2(source_file, target_file)
                    print(f"[CrossIB] 已复制: {hlsl_file}")
                    copied_count += 1
                else:
                    print(f"[CrossIB] 文件已存在，跳过: {hlsl_file}")
            else:
                print(f"[CrossIB] 警告: 源文件不存在: {source_file}")
        
        print(f"[CrossIB] 共复制 {copied_count} 个HLSL文件到 {res_dir}")
