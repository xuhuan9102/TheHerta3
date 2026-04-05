import bpy
import os
import shutil
import bmesh
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras.io_utils import ImportHelper
import bpy.utils.previews

from ..utils.obj_utils import ObjUtils

from ..importer.mesh_importer import MigotoBinaryFile, MeshImporter
from ..config.main_config import GlobalConfig

from ..utils.translate_utils import TR
from ..utils.json_utils import JsonUtils
from ..utils.collection_utils import CollectionUtils,CollectionColor

preview_collections = {}

class Sword_ImportTexture_ImageListItem(PropertyGroup):
    name: StringProperty(name="Image Name") # type: ignore
    filepath: StringProperty(name="File Path") # type: ignore

class SWORD_UL_FastImportTextureList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        pcoll = preview_collections["main"]
        
        if self.layout_type in {'DEFAULT', 'Expand'}:
            if item.name in pcoll:
                layout.template_icon(icon_value=pcoll[item.name].icon_id, scale=1.0)
            else:
                layout.label(text="", icon='IMAGE_DATA')
            
            layout.label(text=item.name)
            
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            if item.name in pcoll:
                layout.template_icon(icon_value=pcoll[item.name].icon_id, scale=6.0)
            else:
                layout.label(text="", icon='IMAGE_DATA')

class Sword_ImportTexture_WM_OT_SelectImageFolder(Operator, ImportHelper):
    bl_idname = "wm.select_image_folder"
    bl_label = TR.translate("选择预览贴图所在的文件夹位置")
    
    directory: StringProperty(subtype='DIR_PATH') # type: ignore
    filter_folder: BoolProperty(default=True, options={'HIDDEN'}) # type: ignore
    filter_image: BoolProperty(default=False, options={'HIDDEN'}) # type: ignore

    def execute(self, context):
        context.scene.sword_image_list.clear()
        
        pcoll = preview_collections["main"]
        pcoll.clear()
        
        image_extensions = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.tga', '.exr', '.hdr','.dds')
        
        image_count = 0
        for filename in os.listdir(self.directory):
            if filename.lower().endswith(image_extensions):
                full_path = os.path.join(self.directory, filename)
                if os.path.isfile(full_path):
                    item = context.scene.sword_image_list.add()
                    item.name = filename
                    item.filepath = full_path
                    
                    try:
                        thumb = pcoll.load(filename, full_path, 'IMAGE')
                        image_count += 1
                    except Exception as e:
                        print(f"Could not load preview for {filename}: {e}")
        
        self.report({'INFO'}, f"Scanned {image_count} images.")
        return {'FINISHED'}
    

def reload_textures_from_folder(picture_folder_path:str):
    bpy.context.scene.sword_image_list.clear()
    pcoll = preview_collections["main"]
    pcoll.clear()
    
    image_extensions = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.tga', '.exr', '.hdr', '.dds')
    
    image_count = 0
    for filename in os.listdir(picture_folder_path):
        if filename.lower().endswith(image_extensions):
            full_path = os.path.join(picture_folder_path, filename)
            if os.path.isfile(full_path):
                item = bpy.context.scene.sword_image_list.add()
                item.name = filename
                item.filepath = full_path
                
                try:
                    thumb = pcoll.load(filename, full_path, 'IMAGE')
                    image_count += 1
                except Exception as e:
                    print(f"Could not load preview for {filename}: {e}")


