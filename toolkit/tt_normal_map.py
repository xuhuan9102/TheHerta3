import bpy
import os
import numpy as np
import traceback
from pathlib import Path
from collections import defaultdict
from .tt_dependency_check import is_dependency_installed
if is_dependency_installed('scipy'): 
    from scipy.ndimage import gaussian_filter, sobel

class TT_OT_generate_normal_maps(bpy.types.Operator):
    bl_idname = "toolkit.tt_generate_normal_maps"
    bl_label = "生成法线贴图 (NormalMap)"
    bl_description = "从基础颜色贴图的灰度值高效生成法线贴图"
    bl_options = {'REGISTER', 'UNDO'}
    
    def _find_base_color_texture(self, material):
        if not material or not material.use_nodes: return None
        output_node = next((n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
        if not output_node: return None
        nodes_to_visit = {link.from_node for inp in output_node.inputs if inp.is_linked for link in inp.links}
        visited_nodes = {output_node}; fallback_image = None
        while nodes_to_visit:
            current_node = nodes_to_visit.pop()
            if current_node in visited_nodes: continue
            visited_nodes.add(current_node)
            if 'Base Color' in current_node.inputs:
                base_color_input = current_node.inputs['Base Color']
                if base_color_input.is_linked:
                    from_node = base_color_input.links[0].from_node
                    if from_node.type == 'TEX_IMAGE' and from_node.image: return from_node.image
            if current_node.type == 'TEX_IMAGE' and current_node.image and fallback_image is None: fallback_image = current_node.image
            for inp in current_node.inputs:
                if inp.is_linked:
                    for link in inp.links:
                        if link.from_node not in visited_nodes: nodes_to_visit.add(link.from_node)
        return fallback_image
    
    def _create_normal_material(self, material_name, normal_map_image_path):
        mat = bpy.data.materials.get(material_name); created_new = False
        if not mat: mat = bpy.data.materials.new(name=material_name); created_new = True
        mat.use_nodes = True; node_tree = mat.node_tree; node_tree.nodes.clear()
        
        tex_node = node_tree.nodes.new('ShaderNodeTexImage'); tex_node.location = (-400, 0)
        image = bpy.data.images.load(normal_map_image_path, check_existing=True)
        tex_node.image = image; image.colorspace_settings.name = 'sRGB'
        
        transparent_bsdf = node_tree.nodes.new('ShaderNodeBsdfTransparent'); transparent_bsdf.location = (-200, 100)
        mix_shader = node_tree.nodes.new('ShaderNodeMixShader'); mix_shader.location = (0, 0)
        output_node = node_tree.nodes.new('ShaderNodeOutputMaterial'); output_node.location = (200, 0)
        
        node_tree.links.new(tex_node.outputs['Alpha'], mix_shader.inputs['Fac'])
        node_tree.links.new(transparent_bsdf.outputs['BSDF'], mix_shader.inputs[1])
        node_tree.links.new(tex_node.outputs['Color'], mix_shader.inputs[2])
        node_tree.links.new(mix_shader.outputs['Shader'], output_node.inputs['Surface'])
        
        return mat, created_new
    
    def execute(self, context):
        if not is_dependency_installed('scipy'):
            self.report({'ERROR'}, "缺少 'scipy' 库。请先安装依赖项并重启Blender。"); return {'CANCELLED'}
        props = context.scene.texture_tools_props
        if not props.output_dir: self.report({'ERROR'}, "请先设置输出目录"); return {'CANCELLED'}
        output_dir = bpy.path.abspath(props.output_dir); Path(output_dir).mkdir(parents=True, exist_ok=True)
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects: self.report({'ERROR'}, "没有选中的网格物体"); return {'CANCELLED'}
        material_map = defaultdict(list)
        for obj in selected_objects:
            if obj.material_slots and obj.material_slots[0].material: material_map[obj.material_slots[0].material].append(obj)
        if not material_map: self.report({'ERROR'}, "选中的物体上没有找到有效材质"); return {'CANCELLED'}
        processed_textures = {}; created_materials_count = 0
        for original_material, objects in material_map.items():
            base_texture = self._find_base_color_texture(original_material)
            if not base_texture: continue
            if base_texture.name in processed_textures: normal_map_path = processed_textures[base_texture.name]
            else:
                try:
                    width, height = base_texture.size
                    pixels_np = np.empty(width * height * 4, dtype=np.float32); base_texture.pixels.foreach_get(pixels_np)
                    pixels_np = pixels_np.reshape((height, width, 4))
                    grayscale = np.dot(pixels_np[...,:3], [0.299, 0.587, 0.114])
                    if props.normal_map_invert: grayscale = 1.0 - grayscale
                    if props.normal_map_blur_radius > 0:
                        from scipy.ndimage import gaussian_filter, sobel
                        grayscale = gaussian_filter(grayscale, sigma=props.normal_map_blur_radius)
                    else: from scipy.ndimage import sobel
                    dx = sobel(grayscale, axis=1); dy = sobel(grayscale, axis=0)
                    strength = props.normal_map_strength; z = np.ones_like(dx) / strength
                    norm = np.sqrt(dx**2 + dy**2 + z**2); norm[norm == 0] = 1
                    nx, ny = -dx / norm, -dy / norm
                    normal_map_pixels = np.zeros((height, width, 4), dtype=np.float32)
                    normal_map_pixels[..., 0] = nx * 0.5 + 0.5; normal_map_pixels[..., 1] = ny * 0.5 + 0.5
                    normal_map_pixels[..., 2] = props.normal_map_blue_channel_value; normal_map_pixels[..., 3] = 1.0
                    safe_name = "".join(c for c in os.path.splitext(base_texture.name)[0] if c.isalnum() or c in ('-','_','.'))
                    output_filename = f"NormalMap_{safe_name}.png"
                    output_path = os.path.join(output_dir, output_filename)
                    normal_image = bpy.data.images.new(name=output_filename, width=width, height=height, alpha=True)
                    normal_image.pixels.foreach_set(normal_map_pixels.flatten())
                    normal_image.filepath_raw = output_path; normal_image.file_format = 'PNG'; normal_image.save()
                    bpy.data.images.remove(normal_image)
                    normal_map_path = output_path; processed_textures[base_texture.name] = normal_map_path
                except Exception: self.report({'WARNING'}, f"处理纹理 {base_texture.name} 时失败: {traceback.format_exc()}"); continue
            if props.normal_map_create_materials and normal_map_path:
                new_mat_name = f"{props.normal_map_material_prefix}{original_material.name}"
                new_mat, created_new = self._create_normal_material(new_mat_name, normal_map_path)
                if created_new: created_materials_count += 1
                for obj in objects: obj.data.materials.append(new_mat)
        self.report({'INFO'}, f"完成！共生成 {len(processed_textures)} 张法线贴图。")
        if props.normal_map_create_materials: self.report({'INFO'}, f"成功创建并追加了 {created_materials_count} 个新材质。")
        return {'FINISHED'}


tt_normal_map_list = (
    TT_OT_generate_normal_maps,
)
