from dataclasses import dataclass, field
import os


class M_DrawIndexed:
    def __init__(self) -> None:
        self.DrawNumber = ""
        self.DrawOffsetIndex = "" 
        self.DrawStartIndex = "0"
        self.AliasName = "" 
        self.UniqueVertexCount = 0 
    
    def get_draw_str(self) -> str:
        return "drawindexed = " + self.DrawNumber + "," + self.DrawOffsetIndex + "," + self.DrawStartIndex

@dataclass
class M_DrawIndexedInstanced:
    IndexCountPerInstance: int = field(init=False, repr=False, default=0)
    InstanceCount: int = field(init=False, repr=False, default=0)
    StartIndexLocation: int = field(init=False, repr=False, default=0)
    BaseVertexLocation: int = field(init=False, repr=False, default=0)
    StartInstanceLocation: int = field(init=False, repr=False, default=0)

    def get_draw_str(self) -> str:
        draw_str = "drawindexedinstanced = "
        draw_str += str(self.IndexCountPerInstance) + ","
        if self.InstanceCount == 0:
            draw_str += "INSTANCE_COUNT,"
        else:
            draw_str += str(self.InstanceCount) + ","
        draw_str += str(self.StartIndexLocation) + ","
        draw_str += str(self.BaseVertexLocation) + ","
        if self.StartInstanceLocation == 0:
            draw_str += "FIRST_INSTANCE"
        else:
            draw_str += str(self.StartInstanceLocation)
        return draw_str

class M_Condition:
    def __init__(self, work_key_list: list = []):
        self.work_key_list = work_key_list
        condition_str = ""
        if len(self.work_key_list) != 0:
            for work_key in self.work_key_list:
                single_condition: str = work_key.key_name + " == " + str(work_key.tmp_value)
                condition_str = condition_str + single_condition + " && "
            condition_str = condition_str[:-4]
        self.condition_str = condition_str

class ObjRuleName:
    _drawib_alias_cache: dict = {}
    _config_loaded: bool = False

    @classmethod
    def _load_config_alias(cls):
        if cls._config_loaded:
            return
        cls._config_loaded = True
        try:
            from ...config.main_config import GlobalConfig
            workspace_path = GlobalConfig.path_workspace_folder()
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
        except Exception as e:
            print(f"[ObjRuleName] 读取 Config.json 失败: {e}")

    def __init__(self, obj_name: str, strict_mode: bool = True):
        self.obj_name = obj_name
        self.draw_ib = ""
        self.index_count = ""
        self.first_index = ""
        self.obj_alias_name = ""
        self.strict_mode = strict_mode
        
        if strict_mode:
            self.objname_parse_error_tips = (
                "Obj名称规则为: DrawIB-IndexCount-FirstIndex.AliasName,例如[67f829fc-2653-0.头发]\n"
                "第一个.前面的内容要符合规则,后面出现的内容是可以自定义的\n"
                "提示: 如果你使用的是第三代格式(DrawIB-Component.Alias)，请关闭 'SSMT4 Alpha测试' 选项"
            )
        else:
            self.objname_parse_error_tips = (
                "Obj名称规则为: DrawIB-Component.AliasName,例如[67f829fc-1.头发]\n"
                "第一个.前面的内容要符合规则,后面出现的内容是可以自定义的"
            )
        
        self._parse_obj_name()

        self._try_apply_config_alias()
    
    def _parse_obj_name(self):
        import re
        
        if "." in self.obj_name:
            obj_name_total_split = self.obj_name.split(".", 1)
            prefix_part = obj_name_total_split[0]
            
            if len(obj_name_total_split) < 2:
                if self.strict_mode:
                    raise Exception("Obj名称解析错误: " + self.obj_name + "  不包含'.'分隔符\n" + self.objname_parse_error_tips)
                else:
                    self.obj_alias_name = ""
            else:
                self.obj_alias_name = obj_name_total_split[1]
            
            normalized_prefix = re.sub(r'[(_\[\{]', '-', prefix_part)
            obj_name_split = normalized_prefix.split("-")
            non_empty_parts = [p for p in obj_name_split if p.strip()]
            
            if self.strict_mode:
                if len(non_empty_parts) < 3:
                    raise Exception("Obj名称解析错误: " + self.obj_name + "  '-'分隔符数量不足，至少需要2个\n" + self.objname_parse_error_tips + f"\n解析后的部分: {non_empty_parts}")
                else:
                    self.draw_ib = non_empty_parts[0]
                    self.index_count = non_empty_parts[1]
                    self.first_index = non_empty_parts[2]
            else:
                if len(non_empty_parts) >= 2:
                    self.draw_ib = non_empty_parts[0]
                    self.index_count = non_empty_parts[1]
                    self.first_index = non_empty_parts[2] if len(non_empty_parts) >= 3 else "0"
                elif len(non_empty_parts) >= 1:
                    self.draw_ib = non_empty_parts[0]
                    self.index_count = "0"
                    self.first_index = "0"
                else:
                    if self.strict_mode:
                        raise Exception("Obj名称解析错误: " + self.obj_name + "  无法解析\n" + self.objname_parse_error_tips)
        else:
            normalized_prefix = re.sub(r'[(_\[\{]', '-', self.obj_name)
            obj_name_split = normalized_prefix.split("-")
            non_empty_parts = [p for p in obj_name_split if p.strip()]
            
            if self.strict_mode:
                raise Exception("Obj名称解析错误: " + self.obj_name + "  不包含'.'分隔符\n" + self.objname_parse_error_tips)
            else:
                if len(non_empty_parts) >= 2:
                    self.draw_ib = non_empty_parts[0]
                    self.index_count = non_empty_parts[1]
                    self.first_index = non_empty_parts[2] if len(non_empty_parts) >= 3 else "0"
                elif len(non_empty_parts) >= 1:
                    self.draw_ib = non_empty_parts[0]
                    self.index_count = "0"
                    self.first_index = "0"
                else:
                    raise Exception("Obj名称解析错误: " + self.obj_name + "  无法解析\n" + self.objname_parse_error_tips)

    def _try_apply_config_alias(self):
        if not self.draw_ib:
            return
        ObjRuleName._load_config_alias()
        config_alias = ObjRuleName._drawib_alias_cache.get(self.draw_ib)
        if config_alias:
            self.obj_alias_name = config_alias

