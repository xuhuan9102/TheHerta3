# blueprint_node_postprocess_vertex_attrs.py
import bpy
from bpy.types import PropertyGroup

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base
from ..blueprint.blueprint_export_helper import BlueprintExportHelper   # 用于获取上游物体


class VertexAttributeItem(bpy.types.PropertyGroup):
    attr_type: bpy.props.EnumProperty(
        name="数据类型",
        description="顶点属性的数据类型",
        items=[
            ('float', 'float', '单精度浮点数 (4字节)'),
            ('float2', 'float2', '2个浮点数 (8字节)'),
            ('float3', 'float3', '3个浮点数 (12字节)'),
            ('float4', 'float4', '4个浮点数 (16字节)'),
            ('int', 'int', '整数 (4字节)'),
            ('int2', 'int2', '2个整数 (8字节)'),
            ('int3', 'int3', '3个整数 (12字节)'),
            ('int4', 'int4', '4个整数 (16字节)'),
            ('uint', 'uint', '无符号整数 (4字节)'),
            ('uint2', 'uint2', '2个无符号整数 (8字节)'),
            ('uint3', 'uint3', '3个无符号整数 (12字节)'),
            ('uint4', 'uint4', '4个无符号整数 (16字节)'),
            ('half', 'half', '半精度浮点数 (2字节)'),
            ('half2', 'half2', '2个半精度浮点数 (4字节)'),
            ('half3', 'half3', '3个半精度浮点数 (6字节)'),
            ('half4', 'half4', '4个半精度浮点数 (8字节)'),
            ('double', 'double', '双精度浮点数 (8字节)'),
            ('double2', 'double2', '2个双精度浮点数 (16字节)'),
            ('double3', 'double3', '3个双精度浮点数 (24字节)'),
            ('double4', 'double4', '4个双精度浮点数 (32字节)'),
        ],
        default='float3'
    )
    attr_name: bpy.props.StringProperty(name="属性名称", description="顶点属性的名称", default="position", maxlen=256)


class ObjectVertexConfig(bpy.types.PropertyGroup):
    """单个物体的顶点属性配置"""
    object_name: bpy.props.StringProperty(
        name="物体名称",
        description="关联的物体名称",
        default=""
    )
    vertex_attributes: bpy.props.CollectionProperty(
        type=VertexAttributeItem,
        description="该物体的顶点属性列表"
    )
    active_vertex_attribute: bpy.props.IntProperty(
        name="活动属性索引",
        default=0
    )


