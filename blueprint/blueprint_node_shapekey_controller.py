import bpy
from .blueprint_node_base import SSMTNodeBase, SSMTSocketObject


class SSMTNode_ShapeKeyController(SSMTNodeBase):
    """形态键控制器：增强版Group节点
    
    将输入的每个物体按其形态键数量增殖成多个副本，
    然后通过单一输出传递给下游节点。
    
    例：输入1个有3个形态键的物体 → 输出4个物体(基准+3个形态键变体)
        输入2个物体(分别有2和3个形态键) → 输出7个物体
    """
    bl_idname = 'SSMTNode_ShapeKeyController'
    bl_label = '形态键控制器'
    bl_icon = 'SHAPEKEY_DATA'

    selected_obj_index: bpy.props.IntProperty(name="插座索引", default=0, min=0)
    selected_key_index: bpy.props.IntProperty(name="形态键索引", default=0, min=0)

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.outputs.new('SSMTSocketObject', "顶点属性定义")
        self.outputs.new('SSMTSocketObject', "形态键配置")
        self.width = 300

    def update(self):
        """动态管理输入插座：与Group节点行为一致"""
        if len(self.inputs) == 0:
            self.inputs.new('SSMTSocketObject', "Input 1")
            return
        if self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
            return
        if len(self.inputs) > 1 and not self.inputs[-2].is_linked and not self.inputs[-1].is_linked:
            self.inputs.remove(self.inputs[-1])
            return

    # ---- 物体提取 ----

    def get_connected_objects(self):
        """返回所有已连接的有效物体列表 [(索引, 物体), ...]"""
        objects = []
        for i, socket in enumerate(self.inputs):
            if socket.is_linked:
                obj = self._get_object_from_socket(socket)
                if obj:
                    objects.append((i, obj))
        return objects

    def get_connected_objects_with_nodes(self):
        """
        返回 [(物体, 原始Object_Info节点, 形态键名或None), ...]
        供导出系统使用，保留元数据传递
        """
        result = []
        for i, socket in enumerate(self.inputs):
            if socket.is_linked:
                from_node = socket.links[0].from_node
                obj = self._get_object_from_socket(socket)
                if not obj:
                    continue
                # 找到上游的原始节点（Object_Info 或 MultiFile_Export）
                src_node = self._find_source_node(from_node)
                if src_node is None:
                    continue
                if obj.type != 'MESH':
                    continue
                # 获取形态键列表（排除参考键）
                shape_keys = []
                if obj.data and obj.data.shape_keys:
                    ref = obj.data.shape_keys.reference_key
                    shape_keys = [kb.name for kb in obj.data.shape_keys.key_blocks if kb != ref]
                # 基准变体（所有形态键归零）
                result.append((obj, src_node, None))
                # 每个形态键一个变体
                for sk_name in shape_keys:
                    result.append((obj, src_node, sk_name))
        return result

    def _find_source_node(self, node):
        """向上追溯找到 Object_Info 或 MultiFile_Export 节点"""
        if node is None:
            return None
        if node.bl_idname in ('SSMTNode_Object_Info', 'SSMTNode_MultiFile_Export'):
            return node
        # 透传类节点
        if node.bl_idname in ('SSMTNode_Object_Name_Modify', 'SSMTNode_VertexGroupProcess',
                              'SSMTNode_Object_Group', 'SSMTNode_ToggleKey', 'SSMTNode_SwitchKey',
                              'SSMTNode_ShapeKeyController'):
            if node.inputs and node.inputs[0].is_linked:
                return self._find_source_node(node.inputs[0].links[0].from_node)
        # 嵌套蓝图
        if node.bl_idname == 'SSMTNode_Blueprint_Nest':
            blueprint_name = getattr(node, 'blueprint_name', '')
            if blueprint_name:
                nested_tree = bpy.data.node_groups.get(blueprint_name)
                if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                    for n in nested_tree.nodes:
                        if n.bl_idname == 'SSMTNode_Result_Output' and n.inputs and n.inputs[0].is_linked:
                            return self._find_source_node(n.inputs[0].links[0].from_node)
        return None

    def _get_object_from_socket(self, socket):
        """从socket向上追溯获取实际物体"""
        if not socket.is_linked:
            return None
        from_node = socket.links[0].from_node
        return self._extract_object_from_node(from_node)

    def _extract_object_from_node(self, node):
        """从上游节点中提取物体引用"""
        if node is None:
            return None
        # Object Info节点：直接读取object_name
        if node.bl_idname == 'SSMTNode_Object_Info':
            return bpy.data.objects.get(getattr(node, 'object_name', ''))
        # MultiFile Export节点
        if node.bl_idname == 'SSMTNode_MultiFile_Export':
            export_index = getattr(node, 'current_export_index', 1) - 1
            obj_list = getattr(node, 'object_list', [])
            if 0 <= export_index < len(obj_list):
                return bpy.data.objects.get(obj_list[export_index].object_name)
            return None
        # 透传类节点：继续向上追溯第一个输入
        if node.bl_idname in ('SSMTNode_Object_Name_Modify', 'SSMTNode_VertexGroupProcess',
                              'SSMTNode_Object_Group', 'SSMTNode_ToggleKey', 'SSMTNode_SwitchKey',
                              'SSMTNode_ShapeKeyController'):
            if node.inputs and node.inputs[0].is_linked:
                return self._extract_object_from_node(node.inputs[0].links[0].from_node)
        # Blueprint Nest节点：找到内部Result_Output
        if node.bl_idname == 'SSMTNode_Blueprint_Nest':
            blueprint_name = getattr(node, 'blueprint_name', '')
            if blueprint_name:
                nested_tree = bpy.data.node_groups.get(blueprint_name)
                if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                    for n in nested_tree.nodes:
                        if n.bl_idname == 'SSMTNode_Result_Output' and n.inputs and n.inputs[0].is_linked:
                            return self._extract_object_from_node(n.inputs[0].links[0].from_node)
        return None

    # ---- 核心功能：增殖 ----

    def get_expanded_objects(self):
        """
        将所有输入物体按形态键增殖后返回
        
        返回格式: [(原始物体, 形态键名或None), ...]
        - 基准变体: 形态键名为None (所有SK值为0)
        - 形态键变体: 对应的形态键名称 (该SK为1，其余为0)
        
        下游节点通过此方法获取增殖后的完整物体列表
        """
        connected = self.get_connected_objects()
        result = []

        for idx, obj in connected:
            if not obj or obj.type != 'MESH' or not obj.data or not obj.data.shape_keys:
                # 无形态键物体直接透传
                result.append((obj, None))
                continue

            shape_keys = [kb for kb in obj.data.shape_keys.key_blocks
                          if kb != obj.data.shape_keys.reference_key]

            # 基准变体（所有形态键归零）
            result.append((obj, None))

            # 每个形态键各一个变体
            for sk in shape_keys:
                result.append((obj, sk.name))

        return result

    def get_expanded_count(self):
        """返回增殖后的总数量（用于UI显示）"""
        return len(self.get_expanded_objects())

    # ---- 形态键操作 ----

    def reset_all(self, context):
        """归零所有连接物体的所有形态键"""
        connected = self.get_connected_objects()
        reseted_names = []
        for idx, obj in connected:
            if obj and obj.type == 'MESH' and obj.data.shape_keys:
                ref = obj.data.shape_keys.reference_key
                for kb in obj.data.shape_keys.key_blocks:
                    if kb != ref:
                        kb.value = 0.0
                obj.data.update_tag()
                reseted_names.append(obj.name)
        return reseted_names

    # ---- UI绘制 ----

    def draw_buttons(self, context, layout):
        # 统计信息
        expanded = self.get_expanded_objects()
        input_count = len(self.get_connected_objects())
        output_count = len(expanded)

        info_row = layout.row(align=True)
        info_row.label(text=f"输入: {input_count} 物体 → 输出: {output_count} 变体", icon='INFO')

        # 归零按钮
        row = layout.row(align=True)
        row.operator("ssmt.shapekey_controller_reset_all", text="归零所有", icon='KEY_DEHLT')
        layout.separator()

        # 形态键查看面板
        connected = self.get_connected_objects()
        selected_obj = None
        for idx, obj in connected:
            if idx == self.selected_obj_index:
                selected_obj = obj
                break

        row = layout.row(align=True)
        if selected_obj:
            row.label(text=f"查看: {selected_obj.name}", icon='OBJECT_DATA')
        else:
            row.label(text="-- 无选择 --", icon='ERROR')
        op = row.operator("ssmt.shapekey_controller_select_object", text="", icon='DOWNARROW_HLT')
        op.node_name = self.name

        box = layout.box()
        if selected_obj and selected_obj.type == 'MESH' and selected_obj.data and selected_obj.data.shape_keys:
            key_blocks = selected_obj.data.shape_keys.key_blocks
            non_ref_keys = [kb for kb in key_blocks if kb != selected_obj.data.shape_keys.reference_key]
            box.label(text=f"形态键: {len(non_ref_keys)} 个", icon='SHAPEKEY_DATA')

            box.template_list(
                "UI_UL_list",
                "shape_key_list",
                selected_obj.data.shape_keys,
                "key_blocks",
                self,
                "selected_key_index",
                rows=3,
            )

            if 0 <= self.selected_key_index < len(key_blocks):
                selected_kb = key_blocks[self.selected_key_index]
                box.prop(selected_kb, "value", text=selected_kb.name, slider=True)
        else:
            if not selected_obj:
                box.label(text="请从上方下拉选择已连接的物体", icon='INFO')
            elif selected_obj.type != 'MESH':
                box.label(text="非网格物体", icon='ERROR')
            else:
                box.label(text="无形态键数据", icon='INFO')