@dataclass
class DrawCallModel:
    obj_name: str
    match_draw_ib: str = field(init=False, repr=False, default="")
    match_index_count: str = field(init=False, repr=False, default="")
    match_first_index: str = field(init=False, repr=False, default="")
    comment_alias_name: str = field(init=False, repr=False, default="")
    display_name: str = field(init=False, repr=False, default="")
    condition: M_Condition = field(init=False, repr=False, default_factory=M_Condition)
    index_count: int = field(init=False, repr=False, default=0)
    vertex_count: int = field(init=False, repr=False, default=0)
    index_offset: int = field(init=False, repr=False, default=0)
    _skip_auto_parse: bool = field(init=False, repr=False, default=False)
    _strict_mode: bool = field(init=False, repr=False, default=None)

    def __post_init__(self):
        if self._skip_auto_parse:
            self.display_name = self.obj_name
            return
        
        strict_mode = self._strict_mode
        if strict_mode is None:
            try:
                from ...config.properties_import_model import Properties_ImportModel
                strict_mode = Properties_ImportModel.use_ssmt4()
            except Exception:
                strict_mode = True
        
        try:
            obj_rule_name = ObjRuleName(self.obj_name, strict_mode=strict_mode)
            self.match_draw_ib = obj_rule_name.draw_ib
            self.match_index_count = obj_rule_name.index_count
            self.match_first_index = obj_rule_name.first_index
            self.comment_alias_name = obj_rule_name.obj_alias_name
            self.display_name = self.obj_name
        except Exception as e:
            print(f"[DrawCallModel] 物体名称解析失败: {self.obj_name}, 错误: {e}")
            self.display_name = self.obj_name

    def set_draw_info(self, draw_ib: str, index_count: str = "", first_index: str = "", alias_name: str = ""):
        self.match_draw_ib = draw_ib
        self.match_index_count = index_count
        self.match_first_index = first_index
        self.comment_alias_name = alias_name
    
    def get_unique_str(self) -> str:
        return self.match_draw_ib + "-" + self.match_index_count + "-" + self.match_first_index
