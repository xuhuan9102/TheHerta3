"""
SSMT4工具模块

提供第四代SSMT4格式的检测和处理功能：
- SSMT4Utils: SSMT4格式检测和Import.json生成工具类
- ImportConfigHelper: Import.json配置读取辅助类

SSMT格式说明：
- SSMT3（第三代）：文件夹结构为 DrawIB/TYPE_xxx/
- SSMT4（第四代）：文件夹结构为 DrawIB-IndexCount-FirstIndex/TYPE_xxx/
"""
import os
import json
from typing import Optional, Dict

from ..config.main_config import GlobalConfig
from ..utils.json_utils import JsonUtils
from ..utils.config_utils import ConfigUtils


class SSMT4Utils:
    """
    SSMT4格式工具类
    
    提供SSMT4格式的检测、Import.json生成等功能
    """
    SSMT4_FOLDER_PREFIX_PATTERN = "-"
    
    @staticmethod
    def check_and_try_generate_import_json() -> Dict[str, str]:
        """
        检查Import.json是否存在，如果不存在则尝试自动生成
        
        Returns:
            Dict[str, str]: draw_ib到游戏类型名称的映射字典
        """
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
            
            has_type_folder = SSMT4Utils._has_type_subfolder(folder_path)
            if not has_type_folder:
                continue
            
            draw_ib_key = folder_name
            
            type_folders = SSMT4Utils._get_type_folders(folder_path)
            
            for type_folder_path in type_folders:
                game_type = SSMT4Utils._extract_game_type_from_folder(type_folder_path)
                if game_type:
                    draw_ib_gametypename_dict[draw_ib_key] = game_type
                    break
        
        if draw_ib_gametypename_dict:
            JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict, filepath=workspace_import_json_path)
        
        return draw_ib_gametypename_dict
    
    @staticmethod
    def find_ssmt4_unique_str(draw_ib: str, draw_ib_gametypename_dict: Dict[str, str]) -> str:
        """
        查找SSMT4格式的unique_str
        
        Args:
            draw_ib: DrawIB名称
            draw_ib_gametypename_dict: draw_ib到游戏类型的映射字典
            
        Returns:
            str: SSMT4格式的unique_str，如果不是SSMT4格式则返回空字符串
        """
        workspace_folder = GlobalConfig.path_workspace_folder()
        
        if draw_ib in draw_ib_gametypename_dict:
            return ""
        
        try:
            all_folders = [f.name for f in os.scandir(workspace_folder) if f.is_dir()]
            ssmt4_folders = [f for f in all_folders if f.startswith(draw_ib + SSMT4Utils.SSMT4_FOLDER_PREFIX_PATTERN)]
            
            if ssmt4_folders:
                for folder_name in ssmt4_folders:
                    if folder_name in draw_ib_gametypename_dict:
                        return folder_name
                    
                    folder_path = os.path.join(workspace_folder, folder_name)
                    if SSMT4Utils._has_type_subfolder(folder_path):
                        return folder_name
        except Exception as e:
            print(f"查找 SSMT4 文件夹时出错: {e}")
        
        return ""
    
    @staticmethod
    def is_ssmt4_format(folder_name: str) -> bool:
        """检查文件夹名称是否符合SSMT4格式（包含至少两个连字符）"""
        if not folder_name:
            return False
        parts = folder_name.split("-")
        return len(parts) >= 3
    
    @staticmethod
    def parse_ssmt4_folder_name(folder_name: str) -> Optional[Dict[str, str]]:
        """
        解析SSMT4格式的文件夹名称

        Args:
            folder_name: SSMT4格式的文件夹名称，如 "DrawIB-IndexCount-FirstIndex"

        Returns:
            包含draw_ib、index_count、first_index、unique_str的字典，如果不是SSMT4格式则返回None
        """
        if not SSMT4Utils.is_ssmt4_format(folder_name):
            return None

        parts = folder_name.split("-")
        if len(parts) >= 3:
            return {
                "draw_ib": parts[0],
                "index_count": parts[1],
                "first_index": parts[2],
                "unique_str": folder_name
            }
        return None
    
    @staticmethod
    def is_ssmt4_object_name(obj_name: str) -> bool:
        """
        检测物体名称是否符合SSMT4格式

        Args:
            obj_name: 物体名称

        Returns:
            bool: 如果符合SSMT4格式则返回True，否则返回False
        """
        if not obj_name:
            return False
        
        # 检查是否包含至少两个连字符
        parts = obj_name.split("-")
        if len(parts) < 3:
            return False
        
        # 检查是否包含点分隔符（可选）
        if "." in obj_name:
            prefix_part = obj_name.split(".", 1)[0]
            parts = prefix_part.split("-")
            return len(parts) >= 3
        
        return True
    
    @staticmethod
    def detect_export_mode_by_object_names(object_names: list) -> bool:
        """
        根据物体名称检测导出模式

        Args:
            object_names: 物体名称列表

        Returns:
            bool: 如果检测到SSMT4格式的物体名称则返回True，否则返回False
        """
        if not object_names:
            return False
        
        # 检查是否有任何物体名称符合SSMT4格式
        for obj_name in object_names:
            if SSMT4Utils.is_ssmt4_object_name(obj_name):
                return True
        
        return False
    
    @staticmethod
    def _has_type_subfolder(folder_path: str) -> bool:
        """检查文件夹是否包含TYPE_开头的子文件夹"""
        try:
            subdirs = os.listdir(folder_path)
            for subdir in subdirs:
                if subdir.startswith("TYPE_"):
                    return True
        except:
            pass
        return False
    
    @staticmethod
    def _get_type_folders(folder_path: str) -> list:
        """获取TYPE_开头的子文件夹列表，优先返回GPU类型"""
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
        
        return gpu_folders + cpu_folders
    
    @staticmethod
    def _extract_game_type_from_folder(type_folder_path: str) -> str:
        """从TYPE文件夹中提取游戏类型名称"""
        import_json_path = os.path.join(type_folder_path, "import.json")
        if os.path.exists(import_json_path):
            try:
                import_json = JsonUtils.LoadFromFile(import_json_path)
                work_game_type = import_json.get("WorkGameType", "")
                if work_game_type:
                    return work_game_type
            except Exception:
                pass
        
        tmp_json_path = os.path.join(type_folder_path, "tmp.json")
        if os.path.exists(tmp_json_path):
            try:
                tmp_json = ConfigUtils.read_tmp_json(type_folder_path)
                work_game_type = tmp_json.get("WorkGameType", "")
                if work_game_type:
                    return work_game_type
            except Exception:
                pass
        
        return ""


