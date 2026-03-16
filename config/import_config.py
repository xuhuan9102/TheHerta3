import os 
import json
import bpy
import json
import math
import bmesh
import os


from typing import List, Dict, Union, Optional
from dataclasses import dataclass, field, asdict

from ..utils.json_utils import JsonUtils
from ..utils.format_utils import Fatal

from .main_config import GlobalConfig

from ..base.d3d11_gametype import D3D11GameType


def check_and_try_generate_import_json() -> dict:
    '''
    检查 Import.json 是否存在，如果不存在则尝试自动生成
    返回 draw_ib_gametypename_dict
    '''
    workspace_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(), "Import.json")
    
    if os.path.exists(workspace_import_json_path):
        return JsonUtils.LoadFromFile(workspace_import_json_path)
    
    print("Import.json 不存在，尝试自动生成...")
    
    from ..utils.config_utils import ConfigUtils
    
    draw_ib_gametypename_dict = {}
    
    current_workspace_folder = GlobalConfig.path_workspace_folder()
    
    # 扫描工作空间中所有文件夹，支持 SSMT3 和 SSMT4 格式
    try:
        all_folders = [f.name for f in os.scandir(current_workspace_folder) if f.is_dir()]
    except Exception as e:
        raise Fatal(f"无法读取工作空间文件夹: {str(e)}\n请确保已在SSMT中正确配置工作空间。")
    
    for folder_name in all_folders:
        folder_path = os.path.join(current_workspace_folder, folder_name)
        
        # 跳过非 DrawIB 文件夹
        if not os.path.exists(os.path.join(folder_path, "tmp.json")) and not os.path.exists(os.path.join(folder_path, "import.json")):
            # 检查是否有 TYPE_ 子文件夹
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
        
        # 判断是 SSMT3 还是 SSMT4 格式
        if "-" in folder_name:
            # SSMT4 格式：DrawIB-IndexCount-FirstIndex
            # 使用完整的文件夹名作为键
            draw_ib_key = folder_name
        else:
            # SSMT3 格式：DrawIB
            draw_ib_key = folder_name
        
        # 查找 TYPE_ 文件夹
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
            # 优先读取 import.json
            import_json_path = os.path.join(type_folder_path, "import.json")
            if os.path.exists(import_json_path):
                try:
                    import_json = JsonUtils.LoadFromFile(import_json_path)
                    work_game_type = import_json.get("WorkGameType", "")
                    if work_game_type:
                        draw_ib_gametypename_dict[draw_ib_key] = work_game_type
                        print(f"自动检测到 DrawIB {draw_ib_key} 的数据类型: {work_game_type} (从 import.json)")
                        break
                except Exception as e:
                    print(f"读取 {import_json_path} 失败: {e}")
                    continue
            
            # 回退到读取 tmp.json
            tmp_json_path = os.path.join(type_folder_path, "tmp.json")
            if os.path.exists(tmp_json_path):
                try:
                    tmp_json = ConfigUtils.read_tmp_json(type_folder_path)
                    work_game_type = tmp_json.get("WorkGameType", "")
                    if work_game_type:
                        draw_ib_gametypename_dict[draw_ib_key] = work_game_type
                        print(f"自动检测到 DrawIB {draw_ib_key} 的数据类型: {work_game_type} (从 tmp.json)")
                        break
                except Exception as e:
                    print(f"读取 {tmp_json_path} 失败: {e}")
                    continue
    
    if draw_ib_gametypename_dict:
        JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict, filepath=workspace_import_json_path)
        print(f"已自动生成 Import.json: {workspace_import_json_path}")
    else:
        print("警告: 无法自动生成 Import.json，没有找到有效的提取数据")
    
    return draw_ib_gametypename_dict


