import bpy
import os
import shutil
from bpy.types import Node, PropertyGroup
from bpy.props import StringProperty, CollectionProperty, BoolProperty

from .blueprint_node_base import SSMTNodeBase, SSMTSocketObject
from ..config.main_config import GlobalConfig


class CrossIBItem(PropertyGroup):
    source_ib: StringProperty(
        name="源IB",
        description="源IB前缀，例如: 9f387166",
        default=""
    )
    target_ib: StringProperty(
        name="目标IB",
        description="目标IB前缀，例如: a55afe59",
        default=""
    )


class SSMT_OT_CrossIB_AddItem(bpy.types.Operator):
    bl_idname = "ssmt.cross_ib_add_item"
    bl_label = "添加跨IB映射"
    bl_description = "添加一个新的跨IB映射项"

    node_name: StringProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            new_item = node.cross_ib_list.add()
            new_item.source_ib = ""
            new_item.target_ib = ""
        
        return {'FINISHED'}


class SSMT_OT_CrossIB_RemoveItem(bpy.types.Operator):
    bl_idname = "ssmt.cross_ib_remove_item"
    bl_label = "删除跨IB映射"
    bl_description = "删除选中的跨IB映射项"

    node_name: StringProperty()
    item_index: bpy.props.IntProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node and self.item_index >= 0 and self.item_index < len(node.cross_ib_list):
            node.cross_ib_list.remove(self.item_index)
        
        return {'FINISHED'}


class SSMTNode_CrossIB(SSMTNodeBase):
    bl_idname = 'SSMTNode_CrossIB'
    bl_label = 'Cross IB (终末地专用)'
    bl_icon = 'ARROW_LEFTRIGHT'
    bl_width_min = 350

    cross_ib_list: CollectionProperty(type=CrossIBItem)

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 350
        self.use_custom_color = True
        self.color = (0.6, 0.3, 0.6)

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="跨IB映射列表 (源IB >> 目标IB)", icon='ARROW_LEFTRIGHT')
        
        for i, item in enumerate(self.cross_ib_list):
            row = box.row(align=True)
            row.prop(item, "source_ib", text="源")
            row.label(text=">>")
            row.prop(item, "target_ib", text="目标")
            op = row.operator("ssmt.cross_ib_remove_item", text="", icon='X')
            op.node_name = self.name
            op.item_index = i
        
        row = layout.row()
        op = row.operator("ssmt.cross_ib_add_item", text="添加映射", icon='ADD')
        op.node_name = self.name

    def update(self):
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
            self.inputs.remove(self.inputs[-1])

    def get_cross_ib_mappings(self):
        mappings = []
        for item in self.cross_ib_list:
            if item.source_ib and item.target_ib:
                mappings.append({
                    'source_ib': item.source_ib,
                    'target_ib': item.target_ib
                })
        return mappings

    def get_source_ib_list(self):
        source_list = []
        for item in self.cross_ib_list:
            if item.source_ib:
                source_list.append(item.source_ib)
        return list(set(source_list))

    def get_target_ib_list(self):
        target_list = []
        for item in self.cross_ib_list:
            if item.target_ib:
                target_list.append(item.target_ib)
        return list(set(target_list))

    def get_ib_mapping_dict(self):
        ib_mapping = {}
        for item in self.cross_ib_list:
            if item.source_ib and item.target_ib:
                if item.source_ib not in ib_mapping:
                    ib_mapping[item.source_ib] = []
                if item.target_ib not in ib_mapping[item.source_ib]:
                    ib_mapping[item.source_ib].append(item.target_ib)
        return ib_mapping


class SSMTNode_PostProcess_CrossIB(SSMTNodeBase):
    bl_idname = 'SSMTNode_PostProcess_CrossIB'
    bl_label = 'Cross IB PostProcess'
    bl_icon = 'FILE_REFRESH'
    bl_width_min = 300

    def init(self, context):
        self.inputs.new('SSMTSocketPostProcess', "Input")
        self.outputs.new('SSMTSocketPostProcess', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        layout.label(text="跨IB后处理节点", icon='FILE_REFRESH')
        layout.label(text="自动复制HLSL文件到res目录")

    def execute_postprocess(self, mod_export_path):
        self._copy_hlsl_files(mod_export_path)

    def _copy_hlsl_files(self, mod_export_path):
        addon_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        source_dir = os.path.join(addon_dir, "超级工具集")
        
        if not os.path.exists(source_dir):
            print(f"[CrossIB] 警告: 超级工具集目录不存在: {source_dir}")
            return
        
        hlsl_files = [
            'extract_cb1_ps.hlsl',
            'extract_cb1_vs.hlsl',
            'record_bones_cs.hlsl',
            'redirect_cb1_cs.hlsl'
        ]
        
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


classes = (
    CrossIBItem,
    SSMT_OT_CrossIB_AddItem,
    SSMT_OT_CrossIB_RemoveItem,
    SSMTNode_CrossIB,
    SSMTNode_PostProcess_CrossIB,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
