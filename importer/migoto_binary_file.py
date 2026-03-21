from .fmt_file import FMTFile

from ..utils.format_utils import FormatUtils
from ..utils.format_utils import Fatal
from ..utils.log_utils import LOG

import os
import numpy
import json


class ConfigTabsHelper:
    _tabs_config_loaded: bool = False
    _drawib_tabs_config: list = []

    @classmethod
    def load_tabs_config(cls, workspace_path: str):
        if cls._tabs_config_loaded:
            return
        cls._tabs_config_loaded = True
        try:
            tabs_folder = os.path.join(workspace_path, "Config", "Tabs")
            print(f"[ConfigTabsHelper] 工作空间路径: {workspace_path}")
            print(f"[ConfigTabsHelper] Tabs 文件夹路径: {tabs_folder}")
            
            if not os.path.exists(tabs_folder):
                print(f"[ConfigTabsHelper] Tabs 文件夹不存在: {tabs_folder}")
                return
            
            json_files = [f for f in os.listdir(tabs_folder) if f.endswith('.json')]
            print(f"[ConfigTabsHelper] 发现 {len(json_files)} 个配置文件: {json_files}")
            
            for json_file in json_files:
                json_path = os.path.join(tabs_folder, json_file)
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    extract_panel_tab = config.get("extractPanelTab", "")
                    print(f"[ConfigTabsHelper] 文件 {json_file}, extractPanelTab={extract_panel_tab}")
                    
                    if extract_panel_tab and extract_panel_tab.lower() == "drawib":
                        tab_name = os.path.splitext(json_file)[0]
                        model_rows = config.get("modelRows", [])
                        
                        draw_ib_to_alias = {}
                        for row in model_rows:
                            if isinstance(row, dict):
                                draw_ib = row.get("drawIB", "")
                                alias_name = row.get("aliasName", "")
                                if draw_ib:
                                    draw_ib_to_alias[draw_ib] = alias_name if alias_name else draw_ib
                        
                        if draw_ib_to_alias:
                            cls._drawib_tabs_config.append({
                                "tab_name": tab_name,
                                "draw_ib_to_alias": draw_ib_to_alias,
                                "config_file": json_file
                            })
                            print(f"[ConfigTabsHelper] 加载分组配置: {tab_name}, 包含 {len(draw_ib_to_alias)} 个 IB: {list(draw_ib_to_alias.keys())}")
                    
                except Exception as e:
                    print(f"[ConfigTabsHelper] 读取配置文件失败 {json_file}: {e}")
            
            print(f"[ConfigTabsHelper] 共加载 {len(cls._drawib_tabs_config)} 个有效分组配置")
        except Exception as e:
            print(f"[ConfigTabsHelper] 加载 Tabs 配置失败: {e}")

    @classmethod
    def get_drawib_tabs_config(cls) -> list:
        return cls._drawib_tabs_config

    @classmethod
    def reset(cls):
        cls._tabs_config_loaded = False
        cls._drawib_tabs_config = []


class ConfigAliasHelper:
    _drawib_alias_cache: dict = {}
    _config_loaded: bool = False

    @classmethod
    def load_config_alias(cls, workspace_path: str):
        if cls._config_loaded:
            return
        cls._config_loaded = True
        try:
            config_path = os.path.join(workspace_path, "Config.json")
            if os.path.exists(config_path):
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_list = json.load(f)
                if isinstance(config_list, list):
                    for item in config_list:
                        if isinstance(item, dict):
                            draw_ib = item.get("DrawIB", "")
                            alias = item.get("Alias", "")
                            if draw_ib and alias:
                                cls._drawib_alias_cache[draw_ib] = alias
                print(f"[ConfigAliasHelper] 加载 Config.json 完成，共 {len(cls._drawib_alias_cache)} 个别名映射")
        except Exception as e:
            print(f"[ConfigAliasHelper] 读取 Config.json 失败: {e}")

    @classmethod
    def get_alias(cls, draw_ib: str) -> str:
        return cls._drawib_alias_cache.get(draw_ib, "")

    @classmethod
    def apply_alias_to_mesh_name(cls, mesh_name: str) -> str:
        if not mesh_name or "." not in mesh_name:
            return mesh_name
        parts = mesh_name.split(".", 1)
        prefix_part = parts[0]
        prefix_split = prefix_part.split("-")
        if len(prefix_split) < 1:
            return mesh_name
        draw_ib = prefix_split[0]
        alias = cls.get_alias(draw_ib)
        if alias:
            return f"{prefix_part}.{alias}"
        return mesh_name


