import bpy
import re
import os
import glob
from bpy.props import StringProperty, CollectionProperty, IntProperty
from bpy.types import PropertyGroup, Operator

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


# -----------------------------------------------------------------------------
# 辅助函数：从物体名称解析 hash 和 index_count
# -----------------------------------------------------------------------------
def parse_object_name(obj_name: str):
    """
    解析物体名称，返回 (hash, index_count, suffix)
    支持格式：
      - SSMT4: 8位hash-index_count-first_index[.可选后缀]  → hash, index_count
      - SSMT3: 8位hash.index_count[.可选后缀]  → hash, index_count
      - 其他：尝试提取前8位十六进制作为hash，index_count留空
    """
    if not obj_name:
        return "", "", ""

    # 匹配 SSMT4 格式：8位hex - 数字 - 数字
    match_ssmt4 = re.match(r'^([a-f0-9]{8})-([0-9]+)-[0-9]+', obj_name)
    if match_ssmt4:
        hash_val = match_ssmt4.group(1)
        index_count = match_ssmt4.group(2)
        suffix = obj_name.split('.')[-1] if '.' in obj_name else ""
        return hash_val, index_count, suffix

    # 匹配 SSMT3 格式：8位hex.数字
    match_ssmt3 = re.match(r'^([a-f0-9]{8})\.([0-9]+)', obj_name)
    if match_ssmt3:
        hash_val = match_ssmt3.group(1)
        index_count = match_ssmt3.group(2)
        suffix = obj_name.split('.')[-1] if '.' in obj_name else ""
        return hash_val, index_count, suffix

    # 仅提取前8位十六进制作为hash
    match_hash = re.match(r'^([a-f0-9]{8})', obj_name)
    if match_hash:
        hash_val = match_hash.group(1)
        # 尝试从名称中提取数字作为 index_count
        match_idx = re.search(r'[-.](\d+)', obj_name)
        index_count = match_idx.group(1) if match_idx else ""
        suffix = obj_name.split('.')[-1] if '.' in obj_name else ""
        return hash_val, index_count, suffix

    return "", "", ""


# -----------------------------------------------------------------------------
# Property Group for each skip item
# -----------------------------------------------------------------------------
class IBSkipItem(PropertyGroup):
    object_name: StringProperty(
        name="物体",
        description="选择要跳过的物体",
        default="",
        update=lambda self, ctx: self._on_object_name_changed(ctx)
    )
    hash_value: StringProperty(name="Hash", default="", get=lambda self: self._get_hash())
    index_count: StringProperty(name="IndexCount", default="", get=lambda self: self._get_index_count())
    custom_name: StringProperty(
        name="节名",
        description="自定义节名后缀（可选）",
        default=""
    )

    def _get_hash(self):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            hash_val, _, _ = parse_object_name(obj.name)
            return hash_val
        return ""

    def _get_index_count(self):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            _, idx, _ = parse_object_name(obj.name)
            return idx
        return ""

    def _on_object_name_changed(self, context):
        node = context.node if hasattr(context, 'node') else None
        if node and hasattr(node, '_check_and_add_new_item'):
            node._check_and_add_new_item()


# -----------------------------------------------------------------------------
# Operators for list management
# -----------------------------------------------------------------------------
class SSMT_OT_IBSkip_AddItem(Operator):
    bl_idname = "ssmt.ib_skip_add_item"
    bl_label = "添加跳过物体"
    bl_description = "添加一个新的跳过物体条目"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: StringProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and hasattr(node, 'skip_items'):
            new_item = node.skip_items.add()
            new_item.object_name = ""
            new_item.custom_name = ""
            node.active_index = len(node.skip_items) - 1
        return {'FINISHED'}


class SSMT_OT_IBSkip_RemoveItem(Operator):
    bl_idname = "ssmt.ib_skip_remove_item"
    bl_label = "移除跳过物体"
    bl_description = "移除选中的跳过物体条目"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: StringProperty()
    index: IntProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and hasattr(node, 'skip_items') and 0 <= self.index < len(node.skip_items):
            node.skip_items.remove(self.index)
            if node.active_index >= len(node.skip_items) and node.active_index > 0:
                node.active_index -= 1
        return {'FINISHED'}


class SSMT_OT_IBSkip_MoveUp(Operator):
    bl_idname = "ssmt.ib_skip_move_up"
    bl_label = "上移"
    bl_description = "将选中条目向上移动"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: StringProperty()
    index: IntProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and hasattr(node, 'skip_items') and self.index > 0:
            node.skip_items.move(self.index, self.index - 1)
            node.active_index = self.index - 1
        return {'FINISHED'}