class SSMTNode_PostProcess_VertexAttrs(SSMTNode_PostProcess_Base):
    '''顶点属性定义节点：为形态键配置和多文件配置提供顶点属性定义'''
    bl_idname = 'SSMTNode_PostProcess_VertexAttrs'
    bl_label = '顶点属性定义'
    bl_description = '为形态键配置和多文件配置提供顶点属性定义'
    bl_width_min = 550 

    # 原有的全局属性列表（向后兼容）
    vertex_attributes: bpy.props.CollectionProperty(type=VertexAttributeItem)
    active_vertex_attribute: bpy.props.IntProperty(default=0)

    # 新增：每个物体的独立配置列表
    objects_config: bpy.props.CollectionProperty(type=ObjectVertexConfig)
    active_object_index: bpy.props.IntProperty(
        name="活动物体索引",
        description="当前选中的物体在列表中的索引",
        default=-1
    )

    # 控制对照表折叠的UI状态
    show_mapping_table: bpy.props.BoolProperty(
        name="显示对照表",
        description="显示后缀与顶点属性的对照表",
        default=False
    )

    global_collapsed: bpy.props.BoolProperty(
        name="全局属性折叠",
        description="折叠/展开全局属性定义区域",
        default=True
    )

    # 后缀到 (类型, 名称) 的映射表（与UI中显示的一致）
    SUFFIX_MAPPING = {
        "P12": ("float3", "position"),
        "N12": ("float3", "normal"),
        "N4": ("uint", "normal"),
        "TA16": ("float4", "tangent"),
        "T4": ("half2", "texcoord"),
        "T8": ("float2", "texcoord"),
        "T1-4": ("half2", "texcoord1"),
        "T1-8": ("float2", "texcoord1"),
        "T2-4": ("half2", "texcoord2"),
        "T2-8": ("float2", "texcoord2"),
        "T3-4": ("half2", "texcoord3"),
        "T3-8": ("float2", "texcoord3"),
        "T4-4": ("half2", "texcoord4"),
        "T4-8": ("float2", "texcoord4"),
        "T5-4": ("half2", "texcoord5"),
        "T5-8": ("float2", "texcoord5"),
        "T6-4": ("half2", "texcoord6"),
        "T6-8": ("float2", "texcoord6"),
        "T7-4": ("half2", "texcoord7"),
        "T7-8": ("float2", "texcoord7"),
        "T8-4": ("half2", "texcoord8"),
        "T8-8": ("float2", "texcoord8"),
        "C4": ("uint", "color"),
        "BW16": ("float4", "blendweights"),
        "BW8": ("half4", "blendweights"),
        "BI16": ("uint4", "blendindices"),
        "BI4": ("uint4", "blendindices"),
    }

    def draw_buttons(self, context, layout):
        # ========== 多物体独立配置区域（上下布局） ==========
        box = layout.box()
        box.label(text="多物体独立配置", icon='OBJECT_DATA')
        
        # 第一行：物体列表（左侧）和操作按钮（右侧）
        row = box.row()
        # 物体列表占更多空间
        row.template_list(
            "SSMT_UL_OBJECT_CONFIGS", "",
            self, "objects_config",
            self, "active_object_index",
            rows=3, maxrows=5
        )
        # 操作按钮列（垂直排列）
        col_ops = row.column(align=True)
        col_ops.operator("ssmt.vertex_attrs_refresh_objects", text="", icon='FILE_REFRESH')
        col_ops.separator()
        col_ops.operator("ssmt.vertex_attrs_add_object", text="", icon='ADD')
        col_ops.operator("ssmt.vertex_attrs_remove_object", text="", icon='REMOVE')
        col_ops.separator()
        col_ops.operator("ssmt.vertex_attrs_auto_config_selected", text="", icon='FILE_TICK')
        
        # 第二行：当前选中物体的属性编辑区
        current_config = None
        if self.active_object_index >= 0 and self.active_object_index < len(self.objects_config):
            current_config = self.objects_config[self.active_object_index]
        
        if current_config:
            sub_box = box.box()
            sub_box.label(text=f"物体: {current_config.object_name}", icon='OBJECT_DATA')
            sub_box.template_list(
                "SSMT_UL_VERTEX_ATTRIBUTES", "",
                current_config, "vertex_attributes",
                current_config, "active_vertex_attribute",
                rows=3
            )
            row2 = sub_box.row()
            row2.operator("ssmt_postprocess.add_vertex_attribute", text="添加", icon='ADD').for_object = True
            row2.operator("ssmt_postprocess.remove_vertex_attribute", text="删除", icon='REMOVE').for_object = True
            if current_config.vertex_attributes and current_config.active_vertex_attribute >= 0:
                item = current_config.vertex_attributes[current_config.active_vertex_attribute]
                sub_box.prop(item, "attr_type")
                sub_box.prop(item, "attr_name")
        else:
            box.label(text="未选中物体或物体列表为空", icon='INFO')

        # ========== 全局属性定义（可折叠，默认折叠） ==========
        box = layout.box()
        row = box.row()
        if not hasattr(self, 'global_collapsed'):
            self.global_collapsed = True
        icon = 'TRIA_DOWN' if not self.global_collapsed else 'TRIA_RIGHT'
        row.prop(self, "global_collapsed", text="", icon=icon, emboss=False)
        row.label(text="全局属性定义（未指定物体时使用）", icon='PROPERTIES')
        if not self.global_collapsed:
            sub_box = box.box()
            sub_box.template_list("SSMT_UL_VERTEX_ATTRIBUTES", "", self, "vertex_attributes", self, "active_vertex_attribute", rows=2)
            row2 = sub_box.row()
            row2.operator("ssmt_postprocess.add_vertex_attribute", text="", icon='ADD').for_object = False
            row2.operator("ssmt_postprocess.remove_vertex_attribute", text="", icon='REMOVE').for_object = False
            if self.vertex_attributes and self.active_vertex_attribute >= 0:
                item = self.vertex_attributes[self.active_vertex_attribute]
                sub_box.prop(item, "attr_type")
                sub_box.prop(item, "attr_name")
            # 添加自动配置按钮到折叠框内
            sub_box.separator()
            auto_row = sub_box.row(align=True)
            auto_row.operator("ssmt.vertex_attrs_auto_config", text="从选中物体自动配置全局", icon='FILE_REFRESH')
            auto_row.label(text="根据物体的 GameTypeName 添加全局属性", icon='INFO')

        # ========== 可折叠的对照表 ==========
        box = layout.box()
        row = box.row()
        row.prop(self, "show_mapping_table", icon='TRIA_DOWN' if self.show_mapping_table else 'TRIA_RIGHT',
                 emboss=False, icon_only=False)
        row.label(text="后缀与顶点属性对照表")
        if self.show_mapping_table:
            grid = box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
            for suffix, (dtype, name) in self.SUFFIX_MAPPING.items():
                row = grid.row(align=True)
                row.label(text=f"{suffix} →", icon='RIGHTARROW')
                row.label(text=f"{dtype}  ({name})")
            box.label(text="注意：请按模型文件夹名称中的后缀顺序依次添加属性，不要遗漏或错位。", icon='ERROR')

    # ------------------ 辅助方法 ------------------
    def _get_upstream_objects(self):
        """从当前蓝图的上游收集所有连接到最终输出节点的物体名称（去重）
           优先使用节点自身所在的蓝图树（self.id_data）
        """
        # 方法1：优先使用节点自身的蓝图树
        tree = self.id_data
        if not tree or tree.bl_idname != 'SSMTBlueprintTreeType':
            # 回退到原来的静态方法
            tree = BlueprintExportHelper.get_current_blueprint_tree()
            if not tree:
                print("[VertexAttrs] 警告: 无法获取当前蓝图树")
                return []
        
        objects = set()
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        if not output_nodes:
            print("[VertexAttrs] 当前蓝图树中没有找到输出节点 (Result_Output)")
            return []

        def collect_from_node(node):
            if node.mute:
                return
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    objects.add(obj_name)
            elif node.bl_idname == 'SSMTNode_MultiFile_Export':
                for item in node.object_list:
                    obj_name = getattr(item, 'object_name', '')
                    if obj_name:
                        objects.add(obj_name)
            elif node.bl_idname == 'SSMTNode_ShapeKeyController':
                expanded = node.get_expanded_objects()
                for obj, _ in expanded:
                    if obj:
                        objects.add(obj.name)
            elif hasattr(node, 'inputs'):
                for inp in node.inputs:
                    if inp.is_linked:
                        for link in inp.links:
                            collect_from_node(link.from_node)

        for output in output_nodes:
            collect_from_node(output)
        
        sorted_objects = sorted(objects)
        print(f"[VertexAttrs] 从上游收集到 {len(sorted_objects)} 个物体: {sorted_objects}")
        return sorted_objects

    def _sync_objects_config(self):
        """同步物体配置列表：添加新物体，但保留用户手动添加的物体（即使不在上游）"""
        upstream_objects = self._get_upstream_objects()
        current_names = {cfg.object_name for cfg in self.objects_config}
        
        # 添加上游的新物体
        for obj_name in upstream_objects:
            if obj_name not in current_names:
                new_cfg = self.objects_config.add()
                new_cfg.object_name = obj_name
                print(f"[VertexAttrs] 自动添加物体: {obj_name}")
        
        # 注意：不再自动移除不存在的物体，以免误删用户手动添加的配置
        # 如果确实需要清理，可以让用户手动点击“删除”按钮
        
        # 若当前活动索引无效，重置
        if self.active_object_index >= len(self.objects_config):
            self.active_object_index = len(self.objects_config) - 1
        
        print(f"[VertexAttrs] 同步完成，当前配置物体: {[cfg.object_name for cfg in self.objects_config]}")

    def _sync_objects_config(self):
        """同步物体配置列表：添加新物体，移除已不存在的物体"""
        upstream_objects = self._get_upstream_objects()
        current_names = {cfg.object_name for cfg in self.objects_config}
        # 添加新物体
        for obj_name in upstream_objects:
            if obj_name not in current_names:
                new_cfg = self.objects_config.add()
                new_cfg.object_name = obj_name
        # 移除已不存在的物体
        to_remove = []
        for i, cfg in enumerate(self.objects_config):
            if cfg.object_name not in upstream_objects:
                to_remove.append(i)
        for i in reversed(to_remove):
            self.objects_config.remove(i)
        # 若当前活动索引无效，重置
        if self.active_object_index >= len(self.objects_config):
            self.active_object_index = len(self.objects_config) - 1

    def _get_or_create_object_config(self, obj_name):
        """获取指定物体的配置，若不存在则创建（但不自动添加到列表，需调用_sync）"""
        for cfg in self.objects_config:
            if cfg.object_name == obj_name:
                return cfg
        # 创建新配置
        new_cfg = self.objects_config.add()
        new_cfg.object_name = obj_name
        return new_cfg

    # ------------------ 原有方法 ------------------
    def get_vertex_struct_definition(self):
        """获取顶点属性结构体定义字符串（全局版本，向后兼容）"""
        if not self.vertex_attributes or len(self.vertex_attributes) == 0:
            return "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"
        
        struct_lines = ["struct VertexAttributes {"]
        for item in self.vertex_attributes:
            if item.attr_type and item.attr_name:
                struct_lines.append(f"    {item.attr_type} {item.attr_name};")
        struct_lines.append("};")
        
        return "\n".join(struct_lines)

    def parse_vertex_struct(self):
        """解析顶点属性结构体定义，计算总字节数和float数量（全局）"""
        struct_definition = self.get_vertex_struct_definition()
        
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
        
        if total_bytes == 0:
            return None
        
        return (total_bytes, total_floats, attributes)

    def execute_postprocess(self, mod_export_path):
        """顶点属性定义节点不执行任何操作，只是提供配置信息"""
        print(f"顶点属性定义节点已配置，Mod导出路径: {mod_export_path}")

    def auto_configure_from_object(self, obj, target_config=None):
        """从网格物体自动配置顶点属性列表
        :param target_config: 若指定，则配置该物体的独立属性；否则配置全局属性
        """
        if not obj or obj.type != 'MESH':
            return False, "请选择一个网格物体"

        # 读取物体上存储的 GameTypeName (由导入时设置)
        game_type_name = obj.get("3DMigoto:GameTypeName", "")
        if not game_type_name:
            return False, "物体缺少 3DMigoto:GameTypeName 属性，请使用 SSMT 导入模型"

        print(f"[VertexAttrs] 从物体 {obj.name} 读取到 GameTypeName: {game_type_name}")

        # 解析后缀：格式如 "CPU_P12_N12_TA16_T8_" 或 "GPU_P12_N12_TA16_T8_"
        # 去掉前缀 CPU_ 或 GPU_
        if game_type_name.startswith("CPU_") or game_type_name.startswith("GPU_"):
            suffix_part = game_type_name[4:]  # 去掉 "CPU_" 或 "GPU_"
        else:
            suffix_part = game_type_name

        # 按 "_" 分割，得到后缀列表，例如 ["P12", "N12", "TA16", "T8"]
        suffixes = [s for s in suffix_part.split("_") if s]
        if not suffixes:
            return False, f"无法解析 GameTypeName: {game_type_name}"

        print(f"[VertexAttrs] 解析出的后缀列表: {suffixes}")

        # 清空目标属性列表
        if target_config is None:
            target_attrs = self.vertex_attributes
        else:
            target_attrs = target_config.vertex_attributes
        target_attrs.clear()

        added_count = 0
        for suffix in suffixes:
            if suffix in self.SUFFIX_MAPPING:
                dtype, name = self.SUFFIX_MAPPING[suffix]
                new_item = target_attrs.add()
                new_item.attr_type = dtype
                new_item.attr_name = name
                added_count += 1
                print(f"[VertexAttrs] 添加属性: {dtype} {name} (后缀: {suffix})")
            else:
                print(f"[VertexAttrs] 警告: 未知后缀 '{suffix}'，已跳过")

        if added_count == 0:
            return False, f"未能从 GameTypeName 解析出任何已知后缀"

        # 如果解析出的属性少于3个，给出提示但不报错
        if added_count < 3:
            print(f"[VertexAttrs] 提示: 只解析出 {added_count} 个属性，可能缺少 position/normal/tangent")
            return True, f"已添加 {added_count} 个属性（少于预期）"
        else:
            return True, f"已添加前 {added_count} 个顶点属性"


