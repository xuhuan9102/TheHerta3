"""
崩坏三
"""
import math
import bpy
import os

from ..config.main_config import GlobalConfig, LogicName
from ..common.draw_ib_model import DrawIBModel

from ..base.m_global_key_counter import M_GlobalKeyCounter
from ..blueprint.blueprint_model import BluePrintModel
from ..blueprint.blueprint_export_helper import BlueprintExportHelper

from ..common.m_ini_builder import M_IniBuilder,M_IniSection,M_SectionType
from ..config.properties_generate_mod import Properties_GenerateMod
from ..common.m_ini_helper import M_IniHelper,M_IniHelper
from ..common.m_ini_helper_gui import M_IniHelperGUI

from ..utils.json_utils import JsonUtils
from ..utils.config_utils import ConfigUtils


def check_and_try_generate_import_json_for_ssmt4() -> dict:
    '''
    检查 Import.json 是否存在，如果不存在则尝试自动生成
    返回 draw_ib_gametypename_dict
    '''
    workspace_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(), "Import.json")
    
    if os.path.exists(workspace_import_json_path):
        return JsonUtils.LoadFromFile(workspace_import_json_path)
    
    print("Import.json 不存在，尝试自动生成...")
    
    draw_ib_gametypename_dict = {}
    
    current_workspace_folder = GlobalConfig.path_workspace_folder()
    
    try:
        all_folders = [f.name for f in os.scandir(current_workspace_folder) if f.is_dir()]
    except Exception as e:
        return draw_ib_gametypename_dict
    
    for folder_name in all_folders:
        folder_path = os.path.join(current_workspace_folder, folder_name)
        
        has_type_folder = False
        try:
            subdirs = os.listdir(folder_path)
            for subdir in subdirs:
                if subdir.startswith("TYPE_"):
                    has_type_folder = True
                    break
        except:
            pass
        
        if not has_type_folder:
            continue
        
        if "-" in folder_name:
            draw_ib_key = folder_name
        else:
            draw_ib_key = folder_name
        
        dirs = os.listdir(folder_path)
        gpu_folders = []
        cpu_folders = []
        
        for dirname in dirs:
            if not dirname.startswith("TYPE_"):
                continue
            type_folder_path = os.path.join(folder_path, dirname)
            if dirname.startswith("TYPE_GPU"):
                gpu_folders.append(type_folder_path)
            elif dirname.startswith("TYPE_CPU"):
                cpu_folders.append(type_folder_path)
        
        all_type_folders = gpu_folders + cpu_folders
        
        for type_folder_path in all_type_folders:
            import_json_path = os.path.join(type_folder_path, "import.json")
            if os.path.exists(import_json_path):
                try:
                    import_json = JsonUtils.LoadFromFile(import_json_path)
                    work_game_type = import_json.get("WorkGameType", "")
                    if work_game_type:
                        draw_ib_gametypename_dict[draw_ib_key] = work_game_type
                        break
                except Exception:
                    continue
            
            tmp_json_path = os.path.join(type_folder_path, "tmp.json")
            if os.path.exists(tmp_json_path):
                try:
                    tmp_json = ConfigUtils.read_tmp_json(type_folder_path)
                    work_game_type = tmp_json.get("WorkGameType", "")
                    if work_game_type:
                        draw_ib_gametypename_dict[draw_ib_key] = work_game_type
                        break
                except Exception:
                    continue
    
    if draw_ib_gametypename_dict:
        JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict, filepath=workspace_import_json_path)
    
    return draw_ib_gametypename_dict