class Sword_ImportTexture_WM_OT_AutoDetectTextureFolder(Operator):
    bl_idname = "wm.auto_detect_texture_folder"
    bl_label = TR.translate("自动检测提取的贴图文件夹")
    
    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}
        
        obj = selected_objects[0]
        obj_name = obj.name 
        
        selected_drawib_folder_path = os.path.join(GlobalConfig.path_workspace_folder(),  obj_name.split("-")[0] + "\\"  )
        
        deduped_textures_jpg_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures_jpg\\")
        deduped_textures_png_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures_png\\")
        deduped_textures_tga_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures_tga\\")

        deduped_textures_jpg_exists = os.path.exists(deduped_textures_jpg_folder_path)
        deduped_textures_png_exists = os.path.exists(deduped_textures_png_folder_path)
        deduped_textures_tga_exists = os.path.exists(deduped_textures_tga_folder_path)

        
        if not deduped_textures_jpg_exists and not deduped_textures_png_exists and not deduped_textures_tga_exists:
            self.report({'ERROR'}, TR.translate("未找到当前DrawIB: " + obj_name.split("-")[0] + "的DedupedTextures转换后的贴图文件夹，请确保此IB在当前工作空间中已经正常提取出来了"))
            return {'CANCELLED'}
        
        context.scene.sword_image_list.clear()
        pcoll = preview_collections["main"]
        pcoll.clear()
        
        image_extensions = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.tga', '.exr', '.hdr','.dds')
        
        image_count = 0
        for filename in os.listdir(deduped_textures_jpg_folder_path):
            if filename.lower().endswith(image_extensions):
                full_path = os.path.join(deduped_textures_jpg_folder_path, filename)
                if os.path.isfile(full_path):
                    item = context.scene.sword_image_list.add()
                    item.name = filename
                    item.filepath = full_path
                    
                    try:
                        thumb = pcoll.load(filename, full_path, 'IMAGE')
                        image_count += 1
                    except Exception as e:
                        print(f"Could not load preview for {filename}: {e}")
        
        self.report({'INFO'}, f"Auto-detected and loaded {image_count} images from DedupedTextures_jpg folder.")
        return {'FINISHED'}



class Sword_ImportTexture_WM_OT_ApplyImageToMaterial(Operator):
    bl_idname = "wm.apply_image_to_material"
    bl_label = "应用贴图到选中的物体"
    
    def execute(self, context):
        scene = context.scene
        selected_index = scene.sword_image_list_index
        
        if selected_index < 0 or selected_index >= len(scene.sword_image_list):
            self.report({'ERROR'}, "No image selected in the list.")
            return {'CANCELLED'}
        
        selected_image = scene.sword_image_list[selected_index]
        image_path = selected_image.filepath
        
        image_data = bpy.data.images.load(image_path, check_existing=True)
        
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}
        
        applied_count = 0
        for obj in selected_objects:
            if obj.type != 'MESH':
                continue
            
            if not obj.data.materials:
                mat = bpy.data.materials.new(name=f"Mat_{selected_image.name}")
                obj.data.materials.append(mat)
            else:
                mat = obj.data.materials[0]

                if mat is None:
                    mat = bpy.data.materials.new(name=f"Mat_{selected_image.name}")
                    obj.data.materials[0] = mat
            
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            bsdf_node = nodes.get("Principled BSDF")
            if not bsdf_node:
                print("疑似英文Principled BSDF无法获取，尝试获取中文的原理化 BSDF")
                bsdf_node = nodes.get("原理化 BSDF")
            
            if not bsdf_node:
                print("疑似英文Principled BSDF无法获取，尝试获取中文的原理化 BSDF")
                bsdf_node = nodes.get("原理化BSDF")

            if not bsdf_node:
                print("BSDF not exists ,ready to create one.")
                bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
                bsdf_node.location = (0, 0)
                
                output_node = nodes.get("Material Output")
                if not output_node:
                    output_node = nodes.new(type='ShaderNodeOutputMaterial')
                    output_node.location = (400, 0)
                
                links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
            
            tex_image = nodes.new('ShaderNodeTexImage')
            tex_image.image = image_data
            tex_image.location = (-300, 0)
            
            links.new(tex_image.outputs['Color'], bsdf_node.inputs['Base Color'])
            links.new(tex_image.outputs['Alpha'], bsdf_node.inputs['Alpha'])

            applied_count += 1
        
        self.report({'INFO'}, f"Applied {selected_image.name} to {applied_count} object(s).")
        return {'FINISHED'}


