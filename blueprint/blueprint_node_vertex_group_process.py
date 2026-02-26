# -*- coding: utf-8 -*-
import bpy
import re
from collections import defaultdict
from bpy.types import PropertyGroup

from .blueprint_node_base import SSMTNodeBase


class VGProcessMappingItem(PropertyGroup):
    target_hash: bpy.props.StringProperty(
        name="目标哈希",
        description="应用此映射表的物体哈希标识（物体名称中包含此字符串时匹配）",
        default=""
    )


class SSMTNode_VertexGroupProcess(SSMTNodeBase):
    '''顶点组处理节点：在前处理流程中自动执行顶点组重命名、合并、清理、填充和排序'''
    bl_idname = 'SSMTNode_VertexGroupProcess'
    bl_label = '顶点组处理'
    bl_description = '在前处理流程中自动执行顶点组重命名、合并、清理、填充和排序'
    bl_icon = 'GROUP'
    bl_width_min = 300

    mapping_hashes: bpy.props.CollectionProperty(
        name="映射表哈希配置",
        type=VGProcessMappingItem
    )

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "物体")
        self.inputs.new('SSMTSocketObject', "映射表 1")
        self.mapping_hashes.add()
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="顶点组处理", icon='GROUP')
        
        connected_count = self._get_connected_mapping_count()
        box.label(text=f"已连接映射表: {connected_count}", icon='TEXT')
        
        box.separator()
        box.label(text="映射表哈希配置:", icon='HASH')
        
        for i, socket in enumerate(self.inputs):
            if i > 0:
                row = box.row(align=True)
                row.label(text=f"映射表 {i}:")
                
                if i - 1 < len(self.mapping_hashes):
                    item = self.mapping_hashes[i - 1]
                    row.prop(item, "target_hash", text="")
                else:
                    row.label(text="(未配置)")
                
                if socket.is_linked:
                    for link in socket.links:
                        node_name = link.from_node.name if link.from_node else "未知"
                        row.label(text=f"→ {node_name[:15]}", icon='LINKED')

    def update(self):
        if self.inputs and len(self.inputs) >= 2:
            if self.inputs[-1].is_linked:
                self.inputs.new('SSMTSocketObject', f"映射表 {len(self.inputs)}")
                self.mapping_hashes.add()
            
            while len(self.inputs) > 2 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
                self.inputs.remove(self.inputs[-1])
                if len(self.mapping_hashes) > len(self.inputs) - 1:
                    self.mapping_hashes.remove(len(self.mapping_hashes) - 1)

    def _get_connected_mapping_count(self):
        count = 0
        for i, socket in enumerate(self.inputs):
            if i > 0 and socket.is_linked:
                count += 1
        return count

    def get_connected_mapping_nodes(self):
        mapping_nodes = []
        for i, socket in enumerate(self.inputs):
            if i > 0 and socket.is_linked:
                target_hash = ""
                if i - 1 < len(self.mapping_hashes):
                    target_hash = self.mapping_hashes[i - 1].target_hash
                
                for link in socket.links:
                    if hasattr(link.from_node, 'source_object') and hasattr(link.from_node, 'target_object'):
                        mapping_nodes.append({
                            'node': link.from_node,
                            'target_hash': target_hash,
                            'index': i
                        })
        return mapping_nodes

    def get_merged_mapping_for_object(self, obj_name, mapping_nodes):
        merged_mapping = {}
        
        sorted_nodes = sorted(mapping_nodes, key=lambda x: x['index'])
        
        for node_info in sorted_nodes:
            node = node_info['node']
            target_hash = node_info['target_hash']
            
            if target_hash and target_hash not in obj_name:
                continue
            
            source_obj_name = getattr(node, 'source_object', '')
            target_obj_name = getattr(node, 'target_object', '')
            
            text_name = f"VG_Match_{source_obj_name}_to_{target_obj_name}"
            text = bpy.data.texts.get(text_name)
            
            if text:
                mapping = self.parse_mapping_text(text)
                merged_mapping.update(mapping)
        
        return merged_mapping

    def parse_mapping_text(self, text):
        mapping = {}
        for line in text.lines:
            clean_line = re.sub(r'[#//].*', '', line.body).strip()
            if '=' in clean_line:
                parts = clean_line.split('=', 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    if left and right:
                        mapping[left] = right
        return mapping

    def generate_unique_name(self, base_name, collection):
        if base_name not in collection:
            return base_name
        suffix = 1
        while f"{base_name}.{suffix:03d}" in collection:
            suffix += 1
        return f"{base_name}.{suffix:03d}"

    def process_object(self, obj):
        if not obj or obj.type != 'MESH':
            return {"renamed": 0, "merged": 0, "cleaned": 0, "filled": 0}
        
        stats = {"renamed": 0, "merged": 0, "cleaned": 0, "filled": 0}
        
        mapping_nodes = self.get_connected_mapping_nodes()
        
        if mapping_nodes:
            merged_mapping = self.get_merged_mapping_for_object(obj.name, mapping_nodes)
            if merged_mapping:
                stats["renamed"] = self._rename_vertex_groups(obj, merged_mapping)
        
        stats["merged"] = self._merge_vertex_groups_by_prefix(obj)
        stats["cleaned"] = self._remove_non_numeric_vertex_groups(obj)
        stats["filled"] = self._fill_vertex_group_gaps(obj)
        self._sort_vertex_groups(obj)
        
        return stats

    def _rename_vertex_groups(self, obj, mapping):
        renamed_count = 0
        for vg in obj.vertex_groups:
            if vg.name in mapping:
                new_name = mapping[vg.name]
                if vg.name != new_name:
                    if new_name in obj.vertex_groups:
                        obj.vertex_groups[new_name].name = self.generate_unique_name(new_name, obj.vertex_groups)
                    vg.name = new_name
                    renamed_count += 1
        return renamed_count

    def _merge_vertex_groups_by_prefix(self, obj):
        prefix_map = defaultdict(list)
        for vg in obj.vertex_groups:
            match = re.match(r'^(\d+)', vg.name)
            if match:
                prefix_map[match.group(1)].append(vg)
        
        merged_count = 0
        groups_to_delete = []
        
        for prefix, source_groups in prefix_map.items():
            if len(source_groups) > 1 or (len(source_groups) == 1 and source_groups[0].name != prefix):
                target_vg = obj.vertex_groups.get(prefix) or obj.vertex_groups.new(name=prefix)
                
                for vert in obj.data.vertices:
                    total_weight = 0.0
                    for source_vg in source_groups:
                        try:
                            total_weight += source_vg.weight(vert.index)
                        except RuntimeError:
                            continue
                    
                    if total_weight > 0:
                        target_vg.add([vert.index], min(1.0, total_weight), 'REPLACE')
                
                groups_to_delete.extend(g for g in source_groups if not g.name.isdigit())
                merged_count += 1
        
        for vg in set(groups_to_delete):
            if vg.name in obj.vertex_groups:
                obj.vertex_groups.remove(vg)
        
        return merged_count

    def _remove_non_numeric_vertex_groups(self, obj):
        groups_to_remove = [vg for vg in obj.vertex_groups if not vg.name.isdigit()]
        for vg in reversed(groups_to_remove):
            obj.vertex_groups.remove(vg)
        return len(groups_to_remove)

    def _fill_vertex_group_gaps(self, obj):
        numeric_names = {vg.name for vg in obj.vertex_groups if vg.name.isdigit()}
        if not numeric_names:
            return 0
        
        max_num = max(int(name) for name in numeric_names)
        filled_count = 0
        
        for num in range(max_num + 1):
            name = str(num)
            if name not in numeric_names:
                obj.vertex_groups.new(name=name)
                filled_count += 1
        
        return filled_count

    def _sort_vertex_groups(self, obj):
        try:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.vertex_group_sort(sort_type='NAME')
        except Exception:
            pass


classes = (
    VGProcessMappingItem,
    SSMTNode_VertexGroupProcess,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
