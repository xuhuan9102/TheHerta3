
import bpy
from bpy.types import NodeTree, Node, NodeSocket

from ..config.main_config import GlobalConfig

# Custom Socket Types
class SSMTSocketObject(NodeSocket):
    '''Custom Socket for Object Data'''
    bl_idname = 'SSMTSocketObject'
    bl_label = 'Object Socket'

    def draw_color(self, context, node):
        return (0.0, 0.8, 0.8, 1.0) # Cyan/Teal

    def draw(self, context, layout, node, text):
        layout.label(text=text)

# 1. 定义自定义节点树类型
class SSMTBlueprintTree(NodeTree):
    '''SSMT Mod Logic Blueprint'''
    bl_idname = 'SSMTBlueprintTreeType'
    bl_label = 'SSMT BluePrint'
    bl_icon = 'NODETREE'

# 2. 定义基础节点
class SSMTNodeBase(Node):
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'SSMTBlueprintTreeType'


# 对象信息节点
class SSMTNode_Object_Info(SSMTNodeBase):
    '''Object Info Node'''
    bl_idname = 'SSMTNode_Object_Info'
    bl_label = 'Object Info'
    bl_icon = 'OBJECT_DATAMODE'
    bl_width_min = 300
    
    # 定义属性用于存储信息
    # 使用 props.PointerProperty 指向 Object 可能会有上下文问题（特别是跨文件保存时），
    # 但在 Runtime UI 中通常结合 prop_search 使用 StringProperty 来模拟体验。
    # 为了更好的体验，我们使用 StringProperty 并配合 prop_search 绘制。
    
    def update_object_name(self, context):
        if self.object_name:
            self.label = self.object_name
            if "-" in self.object_name:
                obj_name_split = self.object_name.split("-")
                self.draw_ib = obj_name_split[0]
                self.component = obj_name_split[1]
                self.alias_name = obj_name_split[2]
        else:
            self.label = "Object Info"
    object_name: bpy.props.StringProperty(name="Object Name", default="", update=update_object_name) # type: ignore


    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    alias_name: bpy.props.StringProperty(name="Alias Name", default="") # type: ignore

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Object")
        # self.width = 300 # 让节点宽一点

    def draw_buttons(self, context, layout):
        # 1. 物体选择：使用 prop_search 让用户可以像属性面板一样搜索选择
        # 但是 node 本身没有 PointerProperty 指向 ID 类型的简单 GUI 支持，
        # 所以通常是用 search 指向 bpy.data.objects
        layout.prop_search(self, "object_name", bpy.data, "objects", text="", icon='OBJECT_DATA')
        
        # 2. DrawIB 和 Component 自由修改
        layout.prop(self, "draw_ib", text="DrawIB")
        layout.prop(self, "component", text="Component")
        layout.prop(self, "alias_name", text="Alias Name")


# 组合节点：用于将多个 Object Info 按顺序组合
class SSMTNode_Object_Group(SSMTNodeBase):
    '''单纯用于分组的节点，可以接受任何节点作为输入，放在一个组里'''
    bl_idname = 'SSMTNode_Object_Group'
    bl_label = 'Group'
    bl_icon = 'GROUP'

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200

    def draw_buttons(self, context, layout):
        layout.operator("ssmt.view_group_objects", text="查看递归解析预览", icon='HIDE_OFF').node_name = self.name

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        # 移除中间断开的连接，或者整理列表（可选）
        # 这里实现一个简单的逻辑：如果倒数第二个也没有连接，就移除最后一个
        # 防止无限增长，或者用户断开最后一个连接的情况
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


class SSMTNode_ToggleKey(SSMTNodeBase):
    '''【按键开关】会控制所有连接到它输入端口的对象,是【按键切换】的一个特殊情况，因为常用所以单独做成了一个节点'''
    bl_idname = 'SSMTNode_ToggleKey'
    bl_label = 'Toggle Key'
    bl_icon = 'GROUP'

    key_name: bpy.props.StringProperty(name="Key Name", default="") # type: ignore
    default_on: bpy.props.BoolProperty(name="Default On", default=False) # type: ignore

    def init(self, context):
        self.label = "按键开关"
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200
        self.use_custom_color = True
        self.color = (0.41, 0.42, 0.66)

    def draw_buttons(self, context, layout):
        # layout.prop(self, "key_name", text="按键")
        row = layout.row(align=True)
        row.prop(self, "key_name", text="按键")
        row.operator("wm.url_open", text="", icon='HELP').url = "https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes"
        
        layout.prop(self, "default_on", text="默认开启")

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        # 移除中间断开的连接，或者整理列表（可选）
        # 这里实现一个简单的逻辑：如果倒数第二个也没有连接，就移除最后一个
        # 防止无限增长，或者用户断开最后一个连接的情况
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])