# ===================== UIList 类 =====================
class SSMT_UL_VERTEX_ATTRIBUTES(bpy.types.UIList):
    bl_idname = 'SSMT_UL_VERTEX_ATTRIBUTES'
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=f"{item.attr_type} {item.attr_name}")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=f"{item.attr_type} {item.attr_name}")


class SSMT_UL_OBJECT_CONFIGS(bpy.types.UIList):
    bl_idname = 'SSMT_UL_OBJECT_CONFIGS'

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.object_name, icon='OBJECT_DATA')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.object_name)


# ===================== 操作符 =====================

class SSMT_OT_PostProcess_AddVertexAttribute(bpy.types.Operator):
    bl_idname = "ssmt_postprocess.add_vertex_attribute"
    bl_label = "添加顶点属性"
    bl_description = "添加新的顶点属性项"
    bl_options = {'REGISTER', 'UNDO'}
    
    for_object: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}

        if self.for_object:
            if node.active_object_index < 0 or node.active_object_index >= len(node.objects_config):
                self.report({'WARNING'}, "请先在左侧选择物体")
                return {'CANCELLED'}
            config = node.objects_config[node.active_object_index]
            attrs = config.vertex_attributes
            active_prop = "active_vertex_attribute"
        else:
            config = node
            attrs = node.vertex_attributes
            active_prop = "active_vertex_attribute"

        new_item = attrs.add()
        if len(attrs) == 1:
            new_item.attr_name = "position"
        elif len(attrs) == 2:
            new_item.attr_name = "normal"
        elif len(attrs) == 3:
            new_item.attr_name = "tangent"
        else:
            new_item.attr_name = f"attr{len(attrs)}"
        
        setattr(config, active_prop, len(attrs) - 1)
        return {'FINISHED'}