class ModModelHIMI:
    def __init__(self):
        self.branch_model = BluePrintModel()
        self.drawib_drawibmodel_dict:dict[str,DrawIBModel] = {}
        self.parse_draw_ib_draw_ib_model_dict()
        self.vlr_filter_index_indent = ""
        self.texture_hash_filter_index_dict = {}

    def _find_ssmt4_unique_str(self, draw_ib: str, draw_ib_gametypename_dict: dict) -> str:
        '''
        查找 SSMT4 格式的 unique_str
        
        第三代格式（SSMT3）：文件夹结构为 DrawIB/TYPE_xxx/
        第四代格式（SSMT4）：文件夹结构为 DrawIB-IndexCount-FirstIndex/TYPE_xxx/
        
        通过检查工作空间中是否存在以 draw_ib 开头的 SSMT4 格式文件夹来判断
        '''
        workspace_folder = GlobalConfig.path_workspace_folder()
        
        if draw_ib in draw_ib_gametypename_dict:
            return ""
        
        try:
            all_folders = [f.name for f in os.scandir(workspace_folder) if f.is_dir()]
            ssmt4_folders = [f for f in all_folders if f.startswith(draw_ib + "-")]
            
            if ssmt4_folders:
                for folder_name in ssmt4_folders:
                    if folder_name in draw_ib_gametypename_dict:
                        return folder_name
                    
                    folder_path = os.path.join(workspace_folder, folder_name)
                    try:
                        subdirs = os.listdir(folder_path)
                        for subdir in subdirs:
                            if subdir.startswith("TYPE_"):
                                return folder_name
                    except:
                        continue
        except Exception as e:
            print(f"查找 SSMT4 文件夹时出错: {e}")
        
        return ""

    def parse_draw_ib_draw_ib_model_dict(self):
        '''
        根据obj的命名规则，推导出DrawIB并抽象为DrawIBModel
        支持第三代(SSMT3)和第四代(SSMT4)格式
        
        第三代格式：物体名称为 DrawIB-Component.Alias，文件夹结构为 DrawIB/TYPE_xxx/
        第四代格式：物体名称为 DrawIB-IndexCount-FirstIndex.Alias，文件夹结构为 DrawIB-IndexCount-FirstIndex/TYPE_xxx/
        '''
        draw_ib_gametypename_dict = check_and_try_generate_import_json_for_ssmt4()
        
        for draw_ib in self.branch_model.draw_ib__component_count_list__dict.keys():
            unique_str = self._find_ssmt4_unique_str(draw_ib, draw_ib_gametypename_dict)
            
            if unique_str:
                print(f"检测到 SSMT4 格式: draw_ib={draw_ib}, unique_str={unique_str}")
            
            draw_ib_model = DrawIBModel(draw_ib=draw_ib, branch_model=self.branch_model, unique_str=unique_str)
            self.drawib_drawibmodel_dict[draw_ib] = draw_ib_model
            
        
    def add_unity_vs_texture_override_vb_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        # 声明TextureOverrideVB部分，只有使用GPU-PreSkinning时是直接替换hash对应槽位
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        # 只有GPU-PreSkinning需要生成TextureOverrideVB部分，CPU类型不需要

        texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
        texture_override_vb_section.append("; " + draw_ib + " ")
        
        unique_str = getattr(draw_ib_model, 'unique_str', "")
        
        for category_name in d3d11GameType.OrderedCategoryNameList:
            category_hash = draw_ib_model.import_config.category_hash_dict[category_name]
            category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]

            texture_override_vb_name_suffix = "VB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + category_name
            texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_name_suffix + "]")
            texture_override_vb_section.append("hash = " + category_hash)

            
            # (1) 先初始化CommandList
            drawtype_indent_prefix = ""

            
            # 如果出现了VertexLimitRaise，Texcoord槽位需要检测filter_index才能替换
            filterindex_indent_prefix = ""


            # 遍历获取所有在当前分类hash下进行替换的分类，并添加对应的资源替换
            for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                if category_name == draw_category_name:
                    category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                    if unique_str:
                        resource_name = "Resource_" + unique_str.replace("-", "_") + "_" + original_category_name
                    else:
                        resource_name = "Resource" + draw_ib + original_category_name
                    texture_override_vb_section.append(filterindex_indent_prefix + drawtype_indent_prefix + category_original_slot + " = " + resource_name)

            # draw一般都是在Blend槽位上进行的，所以我们这里要判断确定是Blend要替换的hash才能进行draw。
            draw_category_name = d3d11GameType.CategoryDrawCategoryDict.get("Blend",None)
            if draw_category_name is not None and category_name == d3d11GameType.CategoryDrawCategoryDict["Blend"]:
                texture_override_vb_section.append(drawtype_indent_prefix + "handling = skip")
                texture_override_vb_section.append(drawtype_indent_prefix + "draw = " + str(draw_ib_model.draw_number) + ", 0")

       

            

            # 分支架构，如果是Position则需提供激活变量
            if category_name == d3d11GameType.CategoryDrawCategoryDict["Position"]:
                if len(self.branch_model.keyname_mkey_dict.keys()) != 0:
                    texture_override_vb_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")

                    if Properties_GenerateMod.generate_branch_mod_gui():
                        texture_override_vb_section.append("$ActiveCharacter = 1")

            texture_override_vb_section.new_line()


        config_ini_builder.append_section(texture_override_vb_section)

    def add_unity_vs_texture_override_ib_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib
        
        d3d11GameType = draw_ib_model.d3d11GameType

        texture_override_ib_section.append("[TextureOverride_IB_" + draw_ib + "]")
        texture_override_ib_section.append("hash = " + draw_ib)
        texture_override_ib_section.append("handling = skip")
        texture_override_ib_section.new_line()

        unique_str = getattr(draw_ib_model, 'unique_str', "")
        
        if unique_str:
            for component_model in draw_ib_model._component_model_list:
                component_name = component_model.component_name
                first_index = getattr(component_model, 'first_index', 0)
                component_index = component_name.replace("Component ", "")
                
                style_part_name = "Component" + component_index
                texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name
                
                ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(component_index, "")
                
                texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
                texture_override_ib_section.append("hash = " + draw_ib)
                texture_override_ib_section.append("match_first_index = " + str(first_index))
                
                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))
                
                ib_buf = draw_ib_model.componentname_ibbuf_dict.get(component_name, None)
                if ib_buf is None or len(ib_buf) == 0:
                    texture_override_ib_section.append("ib = null")
                    texture_override_ib_section.new_line()
                else:
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)
                    
                    if not Properties_GenerateMod.forbid_auto_texture_ini():
                        texture_markup_info_list = None
                        if component_model.final_ordered_draw_obj_model_list:
                            first_obj = component_model.final_ordered_draw_obj_model_list[0]
                            obj_full_name = f"{first_obj.draw_ib}-{first_obj.index_count}-{first_obj.first_index}"
                            print(f"调试: obj_full_name={obj_full_name}, is_ssmt4={first_obj.is_ssmt4}")
                            print(f"调试: partname_texturemarkinfolist_dict keys={list(draw_ib_model.import_config.partname_texturemarkinfolist_dict.keys())}")
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(obj_full_name, None)
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(component_index, None)
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get("1", None)
                        print(f"调试: texture_markup_info_list={texture_markup_info_list}")
                        if texture_markup_info_list is not None:
                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_type == "Slot":
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())
                    
                    drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                    for drawindexed_str in drawindexed_str_list:
                        texture_override_ib_section.append(drawindexed_str)
                    
                    if self.vlr_filter_index_indent:
                        texture_override_ib_section.append("endif")
                        texture_override_ib_section.new_line()
        else:
            for count_i,part_name in enumerate(draw_ib_model.import_config.part_name_list):
                match_first_index = draw_ib_model.import_config.match_first_index_list[count_i]
                # part_name = draw_ib_model.import_config.part_name_list[count_i]
                style_part_name = "Component" + part_name
                texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name

                # 读取使用的IBResourceName，如果读取不到，就使用默认的
                ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(part_name,"")
                

                texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
                texture_override_ib_section.append("hash = " + draw_ib)
                texture_override_ib_section.append("match_first_index = " + match_first_index)

                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                # texture_override_ib_section.append(self.vlr_filter_index_indent + "handling = skip")

                # If ib buf is emprt, continue to avoid add ib resource replace.
                ib_buf = draw_ib_model.componentname_ibbuf_dict.get("Component " + part_name,None)
                if ib_buf is None or len(ib_buf) == 0:
                    # 不导出对应部位时，要写ib = null，否则在部分场景会发生卡顿，原因未知但是这就是解决方案。
                    texture_override_ib_section.append("ib = null")
                    texture_override_ib_section.new_line()
                    continue


                # Add ib replace
                texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)


                # Add slot style texture slot replace.
                if not Properties_GenerateMod.forbid_auto_texture_ini():
                    texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                    # It may not have auto texture
                    if texture_markup_info_list is not None:
                        for texture_markup_info in texture_markup_info_list:
                            if texture_markup_info.mark_type == "Slot":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

                # DrawIndexed部分
                component_name = "Component " + part_name
                component_model = draw_ib_model.component_name_component_model_dict[component_name]

                drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                for drawindexed_str in drawindexed_str_list:
                    texture_override_ib_section.append(drawindexed_str)

                # 补全endif
                if self.vlr_filter_index_indent:
                    texture_override_ib_section.append("endif")
                    texture_override_ib_section.new_line()
            
        config_ini_builder.append_section(texture_override_ib_section)

    def add_unity_vs_texture_override_vlr_section(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        '''
        Add VertexLimitRaise section, UnityVS style.
        Only Unity VertexShader GPU-PreSkinning use this.

        格式问题：
        override_byte_stride = 40
        override_vertex_count = 14325
        uav_byte_stride = 4
        由于这个格式并未添加到CommandList的解析中，所以没法单独写在CommandList里，只能写在TextureOverride下面
        所以我们这个VertexLimitRaise部分直接整体写入CommandList.ini中

        这个部分由于有一个Hash值，所以如果需要加密Mod并且让Hash值修复脚本能够运作的话，
        可以在最终制作完成Mod后，手动把这个VertexLimitRaise部分放到Config.ini中
        '''
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib
        if d3d11GameType.GPU_PreSkinning:
            vertexlimit_section = M_IniSection(M_SectionType.TextureOverrideVertexLimitRaise)
            

            vertexlimit_section_name_suffix =  draw_ib + "_" + draw_ib_model.draw_ib_alias + "_VertexLimitRaise"
            vertexlimit_section.append("[TextureOverride_" + vertexlimit_section_name_suffix + "]")
            vertexlimit_section.append("hash = " + draw_ib_model.import_config.vertex_limit_hash)
            


            vertexlimit_section.append("override_byte_stride = " + str(d3d11GameType.CategoryStrideDict["Position"]))
            vertexlimit_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))
            vertexlimit_section.append("uav_byte_stride = 4")
            vertexlimit_section.new_line()

            commandlist_ini_builder.append_section(vertexlimit_section)

    def add_unity_vs_resource_vb_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add Resource VB Section
        '''
        resource_vb_section = M_IniSection(M_SectionType.ResourceBuffer)
        
        buffer_folder_name = GlobalConfig.get_buffer_folder_name()
        
        unique_str = getattr(draw_ib_model, 'unique_str', "")
        
        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            if unique_str:
                resource_name = "Resource_" + unique_str.replace("-", "_") + "_" + category_name
                buf_filename = unique_str + "-" + category_name + ".buf"
            else:
                resource_name = "Resource" + draw_ib_model.draw_ib + category_name
                buf_filename = draw_ib_model.draw_ib + "-" + category_name + ".buf"
            
            resource_vb_section.append("[" + resource_name + "]")
            resource_vb_section.append("type = Buffer")
            resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + buf_filename)
            resource_vb_section.new_line()
        
        '''
        Add Resource IB Section

        We default use R32_UINT because R16_UINT have a very small number limit.
        '''

        for partname, ib_filename in draw_ib_model.PartName_IBBufferFileName_Dict.items():
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(partname,None)
            resource_vb_section.append("[" + ib_resource_name + "]")
            resource_vb_section.append("type = Buffer")
            resource_vb_section.append("format = DXGI_FORMAT_R32_UINT")
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + ib_filename)
            resource_vb_section.new_line()

        ini_builder.append_section(resource_vb_section)


    def add_resource_texture_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add texture resource.
        只有槽位风格贴图会用到，因为Hash风格贴图有专门的方法去声明这个。
        '''
        if Properties_GenerateMod.forbid_auto_texture_ini():
            return 
        
        resource_texture_section = M_IniSection(M_SectionType.ResourceTexture)
        for partname, texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.items():
            for texture_markup_info in texture_markup_info_list:
                if texture_markup_info.mark_type == "Slot":
                    resource_texture_section.append("[" + texture_markup_info.get_resource_name() + "]")
                    resource_texture_section.append("filename = Texture/" + texture_markup_info.mark_filename)
                    resource_texture_section.new_line()

        ini_builder.append_section(resource_texture_section)


    def add_unity_cs_texture_override_vb_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        # 声明TextureOverrideVB部分，只有使用GPU-PreSkinning时是直接替换hash对应槽位
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        if d3d11GameType.GPU_PreSkinning:
            texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
            texture_override_vb_section.append("; " + draw_ib )
            
            unique_str = getattr(draw_ib_model, 'unique_str', "")
            
            for category_name in d3d11GameType.OrderedCategoryNameList:
                category_hash = draw_ib_model.import_config.category_hash_dict[category_name]
                category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]
                texture_override_vb_namesuffix = "VB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + category_name

                if GlobalConfig.logic_name == LogicName.SRMI:
                    if category_name == "Position":
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "_VertexLimitRaise]")
                        texture_override_vb_section.append("override_byte_stride = " + str(d3d11GameType.CategoryStrideDict["Position"]))
                        texture_override_vb_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))
                        texture_override_vb_section.append("uav_byte_stride = 4")
                    else:
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                else:
                    texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                texture_override_vb_section.append("hash = " + category_hash)
                


                # 如果出现了VertexLimitRaise，Texcoord槽位需要检测filter_index才能替换
                filterindex_indent_prefix = ""
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                # 遍历获取所有在当前分类hash下进行替换的分类，并添加对应的资源替换
                for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                    if category_name == draw_category_name:
                        if original_category_name == "Position":
                            if unique_str:
                                texture_override_vb_section.append("cs-cb0 = Resource_" + unique_str.replace("-", "_") + "_VertexLimit")
                            else:
                                texture_override_vb_section.append("cs-cb0 = Resource_" + draw_ib + "_VertexLimit")

                            position_category_slot = d3d11GameType.CategoryExtractSlotDict["Position"]
                            blend_category_slot = d3d11GameType.CategoryExtractSlotDict["Blend"]
                            # print(position_category_slot)

                            if unique_str:
                                texture_override_vb_section.append(position_category_slot + " = Resource_" + unique_str.replace("-", "_") + "_Position")
                                texture_override_vb_section.append(blend_category_slot + " = Resource_" + unique_str.replace("-", "_") + "_Blend")
                            else:
                                texture_override_vb_section.append(position_category_slot + " = Resource" + draw_ib + "Position")
                                texture_override_vb_section.append(blend_category_slot + " = Resource" + draw_ib + "Blend")

                            texture_override_vb_section.append("handling = skip")

                            dispatch_number = int(math.ceil(draw_ib_model.draw_number / 64)) + 1
                            texture_override_vb_section.append("dispatch = " + str(dispatch_number) + ",1,1")
                        elif original_category_name != "Blend":
                            category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                            if unique_str:
                                resource_name = "Resource_" + unique_str.replace("-", "_") + "_" + original_category_name
                            else:
                                resource_name = "Resource" + draw_ib + original_category_name
                            texture_override_vb_section.append(filterindex_indent_prefix  + category_original_slot + " = " + resource_name)

                # 对应if vb0 == 3000的结束
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("endif")
                
                # 分支架构，如果是Position则需提供激活变量
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Position"]:
                    if len(self.branch_model.keyname_mkey_dict.keys()) != 0:
                        texture_override_vb_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")

                        if Properties_GenerateMod.generate_branch_mod_gui():
                            texture_override_vb_section.append("$ActiveCharacter = 1")

                texture_override_vb_section.new_line()
            config_ini_builder.append_section(texture_override_vb_section)
            
            
    def add_unity_cs_texture_override_ib_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib
        d3d11GameType = draw_ib_model.d3d11GameType

        unique_str = getattr(draw_ib_model, 'unique_str', "")
        
        if unique_str:
            for component_model in draw_ib_model._component_model_list:
                component_name = component_model.component_name
                first_index = getattr(component_model, 'first_index', 0)
                component_index = component_name.replace("Component ", "")
                
                style_part_name = "Component" + component_index
                ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(component_index, "")
                texture_override_ib_namesuffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name
                
                texture_override_ib_section.append("[TextureOverride_" + texture_override_ib_namesuffix + "]")
                texture_override_ib_section.append("hash = " + draw_ib)
                texture_override_ib_section.append("match_first_index = " + str(first_index))
                texture_override_ib_section.append("checktextureoverride = vb1")
                
                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                texture_override_ib_section.append(self.vlr_filter_index_indent + "handling = skip")

                ib_buf = draw_ib_model.componentname_ibbuf_dict.get(component_name, None)
                if ib_buf is None or len(ib_buf) == 0:
                    texture_override_ib_section.new_line()
                else:
                    if not d3d11GameType.GPU_PreSkinning:
                        for category_name in d3d11GameType.OrderedCategoryNameList:
                            category_hash = draw_ib_model.import_config.category_hash_dict[category_name]
                            category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]

                            for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                                if original_category_name == draw_category_name:
                                    category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                                    resource_name = "Resource_" + unique_str.replace("-", "_") + "_" + original_category_name
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + category_original_slot + " = " + resource_name)

                    texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)

                    if not Properties_GenerateMod.forbid_auto_texture_ini():
                        texture_markup_info_list = None
                        if component_model.final_ordered_draw_obj_model_list:
                            first_obj = component_model.final_ordered_draw_obj_model_list[0]
                            obj_full_name = f"{first_obj.draw_ib}-{first_obj.index_count}-{first_obj.first_index}"
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(obj_full_name, None)
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(component_index, None)
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get("1", None)
                        if texture_markup_info_list is not None:
                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_type == "Slot":
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

                    drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                    for drawindexed_str in drawindexed_str_list:
                        texture_override_ib_section.append(drawindexed_str)

                    if self.vlr_filter_index_indent != "":
                        texture_override_ib_section.append("endif")
                        texture_override_ib_section.new_line()
        else:
            for count_i,part_name in enumerate(draw_ib_model.import_config.part_name_list):
                match_first_index = draw_ib_model.import_config.match_first_index_list[count_i]

                style_part_name = "Component" + part_name
                ib_resource_name = "Resource_" + draw_ib + "_" + style_part_name
                texture_override_ib_namesuffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name
                
                texture_override_ib_section.append("[TextureOverride_" + texture_override_ib_namesuffix + "]")
                texture_override_ib_section.append("hash = " + draw_ib)
                texture_override_ib_section.append("match_first_index = " + match_first_index)
                texture_override_ib_section.append("checktextureoverride = vb1")
                
                # add slot check
                if not Properties_GenerateMod.forbid_auto_texture_ini():
                    texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                    # It may not have auto texture
                    if texture_markup_info_list is not None:
                        for texture_markup_info in texture_markup_info_list:

                            if texture_markup_info.mark_type == "Hash":
                                texture_override_ib_section.append("checktextureoverride = " + texture_markup_info.mark_slot)

                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                texture_override_ib_section.append(self.vlr_filter_index_indent + "handling = skip")


                # If ib buf is emprt, continue to avoid add ib resource replace.
                ib_buf = draw_ib_model.componentname_ibbuf_dict.get("Component " + part_name,None)
                if ib_buf is None or len(ib_buf) == 0:
                    texture_override_ib_section.new_line()
                    continue

                # 如果不使用GPU-Skinning即为Object类型，此时需要在ib上面替换对应槽位
                # 必须在ib上面替换，否则阴影不正确
                if not d3d11GameType.GPU_PreSkinning:
                    for category_name in d3d11GameType.OrderedCategoryNameList:
                        category_hash = draw_ib_model.import_config.category_hash_dict[category_name]
                        category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]

                        for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                            if original_category_name == draw_category_name:
                                category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                                texture_override_ib_section.append(self.vlr_filter_index_indent + category_original_slot + " = Resource" + draw_ib + original_category_name)



                # Add ib replace
                texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)

                # Add slot style texture slot replace.
                if not Properties_GenerateMod.forbid_auto_texture_ini():
                    texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                    # It may not have auto texture
                    if texture_markup_info_list is not None:
                        for texture_markup_info in texture_markup_info_list:
                            if texture_markup_info.mark_type == "Slot":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())


                

                # Component DrawIndexed输出
                component_name = "Component " + part_name 
                
                component_model = draw_ib_model.component_name_component_model_dict[component_name]
                drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                for drawindexed_str in drawindexed_str_list:
                    texture_override_ib_section.append(drawindexed_str)
 
                
                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("endif")
                    texture_override_ib_section.new_line()


        config_ini_builder.append_section(texture_override_ib_section)

    def add_unity_cs_resource_vb_sections(self,config_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        '''
        Add Resource VB Section (UnityCS)
        '''
        resource_vb_section = M_IniSection(M_SectionType.ResourceBuffer)
        
        buffer_folder_name = GlobalConfig.get_buffer_folder_name()
        
        unique_str = getattr(draw_ib_model, 'unique_str', "")
        
        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            if unique_str:
                resource_name = "Resource_" + unique_str.replace("-", "_") + "_" + category_name
                buf_filename = unique_str + "-" + category_name + ".buf"
            else:
                resource_name = "Resource" + draw_ib_model.draw_ib + category_name
                buf_filename = draw_ib_model.draw_ib + "-" + category_name + ".buf"
            
            resource_vb_section.append("[" + resource_name + "]")

            if draw_ib_model.d3d11GameType.GPU_PreSkinning:
                if category_name == "Position" or category_name == "Blend":
                    resource_vb_section.append("type = ByteAddressBuffer")
                else:
                    resource_vb_section.append("type = Buffer")
            else:
                resource_vb_section.append("type = Buffer")

            resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + buf_filename)
            resource_vb_section.new_line()
        
        # Add Resource IB Section
        # We default use R32_UINT because R16_UINT have a very small number limit.
        
        for partname, ib_filename in draw_ib_model.PartName_IBBufferFileName_Dict.items():
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(partname, None)
            resource_vb_section.append("[" + ib_resource_name + "]")
            resource_vb_section.append("type = Buffer")
            resource_vb_section.append("format = DXGI_FORMAT_R32_UINT")
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + ib_filename)
            resource_vb_section.new_line()
        
        config_ini_builder.append_section(resource_vb_section)
    
    def add_unity_cs_resource_vertexlimit(self,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        '''
        此部分由于顶点数变化后会刷新，应该写在CommandList.ini中
        '''
        resource_vertex_limit_section = M_IniSection(M_SectionType.ResourceBuffer)
        
        unique_str = getattr(draw_ib_model, 'unique_str', "")
        if unique_str:
            resource_name = "Resource_" + unique_str.replace("-", "_") + "_VertexLimit"
        else:
            resource_name = "Resource_" + draw_ib_model.draw_ib + "_VertexLimit"
        
        resource_vertex_limit_section.append("[" + resource_name + "]")
        resource_vertex_limit_section.append("type = Buffer")
        resource_vertex_limit_section.append("format = R32G32B32A32_UINT")
        resource_vertex_limit_section.append("data = " + str(draw_ib_model.draw_number) + " 0 0 0")
        resource_vertex_limit_section.new_line()

        commandlist_ini_builder.append_section(resource_vertex_limit_section)


    def add_unity_cs_vertex_shader_check(self,ini_builder:M_IniBuilder):
        print("add_unity_cs_vertex_shader_check::")
        vscheck_section = M_IniSection(M_SectionType.VertexShaderCheck)

        vs_hash_set = set()
        for draw_ib, draw_ib_model in self.drawib_drawibmodel_dict.items():
            for vs_hash in draw_ib_model.import_config.vshash_list:
                vs_hash_set.add(vs_hash)
        
        for vs_hash in vs_hash_set:
            print("VSHash: " + vs_hash)
            vscheck_section.append("[ShaderOverride_" + vs_hash + "]")
            vscheck_section.append("allow_duplicate_hash = overrule")
            vscheck_section.append("hash = " + vs_hash)
            vscheck_section.append("if $costume_mods")
            vscheck_section.append("  checktextureoverride = ib")
            vscheck_section.append("endif")
            vscheck_section.new_line()
        
        ini_builder.append_section(vscheck_section)


    def generate_unity_cs_config_ini(self):
        config_ini_builder = M_IniBuilder()
        
        M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)

        for draw_ib, draw_ib_model in self.drawib_drawibmodel_dict.items():

            # 按键开关与按键切换声明部分


            if GlobalConfig.logic_name != LogicName.SRMI:
                self.add_unity_vs_texture_override_vlr_section(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model) 
            self.add_unity_cs_texture_override_vb_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model) 
            self.add_unity_cs_texture_override_ib_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model) 

            # CommandList.ini
            self.add_unity_cs_resource_vertexlimit(commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            # Resource.ini
            self.add_unity_cs_resource_vb_sections(config_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_texture_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)

            M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        
        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        self.add_unity_cs_vertex_shader_check(ini_builder=config_ini_builder)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")
        
    def generate_unity_vs_config_ini(self):
        config_ini_builder = M_IniBuilder()

        M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)

        for draw_ib, draw_ib_model in self.drawib_drawibmodel_dict.items():

            # 按键开关与按键切换声明部分

        
            self.add_unity_vs_texture_override_vlr_section(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_unity_vs_texture_override_vb_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            self.add_unity_vs_texture_override_ib_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            self.add_unity_vs_resource_vb_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_texture_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)

            M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        M_IniHelper.add_shapekey_ini_sections(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")