# =============================================================================
# 操作符
# =============================================================================

class SSMT_OT_ShapeKeyControllerResetAll(bpy.types.Operator):
    bl_idname = "ssmt.shapekey_controller_reset_all"
    bl_label = "归零所有形态键"
    bl_description = "将所有连接物体的所有形态键值归零"
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        if space and space.type == 'NODE_EDITOR' and space.edit_tree:
            for node in space.edit_tree.nodes:
                if node.select and node.bl_idname == 'SSMTNode_ShapeKeyController':
                    return True
        return False

    def execute(self, context):
        space = context.space_data
        if space and space.type == 'NODE_EDITOR' and space.edit_tree:
            for node in space.edit_tree.nodes:
                if node.select and node.bl_idname == 'SSMTNode_ShapeKeyController':
                    reseted = node.reset_all(context)
                    if reseted:
                        self.report({'INFO'}, f"归零完成: {', '.join(reseted)}")
                    else:
                        self.report({'INFO'}, "没有有效形态键可归零")
                    return {'FINISHED'}
        self.report({'WARNING'}, "请先选中形态键控制器节点")
        return {'CANCELLED'}


class SSMT_OT_ShapeKeyControllerSelectObject(bpy.types.Operator):
    bl_idname = "ssmt.shapekey_controller_select_object"
    bl_label = "选择物体"
    bl_description = "选择要控制的物体"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        node = self._find_target_node(context)
        if not node:
            return {'CANCELLED'}

        connected = node.get_connected_objects()

        def draw_menu(self, context):
            layout = self.layout
            if connected:
                for idx, obj in connected:
                    sk_info = ""
                    if obj.type == 'MESH' and obj.data and obj.data.shape_keys:
                        sk_count = len([kb for kb in obj.data.shape_keys.key_blocks
                                       if kb != obj.data.shape_keys.reference_key])
                        sk_info = f"  ({sk_count} SKs)"
                    op = layout.operator("ssmt.shapekey_controller_set_object_index",
                                        text=f"{obj.name}{sk_info}")
                    op.index = idx
                    op.node_name = node.name
            else:
                layout.label(text="没有已连接的物体", icon='INFO')

        context.window_manager.popup_menu(draw_menu, title="选择要查看的物体", icon='OBJECT_DATA')
        return {'FINISHED'}

    def _find_target_node(self, context):
        if self.node_name:
            space = context.space_data
            if space and space.type == 'NODE_EDITOR':
                tree = space.edit_tree or space.node_tree
                if tree:
                    node = tree.nodes.get(self.node_name)
                    if node:
                        return node

        if context.active_node and context.active_node.bl_idname == 'SSMTNode_ShapeKeyController':
            return context.active_node

        space = context.space_data
        if space and space.type == 'NODE_EDITOR':
            tree = space.edit_tree or space.node_tree
            if tree:
                for n in tree.nodes:
                    if n.select and n.bl_idname == 'SSMTNode_ShapeKeyController':
                        return n
        return None


class SSMT_OT_ShapeKeyControllerSetObjectIndex(bpy.types.Operator):
    bl_idname = "ssmt.shapekey_controller_set_object_index"
    bl_label = "设置物体索引"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: bpy.props.StringProperty()
    index: bpy.props.IntProperty()

    def execute(self, context):
        node = self._find_target_node(context)
        if node and node.bl_idname == 'SSMTNode_ShapeKeyController':
            node.selected_obj_index = self.index
            return {'FINISHED'}
        return {'CANCELLED'}

    def _find_target_node(self, context):
        if self.node_name:
            space = context.space_data
            if space and space.type == 'NODE_EDITOR':
                tree = space.edit_tree or space.node_tree
                if tree:
                    node = tree.nodes.get(self.node_name)
                    if node:
                        return node
        return context.active_node


# =============================================================================
# 注册
# =============================================================================
classes = (
    SSMTNode_ShapeKeyController,
    SSMT_OT_ShapeKeyControllerResetAll,
    SSMT_OT_ShapeKeyControllerSelectObject,
    SSMT_OT_ShapeKeyControllerSetObjectIndex,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)