class ImportConfigHelper:
    """
    Import.json配置读取辅助类
    
    提供缓存机制，避免重复读取Import.json文件
    """
    _cache: Dict[str, dict] = {}
    
    @classmethod
    def get_import_config(cls, unique_str: str) -> dict:
        """获取指定unique_str的import.json配置"""
        if unique_str in cls._cache:
            return cls._cache[unique_str]
        
        import_json_path = cls._get_import_json_path(unique_str)
        if import_json_path and os.path.exists(import_json_path):
            config = JsonUtils.LoadFromFile(import_json_path)
            cls._cache[unique_str] = config
            return config
        
        return {}
    
    @classmethod
    def get_category_hash_dict(cls, unique_str: str) -> dict:
        """获取分类哈希字典"""
        config = cls.get_import_config(unique_str)
        return dict(config.get("CategoryHash", {}))
    
    @classmethod
    def get_part_name_list(cls, unique_str: str) -> list:
        """获取部件名称列表"""
        config = cls.get_import_config(unique_str)
        return list(config.get("PartNameList", []))
    
    @classmethod
    def get_match_first_index_list(cls, unique_str: str) -> list:
        """获取匹配的首索引列表"""
        config = cls.get_import_config(unique_str)
        return list(config.get("MatchFirstIndex", []))
    
    @classmethod
    def get_vertex_limit_hash(cls, unique_str: str) -> str:
        """获取顶点限制哈希值"""
        config = cls.get_import_config(unique_str)
        return config.get("VertexLimitVB", "")
    
    @classmethod
    def get_original_vertex_count(cls, unique_str: str) -> int:
        """获取原始顶点数量"""
        config = cls.get_import_config(unique_str)
        return config.get("OriginalVertexCount", 0)
    
    @classmethod
    def clear_cache(cls):
        """清除缓存"""
        cls._cache.clear()
    
    @classmethod
    def _get_import_json_path(cls, unique_str: str) -> Optional[str]:
        """获取import.json文件的完整路径"""
        if not unique_str:
            return None
        
        workspace_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(), "Import.json")
        if not os.path.exists(workspace_import_json_path):
            return None
        
        workspace_import_json = JsonUtils.LoadFromFile(workspace_import_json_path)
        game_type_name = workspace_import_json.get(unique_str, "")
        
        if not game_type_name:
            return None
        
        return os.path.join(
            GlobalConfig.path_workspace_folder(),
            unique_str,
            f"TYPE_{game_type_name}",
            "import.json"
        )