class SSMT_OT_PostProcess_RemoveVertexAttribute(bpy.types.Operator):
    bl_idname = "ssmt_postprocess.remove_vertex_attribute"
    bl_label = "删除顶点属性"
    bl_description = "删除选中的顶点属性项"
    bl_options = {'REGISTER', 'UNDO'}
    
    for_object: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}

        if self.for_object:
            if node.active_object_index < 0 or node.active_object_index >= len(node.objects_config):
                self.report({'WARNING'}, "请先在左侧选择物体")
                return {'CANCELLED'}
            config = node.objects_config[node.active_object_index]
            attrs = config.vertex_attributes
            active_prop = "active_vertex_attribute"
        else:
            config = node
            attrs = node.vertex_attributes
            active_prop = "active_vertex_attribute"

        active = getattr(config, active_prop)
        if active >= 0 and active < len(attrs):
            attrs.remove(active)
            if active >= len(attrs) and active > 0:
                setattr(config, active_prop, active - 1)
        return {'FINISHED'}


class SSMT_OT_VertexAttrsAutoConfig(bpy.types.Operator):
    """从选中的网格物体自动配置全局顶点属性定义"""
    bl_idname = "ssmt.vertex_attrs_auto_config"
    bl_label = "自动配置全局属性"
    bl_description = "根据当前选中物体的 GameTypeName 自动添加全局顶点属性"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}

        # 获取当前选中的网格物体
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            # 如果没有活动物体，尝试从选中物体中找第一个网格
            for o in context.selected_objects:
                if o.type == 'MESH':
                    obj = o
                    break
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "请先选中一个网格物体（该物体需由 SSMT 导入）")
            return {'CANCELLED'}

        success, message = node.auto_configure_from_object(obj, target_config=None)
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        return {'FINISHED'}