class SSMT_OT_IBSkip_MoveDown(Operator):
    bl_idname = "ssmt.ib_skip_move_down"
    bl_label = "下移"
    bl_description = "将选中条目向下移动"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: StringProperty()
    index: IntProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and hasattr(node, 'skip_items') and self.index < len(node.skip_items) - 1:
            node.skip_items.move(self.index, self.index + 1)
            node.active_index = self.index + 1
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# The main node class
# -----------------------------------------------------------------------------
class SSMTNode_PostProcess_IBSkip(SSMTNode_PostProcess_Base):
    '''IB跳过后处理节点：为指定物体生成跳过绘制配置'''
    bl_idname = 'SSMTNode_PostProcess_IBSkip'
    bl_label = 'IB跳过'
    bl_description = '为选定的物体生成 [TextureOverride_...] 块，跳过其绘制'

    global_prefix: StringProperty(
        name="全局前缀",
        description="所有跳过节的统一前缀（留空则自动生成）",
        default="",
        update=lambda self, ctx: self.update_node_width([self.global_prefix])
    )

    skip_items: CollectionProperty(type=IBSkipItem)
    active_index: IntProperty(default=0)

    _adding_new_item: bool = False

    def init(self, context):
        super().init(context)
        if len(self.skip_items) == 0:
            self.skip_items.add()
        self.width = 420   # 更宽，容纳更多内容

    def draw_buttons(self, context, layout):
        # 全局设置
        box = layout.box()
        box.label(text="全局设置", icon='PREFERENCES')
        box.prop(self, "global_prefix", text="")
        box.label(text="提示：条目自定义节名优先级更高", icon='INFO')

        # 跳过物体列表
        box = layout.box()
        box.label(text="跳过物体列表", icon='OBJECT_DATA')

        # 使用 column_flow 实现紧凑网格
        flow = box.column_flow(columns=1, align=True)

        # 表头行
        header = flow.row(align=True)
        header.label(text="物体", icon='OBJECT_DATA')
        header.label(text="Hash")
        header.label(text="IndexCount")
        header.label(text="节名")
        header.label(text="")  # 操作按钮占位

        for i, item in enumerate(self.skip_items):
            row = flow.row(align=True)

            # 物体选择器（限制最大宽度）
            sub_row = row.row(align=True)
            sub_row.prop_search(item, "object_name", bpy.data, "objects", text="")
            # 自动提取的 Hash
            row.label(text=item.hash_value[:8] if item.hash_value else "-")
            # IndexCount
            row.label(text=item.index_count if item.index_count else "-")
            # 自定义节名（较短输入框）
            row.prop(item, "custom_name", text="")
            # 操作按钮组
            op_row = row.row(align=True)
            if i > 0:
                op = op_row.operator("ssmt.ib_skip_move_up", text="", icon='TRIA_UP')
                op.node_name = self.name
                op.index = i
            if i < len(self.skip_items) - 1:
                op = op_row.operator("ssmt.ib_skip_move_down", text="", icon='TRIA_DOWN')
                op.node_name = self.name
                op.index = i
            op = op_row.operator("ssmt.ib_skip_remove_item", text="", icon='X')
            op.node_name = self.name
            op.index = i

        # 添加按钮
        add_row = box.row()
        op = add_row.operator("ssmt.ib_skip_add_item", text="添加物体", icon='ADD')
        op.node_name = self.name

        # 自动添加新行
        self._check_and_add_new_item()

    def _check_and_add_new_item(self):
        if self._adding_new_item:
            return
        if len(self.skip_items) == 0:
            return
        last_item = self.skip_items[-1]
        if last_item.object_name and last_item.object_name.strip():
            if last_item.object_name.strip() != "":
                self._adding_new_item = True
                self.skip_items.add()
                self._adding_new_item = False

    def _generate_section_name(self, item, obj_name):
        if item.custom_name and item.custom_name.strip():
            base = item.custom_name.strip()
        elif self.global_prefix and self.global_prefix.strip():
            base = self.global_prefix.strip()
        else:
            name_clean = obj_name
            name_clean = re.sub(r'^\w{8}(?:-\d+-\d+)?\.?', '', name_clean)
            name_clean = re.sub(r'^\.', '', name_clean)
            if not name_clean:
                name_clean = "Unknown"
            name_clean = re.sub(r'[^\w\-]', '_', name_clean)
            base = f"IB_Skip_{name_clean}"
        return base

    def execute_postprocess(self, mod_export_path):
        print(f"IB跳过后处理节点开始执行，Mod导出路径: {mod_export_path}")

        valid_items = []
        for item in self.skip_items:
            obj = bpy.data.objects.get(item.object_name)
            if not obj:
                print(f"  跳过无效物体: {item.object_name}")
                continue
            hash_val, idx_count, _ = parse_object_name(obj.name)
            if not hash_val:
                print(f"  无法从物体 '{obj.name}' 提取 hash，跳过")
                continue
            if not idx_count:
                print(f"  无法从物体 '{obj.name}' 提取 IndexCount，跳过")
                continue
            valid_items.append((item, obj.name, hash_val, idx_count))

        if not valid_items:
            print("没有有效的跳过物体，操作终止")
            return

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("未找到任何 .ini 文件，操作终止")
            return
        target_ini = ini_files[0]

        self._create_cumulative_backup(target_ini, mod_export_path)

        with open(target_ini, 'r', encoding='utf-8') as f:
            content = f.read()
        marker = "; --- AUTO-APPENDED IB SKIP BLOCK ---"
        if marker in content:
            print("IB跳过配置已存在于文件中。请手动删除旧块后再生成。")
            return

        new_lines = []
        new_lines.append("\n\n; ==============================================================================")
        new_lines.append("; --- AUTO-APPENDED IB SKIP BLOCK ---")
        new_lines.append("; ==============================================================================\n")

        for item, obj_name, hash_val, idx_count in valid_items:
            section_name = self._generate_section_name(item, obj_name)
            new_lines.append(f"[TextureOverride_{section_name}]")
            new_lines.append(f"hash = {hash_val}")
            new_lines.append(f"match_index_count = {idx_count}")
            new_lines.append("handling = skip")
            new_lines.append("")

        with open(target_ini, 'a', encoding='utf-8') as f:
            f.write("\n".join(new_lines))

        print(f"已为 {len(valid_items)} 个物体生成 IB 跳过配置，追加到 {os.path.basename(target_ini)}")


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------
classes = (
    IBSkipItem,
    SSMT_OT_IBSkip_AddItem,
    SSMT_OT_IBSkip_RemoveItem,
    SSMT_OT_IBSkip_MoveUp,
    SSMT_OT_IBSkip_MoveDown,
    SSMTNode_PostProcess_IBSkip,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)