'''
ZZMI
'''
import math
import bpy
import os

from ..config.main_config import GlobalConfig, LogicName
from ..common.draw_ib_model import DrawIBModel
from ..base.m_global_key_counter import M_GlobalKeyCounter
from ..blueprint.blueprint_model import BluePrintModel
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


class ModModelZZMI:
    '''
    ZZMI生成Mod模板
    '''
    def __init__(self, skip_buffer_export:bool = False):
        # (1) 统计全局分支模型
        print("Initializing ModModelZZMI")
        self.branch_model = BluePrintModel()

        # (2) 抽象每个DrawIB为DrawIBModel
        self.drawib_drawibmodel_dict:dict[str,DrawIBModel] = {}
        self.parse_draw_ib_draw_ib_model_dict(skip_buffer_export)

        # (3) 这些属性用于ini生成
        self.vlr_filter_index_indent = ""
        self.texture_hash_filter_index_dict = {}

        # (4) 跨IB信息
        self.cross_ib_info_dict = self.branch_model.cross_ib_info_dict
        self.cross_ib_method_dict = self.branch_model.cross_ib_method_dict
        self.has_cross_ib = len(self.cross_ib_info_dict) > 0

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

    def parse_draw_ib_draw_ib_model_dict(self, skip_buffer_export:bool = False):
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
            
            draw_ib_model = DrawIBModel(draw_ib=draw_ib, branch_model=self.branch_model, unique_str=unique_str, skip_buffer_export=skip_buffer_export)
            self.drawib_drawibmodel_dict[draw_ib] = draw_ib_model
            
        
    def add_unity_vs_texture_override_vb_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        # 声明TextureOverrideVB部分，只有使用GPU-PreSkinning时是直接替换hash对应槽位
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        # 只有GPU-PreSkinning需要生成TextureOverrideVB部分，CPU类型不需要

        texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
        texture_override_vb_section.append("; " + draw_ib)
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
                    texture_override_vb_section.append(filterindex_indent_prefix + drawtype_indent_prefix + category_original_slot + " = Resource" + draw_ib + original_category_name)

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

    def add_unity_vs_texture_override_ib_sections(self,config_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib
        
        d3d11_game_type = draw_ib_model.d3d11GameType

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
                
                current_ib_key = f"{draw_ib}_{first_index}"
                is_cross_ib_source = current_ib_key in self.cross_ib_info_dict
                is_cross_ib_target = any(current_ib_key in targets for targets in self.cross_ib_info_dict.values())
                source_ib_list_for_target = []
                if is_cross_ib_target:
                    for source_ib, target_ib_list in self.cross_ib_info_dict.items():
                        if current_ib_key in target_ib_list:
                            source_ib_list_for_target.append(source_ib)
                
                if is_cross_ib_source:
                    texture_override_ib_section.append("[ResourceBodyVB_" + draw_ib + "_" + str(first_index) + "]")
                
                style_part_name = "Component" + component_index
                texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name
                
                ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(component_index, "")
                
                texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
                texture_override_ib_section.append("hash = " + draw_ib)
                texture_override_ib_section.append("match_first_index = " + str(first_index))
                
                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))
                
                if is_cross_ib_source:
                    texture_override_ib_section.append("ResourceBodyVB_" + draw_ib + "_" + str(first_index) + " = copy vb0")
                
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
                            print(f"调试: component_model.final_ordered_draw_obj_model_list count={len(component_model.final_ordered_draw_obj_model_list)}")
                            
                            for obj_model in component_model.final_ordered_draw_obj_model_list:
                                current_obj_full_name = f"{obj_model.draw_ib}-{obj_model.index_count}-{obj_model.first_index}"
                                print(f"调试: 检查分块 {current_obj_full_name}")
                                current_texture_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(current_obj_full_name, None)
                                if current_texture_list is not None:
                                    print(f"调试: 找到分块 {current_obj_full_name} 的材质信息")
                                    if texture_markup_info_list is None:
                                        texture_markup_info_list = []
                                    texture_markup_info_list.extend(current_texture_list)
                        
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(component_index, None)
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get("1", None)
                        print(f"调试: 最终 texture_markup_info_list={texture_markup_info_list}")
                        
                        if texture_markup_info_list is not None:
                            if GlobalConfig.logic_name == LogicName.ZZMI:
                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        if texture_markup_info.mark_name == "DiffuseMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            texture_override_ib_section.append("Resource\\ZZMI\\Diffuse = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "NormalMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            texture_override_ib_section.append("Resource\\ZZMI\\NormalMap = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "LightMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            texture_override_ib_section.append("Resource\\ZZMI\\LightMap = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "MaterialMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            texture_override_ib_section.append("Resource\\ZZMI\\MaterialMap = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "StockingMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            texture_override_ib_section.append("Resource\\ZZMI\\WengineFx = ref " + texture_markup_info.get_resource_name())
                                
                                texture_override_ib_section.append("run = CommandList\\ZZMI\\SetTextures")

                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        if texture_markup_info.mark_name == "DiffuseMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            pass
                                        elif texture_markup_info.mark_name == "NormalMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            pass
                                        elif texture_markup_info.mark_name == "LightMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            pass
                                        elif texture_markup_info.mark_name == "MaterialMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            pass
                                        elif texture_markup_info.mark_name == "StockingMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                            pass
                                        else:
                                            texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

                                texture_override_ib_section.append("run = CommandListSkinTexture")
                            else:
                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())
                    
                    if is_cross_ib_source:
                        non_cross_ib_objects = []
                        for obj_model in component_model.final_ordered_draw_obj_model_list:
                            obj_name = obj_model.obj_name
                            if obj_name not in self.branch_model.cross_ib_object_names:
                                non_cross_ib_objects.append(obj_model)
                        
                        drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(non_cross_ib_objects)
                        for drawindexed_str in drawindexed_str_list:
                            texture_override_ib_section.append(drawindexed_str)
                    else:
                        drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                        for drawindexed_str in drawindexed_str_list:
                            texture_override_ib_section.append(drawindexed_str)
                    
                    if is_cross_ib_target and source_ib_list_for_target:
                        for source_ib_key in source_ib_list_for_target:
                            source_parts = source_ib_key.split("_")
                            source_hash = source_parts[0]
                            source_first_index = int(source_parts[1]) if len(source_parts) > 1 else 0
                            source_ib_model = self.drawib_drawibmodel_dict.get(source_hash)
                            source_component_model = None
                            if source_ib_model:
                                for comp_model in source_ib_model._component_model_list:
                                    if getattr(comp_model, 'first_index', 0) == source_first_index:
                                        source_component_model = comp_model
                                        break
                            
                            if source_component_model:
                                target_first_index = first_index
                                target_ib_resource_name = None
                                for part_idx, ib_res_name in draw_ib_model.PartName_IBResourceName_Dict.items():
                                    texture_override_ib_section.append("ib = " + ib_resource_name)
                                    break
                                
                                texture_override_ib_section.append("vb0 = ResourceBodyVB_" + source_hash + "_" + str(source_first_index))
                                texture_override_ib_section.append("vb1 = Resource" + source_hash + "Texcoord")
                                texture_override_ib_section.append("vb2 = Resource" + source_hash + "Blend")
                                texture_override_ib_section.append("vb3 = ResourceBodyVB_" + source_hash + "_" + str(source_first_index))
                                
                                cross_ib_objects = []
                                for obj_model in source_component_model.final_ordered_draw_obj_model_list:
                                    obj_name = obj_model.obj_name
                                    if obj_name in self.branch_model.cross_ib_object_names:
                                        cross_ib_objects.append(obj_model)
                                
                                if cross_ib_objects:
                                    drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(cross_ib_objects)
                                    for drawindexed_str in drawindexed_str_list:
                                        texture_override_ib_section.append(drawindexed_str)
                    
                    if self.vlr_filter_index_indent:
                        texture_override_ib_section.append("endif")
                        texture_override_ib_section.new_line()
        else:
            for count_i,part_name in enumerate(draw_ib_model.import_config.part_name_list):
                match_first_index = draw_ib_model.import_config.match_first_index_list[count_i]
                style_part_name = "Component" + part_name
                texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name

                ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(part_name,"")
                
                component_index = count_i + 1
                current_ib_key = f"{draw_ib}_{component_index}"
                
                is_cross_ib_source = current_ib_key in self.cross_ib_info_dict
                is_cross_ib_target = any(current_ib_key in targets for targets in self.cross_ib_info_dict.values())
                source_ib_list_for_target = []
                if is_cross_ib_target:
                    for source_ib, target_ib_list in self.cross_ib_info_dict.items():
                        if current_ib_key in target_ib_list:
                            source_ib_list_for_target.append(source_ib)
                
                if is_cross_ib_source and count_i == 0:
                    for source_ib_key in [current_ib_key]:
                        source_hash = source_ib_key.split("_")[0]
                        texture_override_ib_section.append("[ResourceBodyVB_" + source_hash + "]")

                texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
                texture_override_ib_section.append("hash = " + draw_ib)
                texture_override_ib_section.append("match_first_index = " + match_first_index)

                if self.vlr_filter_index_indent != "":
                    texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                if is_cross_ib_source:
                    texture_override_ib_section.append("ResourceBodyVB_" + draw_ib + " = copy vb0")

                ib_buf = draw_ib_model.componentname_ibbuf_dict.get("Component " + part_name,None)
                if ib_buf is None or len(ib_buf) == 0:
                    texture_override_ib_section.append("ib = null")
                    texture_override_ib_section.new_line()
                    continue

                texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)

                print("Test: ZZZ")
                if GlobalConfig.logic_name == LogicName.ZZMI:
                    if not Properties_GenerateMod.forbid_auto_texture_ini():
                        texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                        if texture_markup_info_list is not None:
                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_type == "Slot":
                                    if texture_markup_info.mark_name == "DiffuseMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        texture_override_ib_section.append("Resource\\ZZMI\\Diffuse = ref " + texture_markup_info.get_resource_name())
                                    elif texture_markup_info.mark_name == "NormalMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        texture_override_ib_section.append("Resource\\ZZMI\\NormalMap = ref " + texture_markup_info.get_resource_name())
                                    elif texture_markup_info.mark_name == "LightMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        texture_override_ib_section.append("Resource\\ZZMI\\LightMap = ref " + texture_markup_info.get_resource_name())
                                    elif texture_markup_info.mark_name == "MaterialMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        texture_override_ib_section.append("Resource\\ZZMI\\MaterialMap = ref " + texture_markup_info.get_resource_name())
                                    elif texture_markup_info.mark_name == "StockingMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        texture_override_ib_section.append("Resource\\ZZMI\\WengineFx = ref " + texture_markup_info.get_resource_name())
                            
                            texture_override_ib_section.append("run = CommandList\\ZZMI\\SetTextures")

                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_type == "Slot":
                                    if texture_markup_info.mark_name == "DiffuseMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        pass
                                    elif texture_markup_info.mark_name == "NormalMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        pass
                                    elif texture_markup_info.mark_name == "LightMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        pass
                                    elif texture_markup_info.mark_name == "MaterialMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        pass
                                    elif texture_markup_info.mark_name == "StockingMap" and Properties_GenerateMod.zzz_use_slot_fix():
                                        pass
                                    else:
                                        texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

                    texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                    if texture_markup_info_list is not None:
                        texture_override_ib_section.append("run = CommandListSkinTexture")
                else:
                    if not Properties_GenerateMod.forbid_auto_texture_ini():
                        texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                        if texture_markup_info_list is not None:
                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_type == "Slot":
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

                component_name = "Component " + part_name
                component_model = draw_ib_model.component_name_component_model_dict[component_name]

                if is_cross_ib_source:
                    non_cross_ib_objects = []
                    for obj_model in component_model.final_ordered_draw_obj_model_list:
                        obj_name = obj_model.obj_name
                        if obj_name not in self.branch_model.cross_ib_object_names:
                            non_cross_ib_objects.append(obj_model)
                    
                    drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(non_cross_ib_objects)
                    for drawindexed_str in drawindexed_str_list:
                        texture_override_ib_section.append(drawindexed_str)
                else:
                    drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
                    for drawindexed_str in drawindexed_str_list:
                        texture_override_ib_section.append(drawindexed_str)
                
                if is_cross_ib_target and source_ib_list_for_target:
                    for source_ib_key in source_ib_list_for_target:
                        source_hash, source_component_index = source_ib_key.split("_")
                        source_component_index = int(source_component_index)
                        source_ib_model = self.drawib_drawibmodel_dict.get(source_hash)
                        source_component_model = None
                        if source_ib_model:
                            if source_component_index <= len(source_ib_model.import_config.part_name_list):
                                src_part_name = source_ib_model.import_config.part_name_list[source_component_index - 1]
                                src_component_name = "Component " + src_part_name
                                if src_component_name in source_ib_model.component_name_component_model_dict:
                                    source_component_model = source_ib_model.component_name_component_model_dict[src_component_name]
                        
                        if source_component_model:
                            source_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get(part_name, "")
                            texture_override_ib_section.append("ib = " + source_ib_resource_name)
                            texture_override_ib_section.append("vb0 = ResourceBodyVB_" + source_hash)
                            texture_override_ib_section.append("vb1 = Resource" + source_hash + "Texcoord")
                            texture_override_ib_section.append("vb2 = Resource" + source_hash + "Blend")
                            texture_override_ib_section.append("vb3 = ResourceBodyVB_" + source_hash)
                            
                            cross_ib_objects = []
                            for obj_model in source_component_model.final_ordered_draw_obj_model_list:
                                obj_name = obj_model.obj_name
                                if obj_name in self.branch_model.cross_ib_object_names:
                                    cross_ib_objects.append(obj_model)
                            
                            if cross_ib_objects:
                                drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(cross_ib_objects)
                                for drawindexed_str in drawindexed_str_list:
                                    texture_override_ib_section.append(drawindexed_str)

                if self.vlr_filter_index_indent:
                    texture_override_ib_section.append("endif")
                    texture_override_ib_section.new_line()
            
        config_ini_builder.append_section(texture_override_ib_section)

    def add_vertex_limit_raise_section(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        '''
        格式:
        override_byte_stride = 40
        override_vertex_count = 14325
        uav_byte_stride = 4
        '''
        if draw_ib_model.d3d11GameType.GPU_PreSkinning:
            vertexlimit_section = M_IniSection(M_SectionType.TextureOverrideVertexLimitRaise)

            vertexlimit_section_name_suffix =  draw_ib_model.draw_ib + "_" + draw_ib_model.draw_ib_alias + "_VertexLimitRaise"
            vertexlimit_section.append("[TextureOverride_" + vertexlimit_section_name_suffix + "]")
            vertexlimit_section.append("hash = " + draw_ib_model.import_config.vertex_limit_hash)
            vertexlimit_section.append("override_byte_stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict["Position"]))
            vertexlimit_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))
            vertexlimit_section.append("uav_byte_stride = 4")
            vertexlimit_section.new_line()

            commandlist_ini_builder.append_section(vertexlimit_section)

    def add_resource_buffer_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        resource_buffer_section = M_IniSection(M_SectionType.ResourceBuffer)
        
        buffer_folder_name = GlobalConfig.get_buffer_folder_name()

        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            resource_buffer_section.append("[Resource" + draw_ib_model.draw_ib + category_name + "]")
            resource_buffer_section.append("type = Buffer")
            resource_buffer_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            resource_buffer_section.append("filename = " + buffer_folder_name + "/" + draw_ib_model.draw_ib + "-" + category_name + ".buf")
            resource_buffer_section.new_line()
        
        for partname, ib_filename in draw_ib_model.PartName_IBBufferFileName_Dict.items():
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(partname,None)
            resource_buffer_section.append("[" + ib_resource_name + "]")
            resource_buffer_section.append("type = Buffer")
            resource_buffer_section.append("format = DXGI_FORMAT_R32_UINT")
            resource_buffer_section.append("filename = " + buffer_folder_name + "/" + ib_filename)
            resource_buffer_section.new_line()

        ini_builder.append_section(resource_buffer_section)


    def add_resource_slot_texture_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
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


    def generate_unity_vs_config_ini(self):
        config_ini_builder = M_IniBuilder()
        
        if self.has_cross_ib:
            for node_name, cross_ib_method in self.cross_ib_method_dict.items():
                if cross_ib_method != 'VB_COPY':
                    print(f"[CrossIB] 警告: 节点 {node_name} 使用的跨 IB 方式 '{cross_ib_method}' 不适用于 ZZMI 模式")
                    print(f"[CrossIB] ZZMI 模式只支持 'VB_COPY' (VB 复制) 方式")
                    self.has_cross_ib = False
                    break

        M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        
        for draw_ib_model in self.drawib_drawibmodel_dict.values():
        
            self.add_vertex_limit_raise_section(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_unity_vs_texture_override_vb_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_unity_vs_texture_override_ib_sections(config_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_buffer_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_slot_texture_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)
            M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        M_IniHelper.add_shapekey_ini_sections(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")