class SSMT_OT_SwitchKey_AddSocket(bpy.types.Operator):
    '''Add a new socket to the switch node'''
    bl_idname = "ssmt.switch_add_socket"
    bl_label = "Add Socket"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or context.space_data.node_tree
        if not tree:
             return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node:
             node.inputs.new('SSMTSocketObject', f"Status {len(node.inputs)}")
        return {'FINISHED'}

class SSMT_OT_SwitchKey_RemoveSocket(bpy.types.Operator):
    '''Remove the last socket from the switch node'''
    bl_idname = "ssmt.switch_remove_socket"
    bl_label = "Remove Socket"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or context.space_data.node_tree
        if not tree:
             return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and len(node.inputs) > 0:
            node.inputs.remove(node.inputs[-1])
        return {'FINISHED'}


class SSMTNode_SwitchKey(SSMTNodeBase):
    '''【按键切换】会把每个连入的分支分配到单独的变量'''
    bl_idname = 'SSMTNode_SwitchKey'
    bl_label = 'Switch Key'
    bl_icon = 'GROUP'

    key_name: bpy.props.StringProperty(name="Key Name", default="") # type: ignore

    def init(self, context):
        self.label = "按键切换"
        self.inputs.new('SSMTSocketObject', "Status 0")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200
        self.use_custom_color = True
        self.color = (0.34, 0.54, 0.34)

    def draw_buttons(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "key_name", text="按键")
        row.operator("wm.url_open", text="", icon='HELP').url = "https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes"
        
        row = layout.row(align=True)
        op_add = row.operator("ssmt.switch_add_socket", text="Add", icon='ADD')
        op_add.node_name = self.name
        
        op_rem = row.operator("ssmt.switch_remove_socket", text="Remove", icon='REMOVE')
        op_rem.node_name = self.name


# 结果输出节点
class SSMTNode_Result_Output(SSMTNodeBase):
    '''Result Output Node'''
    bl_idname = 'SSMTNode_Result_Output'
    bl_label = 'Generate Mod'
    bl_icon = 'EXPORT'

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Group 1")
        self.width = 200

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Group {len(self.inputs) + 1}")
        
        # 移除中间断开的连接
        # 保留 inputs[0](至少一个Group)
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])






class SSMT_OT_CreateGroupFromSelection(bpy.types.Operator):
    '''Create nodes from selected objects and group them under a new Group node'''
    bl_idname = "ssmt.create_group_from_selection"
    bl_label = "将所选物体新建到组节点"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "没有选择任何物体")
            return {'CANCELLED'}

        # 获取或创建与当前 Workspace 同名的 SSMT Blueprint 节点树
        workspace_name = "Mod_" + GlobalConfig.workspacename
        node_tree = bpy.data.node_groups.get(workspace_name)
        
        if not node_tree or node_tree.bl_idname != 'SSMTBlueprintTreeType':
            node_tree = bpy.data.node_groups.new(name=workspace_name, type='SSMTBlueprintTreeType')

        # 切换到节点编辑器并设置该节点树（可选，视需求而定，这里主要负责创建节点）
        # 如果需要跳转可以使用 context.area.type etc. 但在 3D View 操作不一定需要跳转

        # 计算节点位置偏移，防止重叠
        # 简单策略：找到当前最右侧/最下方的节点，或者直接在原点附近偏移
        # 这里使用一个简单的网格布局
        
        # 查找一个放置基准点
        base_x = 0
        base_y = 0
        if node_tree.nodes:
             # 如果已有节点，往右下角找个空地，或者直接往右
             pass

        # 创建 Group 节点
        group_node = node_tree.nodes.new(type='SSMTNode_Object_Group')
        group_node.location = (base_x + 400, base_y)
        
        # 创建 Object Nodes 并连接
        for i, obj in enumerate(selected_objects):
            obj_node = node_tree.nodes.new(type='SSMTNode_Object_Info')
            obj_node.location = (base_x, base_y - i * 150)
            
            # 设置物体
            obj_node.object_name = obj.name
            # 手动触发 update 如果需要，但属性设置通常会自动 update 
            # (注意: 这里 update_object_name 是 property update callback)
            
            # 连接到 group_node
            # Group Node 会自动根据连接增加 input socket (在 update() 中)
            # 但首次连接时可能只有一个 input, 连接后 update 会增加新的
            
            # 获取当前可用的 input
            # 因为 SSMTNode_Object_Group.update() 逻辑是：如果有连接到 inputs[-1]，则 new socket remove...
            # 所以我们需要确保连接
            
            # 找到第一个未连接的 input，或者最后一个
            target_socket = None
            if len(group_node.inputs) > 0:
                 target_socket = group_node.inputs[-1]
            
            if target_socket:
                node_tree.links.new(obj_node.outputs[0], target_socket)
                # 强制更新一下 group node 以生成新的插槽，以便下一个物体连接
                group_node.update()

        return {'FINISHED'}


