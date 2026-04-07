# blueprint_preset.py
import bpy
import json
import os
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

# -----------------------------------------------------------------------------
# 辅助函数：判断属性是否应该保存（过滤工程专有数据）
# -----------------------------------------------------------------------------
def should_save_property(node, prop_name):
    """返回 True 表示保存，False 表示跳过（物体引用等工程专有数据）"""
    # 通用物体引用属性
    if prop_name in {
        "object_name", "object_id", "original_object_name",
        "source_object", "target_object",
        "draw_ib", "component", "index_count", "first_index", "alias_name", "prefix",
        "mapping_text_name", "target_hash", "temp_collection_name",
        "health_character_hash", "health_combat_ui_hash", "health_bar_hash",
        "blueprint_name", "replace_name",
        "mapping_list", "object_list", "cross_ib_list",
    }:
        return False

    # 针对特定节点类型
    if node.bl_idname == 'SSMTNode_MultiFile_Export':
        if prop_name in {"object_list", "temp_collection_name"}:
            return False
    if node.bl_idname == 'SSMTNode_VertexGroupMatch':
        if prop_name in {"source_object", "target_object", "target_hash", "mapping_text_name"}:
            return False
    if node.bl_idname == 'SSMTNode_VertexGroupMappingInput':
        if prop_name == "mapping_text":
            return False
    if node.bl_idname == 'SSMTNode_Object_Name_Modify':
        if prop_name == "mapping_list":
            return False
    return True

def get_node_properties(node):
    """提取节点需要保存的属性（排除工程专有数据）"""
    ignore_props = {
        "rna_type", "name", "id_data", "select", "parent", "dimensions",
        "bl_idname", "bl_label", "bl_icon", "width", "height", "hide",
        "location", "use_custom_color", "color", "inputs", "outputs",
        "internal_links", "mute", "show_options", "show_preview"
    }
    props = {}
    for prop_name in dir(node):
        if prop_name.startswith("_") or prop_name in ignore_props:
            continue
        try:
            prop = node.bl_rna.properties.get(prop_name)
            if prop and not prop.is_readonly and should_save_property(node, prop_name):
                value = getattr(node, prop_name)
                if isinstance(value, (str, int, float, bool, tuple, list)):
                    props[prop_name] = value
        except Exception:
            pass
    return props

def get_node_id(node, id_map):
    if node.name not in id_map:
        id_map[node.name] = len(id_map)
    return id_map[node.name]

def get_socket_index(socket, is_input=True):
    """获取插槽在其所属节点inputs/outputs列表中的索引"""
    if is_input:
        for i, s in enumerate(socket.node.inputs):
            if s == socket:
                return i
    else:
        for i, s in enumerate(socket.node.outputs):
            if s == socket:
                return i
    return -1

