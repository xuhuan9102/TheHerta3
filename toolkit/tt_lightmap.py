import bpy

class TT_OT_generate_lightmap_template(bpy.types.Operator):
    bl_idname = "toolkit.tt_generate_lightmap_template"
    bl_label = "生成光照模板"
    bl_description = "为选中的物体创建LightMap和MaterialMap材质模板"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "请先选择要应用光照模板的物体")
            return {'CANCELLED'}
        
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "选中的物体中没有网格物体")
            return {'CANCELLED'}
        
        props = context.scene.texture_tools_props
        mode = props.lightmap_mode
        generate_lightmap = props.lightmap_generate_lightmap
        generate_materialmap = props.lightmap_generate_materialmap
        
        if not generate_lightmap and not generate_materialmap:
            self.report({'ERROR'}, "请至少选择一种材质类型")
            return {'CANCELLED'}
        
        base_material_name = None
        for obj in mesh_objects:
            if obj.material_slots and obj.material_slots[0].material:
                base_material_name = obj.material_slots[0].material.name
                break
        
        if not base_material_name:
            base_material_name = "Material"
        
        lightmap_material = None
        materialmap_material = None
        
        if generate_lightmap:
            lightmap_material = self._create_lightmap_material(context, base_material_name)
        
        if generate_materialmap:
            materialmap_material = self._create_materialmap_material(context, base_material_name)
        
        for obj in mesh_objects:
            if mode == 'REPLACE':
                obj.active_material_index = 0
                obj.active_material = None
                obj.data.materials.clear()
            
            if lightmap_material:
                obj.data.materials.append(lightmap_material)
            if materialmap_material:
                obj.data.materials.append(materialmap_material)
        
        self.report({'INFO'}, f"已为 {len(mesh_objects)} 个物体生成光照模板 (材质后缀: {base_material_name})")
        return {'FINISHED'}
    
    def _create_lightmap_material(self, context, base_material_name):
        mat_name = f"LightMap_{base_material_name}"
        
        if mat_name in bpy.data.materials:
            return bpy.data.materials[mat_name]
        
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        nodes.clear()
        
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        rgb_node = nodes.new(type='ShaderNodeRGB')
        rgb_node.location = (0, 0)
        rgb_node.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        
        links.new(rgb_node.outputs[0], output_node.inputs['Surface'])
        
        return mat
    
    def _create_materialmap_material(self, context, base_material_name):
        mat_name = f"MaterialMap_{base_material_name}"
        
        if mat_name in bpy.data.materials:
            return bpy.data.materials[mat_name]
        
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        nodes.clear()
        
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        rgb_node = nodes.new(type='ShaderNodeRGB')
        rgb_node.location = (0, 0)
        rgb_node.outputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
        
        links.new(rgb_node.outputs[0], output_node.inputs['Surface'])
        
        return mat


tt_lightmap_list = (
    TT_OT_generate_lightmap_template,
)