def check_tmp_json_exists(draw_ib: str, gametypename: str, unique_str: str = "") -> tuple[bool, str, Optional[str]]:
    '''
    检查 tmp.json 是否存在
    返回: (是否存在, 错误信息, 找到的tmp.json路径)
    '''
    if not gametypename:
        workspace_folder = GlobalConfig.path_workspace_folder()
        print(f"调试: 工作空间文件夹: {workspace_folder}")
        print(f"调试: draw_ib: {draw_ib}")
        print(f"调试: unique_str: {unique_str}")
        
        # 优先尝试 SSMT4 格式（unique_str: DrawIB-IndexCount-FirstIndex）
        if unique_str:
            draw_ib_folder = os.path.join(workspace_folder, unique_str)
            print(f"调试: 尝试 SSMT4 文件夹: {draw_ib_folder}")
            if os.path.exists(draw_ib_folder):
                dirs = os.listdir(draw_ib_folder)
                found_types = []
                for dirname in dirs:
                    if dirname.startswith("TYPE_"):
                        type_folder = os.path.join(draw_ib_folder, dirname)
                        tmp_json_path = os.path.join(type_folder, "tmp.json")
                        if os.path.exists(tmp_json_path):
                            found_types.append(dirname.replace("TYPE_", ""))
                
                if found_types:
                    return False, f"DrawIB '{unique_str}' 找到以下数据类型但没有在 Import.json 中记录: {', '.join(found_types)}\n请尝试重新执行「一键导入当前工作空间内容」操作。", None
        
        # 回退到 SSMT3 格式（draw_ib）
        draw_ib_folder = os.path.join(workspace_folder, draw_ib)
        print(f"调试: 尝试 SSMT3 文件夹: {draw_ib_folder}")
        
        if os.path.exists(draw_ib_folder):
            dirs = os.listdir(draw_ib_folder)
            found_types = []
            for dirname in dirs:
                if dirname.startswith("TYPE_"):
                    type_folder = os.path.join(draw_ib_folder, dirname)
                    tmp_json_path = os.path.join(type_folder, "tmp.json")
                    if os.path.exists(tmp_json_path):
                        found_types.append(dirname.replace("TYPE_", ""))
            
            if found_types:
                return False, f"DrawIB '{draw_ib}' 找到以下数据类型但没有在 Import.json 中记录: {', '.join(found_types)}\n请尝试重新执行「一键导入当前工作空间内容」操作。", None
        
        # 自动检测 SSMT4 格式文件夹（DrawIB-IndexCount-FirstIndex）
        # 扫描工作空间中所有以 draw_ib 开头的文件夹
        try:
            all_folders = [f.name for f in os.scandir(workspace_folder) if f.is_dir()]
            ssmt4_folders = [f for f in all_folders if f.startswith(draw_ib + "-")]
            print(f"调试: 找到的 SSMT4 文件夹: {ssmt4_folders}")
            
            if ssmt4_folders:
                for folder_name in ssmt4_folders:
                    folder_path = os.path.join(workspace_folder, folder_name)
                    dirs = os.listdir(folder_path)
                    for dirname in dirs:
                        if dirname.startswith("TYPE_"):
                            type_folder = os.path.join(folder_path, dirname)
                            tmp_json_path = os.path.join(type_folder, "tmp.json")
                            print(f"调试: 检查 tmp.json: {tmp_json_path}")
                            if os.path.exists(tmp_json_path):
                                print(f"调试: 找到 tmp.json: {tmp_json_path}")
                                return True, "", tmp_json_path
        except Exception as e:
            print(f"自动检测 SSMT4 文件夹时出错: {e}")
        
        return False, f"DrawIB '{draw_ib}' 没有找到对应的提取数据。\n请确保已从游戏中提取模型并执行「一键导入当前工作空间内容」操作。", None
    
    # 优先尝试 SSMT4 格式
    if unique_str:
        extract_gametype_folder_path = os.path.join(GlobalConfig.path_workspace_folder(), unique_str, "TYPE_" + gametypename)
        tmp_json_path = os.path.join(extract_gametype_folder_path, "tmp.json")
        if os.path.exists(tmp_json_path):
            return True, "", tmp_json_path
    
    # 回退到 SSMT3 格式
    extract_gametype_folder_path = GlobalConfig.path_extract_gametype_folder(draw_ib=draw_ib, gametype_name=gametypename)
    tmp_json_path = os.path.join(extract_gametype_folder_path, "tmp.json")
    
    if os.path.exists(tmp_json_path):
        return True, "", tmp_json_path
    
    return False, f"找不到 tmp.json 文件: {tmp_json_path}\n请确保已从游戏中提取模型并执行「一键导入当前工作空间内容」操作。", None