class SwordImportAllReversed(bpy.types.Operator):
    bl_idname = "ssmt.import_all_reverse"
    bl_label = TR.translate("一键导入逆向出来的全部模型")
    bl_description = "把上一次一键逆向出来的所有模型全部导入到Blender，然后你可以手动筛选并删除错误的数据类型，流程上更加方便。"

    def execute(self, context):
        reverse_output_folder_path = GlobalConfig.path_reverse_output_folder()
        if not os.path.exists(reverse_output_folder_path):
            self.report({"ERROR"},"当前一键逆向结果中标注的文件夹位置不存在，请重新运行一键逆向")
            return {'FINISHED'}
        print("测试导入")

        total_folder_name = os.path.basename(reverse_output_folder_path)

        reverse_collection = CollectionUtils.create_new_collection(collection_name=total_folder_name,color_tag=CollectionColor.Red)
        bpy.context.scene.collection.children.link(reverse_collection)

        subfolder_path_list = [f.path for f in os.scandir(reverse_output_folder_path) if f.is_dir()]

        for subfolder_path in subfolder_path_list:
            
            datatype_folder_name = os.path.basename(subfolder_path)

            datatype_collection = CollectionUtils.create_new_collection(collection_name=datatype_folder_name,color_tag=CollectionColor.White, link_to_parent_collection_name=reverse_collection.name)

            fmt_files = []
            for file in os.listdir(subfolder_path):
                if file.endswith('.fmt'):
                    fmt_files.append(os.path.join(subfolder_path, file))

            for fmt_filepath in fmt_files:
                filename_with_extension = os.path.basename(fmt_filepath)
                filename_without_extension = os.path.splitext(filename_with_extension)[0]
                mbf = MigotoBinaryFile(fmt_path=fmt_filepath,mesh_name=filename_without_extension)
                MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=datatype_collection)

        reload_textures_from_folder(reverse_output_folder_path)

        return {'FINISHED'}


class ExtractSubmeshOperator(bpy.types.Operator):
    bl_idname = "mesh.extract_submesh"
    bl_label = "Split By DrawIndexed"
    bl_options = {'REGISTER', 'UNDO'}

    start_index: bpy.props.IntProperty(
        name="Start Index",
        description="Starting index in the index buffer",
        default=0,
        min=0
    ) # type: ignore

    index_count: bpy.props.IntProperty(
        name="Index Count",
        description="Number of indices to include (must be multiple of 3)",
        default=3,
        min=3
    ) # type: ignore

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}

        original_mesh = obj.data
        original_mesh.calc_loop_triangles()
        
        start = self.start_index
        count = self.index_count
        end_index = start + count - 1
        
        if start + count > len(original_mesh.loops):
            self.report({'ERROR'}, f"Index range exceeds buffer, max loop count: {len(original_mesh.loops)}")
            return {'CANCELLED'}
            
        if count % 3 != 0:
            self.report({'ERROR'}, "Index count must be multiple of 3")
            return {'CANCELLED'}

        new_mesh_name = original_mesh.name +  ".Split-" + str(start) + "_" + str(end_index)
        new_mesh = original_mesh.copy()
        new_mesh.name = new_mesh_name
        
        bm = bmesh.new()
        bm.from_mesh(new_mesh)
        
        faces = list(bm.faces)
        
        faces_to_keep = set()
        for i in range(0, count, 3):
            face_index = (start + i) // 3
            if face_index < len(faces):
                faces_to_keep.add(faces[face_index])
        
        for face in list(bm.faces):
            if face not in faces_to_keep:
                bm.faces.remove(face)
        
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
        
        bm.to_mesh(new_mesh)
        bm.free()
        
        new_mesh.validate()
        new_mesh.update()
        
        new_obj = bpy.data.objects.new(new_mesh_name, new_mesh)
        new_obj.matrix_world = obj.matrix_world
        
        if obj.material_slots:
            for slot in obj.material_slots:
                new_obj.data.materials.append(slot.material)
        
        collection_name = new_mesh_name
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(collection)
        
        collection.objects.link(new_obj)
        
        for coll in new_obj.users_collection:
            if coll != collection:
                coll.objects.unlink(new_obj)
        
        context.view_layer.objects.active = new_obj
        new_obj.select_set(True)
        obj.select_set(False)
        
        return {'FINISHED'}