class SSMT_OT_VertexAttrsRefreshObjects(bpy.types.Operator):
    """刷新上游物体列表，同步配置"""
    bl_idname = "ssmt.vertex_attrs_refresh_objects"
    bl_label = "刷新物体列表"
    bl_description = "从上游重新扫描所有物体，并同步配置"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}
        node._sync_objects_config()
        self.report({'INFO'}, "已同步物体列表")
        return {'FINISHED'}


class SSMT_OT_VertexAttrsAddObject(bpy.types.Operator):
    """手动添加一个物体（输入名称）"""
    bl_idname = "ssmt.vertex_attrs_add_object"
    bl_label = "添加物体"
    bl_description = "手动输入物体名称添加到配置列表"
    bl_options = {'REGISTER', 'INTERNAL'}

    object_name: bpy.props.StringProperty(name="物体名称")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}
        if not self.object_name:
            self.report({'WARNING'}, "请输入物体名称")
            return {'CANCELLED'}
        # 检查是否已存在
        for cfg in node.objects_config:
            if cfg.object_name == self.object_name:
                self.report({'WARNING'}, f"物体 '{self.object_name}' 已存在")
                return {'CANCELLED'}
        new_cfg = node.objects_config.add()
        new_cfg.object_name = self.object_name
        node.active_object_index = len(node.objects_config) - 1
        self.report({'INFO'}, f"已添加物体 '{self.object_name}'")
        return {'FINISHED'}