def draw_objects_context_menu_add(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("SSMT_MT_ObjectContextMenuSub", text="SSMT蓝图架构", icon='NODETREE')

class SSMT_MT_ObjectContextMenuSub(bpy.types.Menu):
    bl_label = "SSMT蓝图架构"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("ssmt.create_group_from_selection", text="将所选物体新建到组节点", icon='GROUP')



class SSMT_OT_View_Group_Objects(bpy.types.Operator):
    '''递归解析当前组下面所有的物体并放到一个新的窗口中展示，注意组节点最好不要包含按键切换，否则会同时展示所有切换分支内容'''
    bl_idname = "ssmt.view_group_objects"
    bl_label = "View Group Objects"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or context.space_data.node_tree
        if not tree:
             return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if not node:
             return {'CANCELLED'}

        objects_to_show = set()
        checked_nodes = set()

        def collect_objects(current_node):
            if current_node in checked_nodes: return
            checked_nodes.add(current_node)

            if getattr(current_node, "bl_idname", "") == 'SSMTNode_Object_Info':
                obj_name = getattr(current_node, "object_name", "")
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj:
                        objects_to_show.add(obj)

            if hasattr(current_node, "inputs"):
                for inp in current_node.inputs:
                    if inp.is_linked:
                        for link in inp.links:
                            collect_objects(link.from_node)

        collect_objects(node)
        
        if not objects_to_show:
            self.report({'WARNING'}, "No objects found in this group")
            return {'CANCELLED'}

        # Ensure Object Mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects_to_show:
            obj.select_set(True)

        # Open new window
        bpy.ops.wm.window_new()
        new_window = context.window_manager.windows[-1]

        # Use the first area of the new window and convert it to 3D View
        if new_window.screen and new_window.screen.areas:
            area = new_window.screen.areas[0]
            area.type = 'VIEW_3D'
            area.ui_type = 'VIEW_3D'
            
            # Find the WINDOW region for proper context
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            
            if region:
                with context.temp_override(window=new_window, area=area, region=region):
                    # Enter Local View to isolate selected objects
                    try:
                        if area.spaces.active.region_3d.is_perspective:
                            bpy.ops.view3d.view_persportho() # Switch to Orthographic
                        
                        bpy.ops.view3d.localview() 
                        bpy.ops.view3d.view_axis(type='FRONT')
                        bpy.ops.view3d.view_selected()
                        
                        # Optional: Set shading to Solid or Material
                        if area.spaces.active:
                            area.spaces.active.shading.type = 'SOLID'
                    except Exception as e:
                        print(f"View setup warning: {e}")

        return {'FINISHED'}

# 3. 注册列表
classes = (
    SSMT_OT_View_Group_Objects,
    SSMTSocketObject,
    SSMTBlueprintTree,
    SSMTNode_Object_Info,
    SSMTNode_Object_Group,
    SSMTNode_Result_Output,
    SSMTNode_ToggleKey,
    SSMTNode_SwitchKey,
    SSMT_OT_SwitchKey_AddSocket,
    SSMT_OT_SwitchKey_RemoveSocket,
    SSMT_OT_CreateGroupFromSelection,
    SSMT_MT_ObjectContextMenuSub,
)

def draw_node_add_menu(self, context):
    if not isinstance(context.space_data, bpy.types.SpaceNodeEditor):
        return
    if context.space_data.tree_type != 'SSMTBlueprintTreeType':
        return
    
    layout = self.layout
    layout.operator("node.add_node", text="Object Info", icon='OBJECT_DATAMODE').type = "SSMTNode_Object_Info"
    layout.operator("node.add_node", text="Group", icon='GROUP').type = "SSMTNode_Object_Group"
    layout.operator("node.add_node", text="Mod Output", icon='EXPORT').type = "SSMTNode_Result_Output"
    layout.operator("node.add_node", text="Toggle Key", icon='GROUP').type = "SSMTNode_ToggleKey"
    layout.operator("node.add_node", text="Switch Key", icon='GROUP').type = "SSMTNode_SwitchKey"
    layout.separator()

    # Frame节点没有任何功能，它是Blender自带的一种辅助节点，用于在节点编辑器中组织和分组节点
    # 反正就当一个区域划分来用就行了
    layout.operator("node.add_node", text="Frame", icon='FILE_PARENT').type = "NodeFrame"
    layout.separator()

# 注册与注销函数，在大型Blender插件开发中，不能在最外面的__init__.py中直接注册
# 否则会导致__init__.py过于臃肿，不利于维护，所以在各自的模块中定义register和unregister函数
def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass # Already registered
        
    bpy.types.NODE_MT_add.prepend(draw_node_add_menu)
    # 添加到 3D 视图物体右键菜单
    bpy.types.VIEW3D_MT_object_context_menu.append(draw_objects_context_menu_add)

def unregister():
    bpy.types.NODE_MT_add.remove(draw_node_add_menu)
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_objects_context_menu_add)

    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except ValueError:
            pass



