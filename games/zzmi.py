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
from ..helper.ssmt4_utils import SSMT4Utils


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

    def parse_draw_ib_draw_ib_model_dict(self, skip_buffer_export:bool = False):
        '''
        根据obj的命名规则，推导出DrawIB并抽象为DrawIBModel
        支持第三代(SSMT3)和第四代(SSMT4)格式
        
        第三代格式：物体名称为 DrawIB-Component.Alias，文件夹结构为 DrawIB/TYPE_xxx/
        第四代格式：物体名称为 DrawIB-IndexCount-FirstIndex.Alias，文件夹结构为 DrawIB-IndexCount-FirstIndex/TYPE_xxx/
        '''
        draw_ib_gametypename_dict = SSMT4Utils.check_and_try_generate_import_json()
        
        for draw_ib in self.branch_model.draw_ib__component_count_list__dict.keys():
            unique_str = SSMT4Utils.find_ssmt4_unique_str(draw_ib, draw_ib_gametypename_dict)
            
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
                
                print(f"[CrossIB ZZMI] SSMT4: current_ib_key={current_ib_key}, is_source={is_cross_ib_source}, is_target={is_cross_ib_target}")
                if self.has_cross_ib:
                    print(f"[CrossIB ZZMI] cross_ib_info_dict keys: {list(self.cross_ib_info_dict.keys())}")
                
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
                            
                            if unique_str:
                                texture_lookup_key = f"{draw_ib}-{first_obj.index_count}-{first_obj.first_index}"
                                print(f"调试: SSMT4 模式，构建查找 key: {texture_lookup_key}")
                                
                                if texture_lookup_key not in draw_ib_model.import_config.partname_texturemarkinfolist_dict:
                                    for key in draw_ib_model.import_config.partname_texturemarkinfolist_dict.keys():
                                        if key.startswith(draw_ib + "-") and str(first_obj.first_index) in key:
                                            texture_lookup_key = key
                                            print(f"调试: 使用模糊匹配找到 key: {texture_lookup_key}")
                                            break
                            else:
                                texture_lookup_key = f"{first_obj.draw_ib}-{first_obj.index_count}-{first_obj.first_index}"
                                print(f"调试: SSMT3 模式，构建查找 key: {texture_lookup_key}")
                            
                            print(f"调试: is_ssmt4={first_obj.is_ssmt4}")
                            print(f"调试: partname_texturemarkinfolist_dict keys={list(draw_ib_model.import_config.partname_texturemarkinfolist_dict.keys())}")
                            print(f"调试: component_model.final_ordered_draw_obj_model_list count={len(component_model.final_ordered_draw_obj_model_list)}")
                            
                            found_texture_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(texture_lookup_key, None)
                            if found_texture_list is not None:
                                print(f"调试: 找到分块 {texture_lookup_key} 的材质信息")
                                texture_markup_info_list = found_texture_list
                        
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(component_index, None)
                        if texture_markup_info_list is None:
                            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get("1", None)
                        print(f"调试: 最终 texture_markup_info_list={texture_markup_info_list}")
                        
                        if texture_markup_info_list is not None:
                            added_texture_resources = set()
                            if GlobalConfig.logic_name == LogicName.ZZMI and Properties_GenerateMod.zzz_use_slot_fix():
                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        resource_name = texture_markup_info.get_resource_name()
                                        if resource_name not in added_texture_resources:
                                            added_texture_resources.add(resource_name)
                                            if texture_markup_info.mark_name == "DiffuseMap":
                                                texture_override_ib_section.append("Resource\\ZZMI\\Diffuse = ref " + resource_name)
                                            elif texture_markup_info.mark_name == "NormalMap":
                                                texture_override_ib_section.append("Resource\\ZZMI\\NormalMap = ref " + resource_name)
                                            elif texture_markup_info.mark_name == "LightMap":
                                                texture_override_ib_section.append("Resource\\ZZMI\\LightMap = ref " + resource_name)
                                            elif texture_markup_info.mark_name == "MaterialMap":
                                                texture_override_ib_section.append("Resource\\ZZMI\\MaterialMap = ref " + resource_name)
                                            elif texture_markup_info.mark_name == "StockingMap":
                                                texture_override_ib_section.append("Resource\\ZZMI\\WengineFx = ref " + resource_name)
                                
                                texture_override_ib_section.append("run = CommandList\\ZZMI\\SetTextures")

                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        resource_name = texture_markup_info.get_resource_name()
                                        if resource_name not in added_texture_resources:
                                            added_texture_resources.add(resource_name)
                                            if texture_markup_info.mark_name in ["DiffuseMap", "NormalMap", "LightMap", "MaterialMap", "StockingMap"]:
                                                pass
                                            else:
                                                texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + resource_name)

                                texture_override_ib_section.append("run = CommandListSkinTexture")
                            else:
                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        resource_name = texture_markup_info.get_resource_name()
                                        if resource_name not in added_texture_resources:
                                            added_texture_resources.add(resource_name)
                                            texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + resource_name)
                    
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
                                source_component_index = source_component_model.component_name.replace("Component ", "")
                                source_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get(source_component_index, "")
                                texture_override_ib_section.append("ib = " + source_ib_resource_name)
                                
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
                
                print(f"[CrossIB ZZMI] SSMT3: current_ib_key={current_ib_key}, is_source={is_cross_ib_source}, is_target={is_cross_ib_target}")
                if self.has_cross_ib:
                    print(f"[CrossIB ZZMI] cross_ib_info_dict keys: {list(self.cross_ib_info_dict.keys())}")
                
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
                            if Properties_GenerateMod.zzz_use_slot_fix():
                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        if texture_markup_info.mark_name == "DiffuseMap":
                                            texture_override_ib_section.append("Resource\\ZZMI\\Diffuse = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "NormalMap":
                                            texture_override_ib_section.append("Resource\\ZZMI\\NormalMap = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "LightMap":
                                            texture_override_ib_section.append("Resource\\ZZMI\\LightMap = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "MaterialMap":
                                            texture_override_ib_section.append("Resource\\ZZMI\\MaterialMap = ref " + texture_markup_info.get_resource_name())
                                        elif texture_markup_info.mark_name == "StockingMap":
                                            texture_override_ib_section.append("Resource\\ZZMI\\WengineFx = ref " + texture_markup_info.get_resource_name())
                            
                                texture_override_ib_section.append("run = CommandList\\ZZMI\\SetTextures")

                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
                                        if texture_markup_info.mark_name in ["DiffuseMap", "NormalMap", "LightMap", "MaterialMap", "StockingMap"]:
                                            pass
                                        else:
                                            texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())
                            else:
                                for texture_markup_info in texture_markup_info_list:
                                    if texture_markup_info.mark_type == "Slot":
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
                            source_ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get(src_part_name, "")
                            texture_override_ib_section.append("ib = " + source_ib_resource_name)
                            texture_override_ib_section.append("vb0 = ResourceBodyVB_" + source_hash + "_" + str(source_component_index))
                            texture_override_ib_section.append("vb1 = Resource" + source_hash + "Texcoord")
                            texture_override_ib_section.append("vb2 = Resource" + source_hash + "Blend")
                            texture_override_ib_section.append("vb3 = ResourceBodyVB_" + source_hash + "_" + str(source_component_index))
                            
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
        
        unique_str = getattr(draw_ib_model, 'unique_str', "")

        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            if unique_str:
                resource_name = "Resource_" + unique_str.replace("-", "_") + "_" + category_name
                buf_filename = unique_str + "-" + category_name + ".buf"
            else:
                resource_name = "Resource" + draw_ib_model.draw_ib + category_name
                buf_filename = draw_ib_model.draw_ib + "-" + category_name + ".buf"
            resource_buffer_section.append("[" + resource_name + "]")
            resource_buffer_section.append("type = Buffer")
            resource_buffer_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            resource_buffer_section.append("filename = " + buffer_folder_name + "/" + buf_filename)
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
        added_resource_names = set()
        
        for partname, texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.items():
            for texture_markup_info in texture_markup_info_list:
                if texture_markup_info.mark_type == "Slot":
                    resource_name = texture_markup_info.get_resource_name()
                    if resource_name not in added_resource_names:
                        added_resource_names.add(resource_name)
                        resource_texture_section.append("[" + resource_name + "]")
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