@dataclass
class TextureMarkUpInfo:
    mark_name:str = field(default="",init=False)
    mark_type:str = field(default="",init=False)
    mark_hash:str = field(default="",init=False)
    mark_slot:str = field(default="",init=False)
    mark_filename:str = field(default="",init=False)
    
    def get_resource_name(self):
        return "Resource-" + self.mark_filename.split(".")[0]
    
    def get_hash_style_filename(self):
        return self.mark_hash + "-" + self.mark_name + "." + self.mark_filename.split(".")[1]

@dataclass
class ImportConfig:
    '''
    在一键导入工作空间时，Import.json会记录导入的GameType，在生成Mod时需要用到
    所以这里我们读取Import.json来确定要从哪个提取出来的数据类型文件夹中读取
    然后读取tmp.json来初始化D3D11GameType
    '''
    draw_ib: str  # DrawIB
    unique_str: str = ""  # SSMT4 模式下的唯一标识符（DrawIB-IndexCount-FirstIndex）
    
    # 使用field(default_factory)来初始化可变默认值
    category_hash_dict: Dict[str, str] = field(init=False,default_factory=dict)
    import_model_list: List[str] = field(init=False,default_factory=list)
    match_first_index_list: List[int] = field(init=False,default_factory=list)
    part_name_list: List[str] = field(init=False,default_factory=list)
    vshash_list: List[str] = field(init=False,default_factory=list)
    
    vertex_limit_hash: str = ""
    work_game_type: str = ""
    
    # 全新的贴图标记设计
    partname_texturemarkinfolist_dict:Dict[str,list[TextureMarkUpInfo]] = field(init=False,default_factory=dict)

    def __post_init__(self):
        draw_ib_gametypename_dict = check_and_try_generate_import_json()
        
        # 优先使用第四代识别（SSMT4 格式：DrawIB-IndexCount-FirstIndex）
        # 如果找不到，回退到第三代识别（SSMT3 格式：DrawIB）
        gametypename = ""
        actual_folder_name = self.draw_ib  # 默认使用 draw_ib 作为文件夹名
        
        if self.unique_str:
            gametypename = draw_ib_gametypename_dict.get(self.unique_str, "")
            if gametypename:
                print(f"使用第四代识别（SSMT4格式）: {self.unique_str} -> {gametypename}")
                actual_folder_name = self.unique_str  # SSMT4 格式下使用 unique_str 作为文件夹名
        
        if not gametypename:
            gametypename = draw_ib_gametypename_dict.get(self.draw_ib, "")

        # 根据实际文件夹名构建路径
        extract_gametype_folder_path = os.path.join(GlobalConfig.path_workspace_folder(), actual_folder_name, "TYPE_" + gametypename)
        self.extract_gametype_folder_path = extract_gametype_folder_path
        
        # 优先读取 import.json（SSMT4 格式），如果不存在则回退到 tmp.json（SSMT3 格式）
        import_json_path = os.path.join(extract_gametype_folder_path, "import.json")
        tmp_json_path = os.path.join(extract_gametype_folder_path, "tmp.json")
        
        if os.path.exists(import_json_path):
            tmp_json_path = import_json_path
        else:
            pass
        
        from ..blueprint.blueprint_export_helper import BlueprintExportHelper
        datatype_node_info_list = BlueprintExportHelper.get_datatype_node_info()
        
        matched_datatype_node_info = None
        if datatype_node_info_list:
            for node_info in datatype_node_info_list:
                node = node_info["node"]
                if node.is_draw_ib_matched(self.draw_ib):
                    matched_datatype_node_info = node_info
                    print(f"找到匹配的数据类型节点，DrawIB: {self.draw_ib}, 节点: {node.name}")
                    break
        
        if not os.path.exists(tmp_json_path):
            exists, error_msg, found_path = check_tmp_json_exists(self.draw_ib, gametypename, self.unique_str)
            if not exists:
                raise Fatal(error_msg)
            if found_path:
                tmp_json_path = found_path
                # 从找到的 tmp.json 路径中提取 gametype 和文件夹名
                # 路径格式: workspace/folder_name/TYPE_gametype/tmp.json
                path_parts = tmp_json_path.replace('/', os.sep).split(os.sep)
                print(f"调试: 找到的 tmp.json 路径: {tmp_json_path}")
                print(f"调试: 路径分割后: {path_parts}")
                if len(path_parts) >= 2:
                    type_folder = path_parts[-2]  # TYPE_gametype
                    if type_folder.startswith("TYPE_"):
                        gametypename = type_folder[5:]  # 去掉 "TYPE_" 前缀
                        actual_folder_name = path_parts[-3]  # 文件夹名
                        self.extract_gametype_folder_path = os.path.join(GlobalConfig.path_workspace_folder(), actual_folder_name, type_folder)
                        print(f"调试: 工作空间文件夹: {GlobalConfig.path_workspace_folder()}")
                        print(f"调试: 实际文件夹名: {actual_folder_name}")
                        print(f"调试: 类型文件夹: {type_folder}")
                        print(f"调试: 构建的路径: {self.extract_gametype_folder_path}")
                        print(f"自动检测到 SSMT4 文件夹: {actual_folder_name}, 数据类型: {gametypename}")
        
        if matched_datatype_node_info and matched_datatype_node_info.get("tmp_json_path") and os.path.exists(matched_datatype_node_info["tmp_json_path"]):
            with open(tmp_json_path, 'r', encoding='utf-8') as f:
                base_tmp_json_dict = json.load(f)
            with open(matched_datatype_node_info["tmp_json_path"], 'r', encoding='utf-8') as f:
                datatype_tmp_json_dict = json.load(f)
            
            print(f"调试: base_tmp_json_dict 键列表 = {list(base_tmp_json_dict.keys())}")
            print(f"调试: datatype_tmp_json_dict 键列表 = {list(datatype_tmp_json_dict.keys())}")
            
            if "D3D11ElementList" in datatype_tmp_json_dict:
                base_tmp_json_dict["D3D11ElementList"] = datatype_tmp_json_dict["D3D11ElementList"]
                print(f"使用数据类型节点的 D3D11ElementList 覆盖原始配置")
            
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                json.dump(base_tmp_json_dict, f, indent=2, ensure_ascii=False)
                merged_tmp_json_path = f.name
            
            self.d3d11GameType:D3D11GameType = D3D11GameType(merged_tmp_json_path)
            tmp_json_dict = base_tmp_json_dict
            
            try:
                os.unlink(merged_tmp_json_path)
            except:
                pass
        else:
            self.d3d11GameType:D3D11GameType = D3D11GameType(tmp_json_path)
            tmp_json_dict = JsonUtils.LoadFromFile(tmp_json_path)
        
        '''
        读取tmp.json中的内容，后续会用于生成Mod的ini文件
        需要在确定了D3D11GameType之后再执行
        注意：这里使用已经确定的 tmp_json_dict
        '''
        self.category_hash_dict = tmp_json_dict["CategoryHash"]
        self.import_model_list = tmp_json_dict["ImportModelList"]
        self.match_first_index_list = tmp_json_dict["MatchFirstIndex"]
        self.part_name_list = tmp_json_dict["PartNameList"]
        # print(self.partname_textureresourcereplace_dict)
        self.vertex_limit_hash = tmp_json_dict["VertexLimitVB"]
        self.work_game_type = tmp_json_dict["WorkGameType"]
        self.vshash_list = tmp_json_dict.get("VSHashList",[])
        self.original_vertex_count = tmp_json_dict.get("OriginalVertexCount",0)

        # 自动贴图依赖于这个字典
        partname_texturemarkupinfolist_jsondict = tmp_json_dict.get("ComponentTextureMarkUpInfoListDict", {})

        for partname, texture_markup_info_dict_list in partname_texturemarkupinfolist_jsondict.items():
            texture_markup_info_list = []

            for texture_markup_info_dict in texture_markup_info_dict_list:
                markup_info = TextureMarkUpInfo()
                markup_info.mark_name = texture_markup_info_dict["MarkName"]
                markup_info.mark_type = texture_markup_info_dict["MarkType"]
                markup_info.mark_slot = texture_markup_info_dict["MarkSlot"]
                markup_info.mark_hash = texture_markup_info_dict["MarkHash"]
                markup_info.mark_filename = texture_markup_info_dict["MarkFileName"]

                texture_markup_info_list.append(markup_info)

            self.partname_texturemarkinfolist_dict[partname] = texture_markup_info_list





                


                