# -----------------------------------------------------------------------------
# 保存预设
# -----------------------------------------------------------------------------
class SSMT_OT_SavePreset(Operator):
    bl_idname = "ssmt.save_preset"
    bl_label = "保存蓝图预设"
    bl_description = "将当前蓝图中的所有节点保存为预设文件"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.json', options={'HIDDEN'})

    def invoke(self, context, event):
        tree = self._get_current_blueprint_tree(context)
        if not tree:
            self.report({'ERROR'}, "未找到有效的蓝图树")
            return {'CANCELLED'}
        self.filepath = os.path.join(bpy.path.abspath("//"), f"{tree.name}_preset.json")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        tree = self._get_current_blueprint_tree(context)
        if not tree:
            return {'CANCELLED'}

        node_id_map = {}
        nodes_data = []
        for node in tree.nodes:
            if node.bl_idname == 'NodeFrame':
                continue
            data = {
                "id": get_node_id(node, node_id_map),
                "type": node.bl_idname,
                "location": (node.location.x, node.location.y),
                "properties": get_node_properties(node)
            }
            nodes_data.append(data)

        links_data = []
        for link in tree.links:
            if link.from_node.bl_idname == 'NodeFrame' or link.to_node.bl_idname == 'NodeFrame':
                continue
            links_data.append({
                "from_node": get_node_id(link.from_node, node_id_map),
                "from_socket_idx": get_socket_index(link.from_socket, is_input=False),
                "to_node": get_node_id(link.to_node, node_id_map),
                "to_socket_idx": get_socket_index(link.to_socket, is_input=True),
            })

        preset_data = {"version": 2, "nodes": nodes_data, "links": links_data}
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, indent=4, ensure_ascii=False)
            self.report({'INFO'}, f"预设已保存到: {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"保存失败: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

    def _get_current_blueprint_tree(self, context):
        space = context.space_data
        if space and space.type == 'NODE_EDITOR':
            tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
            if tree and tree.bl_idname == 'SSMTBlueprintTreeType':
                return tree
        return None

# -----------------------------------------------------------------------------
# 加载预设
# -----------------------------------------------------------------------------
class SSMT_OT_LoadPreset(Operator):
    bl_idname = "ssmt.load_preset"
    bl_label = "加载蓝图预设"
    bl_description = "从预设文件加载节点并添加到当前蓝图"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.json', options={'HIDDEN'})
    clear_existing: BoolProperty(
        name="清空现有节点",
        description="加载前清空当前蓝图中的所有节点",
        default=True
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        tree = self._get_current_blueprint_tree(context)
        if not tree:
            self.report({'ERROR'}, "请先打开一个蓝图树")
            return {'CANCELLED'}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                preset = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"读取文件失败: {e}")
            return {'CANCELLED'}

        if self.clear_existing:
            for node in list(tree.nodes):
                if node.bl_idname != 'NodeFrame':
                    tree.nodes.remove(node)

        # 第一步：创建节点
        new_nodes = {}
        for node_info in preset["nodes"]:
            new_node = tree.nodes.new(type=node_info["type"])
            new_node.location = node_info["location"]
            for prop_name, value in node_info["properties"].items():
                if hasattr(new_node, prop_name):
                    setattr(new_node, prop_name, value)
            new_nodes[node_info["id"]] = new_node

        # 第二步：统计每个目标节点需要的最大输入插槽索引
        max_input_slot_needed = {}
        for link_info in preset["links"]:
            target_id = link_info["to_node"]
            idx = link_info["to_socket_idx"]
            if target_id not in max_input_slot_needed or idx > max_input_slot_needed[target_id]:
                max_input_slot_needed[target_id] = idx

        # 第三步：为动态插槽节点预创建足够的输入插槽
        DYNAMIC_NODE_TYPES = {
            'SSMTNode_Object_Group',
            'SSMTNode_Result_Output',
            'SSMTNode_ToggleKey',
            'SSMTNode_SwitchKey',
        }
        for node_id, node in new_nodes.items():
            if node.bl_idname in DYNAMIC_NODE_TYPES:
                needed_count = max_input_slot_needed.get(node_id, -1) + 1
                if needed_count > 0:
                    # 确定插槽类型和基础名称
                    if node.bl_idname == 'SSMTNode_SwitchKey':
                        socket_type = 'SSMTSocketObject'
                        base_name = "Status"
                    elif node.bl_idname == 'SSMTNode_ToggleKey':
                        socket_type = 'SSMTSocketObject'
                        base_name = "Input"
                    else:
                        socket_type = 'SSMTSocketObject'
                        base_name = "Input"
                    # 如果当前插槽数量不足，则添加
                    while len(node.inputs) < needed_count:
                        node.inputs.new(socket_type, f"{base_name} {len(node.inputs) + 1}")

        # 第四步：建立连接（使用插槽索引）
        for link_info in preset["links"]:
            from_node = new_nodes.get(link_info["from_node"])
            to_node = new_nodes.get(link_info["to_node"])
            if not from_node or not to_node:
                continue
            from_idx = link_info["from_socket_idx"]
            to_idx = link_info["to_socket_idx"]
            if from_idx < 0 or from_idx >= len(from_node.outputs):
                continue
            if to_idx < 0 or to_idx >= len(to_node.inputs):
                continue
            from_socket = from_node.outputs[from_idx]
            to_socket = to_node.inputs[to_idx]
            tree.links.new(from_socket, to_socket)

        # 第五步：调用 update 清理多余的空插槽
        for node in new_nodes.values():
            if hasattr(node, 'update'):
                try:
                    node.update()
                except Exception:
                    pass

        # 第六步：修复形态键控制器节点的颜色（确保显示正常）
        for node in new_nodes.values():
            node.use_custom_color = False

        for area in context.screen.areas:
            if area.type == 'NODE_EDITOR':
                area.tag_redraw()

        self.report({'INFO'}, f"预设加载完成，共创建 {len(new_nodes)} 个节点")
        return {'FINISHED'}

    def _get_current_blueprint_tree(self, context):
        space = context.space_data
        if space and space.type == 'NODE_EDITOR':
            tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
            if tree and tree.bl_idname == 'SSMTBlueprintTreeType':
                return tree
        return None

# -----------------------------------------------------------------------------
# 注册
# -----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(SSMT_OT_SavePreset)
    bpy.utils.register_class(SSMT_OT_LoadPreset)

def unregister():
    bpy.utils.unregister_class(SSMT_OT_LoadPreset)
    bpy.utils.unregister_class(SSMT_OT_SavePreset)