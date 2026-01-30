import bpy


@bpy.app.handlers.persistent
def object_post_delete_handler(scene):
    """处理物体删除事件，自动删除对应的物体信息节点"""
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            nodes_to_remove = []
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_name = getattr(node, 'object_name', '')
                    if obj_name and obj_name not in bpy.data.objects:
                        nodes_to_remove.append(node)
            
            for node in nodes_to_remove:
                tree.nodes.remove(node)


@bpy.app.handlers.persistent
def object_visibility_handler(scene):
    """处理物体可见性变化事件，同步更新对应节点的禁用状态"""
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_name = getattr(node, 'object_name', '')
                    if obj_name:
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            node.mute = obj.hide_viewport


def register():
    bpy.app.handlers.depsgraph_update_post.append(object_post_delete_handler)
    bpy.app.handlers.depsgraph_update_post.append(object_visibility_handler)


def unregister():
    if object_post_delete_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(object_post_delete_handler)
    if object_visibility_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(object_visibility_handler)