class MigotoBinaryFile:

    '''
    3Dmigoto模型文件

    暂时还没有更好的设计，暂时先沿用旧的ib vb fmt设计
    
    prefix是前缀，比如Body.ib Body.vb Body.fmt 那么此时Body就是prefix
    location_folder_path是存放这些文件的文件夹路径，比如当前工作空间中提取的对应数据类型文件夹

    '''
    def __init__(self, fmt_path:str, mesh_name:str = ""):
        self.fmt_file = FMTFile(fmt_path)
        print("fmt_path: " + fmt_path)
        location_folder_path = os.path.dirname(fmt_path)
        print("location_folder_path: " + location_folder_path)

        if self.fmt_file.prefix == "":
            self.fmt_file.prefix = os.path.basename(fmt_path).split(".fmt")[0]

        if mesh_name == "":
            self.mesh_name = self.fmt_file.prefix
        else:
            self.mesh_name = mesh_name
        
        self._apply_config_alias()

        print("prefix: " + self.fmt_file.prefix)
        self.init_from_prefix(self.fmt_file.prefix, location_folder_path)

    def _apply_config_alias(self):
        try:
            from ..config.main_config import GlobalConfig
            workspace_path = GlobalConfig.path_workspace_folder()
            ConfigAliasHelper.load_config_alias(workspace_path)
            self.mesh_name = ConfigAliasHelper.apply_alias_to_mesh_name(self.mesh_name)
        except Exception as e:
            print(f"[MigotoBinaryFile] 应用 Config.json 别名失败: {e}")

    def init_from_prefix(self,prefix:str, location_folder_path:str):

        self.fmt_name = prefix + ".fmt"
        self.vb_name = prefix + ".vb"
        self.ib_name = prefix + ".ib"

        self.location_folder_path = location_folder_path

        self.vb_bin_path = os.path.join(location_folder_path, self.vb_name)
        self.ib_bin_path = os.path.join(location_folder_path, self.ib_name)
        self.fmt_path = os.path.join(location_folder_path, self.fmt_name)

        self.file_sanity_check()

        self.vb_file_size = os.path.getsize(self.vb_bin_path)
        self.ib_file_size = os.path.getsize(self.ib_bin_path)

        self.init_data()

    def init_data(self):
        ib_stride = FormatUtils.format_size(self.fmt_file.format)

        self.ib_count = int(self.ib_file_size / ib_stride)
        self.ib_polygon_count = int(self.ib_count / 3)
        self.ib_data = numpy.fromfile(self.ib_bin_path, dtype=FormatUtils.get_nptype_from_format(self.fmt_file.format), count=self.ib_count)
        
        # 读取fmt文件，解析出后面要用的dtype
        fmt_dtype = self.fmt_file.get_dtype()
        vb_stride = fmt_dtype.itemsize

        self.vb_vertex_count = int(self.vb_file_size / vb_stride)
        self.vb_data = numpy.fromfile(self.vb_bin_path, dtype=fmt_dtype, count=self.vb_vertex_count)

    
    def file_sanity_check(self):
        '''
        检查对应文件是否存在，不存在则抛出异常
        三个文件，必须都存在，缺一不可
        '''
        if not os.path.exists(self.vb_bin_path):
            raise Fatal("Unable to find matching .vb file for : " + self.mesh_name)
        if not os.path.exists(self.ib_bin_path):
            raise Fatal("Unable to find matching .ib file for : " + self.mesh_name)
        # if not os.path.exists(self.fmt_path):
        #     raise Fatal("Unable to find matching .fmt file for : " + self.mesh_name)

    def file_size_check(self) -> bool:
        '''
        检查.ib和.vb文件是否为空，如果为空则弹出错误提醒信息，但不报错。
        '''
        # 如果vb和ib文件不存在，则跳过导入
        # 我们不能直接抛出异常，因为有些.ib文件是空的占位文件
        if self.vb_file_size == 0:
            LOG.warning("Current Import " + self.vb_name +" file is empty, skip import.")
            return False
        
        if self.ib_file_size == 0:
            LOG.warning("Current Import " + self.ib_name + " file is empty, skip import.")
            return False
        
        return True