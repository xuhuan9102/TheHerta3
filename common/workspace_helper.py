from ..config.main_config import GlobalConfig
from ..utils.json_utils import JsonUtils
import os

from typing import List, Dict, Union
from dataclasses import dataclass, field, asdict

@dataclass
class DedupedTextureInfo:
    original_hash:str = field(default="",init=False)
    render_hash:str = field(default="",init=False)
    format:str = field(default="",init=False)
    componet_count_list_str:str = field(default="",init=False)


class WorkSpaceHelper:

    @staticmethod
    def find_json_file_in_marktexture_folder(filename_pattern: str, draw_ib: str) -> str:
        '''
        在 Config/MarkTexture 文件夹下递归查找匹配的 JSON 文件
        优先查找文件名包含 draw_ib 的文件，否则返回第一个匹配的文件
        '''
        workspace_folder = GlobalConfig.path_workspace_folder()
        marktexture_folder = os.path.join(workspace_folder, "Config", "MarkTexture")
        
        if not os.path.exists(marktexture_folder):
            print(f"MarkTexture 文件夹不存在: {marktexture_folder}")
            return ""
        
        matching_files = []
        draw_ib_matching_files = []
        
        for root, dirs, files in os.walk(marktexture_folder):
            for file in files:
                if filename_pattern in file and file.endswith(".json"):
                    full_path = os.path.join(root, file)
                    matching_files.append(full_path)
                    if draw_ib in file:
                        draw_ib_matching_files.append(full_path)
        
        if draw_ib_matching_files:
            print(f"找到匹配 draw_ib 的文件: {draw_ib_matching_files[0]}")
            return draw_ib_matching_files[0]
        
        if matching_files:
            print(f"使用默认文件: {matching_files[0]}")
            return matching_files[0]
        
        print(f"未找到匹配的文件: {filename_pattern}")
        return ""

    @staticmethod
    def get_hash_deduped_texture_info_dict(draw_ib:str) -> Dict[str,DedupedTextureInfo]:

        workspace_folder = GlobalConfig.path_workspace_folder()
        
        component_name__drawcall_indexlist_json_path = WorkSpaceHelper.find_json_file_in_marktexture_folder(
            "ComponentName_DrawCallIndexList", draw_ib
        )
        trianglelist_deduped_filename_json_path = WorkSpaceHelper.find_json_file_in_marktexture_folder(
            "TrianglelistDedupedFileName", draw_ib
        )
        
        if not component_name__drawcall_indexlist_json_path or not trianglelist_deduped_filename_json_path:
            print(f"无法找到必要的贴图标记文件，跳过哈希贴图生成")
            return {}

        component_name__drawcall_indexlist_json_dict = JsonUtils.LoadFromFile(component_name__drawcall_indexlist_json_path)

        drawcall_component_count_dict = {}
        for component_name, drawcall_indexlist in component_name__drawcall_indexlist_json_dict.items():
            parts = component_name.split(" ")
            if len(parts) >= 2:
                component_count = parts[1]
            else:
                component_count = parts[0] if parts else ""
            
            for drawcall_index in drawcall_indexlist:
                if component_count:
                    drawcall_component_count_dict[drawcall_index] = component_count

        trianglelist_deduped_filename_json_dict = JsonUtils.LoadFromFile(trianglelist_deduped_filename_json_path)


        deduped_filename_drawcall_index_list_dict = {}
        for trianglelist_deduped_filename,deduped_kv_dict in trianglelist_deduped_filename_json_dict.items():
            deduped_filename:str = deduped_kv_dict["FALogDedupedFileName"]
            draw_call_index:str = trianglelist_deduped_filename[0:6]

            drawcall_index_list = deduped_filename_drawcall_index_list_dict.get(deduped_filename,[])
            if draw_call_index not in drawcall_index_list:
                drawcall_index_list.append(draw_call_index)

            deduped_filename_drawcall_index_list_dict[deduped_filename] = drawcall_index_list

        hash_deduped_texture_info_dict = {}

        for deduped_filename, drawcall_index_list in deduped_filename_drawcall_index_list_dict.items():
            used_component_count_list = []

            original_hash = deduped_filename.split("_")[0]
            render_hash = deduped_filename.split("_")[1].split("-")[0]

            # 从类似于 "b7ff7a6e_03d46264-R8G8B8A8_UNORM_SRGB.dds" 的文件名中
            # 提取出 "R8G8B8A8_UNORM_SRGB" 部分：
            # - 去掉扩展名
            # - 找到第一个下划线 `_` 的位置
            # - 从该下划线之后查找第一个连字符 `-`，并取其后到文件名末尾的子串
            # - 如果找不到上述模式，则退回到以最后一个 `-` 分割并取最后一段的策略
            base_name = os.path.splitext(deduped_filename)[0]
            fmt = ""
            try:
                first_underscore = base_name.find("_")
                if first_underscore != -1:
                    dash_after_underscore = base_name.find("-", first_underscore + 1)
                    if dash_after_underscore != -1:
                        fmt = base_name[dash_after_underscore + 1:]
                # fallback: use last '-' part
                if not fmt:
                    if "-" in base_name:
                        fmt = base_name.rsplit("-", 1)[-1]
                    else:
                        # as ultimate fallback, if there is an underscore then maybe format is after the second underscore
                        parts = base_name.split("_")
                        if len(parts) > 2:
                            fmt = parts[-1]
                        else:
                            fmt = ""
                # strip any stray whitespace
                fmt = fmt.strip()
            except Exception:
                fmt = ""

            format = fmt

            print(format)

            for draw_call_index in drawcall_index_list:
                matched_component_count = drawcall_component_count_dict.get(draw_call_index,"")
                if matched_component_count != "":
                    if matched_component_count not in used_component_count_list:
                        used_component_count_list.append(matched_component_count)

            used_component_count_list.sort()
            # print(used_component_count_list)

            

            componet_count_list_str = ""
            for unique_component_count_str in used_component_count_list:
                componet_count_list_str = componet_count_list_str + unique_component_count_str + "."

            deduped_texture_info = DedupedTextureInfo()
            deduped_texture_info.original_hash = original_hash
            deduped_texture_info.render_hash = render_hash
            deduped_texture_info.format = format
            deduped_texture_info.componet_count_list_str = componet_count_list_str

            hash_deduped_texture_info_dict[original_hash] = deduped_texture_info
    
        return hash_deduped_texture_info_dict