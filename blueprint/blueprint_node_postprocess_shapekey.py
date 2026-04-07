import bpy
import os
import glob
import re
import shutil
import struct
import datetime
from collections import OrderedDict

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base

_name_mapping_cache = {}


def clear_name_mapping_cache():
    """清除名称映射缓存（在每次导出开始时调用）"""
    global _name_mapping_cache
    _name_mapping_cache.clear()
    print("[ShapeKey] 已清除名称映射缓存")


# -------------------------------------------------------------------------
# 属性组：槽位条目和槽位设置
# -------------------------------------------------------------------------
class SSMT_ShapeKeySlotEntry(bpy.types.PropertyGroup):
    """槽位条目：一个物体上的一个形态键，归属到指定槽位"""
    slot_index: bpy.props.IntProperty(
        name="槽位编号",
        description="该形态键所属的Mod槽位编号（1~N）",
        default=1,
        min=1
    )
    object_name: bpy.props.StringProperty(
        name="物体名称",
        description="目标物体名称"
    )
    shapekey_name: bpy.props.StringProperty(
        name="形态键名称",
        description="形态键变体名称（基准形态不需要）"
    )


class SSMT_SlotSettings(bpy.types.PropertyGroup):
    """槽位设置：自动播放参数和备注"""
    slot_index: bpy.props.IntProperty(name="槽位编号", default=1, min=1)
    
    enable_auto_playback: bpy.props.BoolProperty(
        name="启用自动播放",
        description="自动循环播放形态键动画",
        default=False
    )
    auto_playback_frame_count: bpy.props.IntProperty(
        name="循环帧数",
        description="自动播放的动画总帧数",
        default=60,
        min=1,
        max=1000
    )
    auto_playback_step_frames: bpy.props.IntProperty(
        name="速度",
        description="每多少帧前进一帧（值越小速度越快）",
        default=2,
        min=1,
        max=30
    )
    auto_playback_cycle_mode: bpy.props.EnumProperty(
        name="循环模式",
        description="自动播放的循环模式",
        items=[
            ('FORWARD', "正向", "从0到1循环"),
            ('REVERSE', "反向", "从1到0循环"),
            ('PINGPONG', "往返", "0→1→0→1往返循环"),
        ],
        default='FORWARD'
    )
    auto_playback_speed_min: bpy.props.IntProperty(
        name="最小循环帧数",
        description="速度滑块可调整的最小循环帧数",
        default=30,
        min=1,
        max=1000
    )
    auto_playback_speed_max: bpy.props.IntProperty(
        name="最大循环帧数",
        description="速度滑块可调整的最大循环帧数",
        default=120,
        min=1,
        max=1000
    )
    remark: bpy.props.StringProperty(
        name="备注",
        description="该槽位的别名或备注，将写入INI配置文件",
        default=""
    )


class SSMT_OT_ShapeKeySetSlot(bpy.types.Operator):
    """设置形态键的槽位编号"""
    bl_idname = "ssmt.shapekey_set_slot"
    bl_label = "设置槽位"
    bl_description = "设置该形态键归属的Mod槽位编号"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: bpy.props.StringProperty()
    object_name: bpy.props.StringProperty()
    shapekey_name: bpy.props.StringProperty()
    slot_index: bpy.props.IntProperty(name="槽位编号", min=1, default=1)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "slot_index", text="槽位编号")

    def execute(self, context):
        node = self._get_node(context)
        if not node:
            self.report({'ERROR'}, "未找到形态键配置节点")
            return {'CANCELLED'}

        found = False
        for entry in node.slot_entries:
            if entry.object_name == self.object_name and entry.shapekey_name == self.shapekey_name:
                entry.slot_index = self.slot_index
                found = True
                break

        if not found:
            entry = node.slot_entries.add()
            entry.object_name = self.object_name
            entry.shapekey_name = self.shapekey_name
            entry.slot_index = self.slot_index

        self.report({'INFO'}, f"已设置 {self.object_name} / {self.shapekey_name} 为槽位 {self.slot_index}")
        return {'FINISHED'}

    def _get_node(self, context):
        if self.node_name:
            space = context.space_data
            if space and space.type == 'NODE_EDITOR':
                tree = space.edit_tree or space.node_tree
                if tree:
                    return tree.nodes.get(self.node_name)
        return None