class SSMT_OT_VertexAttrsRemoveObject(bpy.types.Operator):
    """删除选中的物体配置"""
    bl_idname = "ssmt.vertex_attrs_remove_object"
    bl_label = "删除物体配置"
    bl_description = "删除当前选中的物体配置（仅删除配置，不删除物体本身）"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}
        if node.active_object_index >= 0 and node.active_object_index < len(node.objects_config):
            node.objects_config.remove(node.active_object_index)
            if node.active_object_index >= len(node.objects_config) and node.active_object_index > 0:
                node.active_object_index -= 1
            self.report({'INFO'}, "已删除物体配置")
        else:
            self.report({'WARNING'}, "没有选中的物体")
        return {'FINISHED'}


class SSMT_OT_VertexAttrsAutoConfigSelected(bpy.types.Operator):
    """为当前选中的物体自动配置顶点属性"""
    bl_idname = "ssmt.vertex_attrs_auto_config_selected"
    bl_label = "自动配置当前物体"
    bl_description = "根据当前选中的物体的 GameTypeName 自动填充该物体的顶点属性"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}

        if node.active_object_index < 0 or node.active_object_index >= len(node.objects_config):
            self.report({'WARNING'}, "请先在左侧列表中选择一个物体")
            return {'CANCELLED'}

        config = node.objects_config[node.active_object_index]
        obj_name = config.object_name
        obj = bpy.data.objects.get(obj_name)
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, f"物体 '{obj_name}' 无效或不是网格")
            return {'CANCELLED'}

        success, message = node.auto_configure_from_object(obj, target_config=config)
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        return {'FINISHED'}


# ===================== 注册列表 =====================
classes = (
    VertexAttributeItem,
    ObjectVertexConfig,
    SSMTNode_PostProcess_VertexAttrs,
    SSMT_UL_VERTEX_ATTRIBUTES,
    SSMT_UL_OBJECT_CONFIGS,
    SSMT_OT_PostProcess_AddVertexAttribute,
    SSMT_OT_PostProcess_RemoveVertexAttribute,
    SSMT_OT_VertexAttrsAutoConfig,
    SSMT_OT_VertexAttrsRefreshObjects,
    SSMT_OT_VertexAttrsAddObject,
    SSMT_OT_VertexAttrsRemoveObject,
    SSMT_OT_VertexAttrsAutoConfigSelected,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)