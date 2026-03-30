import copy
import bpy

from dataclasses import dataclass, field


class BluePrintModel_V4:
    def __init__(self):
        self.keyname_mkey_dict: dict = {}
        self.ordered_draw_obj_data_model_list: list = []
        self.visited_blueprints: set = set()
        self._global_key_index = 0
        self.multifile_export_nodes: list = []
        self.cross_ib_nodes: list = []
        self.cross_ib_info_dict: dict = {}
        self.cross_ib_object_names: set = set()
        self.cross_ib_method_dict: dict = {}
        self.cross_ib_target_info: dict = {}
        self.cross_ib_source_to_target_dict: dict = {}
        self.cross_ib_match_mode: str = 'IB_HASH'
        self.cross_ib_mapping_objects: dict = {}
        self.cross_ib_vb_condition_mapping: dict = {}
        self.cross_ib_object_vb_condition: dict = {}

    def _get_m_key_class(self):
        from ...base.m_key import M_Key
        return M_Key

    def _get_draw_call_model_classes(self):
        from .draw_call_model import DrawCallModel, M_Condition as V4_Condition
        return DrawCallModel, V4_Condition

    def initialize_from_tree(self, tree):
        if tree:
            output_node = self._get_node_from_bl_idname(tree, 'SSMTNode_Result_Output')
            if output_node:
                self.parse_current_node(output_node, [])
                print(f"BluePrintModel_V4: 解析完成，共收集 {len(self.ordered_draw_obj_data_model_list)} 个物体")

    def _get_node_from_bl_idname(self, tree, bl_idname):
        for node in tree.nodes:
            if node.bl_idname == bl_idname:
                return node
        return None

    def _get_connected_nodes(self, node):
        connected_nodes = []
        for input_socket in node.inputs:
            if input_socket.is_linked:
                for link in input_socket.links:
                    connected_nodes.append(link.from_node)
        return connected_nodes

    def parse_current_node(self, current_node, chain_key_list: list):
        for unknown_node in self._get_connected_nodes(current_node):
            self.parse_single_node(unknown_node, chain_key_list)

    def parse_single_node(self, unknown_node, chain_key_list: list):
        if unknown_node.mute:
            return

        DrawCallModel, V4_Condition = self._get_draw_call_model_classes()
        M_Key = self._get_m_key_class()

        if unknown_node.bl_idname == "SSMTNode_Object_Group":
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_VertexGroupProcess":
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_ToggleKey":
            m_key = M_Key()
            current_add_key_index = len(self.keyname_mkey_dict.keys())
            m_key.key_name = "$swapkey" + str(self._global_key_index)
            m_key.value_list = [0, 1]
            m_key.initialize_vk_str = getattr(unknown_node, 'key_name', '')
            m_key.initialize_value = 1 if getattr(unknown_node, 'default_on', False) else 0
            m_key.comment = getattr(unknown_node, 'comment', '')
            
            self.keyname_mkey_dict[m_key.key_name] = m_key
            
            if len(self.keyname_mkey_dict.keys()) > current_add_key_index:
                self._global_key_index += 1

            chain_tmp_key = copy.deepcopy(m_key)
            chain_tmp_key.tmp_value = 1

            tmp_chain_key_list = copy.deepcopy(chain_key_list)
            tmp_chain_key_list.append(chain_tmp_key)
            self.parse_current_node(unknown_node, tmp_chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_SwitchKey":
            valid_input_sockets = unknown_node.inputs[:]
            is_any_socket_linked = False
            for sock in valid_input_sockets:
                if sock.is_linked:
                    is_any_socket_linked = True
                    break

            if not is_any_socket_linked:
                return

            if len(valid_input_sockets) == 1:
                if valid_input_sockets[0].is_linked:
                    for link in valid_input_sockets[0].links:
                        self.parse_single_node(link.from_node, chain_key_list)
            else:
                m_key = M_Key()
                current_add_key_index = len(self.keyname_mkey_dict.keys())
                m_key.key_name = "$swapkey" + str(self._global_key_index)
                m_key.value_list = list(range(len(valid_input_sockets)))
                m_key.initialize_vk_str = getattr(unknown_node, 'key_name', '')
                m_key.initialize_value = 0
                m_key.comment = getattr(unknown_node, 'comment', '')
                
                self.keyname_mkey_dict[m_key.key_name] = m_key
                
                if len(self.keyname_mkey_dict.keys()) > current_add_key_index:
                    self._global_key_index += 1

                key_tmp_value = 0
                for socket in valid_input_sockets:
                    if socket.is_linked:
                        for link in socket.links:
                            chain_tmp_key = copy.deepcopy(m_key)
                            chain_tmp_key.tmp_value = key_tmp_value
                            tmp_chain_key_list = copy.deepcopy(chain_key_list)
                            tmp_chain_key_list.append(chain_tmp_key)
                            self.parse_single_node(link.from_node, tmp_chain_key_list)
                    key_tmp_value += 1

        elif unknown_node.bl_idname == "SSMTNode_Object_Name_Modify":
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_Object_Info":
            obj_model = DrawCallModel(obj_name=unknown_node.object_name)
            obj_model.condition = V4_Condition(work_key_list=copy.deepcopy(chain_key_list))
            
            draw_ib = getattr(unknown_node, 'draw_ib', '')
            index_count = getattr(unknown_node, 'index_count', '')
            first_index = getattr(unknown_node, 'first_index', '')
            alias_name = getattr(unknown_node, 'alias_name', '')
            
            if draw_ib:
                obj_model.set_draw_info(draw_ib, index_count, first_index, alias_name)
            
            if hasattr(unknown_node, 'original_object_name') and unknown_node.original_object_name:
                obj_model.display_name = unknown_node.original_object_name
            
            self.ordered_draw_obj_data_model_list.append(obj_model)
            print(f"BluePrintModel_V4: 解析 Object_Info 节点，物体: {unknown_node.object_name}, DrawIB: {draw_ib}, IndexCount: {index_count}")

        elif unknown_node.bl_idname == "SSMTNode_MultiFile_Export":
            if len(unknown_node.object_list) > 0:
                from ...blueprint.blueprint_export_helper import BlueprintExportHelper
                
                export_index = BlueprintExportHelper.current_export_index - 1
                
                if export_index < 0:
                    export_index = 0
                if export_index >= len(unknown_node.object_list):
                    export_index = len(unknown_node.object_list) - 1
                
                current_item = unknown_node.object_list[export_index]
                obj_model = DrawCallModel(obj_name=current_item.object_name)
                obj_model.condition = V4_Condition(work_key_list=copy.deepcopy(chain_key_list))
                
                draw_ib = getattr(current_item, 'draw_ib', '')
                index_count = getattr(current_item, 'index_count', '')
                first_index = getattr(current_item, 'first_index', '')
                alias_name = getattr(current_item, 'alias_name', '')
                
                if draw_ib:
                    obj_model.set_draw_info(draw_ib, index_count, first_index, alias_name)
                
                if hasattr(current_item, 'original_object_name') and current_item.original_object_name:
                    obj_model.display_name = current_item.original_object_name
                
                self.ordered_draw_obj_data_model_list.append(obj_model)
                print(f"BluePrintModel_V4: 解析 MultiFile_Export 节点，导出索引: {export_index + 1}, 物体: {current_item.object_name}, DrawIB: {draw_ib}, IndexCount: {index_count}")
            self.multifile_export_nodes.append(unknown_node)
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_DataType":
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_CrossIB":
            self.cross_ib_nodes.append(unknown_node)
            cross_ib_method = getattr(unknown_node, 'cross_ib_method', 'END_FIELD')
            self.cross_ib_method_dict[unknown_node.name] = cross_ib_method
            
            match_mode = getattr(unknown_node, 'get_match_mode', lambda: 'IB_HASH')()
            self.cross_ib_match_mode = match_mode
            
            vb_condition_source = ""
            vb_condition_target = ""
            if hasattr(unknown_node, 'get_vb_condition_source'):
                vb_condition_source = unknown_node.get_vb_condition_source()
            if hasattr(unknown_node, 'get_vb_condition_target'):
                vb_condition_target = unknown_node.get_vb_condition_target()
            
            if hasattr(unknown_node, 'get_ib_mapping_dict'):
                ib_mapping = unknown_node.get_ib_mapping_dict()
                for source_key, target_key_list in ib_mapping.items():
                    if source_key not in self.cross_ib_info_dict:
                        self.cross_ib_info_dict[source_key] = []
                    for target_key in target_key_list:
                        if target_key not in self.cross_ib_info_dict[source_key]:
                            self.cross_ib_info_dict[source_key].append(target_key)
                        
                        if target_key not in self.cross_ib_target_info:
                            self.cross_ib_target_info[target_key] = []
                        if source_key not in self.cross_ib_target_info[target_key]:
                            self.cross_ib_target_info[target_key].append(source_key)
                        
                        if source_key not in self.cross_ib_source_to_target_dict:
                            self.cross_ib_source_to_target_dict[source_key] = []
                        for tk in target_key_list:
                            if tk not in self.cross_ib_source_to_target_dict[source_key]:
                                self.cross_ib_source_to_target_dict[source_key].append(tk)
                        
                        mapping_key = (source_key, target_key)
                        self.cross_ib_vb_condition_mapping[mapping_key] = {
                            'source': vb_condition_source,
                            'target': vb_condition_target
                        }
            
            connected_objects = self._collect_cross_ib_objects(unknown_node, vb_condition_source, vb_condition_target)
            for obj_info in connected_objects:
                if obj_info.get('is_cross_ib_source', False):
                    obj_name = obj_info['object_name']
                    self.cross_ib_object_names.add(obj_name)
                    
                    source_ib_key = obj_info.get('source_ib_key', '')
                    target_ib_keys = obj_info.get('target_ib_keys', [])
                    obj_vb_source = obj_info.get('vb_condition_source', vb_condition_source)
                    obj_vb_target = obj_info.get('vb_condition_target', vb_condition_target)
                    
                    if source_ib_key:
                        for target_ib_key in target_ib_keys:
                            mapping_key = (source_ib_key, target_ib_key)
                            if mapping_key not in self.cross_ib_mapping_objects:
                                self.cross_ib_mapping_objects[mapping_key] = set()
                            self.cross_ib_mapping_objects[mapping_key].add(obj_name)
                            
                            object_mapping_key = (obj_name, source_ib_key, target_ib_key)
                            self.cross_ib_object_vb_condition[object_mapping_key] = {
                                'source': obj_vb_source,
                                'target': obj_vb_target
                            }
            
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_Blueprint_Nest":
            blueprint_name = getattr(unknown_node, 'blueprint_name', '')
            if not blueprint_name:
                return
            if blueprint_name in self.visited_blueprints:
                print(f"[Blueprint Nest V4] 警告: 检测到循环引用，跳过蓝图 {blueprint_name}")
                return
            self.visited_blueprints.add(blueprint_name)
            nested_tree = bpy.data.node_groups.get(blueprint_name)
            if not nested_tree or nested_tree.bl_idname != 'SSMTBlueprintTreeType':
                return
            nested_output_node = self._get_node_from_bl_idname(nested_tree, 'SSMTNode_Result_Output')
            if nested_output_node:
                self.parse_current_node(nested_output_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_ShapeKey":
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_VertexGroupMatch":
            self.parse_current_node(unknown_node, chain_key_list)

        elif unknown_node.bl_idname == "SSMTNode_VertexGroupMappingInput":
            self.parse_current_node(unknown_node, chain_key_list)

        else:
            self.parse_current_node(unknown_node, chain_key_list)

    def _collect_cross_ib_objects(self, cross_ib_node, vb_condition_source="", vb_condition_target=""):
        connected_objects = []
        visited_nodes = set()
        
        match_mode = getattr(cross_ib_node, 'get_match_mode', lambda: 'IB_HASH')()
        
        source_to_targets_map = {}
        if match_mode == 'INDEX_COUNT':
            for item in cross_ib_node.cross_ib_list:
                if item.source_index_count:
                    source_key = f"indexcount_{item.source_index_count}"
                    if source_key not in source_to_targets_map:
                        source_to_targets_map[source_key] = []
                    if item.target_index_count:
                        target_key = f"indexcount_{item.target_index_count}"
                        if target_key not in source_to_targets_map[source_key]:
                            source_to_targets_map[source_key].append(target_key)
            print(f"[CrossIB V4] INDEX_COUNT 模式，映射关系: {source_to_targets_map}")
        else:
            for item in cross_ib_node.cross_ib_list:
                if item.source_ib:
                    source_hash, source_component = self._parse_ib_with_component(item.source_ib)
                    source_key = f"{source_hash}_{source_component}"
                    if source_key not in source_to_targets_map:
                        source_to_targets_map[source_key] = []
                    if item.target_ib:
                        target_hash, target_component = self._parse_ib_with_component(item.target_ib)
                        target_key = f"{target_hash}_{target_component}"
                        if target_key not in source_to_targets_map[source_key]:
                            source_to_targets_map[source_key].append(target_key)
            print(f"[CrossIB V4] IB_HASH 模式，映射关系: {source_to_targets_map}")
        
        source_identifiers = set(source_to_targets_map.keys())
        
        PASS_THROUGH_NODES = {
            "SSMTNode_Object_Group",
            "SSMTNode_VertexGroupProcess",
            "SSMTNode_Object_Name_Modify",
            "SSMTNode_ToggleKey",
            "SSMTNode_SwitchKey",
            "SSMTNode_ShapeKey",
            "SSMTNode_VertexGroupMatch",
            "SSMTNode_VertexGroupMappingInput",
            "SSMTNode_DataType",
            "SSMTNode_CrossIB",
        }
        
        def recursive_collect(node):
            if node in visited_nodes:
                return
            visited_nodes.add(node)
            
            if node.bl_idname == "SSMTNode_Object_Info":
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    source_ib_key = ''
                    target_ib_keys = []
                    is_match = False
                    
                    if match_mode == 'INDEX_COUNT':
                        index_count = getattr(node, 'index_count', '')
                        if not index_count and "-" in obj_name:
                            obj_name_split = obj_name.split("-")
                            if len(obj_name_split) >= 2:
                                index_count = obj_name_split[1]
                                if "." in index_count:
                                    index_count = index_count.split(".")[0]
                        print(f"[CrossIB V4] 检查节点 {node.name}, obj_name={obj_name}, index_count={index_count}, source_identifiers={source_identifiers}")
                        source_ib_key = f"indexcount_{index_count}"
                        if source_ib_key in source_identifiers:
                            is_match = True
                            target_ib_keys = source_to_targets_map[source_ib_key].copy()
                            print(f"[CrossIB V4] 匹配成功: {obj_name} (index_count={index_count}), targets={target_ib_keys}")
                    else:
                        draw_ib = getattr(node, 'draw_ib', '')
                        if not draw_ib and "-" in obj_name:
                            draw_ib = obj_name.split("-")[0]
                        component = getattr(node, 'component', 1) or 1
                        source_ib_key = f"{draw_ib}_{component}"
                        if source_ib_key in source_identifiers:
                            is_match = True
                            target_ib_keys = source_to_targets_map[source_ib_key].copy()
                    
                    connected_objects.append({
                        'node': node,
                        'object_name': obj_name,
                        'draw_ib': getattr(node, 'draw_ib', '') or (obj_name.split("-")[0] if "-" in obj_name else ''),
                        'index_count': index_count if match_mode == 'INDEX_COUNT' else '',
                        'is_cross_ib_source': is_match,
                        'source_ib_key': source_ib_key,
                        'target_ib_keys': target_ib_keys,
                        'vb_condition_source': vb_condition_source,
                        'vb_condition_target': vb_condition_target
                    })
            
            elif node.bl_idname == "SSMTNode_MultiFile_Export":
                if hasattr(node, 'object_list'):
                    for item in node.object_list:
                        obj_name = getattr(item, 'object_name', '')
                        if obj_name:
                            source_ib_key = ''
                            target_ib_keys = []
                            is_match = False
                            index_count = ''
                            draw_ib = ''
                            
                            if match_mode == 'INDEX_COUNT':
                                index_count = getattr(item, 'index_count', '')
                                if not index_count and "-" in obj_name:
                                    obj_name_split = obj_name.split("-")
                                    if len(obj_name_split) >= 2:
                                        index_count = obj_name_split[1]
                                        if "." in index_count:
                                            index_count = index_count.split(".")[0]
                                source_ib_key = f"indexcount_{index_count}"
                                if source_ib_key in source_identifiers:
                                    is_match = True
                                    target_ib_keys = source_to_targets_map[source_ib_key].copy()
                            else:
                                draw_ib = getattr(item, 'draw_ib', '')
                                if not draw_ib and "-" in obj_name:
                                    draw_ib = obj_name.split("-")[0]
                                component = getattr(item, 'component', 1) or 1
                                source_ib_key = f"{draw_ib}_{component}"
                                if source_ib_key in source_identifiers:
                                    is_match = True
                                    target_ib_keys = source_to_targets_map[source_ib_key].copy()
                            
                            connected_objects.append({
                                'node': node,
                                'object_name': obj_name,
                                'draw_ib': draw_ib or (obj_name.split("-")[0] if "-" in obj_name else ''),
                                'index_count': index_count,
                                'is_cross_ib_source': is_match,
                                'source_ib_key': source_ib_key,
                                'target_ib_keys': target_ib_keys,
                                'vb_condition_source': vb_condition_source,
                                'vb_condition_target': vb_condition_target
                            })
            
            elif node.bl_idname == "SSMTNode_Blueprint_Nest":
                blueprint_name = getattr(node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        nested_output_node = self._get_node_from_bl_idname(nested_tree, 'SSMTNode_Result_Output')
                        if nested_output_node:
                            recursive_collect(nested_output_node)
            
            elif node.bl_idname in PASS_THROUGH_NODES:
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            recursive_collect(link.from_node)
            
            else:
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            recursive_collect(link.from_node)
        
        for input_socket in cross_ib_node.inputs:
            if input_socket.is_linked:
                for link in input_socket.links:
                    recursive_collect(link.from_node)
        
        return connected_objects
    
    def _parse_ib_with_component(self, ib_str):
        if not ib_str:
            return "", 1
        
        parts = ib_str.split("-")
        ib_hash = parts[0]
        
        if len(parts) > 1 and parts[1].isdigit():
            component_index = int(parts[1])
        else:
            component_index = 1
        
        return ib_hash, component_index