# -------------------------------------------------------------------------
# 主节点类
# -------------------------------------------------------------------------
class SSMTNode_PostProcess_ShapeKey(SSMTNode_PostProcess_Base):
    '''形态键配置后处理节点：支持多形态叠加混合的INI配置，可选自动播放动画，支持手动配置Mod槽位'''
    bl_idname = 'SSMTNode_PostProcess_ShapeKey'
    bl_label = '形态键配置'
    bl_description = '读取分类文本或手动配置，生成支持多形态叠加混合的INI配置'

    INTENSITY_START_INDEX = 100
    VERTEX_RANGE_START_INDEX = 200

    use_packed_buffers: bpy.props.BoolProperty(
        name="使用紧凑缓冲区",
        description="仅存储变化的顶点数据，大幅减小体积。需要 'numpy' 库。",
        default=True
    )
    store_deltas: bpy.props.BoolProperty(
        name="存储顶点增量",
        description="不存储完整的顶点坐标，而是存储与基础模型的差值，进一步减小体积。需要 'numpy' 库。",
        default=True
    )
    use_optimized_lookup: bpy.props.BoolProperty(
        name="优化查找性能",
        description="使用顶点FREQ索引缓冲区替代大量条件分支，显著提升GPU性能。需要 'numpy' 库。",
        default=True
    )
    
    # 自动播放选项
    enable_auto_playback: bpy.props.BoolProperty(
        name="启用自动播放",
        description="自动循环播放形态键动画（0→1 循环）",
        default=False
    )
    auto_playback_frame_count: bpy.props.IntProperty(
        name="循环帧数",
        description="自动播放的动画总帧数",
        default=60,
        min=1,
        max=1000
    )
    auto_playback_step_frames: bpy.props.IntProperty(
        name="速度",
        description="每多少帧前进一帧（值越小速度越快）",
        default=2,
        min=1,
        max=30
    )

    auto_playback_speed_min: bpy.props.IntProperty(
        name="最小循环帧数",
        description="速度滑块可调整的最小循环帧数（值越小速度越快）",
        default=30,
        min=1,
        max=1000
    )
    auto_playback_speed_max: bpy.props.IntProperty(
        name="最大循环帧数",
        description="速度滑块可调整的最大循环帧数（值越大速度越慢）",
        default=120,
        min=1,
        max=1000
    )

    # 槽位设置集合
    slot_settings: bpy.props.CollectionProperty(type=SSMT_SlotSettings)
    active_slot_setting_index: bpy.props.IntProperty(
        name="活动槽位",
        description="当前编辑的槽位编号",
        default=1,
        min=1
    )
    export_slot_index: bpy.props.IntProperty(
        name="导出槽位",
        description="导出时使用哪个槽位的自动播放参数",
        default=1,
        min=1
    )

    auto_playback_cycle_mode: bpy.props.EnumProperty(
        name="循环模式",
        description="自动播放的循环模式",
        items=[
            ('FORWARD', "正向", "从0到1循环"),
            ('REVERSE', "反向", "从1到0循环"),
            ('PINGPONG', "往返", "0→1→0→1往返循环"),
        ],
        default='FORWARD'
    )

    # 手动槽位条目集合（通过 ssmt.shapekey_set_slot 添加）
    slot_entries: bpy.props.CollectionProperty(type=SSMT_ShapeKeySlotEntry)

    def apply_name_mapping(self, mapping):
        """接收从物体重命名节点传递的名称映射"""
        global _name_mapping_cache
        _name_mapping_cache[self.name] = mapping.copy()
        print(f"[ShapeKey] 已接收名称映射: {mapping}")

    def _get_name_mapping(self):
        """获取名称映射字典"""
        global _name_mapping_cache
        return _name_mapping_cache.get(self.name, {})

    def _apply_name_mapping_to_object(self, obj_name):
        """应用名称映射到物体名称"""
        mapping = self._get_name_mapping()
        if not mapping:
            return obj_name
        
        for old_part, new_part in mapping.items():
            if old_part in obj_name:
                obj_name = obj_name.replace(old_part, new_part)
        
        return obj_name
    
    def init(self, context):
        super().init(context)
        self.inputs.new('SSMTSocketObject', "形态键控制器")
        self.width = 300
        if len(self.slot_settings) == 0:
            default = self.slot_settings.add()
            default.slot_index = 1

    # -------------------------------------------------------------------------
    # 从上游形态键控制器读取预览数据
    # -------------------------------------------------------------------------
    def _get_upstream_shapekey_controller(self):
        target_socket = None
        for s in self.inputs:
            if s.name == "形态键控制器":
                target_socket = s
                break
        if not target_socket:
            return None
        if not target_socket.is_linked:
            return None
        node = target_socket.links[0].from_node
        return self._find_controller_node(node)

    def _find_controller_node(self, node):
        if node is None:
            return None
        if node.bl_idname == 'SSMTNode_ShapeKeyController':
            return node
        if node.bl_idname in ('SSMTNode_Object_Name_Modify', 'SSMTNode_VertexGroupProcess',
                              'SSMTNode_Object_Group', 'SSMTNode_ToggleKey', 'SSMTNode_SwitchKey'):
            if node.inputs and node.inputs[0].is_linked:
                return self._find_controller_node(node.inputs[0].links[0].from_node)
        if node.bl_idname == 'SSMTNode_Blueprint_Nest':
            blueprint_name = getattr(node, 'blueprint_name', '')
            if blueprint_name:
                nested_tree = bpy.data.node_groups.get(blueprint_name)
                if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                    for n in nested_tree.nodes:
                        if n.bl_idname == 'SSMTNode_Result_Output' and n.inputs and n.inputs[0].is_linked:
                            return self._find_controller_node(n.inputs[0].links[0].from_node)
        return None

    def _get_preview_data_from_controller(self):
        controller = self._get_upstream_shapekey_controller()
        if not controller:
            return None
        expanded = controller.get_expanded_objects()
        obj_to_shapekeys = {}
        for obj, sk_name in expanded:
            if sk_name is None:
                continue
            if obj.name not in obj_to_shapekeys:
                obj_to_shapekeys[obj.name] = []
            if sk_name not in obj_to_shapekeys[obj.name]:
                obj_to_shapekeys[obj.name].append(sk_name)
        return {
            'objects': list(obj_to_shapekeys.keys()),
            'obj_to_sk': obj_to_shapekeys,
            'total_variants': len(expanded) - len(obj_to_shapekeys)
        }

    def _get_preview_data_from_classification(self):
        classification_text_obj = next((t for t in bpy.data.texts if "Shape_Key_Classification" in t.name), None)
        if not classification_text_obj:
            return None
        content = classification_text_obj.as_string()
        slot_to_name_to_objects, _, _, _ = self._parse_classification_text_final(content)
        obj_to_shapekeys = {}
        for slot, name_dict in slot_to_name_to_objects.items():
            for sk_name, obj_list in name_dict.items():
                for obj_name in obj_list:
                    if obj_name not in obj_to_shapekeys:
                        obj_to_shapekeys[obj_name] = []
                    if sk_name not in obj_to_shapekeys[obj_name]:
                        obj_to_shapekeys[obj_name].append(sk_name)
        return {
            'objects': list(obj_to_shapekeys.keys()),
            'obj_to_sk': obj_to_shapekeys,
            'total_variants': sum(len(ks) for ks in obj_to_shapekeys.values())
        }

    # -------------------------------------------------------------------------
    # UI 绘制
    # -------------------------------------------------------------------------
    def draw_buttons(self, context, layout):
        layout.prop(self, "use_packed_buffers")
        layout.prop(self, "store_deltas")
        layout.prop(self, "use_optimized_lookup")

        if not NUMPY_AVAILABLE:
            layout.label(text="警告: 未安装numpy库，优化功能不可用", icon='ERROR')
        
        layout.separator()
        main_box = layout.box()
        main_box.label(text="槽位设置", icon='PREFERENCES')
        
        if len(self.slot_settings) == 0:
            main_box.label(text="提示：暂无槽位设置，请重新加载节点或使用默认值", icon='INFO')
        else:
            row = main_box.row(align=True)
            row.prop(self, "active_slot_setting_index", text="编辑槽位")
            row = main_box.row(align=True)
            row.prop(self, "export_slot_index", text="导出槽位")
            
            current_setting = None
            for s in self.slot_settings:
                if s.slot_index == self.active_slot_setting_index:
                    current_setting = s
                    break
            if current_setting is None:
                main_box.label(text=f"错误：槽位 {self.active_slot_setting_index} 无设置", icon='ERROR')
            else:
                main_box.prop(current_setting, "enable_auto_playback")
                if current_setting.enable_auto_playback:
                    row = main_box.row()
                    row.prop(current_setting, "auto_playback_frame_count")
                    row.prop(current_setting, "auto_playback_step_frames")
                    main_box.prop(current_setting, "auto_playback_cycle_mode", text="循环模式")
                    row = main_box.row()
                    row.prop(current_setting, "auto_playback_speed_min", text="速度范围最小")
                    row.prop(current_setting, "auto_playback_speed_max", text="最大")
                
                main_box.separator()
                main_box.prop(current_setting, "remark", text="槽位别名备注")

        layout.separator()
        box = layout.box()
        box.label(text="形态键预览", icon='SHAPEKEY_DATA')
        
        preview = None
        try:
            preview = self._get_preview_data_from_controller()
            if preview is None:
                preview = self._get_preview_data_from_classification()
        except Exception as e:
            print(f"[ShapeKey] 获取预览数据失败: {e}")
        
        if preview and preview.get('objects'):
            obj_count = len(preview['objects'])
            variant_count = preview.get('total_variants', 0)
            box.label(text=f"物体数: {obj_count}  |  形态键变体总数: {variant_count}", icon='INFO')
            col = box.column(align=True)
            for obj_name in preview['objects']:
                sk_list = preview['obj_to_sk'].get(obj_name, [])
                row = col.row()
                row.label(text=f"• {obj_name}", icon='OBJECT_DATA')
                subcol = col.column(align=True)
                subcol.scale_y = 0.8
                for sk_name in sk_list:
                    slot_value = 1
                    for entry in self.slot_entries:
                        if entry.object_name == obj_name and entry.shapekey_name == sk_name:
                            slot_value = entry.slot_index
                            break
                    row_item = subcol.row(align=True)
                    row_item.label(text=f"   ↳ {sk_name}", icon='SHAPEKEY_DATA')
                    op = row_item.operator("ssmt.shapekey_set_slot", text=f"槽位 {slot_value}")
                    op.node_name = self.name
                    op.object_name = obj_name
                    op.shapekey_name = sk_name
                    op.slot_index = slot_value
                col.separator(factor=0.3)
        else:
            box.label(text="未找到形态键数据", icon='ERROR')
            box.label(text="请确保:", icon='INFO')
            box.label(text="  - 上游连接了形态键控制器", icon='BLANK1')
            box.label(text="  - 或存在分类文本 'Shape_Key_Classification'", icon='BLANK1')

    # -------------------------------------------------------------------------
    # 构建最终形态键数据结构（根据手动配置或自动检测）
    # -------------------------------------------------------------------------
    def _build_slot_data(self):
        """返回 (slot_to_name_to_objects, unique_hashes, hash_to_objects, all_objects)
        优先使用手动配置的 slot_entries，如果为空则使用自动检测（控制器或分类文本）。
        """
        if self.slot_entries:
            return self._build_slot_data_from_manual()
        else:
            controller_data = self._get_shapekey_data_from_controller()
            if controller_data:
                return controller_data
            classification_text_obj = next((t for t in bpy.data.texts if "Shape_Key_Classification" in t.name), None)
            if classification_text_obj:
                return self._parse_classification_text_final(classification_text_obj.as_string())
            return (OrderedDict(), [], OrderedDict(), [])

    def _build_slot_data_from_manual(self):
        slot_to_name_to_objects = OrderedDict()
        all_objects = []
        hash_to_objects = OrderedDict()

        for entry in self.slot_entries:
            slot = entry.slot_index
            obj_name = entry.object_name
            sk_name = entry.shapekey_name

            if slot not in slot_to_name_to_objects:
                slot_to_name_to_objects[slot] = OrderedDict()
            if sk_name not in slot_to_name_to_objects[slot]:
                slot_to_name_to_objects[slot][sk_name] = []
            if obj_name not in slot_to_name_to_objects[slot][sk_name]:
                slot_to_name_to_objects[slot][sk_name].append(obj_name)

            if obj_name not in all_objects:
                all_objects.append(obj_name)

            obj_hash = self._extract_hash_from_name(obj_name)
            if obj_hash:
                if obj_hash not in hash_to_objects:
                    hash_to_objects[obj_hash] = []
                if obj_name not in hash_to_objects[obj_hash]:
                    hash_to_objects[obj_hash].append(obj_name)

        unique_hashes = list(OrderedDict.fromkeys(h for obj in all_objects if (h := self._extract_hash_from_name(obj))))
        return slot_to_name_to_objects, unique_hashes, hash_to_objects, all_objects

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------
    def _create_safe_var_name(self, text, prefix="", existing_names=None):
        if not text:
            text = "unnamed"
        safe_text = re.sub(r'\s+', '_', text)
        safe_text = re.sub(r'[^a-zA-Z0-9_]', '', safe_text)
        if safe_text and safe_text[0].isdigit():
            safe_text = "_" + safe_text
        if not safe_text:
            safe_text = "var"
        result = f"{prefix}{safe_text}"
        if existing_names is not None:
            original_result = result
            counter = 1
            while result in existing_names:
                result = f"{original_result}_{counter}"
                counter += 1
            existing_names.add(result)
        return result

    def _parse_ini_for_draw_info(self, sections, base_path):
        draw_info, resource_map = {}, {}
        for section_name, lines in sections.items():
            if section_name.lower().startswith('[resource'):
                filename = next((l.split('=', 1)[1].strip() for l in lines if l.strip().lower().startswith('filename =')), None)
                if filename: resource_map[section_name.strip('[]')] = os.path.join(base_path, filename.replace('/', os.sep))
        for section_name, lines in sections.items():
            if section_name.lower().startswith('[textureoverride'):
                current_mesh_name = None
                for i, line in enumerate(lines):
                    stripped_line = line.strip()
                    mesh_match = re.search(r'\[mesh:([^\]]+)\]', stripped_line)
                    if mesh_match:
                        current_mesh_name = mesh_match.group(1).strip()
                        continue
                    if current_mesh_name:
                        lower_line = stripped_line.lower()
                        if lower_line.startswith('drawindexed ') or lower_line.startswith('drawindexedinstanced '):
                            ib_path = None
                            for j in range(i, -1, -1):
                                prev_line = lines[j].strip().lower()
                                if prev_line.startswith('ib ='):
                                    ib_resource_ref = lines[j].strip().split('=', 1)[1].strip()
                                    if ib_resource_ref.lower().startswith('ref '):
                                        ib_resource_name = ib_resource_ref[4:].strip()
                                    else:
                                        ib_resource_name = ib_resource_ref
                                    if ib_resource_name in resource_map:
                                        ib_path = resource_map[ib_resource_name]
                                    break
                            if ib_path:
                                try:
                                    if lower_line.startswith('drawindexed '):
                                        parts = [int(p.strip()) for p in stripped_line.split('=')[1].strip().split(',')]
                                        if len(parts) == 3:
                                            info_item = {'draw_params': tuple(parts), 'ib_path': ib_path}
                                    else:
                                        parts = [p.strip() for p in stripped_line.split('=')[1].strip().split(',')]
                                        if len(parts) >= 5:
                                            index_count = int(parts[0])
                                            start_index_location = int(parts[2]) if parts[2].lstrip('-').isdigit() else 0
                                            base_vertex_location = int(parts[3]) if parts[3].lstrip('-').isdigit() else 0
                                            info_item = {'draw_params': (index_count, start_index_location, base_vertex_location), 'ib_path': ib_path}
                                    if current_mesh_name not in draw_info:
                                        draw_info[current_mesh_name] = []
                                    draw_info[current_mesh_name].append(info_item)
                                except (ValueError, IndexError): pass
                            current_mesh_name = None
        return draw_info

    def _calculate_vertex_range(self, ib_path, draw_params):
        index_count, start_index_location, base_vertex_location = draw_params
        if not os.path.isfile(ib_path): return None, None
        try:
            with open(ib_path, 'rb') as f:
                f.seek(start_index_location * 4)
                data = f.read(index_count * 4)
                if len(data) < index_count * 4: return None, None
                indices = [idx + base_vertex_location for idx in struct.unpack(f'<{index_count}I', data)]
                return (min(indices), max(indices)) if indices else (None, None)
        except Exception: return None, None

    def _extract_hash_from_name(self, obj_name):
        match = re.match(r'^([a-f0-9]{8}-[a-f0-9]+(?:-[a-f0-9]+)?)', obj_name)
        if match:
            return match.group(1)
        match = re.match(r'^([a-f0-9]{8})', obj_name)
        if match:
            return match.group(1)
        return None

    def _extract_hash_prefix(self, hash_val):
        if hash_val:
            return hash_val.split('-')[0]
        return None

    def _hash_to_resource_prefix(self, h):
        return h.replace('-', '_')

    def _parse_classification_text_final(self, text_content):
        slot_to_name_to_objects, hash_to_objects, all_objects = OrderedDict(), OrderedDict(), []
        current_slot, current_shapekey_name = None, None
        for line in text_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            slot_match = re.search(r'槽位\s*(\d+):', line)
            if slot_match:
                current_slot = int(slot_match.group(1))
                if current_slot not in slot_to_name_to_objects: slot_to_name_to_objects[current_slot] = OrderedDict()
                current_shapekey_name = None; continue
            name_match = re.search(r'名称:\s*(.+)', line)
            if name_match and current_slot is not None:
                current_shapekey_name = name_match.group(1).strip()
                if current_shapekey_name not in slot_to_name_to_objects[current_slot]: slot_to_name_to_objects[current_slot][current_shapekey_name] = []
                continue
            obj_match = re.search(r'物体:\s*(.+)', line)
            if obj_match and current_slot is not None and current_shapekey_name is not None:
                obj_name = obj_match.group(1).strip()
                obj_name = self._apply_name_mapping_to_object(obj_name)
                if obj_name not in slot_to_name_to_objects[current_slot][current_shapekey_name]:
                    slot_to_name_to_objects[current_slot][current_shapekey_name].append(obj_name)
                if obj_name not in all_objects: all_objects.append(obj_name)
                obj_hash = self._extract_hash_from_name(obj_name)
                if obj_hash:
                    if obj_hash not in hash_to_objects: hash_to_objects[obj_hash] = []
                    if obj_name not in hash_to_objects[obj_hash]: hash_to_objects[obj_hash].append(obj_name)
        unique_hashes = list(OrderedDict.fromkeys(h for obj in all_objects if (h := self._extract_hash_from_name(obj))))
        return slot_to_name_to_objects, unique_hashes, hash_to_objects, all_objects

    def parse_vertex_struct(self, struct_definition):
        if not struct_definition or not struct_definition.strip():
            return None
        TYPE_SIZES = {
            'float': 4, 'float2': 8, 'float3': 12, 'float4': 16,
            'int': 4, 'int2': 8, 'int3': 12, 'int4': 16,
            'uint': 4, 'uint2': 8, 'uint3': 12, 'uint4': 16,
            'half': 2, 'half2': 4, 'half3': 6, 'half4': 8,
            'double': 8, 'double2': 16, 'double3': 24, 'double4': 32,
        }
        total_bytes = 0
        total_floats = 0
        attributes = []
        unrecognized_types = set()
        lines = struct_definition.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
                continue
            line = line.rstrip(';').strip()
            parts = line.split()
            if len(parts) >= 2:
                type_name = parts[0]
                var_name = parts[1].rstrip(';')
                if type_name in TYPE_SIZES:
                    byte_size = TYPE_SIZES[type_name]
                    total_bytes += byte_size
                    total_floats += byte_size // 4
                    attributes.append({'type': type_name, 'name': var_name, 'size': byte_size})
                elif type_name.lower() != 'struct' and not line.endswith('{') and not line.endswith('}'):
                    unrecognized_types.add(type_name)
        if unrecognized_types:
            print(f"警告: 发现未识别的顶点属性类型: {', '.join(unrecognized_types)}")
        if total_bytes == 0:
            print(f"警告: 无法解析顶点结构体定义，total_bytes为0")
            return None
        if not attributes:
            print(f"警告: 未找到有效的顶点属性")
            return None
        return (total_bytes, total_floats, attributes)

    def _detect_vertex_format(self, base_bytes, shapekey_bytes, struct_definition=None):
        VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX = 40, 10
        num_vertices = len(base_bytes) // VERTEX_STRIDE
        if struct_definition and struct_definition.strip():
            parsed = self.parse_vertex_struct(struct_definition)
            if parsed:
                VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, attributes = parsed
                num_vertices = len(base_bytes) // VERTEX_STRIDE
                print(f"使用结构体定义: 步长={VERTEX_STRIDE}字节, 每顶点{NUM_FLOATS_PER_VERTEX}个float, 顶点数={num_vertices}")
                return (VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, num_vertices)
            else:
                print(f"警告: 结构体定义解析失败，使用默认值")
        print(f"使用默认值: 步长={VERTEX_STRIDE}字节, 每顶点{NUM_FLOATS_PER_VERTEX}个float, 顶点数={num_vertices}")
        return (VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, num_vertices)

    def _process_shapekey_buffers(self, mod_export_path, slot_to_name_to_objects, hash_to_stride, hash_to_struct_def=None):
        use_packed = self.use_packed_buffers
        use_delta = self.store_deltas
        if not NUMPY_AVAILABLE:
            print("Numpy库未找到，无法执行缓冲区优化。")
            return False, {}
        print(f"开始处理缓冲区 (紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'})...")
        hash_to_actual_file_hash = {}
        buffers_to_process = set()
        for slot, names_data in slot_to_name_to_objects.items():
            for obj in [o for name, objs in names_data.items() for o in objs]:
                h = self._extract_hash_from_name(obj)
                if h: buffers_to_process.add((h, slot))
        print(f"  [DEBUG] 需要处理 {len(buffers_to_process)} 个缓冲区组合")
        for h, slot in sorted(list(buffers_to_process)):
            h_prefix = self._extract_hash_prefix(h)
            base_filename = f"{h}-Position.buf"
            base_path = os.path.join(mod_export_path, "Buffer0000", base_filename)
            print(f"  [DEBUG] 尝试查找基础文件: {base_path}")
            actual_hash = h
            if not os.path.exists(base_path):
                pattern = os.path.join(mod_export_path, "Buffer0000", f"{h_prefix}-*-Position.buf")
                matches = glob.glob(pattern)
                if matches:
                    base_path = matches[0]
                    base_filename = os.path.basename(base_path)
                    actual_hash = base_filename.replace("-Position.buf", "")
                    print(f"    通过前缀匹配找到基础文件: {base_filename}")
                else:
                    print(f"    [WARNING] 找不到基础文件，pattern: {pattern}")
            folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
            shapekey_filename = f"{actual_hash}-Position.buf"
            shapekey_path = os.path.join(mod_export_path, folder_name, shapekey_filename)
            print(f"  [DEBUG] 尝试查找形态键文件: {shapekey_path}")
            if not os.path.exists(shapekey_path):
                pattern = os.path.join(mod_export_path, folder_name, f"{h_prefix}-*-Position.buf")
                matches = glob.glob(pattern)
                if matches:
                    shapekey_path = matches[0]
                    shapekey_filename = os.path.basename(shapekey_path)
                    actual_hash = shapekey_filename.replace("-Position.buf", "")
                    print(f"    通过前缀匹配找到形态键文件: {shapekey_filename}")
                else:
                    print(f"    [WARNING] 找不到形态键文件，pattern: {pattern}")
            output_dir = os.path.join(mod_export_path, folder_name)
            print(f"  处理槽位 {slot} (哈希: {h}, 实际文件哈希: {actual_hash}, 前缀: {h_prefix})...")
            if not all(os.path.exists(p) for p in [base_path, shapekey_path]):
                print(f"    -> 跳过：找不到基础或形态键文件 for hash {h}, slot {slot}")
                print(f"       基础路径: {base_path} (存在: {os.path.exists(base_path)})")
                print(f"       形态键路径: {shapekey_path} (存在: {os.path.exists(shapekey_path)})")
                continue
            if h not in hash_to_actual_file_hash:
                hash_to_actual_file_hash[h] = actual_hash
            os.makedirs(output_dir, exist_ok=True)
            try:
                with open(base_path, 'rb') as f: base_bytes = f.read()
                with open(shapekey_path, 'rb') as f: shapekey_bytes = f.read()
                if len(base_bytes) != len(shapekey_bytes):
                    print(f"    -> 跳过：文件大小不匹配 for hash {h}, slot {slot}")
                    continue
                struct_definition = None
                if hash_to_struct_def and h in hash_to_struct_def:
                    struct_definition = hash_to_struct_def[h]
                VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, num_vertices = self._detect_vertex_format(base_bytes, shapekey_bytes, struct_definition)
                print(f"    -> 检测到格式: 步长={VERTEX_STRIDE}字节, 每顶点{NUM_FLOATS_PER_VERTEX}个float, 顶点数={num_vertices}")
                if h_prefix not in hash_to_stride:
                    hash_to_stride[h_prefix] = VERTEX_STRIDE
                base_data = np.frombuffer(base_bytes, dtype='f').reshape((num_vertices, NUM_FLOATS_PER_VERTEX))
                shapekey_data = np.frombuffer(shapekey_bytes, dtype='f').reshape((num_vertices, NUM_FLOATS_PER_VERTEX))
                output_prefix = os.path.join(output_dir, f"{actual_hash}-Position")
                if use_delta:
                    data_to_write = shapekey_data[:, :3] - base_data[:, :3]
                    filename_suffix = "_pos_delta"
                    if use_packed: filename_suffix = "_packed_pos_delta"
                    pos_diff_mask = ~np.isclose(base_data[:, :3], shapekey_data[:, :3], atol=1e-6).all(axis=1)
                    num_active_vertices = np.sum(pos_diff_mask)
                    if num_active_vertices == 0:
                        print(f"    -> 无位置差异，生成空文件。")
                        if use_packed:
                            open(f"{output_prefix}{filename_suffix}.buf", 'wb').close()
                            open(f"{output_prefix}_map.buf", 'wb').close()
                        else:
                            open(f"{output_prefix}{filename_suffix}.buf", 'wb').close()
                        continue
                    if use_packed:
                        packed_data = data_to_write[pos_diff_mask]
                        data_path = f"{output_prefix}{filename_suffix}.buf"
                        with open(data_path, 'wb') as f: f.write(packed_data.tobytes())
                        index_map = np.full(num_vertices, -1, dtype=np.int32)
                        index_map[pos_diff_mask] = np.arange(num_active_vertices, dtype=np.int32)
                        map_path = f"{output_prefix}_map.buf"
                        with open(map_path, 'wb') as f: f.write(index_map.tobytes())
                        print(f"    -> 成功生成: {os.path.basename(data_path)} 和 {os.path.basename(map_path)}")
                    else:
                        data_path = f"{output_prefix}{filename_suffix}.buf"
                        with open(data_path, 'wb') as f: f.write(data_to_write.tobytes())
                        print(f"    -> 成功生成: {os.path.basename(data_path)}")
                elif use_packed:
                    filename_suffix = "_packed"
                    diff_mask = ~np.isclose(base_data, shapekey_data, atol=1e-6).all(axis=1)
                    num_active_vertices = np.sum(diff_mask)
                    if num_active_vertices == 0:
                        print(f"    -> 无差异，生成空文件。")
                        open(f"{output_prefix}{filename_suffix}.buf", 'wb').close()
                        open(f"{output_prefix}_map.buf", 'wb').close()
                        continue
                    packed_data = shapekey_data[diff_mask]
                    data_path = f"{output_prefix}{filename_suffix}.buf"
                    with open(data_path, 'wb') as f: f.write(packed_data.tobytes())
                    index_map = np.full(num_vertices, -1, dtype=np.int32)
                    index_map[diff_mask] = np.arange(num_active_vertices, dtype=np.int32)
                    map_path = f"{output_prefix}_map.buf"
                    with open(map_path, 'wb') as f: f.write(index_map.tobytes())
                    print(f"    -> 成功生成: {os.path.basename(data_path)} 和 {os.path.basename(map_path)}")
                else:
                    print(f"    -> 标准模式，使用原始形态键文件。")
                    pass
            except Exception as e:
                print(f"    -> 处理时出错: {e}")
                return False, {}
        print("缓冲区处理完成。")
        return True, hash_to_actual_file_hash

    def _read_ini_to_ordered_dict(self, ini_file_path):
        sections = OrderedDict()
        current_section = None
        slider_panel_content = ""
        slider_marker = "; --- AUTO-APPENDED SLIDER CONTROL PANEL ---"
        try:
            with open(ini_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if slider_marker in content:
                marker_pos = content.find(slider_marker)
                slider_panel_content = content[marker_pos:]
                content = content[:marker_pos]
                print("[ShapeKey] 检测到滑块面板内容，将保留")
            for line in content.splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith('[') and stripped_line.endswith(']'):
                    current_section = stripped_line
                    if current_section not in sections:
                        sections[current_section] = []
                    continue
                if current_section:
                    sections[current_section].append(line)
        except Exception as e:
            print(f"读取INI文件失败: {e}")
        return sections, slider_panel_content

    def _write_ordered_dict_to_ini(self, sections, ini_file_path, slider_panel_content=""):
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

    def _get_vertex_attrs_node(self):
        if not self.inputs[0].is_linked:
            return None
        source_node = self.inputs[0].links[0].from_node
        if source_node.bl_idname == 'SSMTNode_PostProcess_VertexAttrs':
            return source_node
        if source_node.inputs[0].is_linked:
            prev_node = source_node.inputs[0].links[0].from_node
            if prev_node.bl_idname == 'SSMTNode_PostProcess_VertexAttrs':
                return prev_node
        return None

    def _get_vertex_struct_definition_for_object(self, vertex_attrs_node, obj_name):
        """根据物体名称获取顶点结构体定义（优先使用物体独立配置）"""
        if not vertex_attrs_node:
            return "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"
        
        # 尝试从 objects_config 中查找
        for cfg in vertex_attrs_node.objects_config:
            if cfg.object_name == obj_name and cfg.vertex_attributes and len(cfg.vertex_attributes) > 0:
                struct_lines = ["struct VertexAttributes {"]
                for item in cfg.vertex_attributes:
                    if item.attr_type and item.attr_name:
                        struct_lines.append(f"    {item.attr_type} {item.attr_name};")
                struct_lines.append("};")
                return "\n".join(struct_lines)
        
        # 回退到全局配置
        return vertex_attrs_node.get_vertex_struct_definition()

    def _get_shader_template_name(self):
        use_packed = self.use_packed_buffers
        use_delta = self.store_deltas
        use_optimized = self.use_optimized_lookup
        if use_optimized and use_delta and use_packed:
            return "shapekey_anim_packed_delta_v4_optimized.hlsl"
        elif use_delta and use_packed:
            return "shapekey_anim_packed_delta_v3.hlsl"
        elif use_delta:
            return "shapekey_anim_standard_delta_v3.hlsl"
        elif use_packed:
            return "shapekey_anim_packed.hlsl"
        else:
            return "shapekey_anim_standard.hlsl"

    def _get_shader_source_path(self):
        try:
            addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            asset_source_dir = os.path.join(addon_dir, "Toolset")
            shader_template_name = self._get_shader_template_name()
            shader_source_path = os.path.join(asset_source_dir, shader_template_name)
            return shader_source_path
        except Exception as e:
            print(f"获取着色器模板路径时出错: {e}")
            return None

    def _get_vertex_struct_definition(self):
        vertex_attrs_node = self._get_vertex_attrs_node()
        if vertex_attrs_node:
            return vertex_attrs_node.get_vertex_struct_definition()
        return "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"

    def _update_shader_file(self, shader_path, hash_slot_data, use_packed, use_delta, slot_list, hash_unique_objects, use_optimized=False, vertex_struct=None):
        try:
            with open(shader_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if vertex_struct is None:
                vertex_struct = self._get_vertex_struct_definition()
            if vertex_struct:
                content = re.sub(r"struct VertexAttributes\s*\{[^}]*\};", vertex_struct, content, flags=re.DOTALL)
            
            slot_to_freq_def = {slot: f"FREQ{i+1}" for i, slot in enumerate(slot_list)}
            obj_to_range_defs = {obj: (f"START{i+1}", f"END{i+1}") for i, obj in enumerate(hash_unique_objects)}
            
            define_lines = [f"// --- Shared Animation Intensity (per Slot) ---\n// From index {self.INTENSITY_START_INDEX} onwards"]
            for i, slot in enumerate(slot_list):
                define_lines.append(f"#define FREQ{i+1} IniParams[{self.INTENSITY_START_INDEX + i}].x // Slot {slot}")
            if not use_optimized:
                define_lines.extend([f"\n// --- Per-Object Vertex Ranges ---\n// From index {self.VERTEX_RANGE_START_INDEX} onwards"])
                for i, obj_name in enumerate(hash_unique_objects):
                    start_idx = self.VERTEX_RANGE_START_INDEX + i * 2
                    define_lines.append(f"#define START{i+1} (uint)IniParams[{start_idx}].x // {obj_name}")
                    define_lines.append(f"#define END{i+1}   (uint)IniParams[{start_idx + 1}].x")
            
            logic_lines = []
            if use_optimized:
                logic_lines.append("    // Optimized: Direct FREQ index lookup instead of hundreds of if-else branches")
                num_slots = len(slot_list)
                logic_lines.append(f"    uint num_slots = {num_slots};")
                for i, slot in enumerate(slot_list):
                    slot_index = i
                    logic_lines.extend([f"    // --- Slot {slot} (t{51+slot_index}) ---"])
                    logic_lines.append(f"    uint packed_idx_slot{slot_index} = i * num_slots + {slot_index};")
                    logic_lines.append(f"    uint freq_idx_slot{slot_index} = vertex_freq_indices[packed_idx_slot{slot_index}];")
                    logic_lines.append(f"    if (freq_idx_slot{slot_index} != 255)")
                    logic_lines.append("    {")
                    logic_lines.append(f"        float anim_weight_slot{slot_index} = IniParams[{self.INTENSITY_START_INDEX} + freq_idx_slot{slot_index}].x;")
                    if use_packed:
                        logic_lines.extend([f"        int packed_index = shapekey_maps[{slot_index}][i];", "        if (packed_index != -1)", "        {"])
                        logic_lines.append(f"            total_diff_position += shapekey_pos_deltas[{slot_index}][packed_index] * anim_weight_slot{slot_index};")
                        logic_lines.append("        }")
                    else:
                        logic_lines.append(f"        total_diff_position += shapekey_pos_deltas[{slot_index}][i] * anim_weight_slot{slot_index};")
                    logic_lines.append("    }")
            else:
                for i, slot in enumerate(slot_list):
                    slot_index = i
                    is_first_if = True
                    logic_lines.extend([f"    // --- Slot {slot} (t{51+slot_index}) ---", f"    float anim_weight_slot{slot_index} = 0.0;"])
                    logic_lines.append(f"    anim_weight_slot{slot_index} = {slot_to_freq_def[slot]};")
                    logic_lines.append(f"    if (anim_weight_slot{slot_index} > 1e-5)")
                    logic_lines.append("    {")
                    indent = "        "
                    read_idx = "i"
                    if use_packed:
                        logic_lines.extend([f"        int packed_index = shapekey_maps[{slot_index}][i];", "        if (packed_index != -1)", "        {"])
                        read_idx = "packed_index"
                        indent = "            "
                    if use_delta:
                        calc_line = f"total_diff_position += shapekey_pos_deltas[{slot_index}][{read_idx}] * anim_weight_slot{slot_index};"
                    else:
                        calc_line = f"total_diff_position += (shapekeys[{slot_index}][{read_idx}].position - base[i].position) * anim_weight_slot{slot_index};"
                    logic_lines.append(indent + calc_line)
                    if use_packed:
                        logic_lines.extend(["        }", "    }\n"])
                    else:
                        logic_lines.extend(["    }\n"])
            
            content = re.sub(r"// --- \[PYTHON-MANAGED BLOCK START\] ---.*?// --- \[PYTHON-MANAGED BLOCK END\] ---",
                            f"// --- [PYTHON-MANAGED BLOCK START] ---\n{chr(10).join(define_lines)}\n// --- [PYTHON-MANAGED BLOCK END] ---",
                            content, flags=re.DOTALL)
            content = re.sub(r"// --- \[PYTHON-MANAGED LOGIC START\] ---.*?// --- \[PYTHON-MANAGED LOGIC END\] ---",
                            f"// --- [PYTHON-MANAGED LOGIC START] ---\n{chr(10).join(logic_lines)}    // --- [PYTHON-MANAGED LOGIC END] ---",
                            content, flags=re.DOTALL)
            with open(shader_path, 'w', encoding='utf-8') as f:
                f.write(content)
            mode_str = f"紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'}, 优化查找:{'是' if use_optimized else '否'}"
            print(f"成功更新着色器 ({mode_str})，支持 {len(slot_list)} 个槽位。")
            return True
        except Exception as e:
            print(f"更新着色器文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _generate_vertex_freq_index_buffers(self, mod_export_path, hash_val, hash_slot_data, slot_list, vertex_count, calculated_ranges):
        if not NUMPY_AVAILABLE:
            print("Numpy库未找到，无法生成FREQ索引缓冲区")
            return False
        slot_to_index = {slot: i for i, slot in enumerate(slot_list)}
        print(f"    [DEBUG] 槽位到FREQ索引映射: {slot_to_index}")
        print(f"    [DEBUG] calculated_ranges 键: {list(calculated_ranges.keys())}")
        num_slots = len(slot_list)
        freq_indices = np.full(vertex_count * num_slots, 255, dtype=np.uint32)
        for slot, objects in hash_slot_data.items():
            if slot not in slot_to_index:
                continue
            freq_idx = slot_to_index[slot]
            slot_index = freq_idx
            slot_map_files = {}
            for obj_name in objects:
                obj_hash = self._extract_hash_from_name(obj_name)
                if obj_hash:
                    obj_prefix = self._extract_hash_prefix(obj_hash)
                    folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
                    map_path = os.path.join(mod_export_path, folder_name, f"{obj_hash}-Position_map.buf")
                    if not os.path.exists(map_path):
                        pattern = os.path.join(mod_export_path, folder_name, f"{obj_prefix}-*-Position_map.buf")
                        matches = glob.glob(pattern)
                        if matches:
                            map_path = matches[0]
                    if os.path.exists(map_path) and obj_hash not in slot_map_files:
                        try:
                            with open(map_path, 'rb') as f:
                                slot_map_files[obj_hash] = np.frombuffer(f.read(), dtype=np.int32)
                                print(f"    [DEBUG] 加载映射文件: {os.path.basename(map_path)}")
                        except Exception as e:
                            print(f"    读取映射文件失败: {e}")
            print(f"    [DEBUG] Slot {slot}: 处理 {len(objects)} 个物体, 找到 {len(slot_map_files)} 个映射文件")
            for obj_name in objects:
                obj_hash = self._extract_hash_from_name(obj_name)
                obj_prefix = self._extract_hash_prefix(obj_hash) if obj_hash else None
                hash_prefix = self._extract_hash_prefix(hash_val)
                if obj_prefix != hash_prefix:
                    print(f"        [DEBUG] 跳过物体 '{obj_name}' (前缀不匹配: {obj_prefix} != {hash_prefix})")
                    continue
                if obj_name not in calculated_ranges:
                    print(f"        [DEBUG] 物体 '{obj_name}' 不在 calculated_ranges 中")
                    continue
                start_v, end_v = calculated_ranges[obj_name]
                if start_v is None or end_v is None:
                    print(f"        [DEBUG] 物体 '{obj_name}' 范围无效: {start_v}-{end_v}")
                    continue
                start_v = max(0, min(start_v, vertex_count - 1))
                end_v = max(0, min(end_v, vertex_count - 1))
                print(f"        [DEBUG] 物体 '{obj_name}' 设置顶点 {start_v}-{end_v} 为 FREQ索引 {freq_idx}")
                index_map = slot_map_files.get(obj_hash)
                if index_map is not None:
                    for v in range(start_v, end_v + 1):
                        if v < len(index_map) and index_map[v] >= 0:
                            packed_idx = v * num_slots + slot_index
                            freq_indices[packed_idx] = freq_idx
                else:
                    for v in range(start_v, end_v + 1):
                        packed_idx = v * num_slots + slot_index
                        freq_indices[packed_idx] = freq_idx
                    print(f"        [DEBUG] 物体 '{obj_name}' 没有映射文件，直接设置所有顶点")
        output_dir = os.path.join(mod_export_path, "Buffer0000")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{hash_val}-Position_freq_indices.buf")
        with open(output_path, 'wb') as f:
            f.write(freq_indices.tobytes())
        print(f"    生成FREQ索引缓冲区: {os.path.basename(output_path)} (顶点数: {vertex_count}, 槽位数: {num_slots})")
        return num_slots

    def _add_auto_playback_logic(self, sections, slot_to_var):
        if not self.enable_auto_playback:
            return
        if '[Constants]' not in sections:
            sections['[Constants]'] = []
        const_lines = sections['[Constants]']
        const_content = "\n".join(const_lines)

        frame_count = self.auto_playback_frame_count
        step = self.auto_playback_step_frames
        mode = self.auto_playback_cycle_mode
        speed_min = self.auto_playback_speed_min
        speed_max = self.auto_playback_speed_max

        auto_vars = [
            "global $auto_play_enabled = 1",
            "global $auxTime = 0",
            "global $shapekey_frame = 0",
            f"global $frameEnd_min = {speed_min}",
            f"global $frameEnd_max = {speed_max}",
            f"global $frameEnd = {frame_count}",
        ]
        if mode == 'PINGPONG':
            auto_vars.append("global $pingpong_dir = 1")

        for var_line in auto_vars:
            if var_line.split('=')[0].strip() not in const_content:
                const_lines.append(var_line)

        playback_code = []
        playback_code.append("; ========== AUTO PLAYBACK (generated by ShapeKey node) ==========")
        playback_code.append("if ($auto_play_enabled == 1)")
        playback_code.append("    $auxTime = $auxTime + 1")
        playback_code.append(f"    if ($auxTime % {step} == 0)")

        if mode == 'FORWARD':
            playback_code.extend([
                "        if ($shapekey_frame < $frameEnd)",
                "            $shapekey_frame = $shapekey_frame + 1",
                "        else",
                "            $shapekey_frame = 0",
                "        endif"
            ])
        elif mode == 'REVERSE':
            playback_code.extend([
                "        if ($shapekey_frame < $frameEnd)",
                "            $shapekey_frame = $shapekey_frame + 1",
                "        else",
                "            $shapekey_frame = 0",
                "        endif"
            ])
        else:
            playback_code.extend([
                "        $shapekey_frame = $shapekey_frame + $pingpong_dir",
                "        if ($shapekey_frame >= $frameEnd)",
                "            $shapekey_frame = $frameEnd",
                "            $pingpong_dir = -1",
                "        endif",
                "        if ($shapekey_frame <= 0)",
                "            $shapekey_frame = 0",
                "            $pingpong_dir = 1",
                "        endif"
            ])

        playback_code.append("    endif")
        playback_code.append("")
        for slot, var_name in slot_to_var.items():
            if mode == 'FORWARD':
                expr = f"$shapekey_frame / $frameEnd"
            elif mode == 'REVERSE':
                expr = f"($frameEnd - $shapekey_frame) / $frameEnd"
            else:
                expr = f"$shapekey_frame / $frameEnd"
            playback_code.append(f"    {var_name} = {expr}")
        playback_code.append("endif")
        playback_code.append("; ========== END AUTO PLAYBACK ==========")

        if '[Present]' not in sections:
            sections['[Present]'] = []
        present_lines = sections['[Present]']
        insert_pos = 0
        for i, line in enumerate(present_lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(';'):
                insert_pos = i
                break
            else:
                insert_pos = i + 1
        for code_line in reversed(playback_code):
            present_lines.insert(insert_pos, code_line)

        print(f"[ShapeKey] 已添加自动播放逻辑 (模式={mode}, 基础帧数={frame_count}, 速度范围={speed_min}-{speed_max})")

    def _find_source_object_info_node(self, node):
        if node is None:
            return None
        if node.bl_idname == 'SSMTNode_Object_Info':
            return node
        if node.bl_idname in ('SSMTNode_Object_Group', 'SSMTNode_ToggleKey', 'SSMTNode_SwitchKey',
                            'SSMTNode_Object_Name_Modify', 'SSMTNode_VertexGroupProcess'):
            if node.inputs and node.inputs[0].is_linked:
                return self._find_source_object_info_node(node.inputs[0].links[0].from_node)
        if node.bl_idname == 'SSMTNode_Blueprint_Nest':
            blueprint_name = getattr(node, 'blueprint_name', '')
            if blueprint_name:
                nested_tree = bpy.data.node_groups.get(blueprint_name)
                if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                    for n in nested_tree.nodes:
                        if n.bl_idname == 'SSMTNode_Result_Output' and n.inputs and n.inputs[0].is_linked:
                            return self._find_source_object_info_node(n.inputs[0].links[0].from_node)
        return None

    def _get_shapekey_data_from_controller(self):
        controller = self._get_upstream_shapekey_controller()
        if not controller:
            print("[ShapeKey] 控制器不存在")
            return None

        def find_original_object(node):
            if node is None:
                return None
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'original_object_name', '')
                if not obj_name:
                    obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    return bpy.data.objects.get(obj_name)
                return None
            for input_socket in node.inputs:
                if input_socket.is_linked:
                    for link in input_socket.links:
                        result = find_original_object(link.from_node)
                        if result:
                            return result
            if node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for n in nested_tree.nodes:
                            if n.bl_idname == 'SSMTNode_Result_Output' and n.inputs and n.inputs[0].is_linked:
                                return find_original_object(n.inputs[0].links[0].from_node)
            return None

        original_objects = []
        for socket in controller.inputs:
            if socket.is_linked:
                for link in socket.links:
                    obj = find_original_object(link.from_node)
                    if obj and obj.type == 'MESH' and obj not in original_objects:
                        original_objects.append(obj)
                        print(f"[ShapeKey] 找到原始物体: {obj.name}")

        if not original_objects:
            print("[ShapeKey] 未找到任何原始物体")
            return None

        sk_to_objects = {}
        for obj in original_objects:
            if not obj.data or not obj.data.shape_keys:
                continue
            ref = obj.data.shape_keys.reference_key
            for kb in obj.data.shape_keys.key_blocks:
                if kb == ref:
                    continue
                sk_name = kb.name
                obj_name = obj.name
                if sk_name not in sk_to_objects:
                    sk_to_objects[sk_name] = []
                if obj_name not in sk_to_objects[sk_name]:
                    sk_to_objects[sk_name].append(obj_name)

        if not sk_to_objects:
            print("[ShapeKey] 原始物体没有形态键变体")
            return None

        slot_to_name_to_objects = OrderedDict()
        slot_index = 1
        for sk_name, obj_list in sk_to_objects.items():
            slot_to_name_to_objects[slot_index] = {sk_name: obj_list}
            slot_index += 1

        all_objects = [obj.name for obj in original_objects]
        hash_to_objects = OrderedDict()
        unique_hashes = []
        for obj_name in all_objects:
            h = self._extract_hash_from_name(obj_name)
            if h:
                if h not in unique_hashes:
                    unique_hashes.append(h)
                hash_to_objects.setdefault(h, []).append(obj_name)

        return slot_to_name_to_objects, unique_hashes, hash_to_objects, all_objects

    # -------------------------------------------------------------------------
    # 核心执行函数
    # -------------------------------------------------------------------------
    def execute_postprocess(self, mod_export_path):
        print(f"形态键配置后处理节点开始执行，Mod导出路径: {mod_export_path}")

        slot_to_name_to_objects, unique_hashes, hash_to_objects, all_objects = self._build_slot_data()

        if not slot_to_name_to_objects:
            print("未找到形态键数据（自动检测和手动配置均为空），跳过后处理")
            return

        print(f"[ShapeKey] 使用数据源: {'手动配置' if (self.slot_entries) else '自动检测'}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("路径中未找到任何.ini文件")
            return

        target_ini_file = ini_files[0]
        use_packed = self.use_packed_buffers
        use_delta = self.store_deltas
        use_optimized = self.use_optimized_lookup

        if (use_packed or use_delta or use_optimized) and not NUMPY_AVAILABLE:
            print("Numpy库未找到，无法使用优化功能")
            return

        shader_source_path = self._get_shader_source_path()
        if not shader_source_path or not os.path.exists(shader_source_path):
            print(f"着色器模板文件未找到: {shader_source_path}")
            return

        print(f"使用着色器模板: {self._get_shader_template_name()}")

        self._create_cumulative_backup(target_ini_file, mod_export_path)

        try:
            sections, slider_panel_content = self._read_ini_to_ordered_dict(target_ini_file)

            hash_to_stride = {}
            vertex_attrs_node = self._get_vertex_attrs_node()
            # 注意：不再调用 vertex_attrs_node._sync_objects_config()
            # 避免修改用户的顶点属性配置

            # 构建每个哈希对应的顶点结构体定义（基于该哈希下的代表物体）
            hash_to_struct_def = {}
            for h in unique_hashes:
                sample_objs = hash_to_objects.get(h, [])
                if sample_objs:
                    sample_obj_name = sample_objs[0]
                    struct_def = self._get_vertex_struct_definition_for_object(vertex_attrs_node, sample_obj_name)
                    hash_to_struct_def[h] = struct_def
                else:
                    if vertex_attrs_node:
                        hash_to_struct_def[h] = vertex_attrs_node.get_vertex_struct_definition()
                    else:
                        hash_to_struct_def[h] = "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"

            success, hash_to_actual_file_hash = self._process_shapekey_buffers(mod_export_path, slot_to_name_to_objects, hash_to_stride, hash_to_struct_def)
            if not success:
                print("缓冲区处理失败")
                return

            print(f"  [DEBUG] 哈希映射表: {hash_to_actual_file_hash}")

            all_slots = sorted(set(slot for slot in slot_to_name_to_objects.keys()))
            slot_to_objects = {}
            for slot, name_data in slot_to_name_to_objects.items():
                obj_list = []
                for obj in [o for name, objs in name_data.items() for o in objs]:
                    if obj not in obj_list:
                        obj_list.append(obj)
                slot_to_objects[slot] = obj_list

            all_unique_objects = list(OrderedDict.fromkeys(obj for slot_data in slot_to_name_to_objects.values() for name_data in slot_data.values() for obj in name_data))

            hash_to_base_resources = {}
            resource_pattern = re.compile(r'\[(Resource_?([a-f0-9]{8}(?:[_-][a-f0-9]+)*)_?Position(\d*))\]')
            for section_name in sections.keys():
                match = resource_pattern.match(section_name)
                if match:
                    full_name, hash_val, number = match.groups()
                    hash_val_normalized = hash_val.replace('_', '-')
                    hash_prefix = self._extract_hash_prefix(hash_val_normalized)
                    if hash_prefix and hash_prefix not in hash_to_base_resources:
                        hash_to_base_resources[hash_prefix] = []
                    if hash_prefix:
                        hash_to_base_resources[hash_prefix].append((int(number) if number else 1, full_name))
            for hash_val in hash_to_base_resources:
                hash_to_base_resources[hash_val].sort()
                hash_to_base_resources[hash_val] = [name for key, name in hash_to_base_resources[hash_val]]

            print("开始自动计算顶点索引范围...")
            draw_info_map = self._parse_ini_for_draw_info(sections, mod_export_path)
            calculated_ranges = {}
            for obj_name in all_objects:
                if obj_name not in draw_info_map:
                    continue
                info_list = draw_info_map[obj_name]
                all_ranges = []
                for info in info_list:
                    start_v, end_v = self._calculate_vertex_range(info['ib_path'], info['draw_params'])
                    if start_v is not None and end_v is not None:
                        all_ranges.append((start_v, end_v))
                if all_ranges:
                    min_start = min(r[0] for r in all_ranges)
                    max_end = max(r[1] for r in all_ranges)
                    calculated_ranges[obj_name] = (min_start, max_end)

            vertex_counts = {}
            for s, ls in sections.items():
                m = re.match(r'\[TextureOverride_([a-f0-9]{8}(?:[_-][a-f0-9]+)*)_[^_]*_VertexLimitRaise\]', s)
                if m:
                    for l in ls:
                        if l.strip().startswith('override_vertex_count'):
                            try:
                                hash_val = m.group(1).replace('_', '-')
                                hash_prefix = self._extract_hash_prefix(hash_val)
                                if hash_prefix:
                                    vertex_counts[hash_prefix] = int(l.split('=')[1].strip())
                                    print(f"  [DEBUG] 从INI读取顶点数: section={s}, hash_prefix={hash_prefix}, count={vertex_counts[hash_prefix]}")
                            except (ValueError, IndexError):
                                pass

            print(f"  [DEBUG] vertex_counts 字典: {vertex_counts}")

            for h in unique_hashes:
                h_prefix = self._extract_hash_prefix(h)
                if h_prefix not in vertex_counts:
                    pattern = os.path.join(mod_export_path, "Buffer0000", f"{h_prefix}-*-Position.buf")
                    matches = glob.glob(pattern)
                    if matches:
                        try:
                            file_size = os.path.getsize(matches[0])
                            stride = hash_to_stride.get(h_prefix, 40)
                            inferred_count = file_size // stride
                            vertex_counts[h_prefix] = inferred_count
                            print(f"  [DEBUG] 从文件大小推断顶点数: hash_prefix={h_prefix}, file={os.path.basename(matches[0])}, size={file_size}, stride={stride}, count={inferred_count}")
                        except Exception as e:
                            print(f"  [WARNING] 无法推断顶点数: {e}")

            dest_res_dir = os.path.join(mod_export_path, "res")
            os.makedirs(dest_res_dir, exist_ok=True)

            hash_to_shader_paths = {}
            for hash_val in unique_hashes:
                shader_dest_path = os.path.join(dest_res_dir, f"shapekey_anim_{hash_val}.hlsl")
                shutil.copy2(shader_source_path, shader_dest_path)
                hash_to_shader_paths[hash_val] = shader_dest_path
                print(f"已创建独立着色器文件: shapekey_anim_{hash_val}.hlsl")

            for hash_val in unique_hashes:
                hash_objects = hash_to_objects.get(hash_val, [])
                hash_slot_objects = {}
                for slot, name_data in slot_to_name_to_objects.items():
                    matched_objs = []
                    for obj in [o for name, objs in name_data.items() for o in objs]:
                        if obj in hash_objects and obj not in matched_objs:
                            matched_objs.append(obj)
                    if matched_objs:
                        hash_slot_objects[slot] = matched_objs
                if not hash_slot_objects:
                    continue

                slot_list = sorted(hash_slot_objects.keys())
                hash_unique_objects = list(OrderedDict.fromkeys(obj for slot, objs in hash_slot_objects.items() for obj in objs))

                if use_optimized:
                    hash_prefix = self._extract_hash_prefix(hash_val)
                    vertex_count = vertex_counts.get(hash_prefix, 10000)
                    actual_file_hash = hash_to_actual_file_hash.get(hash_val, hash_val)
                    self._generate_vertex_freq_index_buffers(mod_export_path, actual_file_hash, hash_slot_objects, slot_list, vertex_count, calculated_ranges)

                struct_def = hash_to_struct_def.get(hash_val)
                if not self._update_shader_file(hash_to_shader_paths[hash_val], hash_slot_objects, use_packed, use_delta, slot_list, hash_unique_objects, use_optimized, struct_def):
                    print(f"更新哈希 {hash_val} 的着色器文件失败")

            if '[Constants]' not in sections:
                sections['[Constants]'] = []
            constants_lines = sections['[Constants]']
            constants_content = "".join(constants_lines)
            vars_to_define = set()

            existing_param_names = set()
            slot_to_var = {}
            for slot in all_slots:
                var_name = self._create_safe_var_name(f"slot{slot}", prefix="$Freq_", existing_names=existing_param_names)
                slot_to_var[slot] = var_name

            constants_lines.append("\n; --- Auto-generated Shape Key Intensity Controls (per Slot) ---")
            for slot, var_name in slot_to_var.items():
                if var_name not in constants_content:
                    constants_lines.append(f"; 控制槽位 {slot} 的形态键强度")
                    constants_lines.append(f"global persist {var_name} = 0.0")

            constants_lines.append("\n; --- Auto-generated Vertex Ranges for Shape Keys ---")
            existing_vertex_range_names = set()
            vertex_range_vars = {}
            for obj_name, (start_v, end_v) in calculated_ranges.items():
                if start_v is None:
                    continue
                safe_name = self._create_safe_var_name(obj_name.replace("-", "_"), existing_names=existing_vertex_range_names)
                start_var, end_var = f"$SV_{safe_name}", f"$EV_{safe_name}"
                vertex_range_vars[obj_name] = (start_var, end_var)
                if start_var not in constants_content:
                    constants_lines.append(f"global {start_var} = {start_v}")
                if end_var not in constants_content:
                    constants_lines.append(f"global {end_var} = {end_v}")

            for h in unique_hashes:
                h_prefix = self._extract_hash_prefix(h)
                base_resources = hash_to_base_resources.get(h_prefix, [])
                res_to_post = base_resources if base_resources else [f"Resource_{self._hash_to_resource_prefix(h)}_Position"]
                for res_name in res_to_post:
                    if f"post {res_name} = copy_desc" not in constants_content:
                        constants_lines.append(f"post {res_name} = copy_desc {res_name}_0")
                if len(base_resources) > 1:
                    vars_to_define.add("$swapkey100")
                if f"post run = CustomShader_{h}_Anim" not in constants_content:
                    constants_lines.append(f"post run = CustomShader_{h}_Anim")

            if vars_to_define:
                constants_lines.append("\n; --- Auto-generated Base Mesh Switch Key ---")
                for var in sorted(list(vars_to_define)):
                    if f"global persist {var}" not in constants_content and f"global {var}" not in constants_content:
                        constants_lines.append(f"global persist {var} = 1")

            if '[Present]' not in sections:
                sections['[Present]'] = []
            present_lines = sections['[Present]']
            present_content = "".join(present_lines)
            if 'if $active0 == 1' not in present_content:
                present_lines.extend(['if $active0 == 1', *[f"    run = CustomShader_{h}_Anim" for h in unique_hashes], 'endif'])

            export_setting = None
            for s in self.slot_settings:
                if s.slot_index == self.export_slot_index:
                    export_setting = s
                    break
            if export_setting is None and len(self.slot_settings) > 0:
                export_setting = self.slot_settings[0]

            if export_setting and export_setting.enable_auto_playback:
                old_enable = self.enable_auto_playback
                old_frame = self.auto_playback_frame_count
                old_step = self.auto_playback_step_frames
                old_mode = self.auto_playback_cycle_mode
                old_min = self.auto_playback_speed_min
                old_max = self.auto_playback_speed_max

                self.enable_auto_playback = export_setting.enable_auto_playback
                self.auto_playback_frame_count = export_setting.auto_playback_frame_count
                self.auto_playback_step_frames = export_setting.auto_playback_step_frames
                self.auto_playback_cycle_mode = export_setting.auto_playback_cycle_mode
                self.auto_playback_speed_min = export_setting.auto_playback_speed_min
                self.auto_playback_speed_max = export_setting.auto_playback_speed_max

                self._add_auto_playback_logic(sections, slot_to_var)

                self.enable_auto_playback = old_enable
                self.auto_playback_frame_count = old_frame
                self.auto_playback_step_frames = old_step
                self.auto_playback_cycle_mode = old_mode
                self.auto_playback_speed_min = old_min
                self.auto_playback_speed_max = old_max

            hash_to_slots = {
                h: sorted([s for s, nd in slot_to_name_to_objects.items() if any(h in o for n in nd for o in nd[n])])
                for h in unique_hashes
            }

            compute_blocks_to_add = OrderedDict()
            for h in unique_hashes:
                block_name = f"[CustomShader_{h}_Anim]"
                if block_name in sections:
                    continue

                hash_objects = hash_to_objects.get(h, [])
                hash_slot_objects = {}
                for slot, name_data in slot_to_name_to_objects.items():
                    matched_objs = []
                    for obj in [o for name, objs in name_data.items() for o in objs]:
                        if obj in hash_objects and obj not in matched_objs:
                            matched_objs.append(obj)
                    if matched_objs:
                        hash_slot_objects[slot] = matched_objs

                if hash_slot_objects:
                    slot_list = sorted(hash_slot_objects.keys())
                    hash_unique_objects = list(OrderedDict.fromkeys(obj for slot, objs in hash_slot_objects.items() for obj in objs))

                    block_lines = ["\n    ; --- Shared Intensity Controls (per Slot) ---"]
                    for i, slot in enumerate(slot_list):
                        var_name = slot_to_var.get(slot, f"$Freq_unknown_{slot}")
                        block_lines.append(f"    x{self.INTENSITY_START_INDEX + i} = {var_name} \n; Slot {slot}")
                    block_lines.append("\n    ; --- Per-Object Vertex Range Controls ---")
                    for i, obj_name in enumerate(hash_unique_objects):
                        if obj_name in calculated_ranges and calculated_ranges[obj_name][0] is not None:
                            start_var, end_var = vertex_range_vars.get(obj_name, (f"$SV_unknown", f"$EV_unknown"))
                            block_lines.append(f"    x{self.VERTEX_RANGE_START_INDEX + i*2} = {start_var} \n; {obj_name} Start")
                            block_lines.append(f"    x{self.VERTEX_RANGE_START_INDEX + i*2 + 1} = {end_var} \n; {obj_name} End")

                    t_registers_to_null = []
                    slots_for_hash = hash_to_slots.get(h, [])

                    if not use_delta:
                        block_lines.append(f"\n    cs-t50 = copy Resource_{self._hash_to_resource_prefix(h)}_Position0000")
                        t_registers_to_null.append("cs-t50")

                    res_suffix = "_packed_pos_delta" if use_packed and use_delta else \
                                "_pos_delta" if use_delta else \
                                "_packed" if use_packed else ""

                    mode_str = f"紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'}, 优化查找:{'是' if use_optimized else '否'}"
                    block_lines.append(f"\n    ; --- Binding Shape Key Buffers (Mode: {mode_str}) ---")
                    for slot in slots_for_hash:
                        res_name = f"Resource_{self._hash_to_resource_prefix(h)}_Position100{slot}{res_suffix}"
                        if not (use_packed or use_delta):
                            res_name = f"Resource_{self._hash_to_resource_prefix(h)}_Position100{slot}"

                        t_reg = 51 + slot - 1
                        block_lines.append(f"    cs-t{t_reg} = copy {res_name}")
                        t_registers_to_null.append(f"cs-t{t_reg}")
                        if use_packed:
                            map_reg = 75 + slot - 1
                            block_lines.append(f"    cs-t{map_reg} = copy Resource_{self._hash_to_resource_prefix(h)}_Position100{slot}_Map")
                            t_registers_to_null.append(f"cs-t{map_reg}")

                    if use_optimized:
                        block_lines.append(f"    cs-t99 = copy Resource_{self._hash_to_resource_prefix(h)}_Position_FreqIndices")
                        t_registers_to_null.append("cs-t99")

                    block_lines.append(f"    cs = ./res/shapekey_anim_{h}.hlsl")

                    h_prefix = self._extract_hash_prefix(h)
                    base_resources = hash_to_base_resources.get(h_prefix, [])
                    res_to_bind = base_resources if base_resources else [f"Resource_{self._hash_to_resource_prefix(h)}_Position"]
                    if len(res_to_bind) > 1:
                        block_lines.append(f"\n    ; --- Base Mesh Switching ---")
                        for i, res_name in enumerate(res_to_bind, 1):
                            block_lines.extend([f"    if $swapkey100 == {i}", f"        cs-u5 = copy {res_name}_0", f"        {res_name} = ref cs-u5", "    endif"])
                    else:
                        res_name = res_to_bind[0]
                        block_lines.extend([f"    cs-u5 = copy {res_name}_0", f"    {res_name} = ref cs-u5"])

                    dispatch_count = vertex_counts.get(h_prefix, 10000)
                    if dispatch_count == 0:
                        dispatch_count = 10000
                    block_lines.extend([f"    Dispatch = {dispatch_count}, 1, 1", "    cs-u5 = null", *[f"    {reg} = null" for reg in sorted(list(set(t_registers_to_null)))]])
                    compute_blocks_to_add[block_name] = block_lines

            new_resource_lines = []
            generated_section_names = set()

            for h in unique_hashes:
                h_prefix = self._extract_hash_prefix(h)
                actual_file_hash = hash_to_actual_file_hash.get(h, h)
                section_name = f"[Resource_{self._hash_to_resource_prefix(h)}_Position0000]"
                if section_name not in sections and section_name not in generated_section_names:
                    stride = hash_to_stride.get(h_prefix, 40)
                    new_resource_lines.extend([section_name, "type = Buffer", f"stride = {stride}", f"filename = Buffer0000/{actual_file_hash}-Position.buf", ""])
                    generated_section_names.add(section_name)

            for slot, names_data in slot_to_name_to_objects.items():
                for obj in [o for name, objs in names_data.items() for o in objs]:
                    h = self._extract_hash_from_name(obj)
                    h_prefix = self._extract_hash_prefix(h) if h else None
                    if h_prefix:
                        actual_file_hash = hash_to_actual_file_hash.get(h, h)
                        base_stride = hash_to_stride.get(h_prefix, 40)
                        stride, filename, section_name = 0, "", ""
                        if use_delta:
                            res_suffix = "_packed_pos_delta" if use_packed else "_pos_delta"
                            stride = 12
                        elif use_packed:
                            res_suffix = "_packed"
                            stride = base_stride
                        else:
                            res_suffix = ""
                            stride = base_stride

                        if use_delta or use_packed:
                            section_name = f"[Resource_{self._hash_to_resource_prefix(h)}_Position100{slot}{res_suffix}]"
                            folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
                            filename = f"{folder_name}/{actual_file_hash}-Position{res_suffix}.buf"
                            if section_name not in sections and section_name not in generated_section_names:
                                new_resource_lines.extend([section_name, "type = Buffer", f"stride = {stride}", f"filename = {filename}", ""])
                                generated_section_names.add(section_name)

                        if use_packed:
                            map_section = f"[Resource_{self._hash_to_resource_prefix(h)}_Position100{slot}_Map]"
                            folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
                            if map_section not in sections and map_section not in generated_section_names:
                                new_resource_lines.extend([map_section, "type = Buffer", "stride = 4", f"filename = {folder_name}/{actual_file_hash}-Position_map.buf", ""])
                                generated_section_names.add(map_section)

            if use_optimized:
                for h in unique_hashes:
                    actual_file_hash = hash_to_actual_file_hash.get(h, h)
                    freq_idx_section = f"[Resource_{self._hash_to_resource_prefix(h)}_Position_FreqIndices]"
                    if freq_idx_section not in sections and freq_idx_section not in generated_section_names:
                        new_resource_lines.extend([freq_idx_section, "type = Buffer", "stride = 4", f"filename = Buffer0000/{actual_file_hash}-Position_freq_indices.buf", ""])
                        generated_section_names.add(freq_idx_section)

            if new_resource_lines:
                sections[";; --- Generated Shape Key Buffers ---"] = new_resource_lines

            for h in unique_hashes:
                h_prefix = self._extract_hash_prefix(h)
                for res_name in hash_to_base_resources.get(h_prefix, [f"Resource_{self._hash_to_resource_prefix(h)}_Position"]):
                    if f"[{res_name}]" in sections and not any(f"[{res_name}_0]" in line for line in sections[f"[{res_name}]"]):
                        sections[f"[{res_name}]"].insert(0, f"[{res_name}_0]")

            sections.update(compute_blocks_to_add)
            self._write_ordered_dict_to_ini(sections, target_ini_file, slider_panel_content)

            mode_str = f"紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'}, 优化查找:{'是' if use_optimized else '否'}"
            print(f"形态键配置({mode_str})已生成到 {os.path.basename(target_ini_file)}")

        except Exception as e:
            print(f"生成形态键配置时发生未知错误: {e}")
            import traceback
            traceback.print_exc()

        print("形态键配置后处理节点执行完成")


# =============================================================================
# 注册所有类
# =============================================================================
classes = (
    SSMT_ShapeKeySlotEntry,
    SSMT_SlotSettings,
    SSMT_OT_ShapeKeySetSlot,
    SSMTNode_PostProcess_ShapeKey,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)