class Sword_ImportTexture_VIEW3D_PT_ImageMaterialPanel(Panel):
    bl_label = "3Dmigoto-Sword面板"
    bl_idname = "VIEW3D_PT_image_material_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta3'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return not getattr(context.scene, 'herta_show_toolkit', False)

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("ssmt.import_all_reverse")
        
        layout.operator("import_mesh.migoto_raw_buffers_mmt",icon='IMPORT')

        row = layout.row()

        row = layout.row()
        row.operator("wm.select_image_folder", icon='FILE_FOLDER')
        
        if scene.sword_image_list:
            layout.label(text=f"Found {len(scene.sword_image_list)} images")
        
        if scene.sword_image_list:
            row = layout.row()
            row.template_list(
                "SWORD_UL_FastImportTextureList",
                "Image List", 
                scene, 
                "sword_image_list", 
                scene, 
                "sword_image_list_index",
                rows=6
            )
        else:
            layout.label(text="No images found. Select a folder first.")
        
        row = layout.row()
        row.operator("wm.apply_image_to_material", icon='MATERIAL_DATA')
        
        if scene.sword_image_list and scene.sword_image_list_index >= 0 and scene.sword_image_list_index < len(scene.sword_image_list):
            selected_item = scene.sword_image_list[scene.sword_image_list_index]
            pcoll = preview_collections["main"]
            
            if selected_item.name in pcoll:
                box = layout.box()
                box.label(text="Preview:")
                box.template_icon(icon_value=pcoll[selected_item.name].icon_id, scale=10.0)


class Sword_SplitModel_By_DrawIndexed_Panel(Panel):
    bl_label = "手动逆向后根据DrawIndexed值分割模型"
    bl_idname = "VIEW3D_PT_Sword_SplitModel_By_DrawIndexed_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta3'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return not getattr(context.scene, 'herta_show_toolkit', False)

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "submesh_start")
        layout.prop(scene, "submesh_count")
        
        op = layout.operator("mesh.extract_submesh")
        op.start_index = scene.submesh_start
        op.index_count = scene.submesh_count

def register():
    pcoll = bpy.utils.previews.new()
    preview_collections["main"] = pcoll

    bpy.utils.register_class(Sword_ImportTexture_ImageListItem)
    bpy.utils.register_class(SWORD_UL_FastImportTextureList)
    bpy.utils.register_class(Sword_ImportTexture_VIEW3D_PT_ImageMaterialPanel)
    bpy.utils.register_class(Sword_ImportTexture_WM_OT_ApplyImageToMaterial)
    bpy.utils.register_class(Sword_ImportTexture_WM_OT_SelectImageFolder)
    bpy.utils.register_class(SwordImportAllReversed)
    bpy.utils.register_class(ExtractSubmeshOperator)
    bpy.utils.register_class(Sword_SplitModel_By_DrawIndexed_Panel)

    bpy.types.Scene.sword_image_list = CollectionProperty(type=Sword_ImportTexture_ImageListItem)
    bpy.types.Scene.sword_image_list_index = IntProperty(default=0)
    
    bpy.types.Scene.submesh_start = IntProperty(
        name="Start Index",
        default=0,
        min=0
    )
    bpy.types.Scene.submesh_count = IntProperty(
        name="Index Count",
        default=3,
        min=3
    )

def unregister():
    try:
        del bpy.types.Scene.sword_image_list
        del bpy.types.Scene.sword_image_list_index
    except Exception:
        pass
    
    try:
        del bpy.types.Scene.submesh_start
        del bpy.types.Scene.submesh_count
    except Exception:
        pass

    for pcoll in preview_collections.values():
        try:
            bpy.utils.previews.remove(pcoll)
        except Exception:
            pass
    preview_collections.clear()

    bpy.utils.unregister_class(Sword_SplitModel_By_DrawIndexed_Panel)
    bpy.utils.unregister_class(ExtractSubmeshOperator)
    bpy.utils.unregister_class(SwordImportAllReversed)
    bpy.utils.unregister_class(Sword_ImportTexture_WM_OT_SelectImageFolder)
    bpy.utils.unregister_class(Sword_ImportTexture_WM_OT_ApplyImageToMaterial)
    bpy.utils.unregister_class(Sword_ImportTexture_VIEW3D_PT_ImageMaterialPanel)
    bpy.utils.unregister_class(SWORD_UL_FastImportTextureList)
    bpy.utils.unregister_class(Sword_ImportTexture_ImageListItem)
