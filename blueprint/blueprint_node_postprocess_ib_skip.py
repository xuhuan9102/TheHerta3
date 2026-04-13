import bpy
import re
import os
import glob
from bpy.props import StringProperty, CollectionProperty, IntProperty, EnumProperty
from bpy.types import PropertyGroup, Operator

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base
from ..config.main_config import LogicName


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
    manual_hash: StringProperty(
        name="Hash",
        description="手动指定Hash值，优先于从物体名称解析",
        default=""
    )
    manual_index_count: StringProperty(
        name="IndexCount",
        description="手动指定 IndexCount，优先于从物体名称解析",
        default=""
    )
    custom_name: StringProperty(
        name="节名",
        description="自定义节名后缀（可选）",
        default=""
    )

    def get_hash(self):
        manual = self.manual_hash.strip()
        if manual:
            return manual
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            hash_val, _, _ = parse_object_name(obj.name)
            return hash_val
        return ""

    def get_index_count(self):
        manual = self.manual_index_count.strip()
        if manual:
            return manual
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            _, idx, _ = parse_object_name(obj.name)
            return idx
        return ""

    def _on_object_name_changed(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            hash_val, idx, _ = parse_object_name(obj.name)
            self.manual_hash = hash_val
            self.manual_index_count = idx
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
        # 禁止删除第一个固定条目
        if self.index == 0:
            self.report({'WARNING'}, "不能删除固定的内部虚拟物体条目")
            return {'CANCELLED'}

        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and hasattr(node, 'skip_items') and 0 <= self.index < len(node.skip_items):
            node.skip_items.remove(self.index)
            if node.active_index >= len(node.skip_items) and node.active_index > 0:
                node.active_index -= 1
        return {'FINISHED'}


class SSMT_UL_IBSkipList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            if index == 0:
                row.enabled = False
            row.prop_search(item, "object_name", bpy.data, "objects", text="")
            row.prop(item, "manual_hash", text="")
            row.prop(item, "manual_index_count", text="")
            row.prop(item, "custom_name", text="")
            op = row.operator("ssmt.ib_skip_remove_item", text="", icon='BLANK1' if index == 0 else 'X')
            op.node_name = data.name if hasattr(data, 'name') else ""
            op.index = index
        elif self.layout_type == 'GRID':
            layout.prop_search(item, "object_name", bpy.data, "objects", text="")


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

    mode: EnumProperty(
        name="模式",
        description="选择生成模式：EFMI（支持 match_index_count）或 ZZMI（不使用 match_index_count）",
        items=[
            ('EFMI', 'EFMI', '终末地模式 - 支持 match_index_count 参数'),
            ('ZZMI', 'ZZMI', '绝区零模式 - 不使用 match_index_count 参数'),
        ],
        default='EFMI',
        # update=lambda self, ctx: self.update_node_width([self.mode])
    )

    skip_items: CollectionProperty(type=IBSkipItem)
    active_index: IntProperty(default=0)

    _adding_new_item: bool = False

    def init(self, context):
        super().init(context)
        # 确保至少有一个条目，且第一条为内部虚拟物体
        if len(self.skip_items) == 0:
            self.skip_items.add()
        # 设置第一个条目为固定虚拟物体（仅当该条目为空或未配置时）
        first_item = self.skip_items[0]
        if not first_item.object_name and not first_item.manual_hash and not first_item.custom_name:
            first_item.object_name = "物体"
            first_item.manual_hash = "哈希值"
            first_item.manual_index_count = "index_count"
            first_item.custom_name = "备注"
        self.width = 420

    def draw_buttons(self, context, layout):
        # 全局设置
        box = layout.box()
        box.label(text="全局设置", icon='PREFERENCES')
        box.prop(self, "mode", text="模式")
        box.prop(self, "global_prefix", text="前缀")
        box.label(text="提示：条目自定义节名优先级更高", icon='INFO')
        box.label(text="第一条为固定虚拟物体示例，不可删除", icon='INFO')

        # 跳过物体列表
        box = layout.box()
        box.label(text="跳过物体列表", icon='OBJECT_DATA')

        box.template_list(
            "SSMT_UL_IBSkipList",
            "",
            self,
            "skip_items",
            self,
            "active_index",
            rows=6,
            type='DEFAULT'
        )

        add_row = box.row()
        op = add_row.operator("ssmt.ib_skip_add_item", text="添加物体", icon='ADD')
        op.node_name = self.name

        # 自动添加新行（当最后一个条目有内容时）
        self._check_and_add_new_item()

    def _check_and_add_new_item(self):
        if self._adding_new_item:
            return
        # 列表为空时添加一个空条目（理论上不会发生，因第一条固定）
        if len(self.skip_items) == 0:
            self._adding_new_item = True
            self.skip_items.add()
            self._adding_new_item = False
            return
        # 检查最后一个条目是否有内容（跳过第一个固定条目，从索引1开始检查自动添加）
        last_item = self.skip_items[-1]
        # 如果最后一个条目不是第一个（即列表长度>1）且最后一个条目非空，则添加新行
        if len(self.skip_items) > 1 and (
            (last_item.object_name and last_item.object_name.strip()) or
            (last_item.manual_hash and last_item.manual_hash.strip()) or
            (last_item.manual_index_count and last_item.manual_index_count.strip()) or
            (last_item.custom_name and last_item.custom_name.strip())
        ):
            self._adding_new_item = True
            self.skip_items.add()
            self._adding_new_item = False
        # 如果列表只有第一个固定条目，且该条目的内容被用户清空，不自动添加（避免无限添加）
        # 用户可手动点击“添加物体”来新增条目

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
        # 从第二条开始处理（跳过第一个固定条目）
        for item in self.skip_items[1:]:
            manual_hash = item.manual_hash.strip() if item.manual_hash else ""
            manual_index = item.manual_index_count.strip() if item.manual_index_count else ""
            obj = bpy.data.objects.get(item.object_name) if item.object_name else None
            obj_name = obj.name if obj else item.object_name

            hash_val = manual_hash
            index_count = manual_index
            if obj and (not hash_val or not index_count):
                parsed_hash, parsed_index, _ = parse_object_name(obj.name)
                if not hash_val:
                    hash_val = parsed_hash
                if not index_count:
                    index_count = parsed_index

            if not hash_val:
                print(f"  跳过条目缺少Hash，物体/手动值: '{item.object_name or '—'}'，请填写Hash或选择有效物体")
                continue

            valid_items.append((item, obj_name or "", hash_val, index_count))

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
            # EFMI 模式使用 match_index_count，ZZMI 模式不使用
            if self.mode == 'EFMI' and idx_count:
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
    SSMT_UL_IBSkipList,
    SSMTNode_PostProcess_IBSkip,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)