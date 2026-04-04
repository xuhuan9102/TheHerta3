from .m_condition import M_Condition
from .m_draw_indexed import M_DrawIndexed

from ..utils.log_utils import LOG

from dataclasses import dataclass, field

@dataclass
class ObjDataModel:
    obj_name:str
    display_name:str = field(init=False,repr=False,default="")

    component_count:int = field(init=False,repr=False,default=0)
    draw_ib:str = field(init=False,repr=False,default="")
    obj_alias_name:str = field(init=False,repr=False)

    ib:list = field(init=False,repr=False,default_factory=list)
    category_buffer_dict:dict = field(init=False,repr=False,default_factory=dict)

    index_vertex_id_dict:dict = field(init=False,repr=False,default_factory=dict) 

    condition:M_Condition = field(init=False,repr=False,default_factory=M_Condition)
    drawindexed_obj:M_DrawIndexed = field(init=False,repr=False,default_factory=M_DrawIndexed)

    index_count:int = field(init=False,repr=False,default=0)
    vertex_count:int = field(init=False,repr=False,default=0)
    first_index:int = field(init=False,repr=False,default=0)
    is_ssmt4:bool = field(init=False,repr=False,default=False)

    def __post_init__(self):
        self.display_name = self.obj_name
        if "-" in self.obj_name:
            obj_name_split = self.obj_name.split("-")
            self.draw_ib = obj_name_split[0]
            
            if len(obj_name_split) == 3:
                last_part = obj_name_split[2]
                if "." in last_part:
                    first_index_str, alias = last_part.split(".", 1)
                    try:
                        self.index_count = int(obj_name_split[1])
                        self.first_index = int(first_index_str)
                        self.is_ssmt4 = True
                        self.component_count = 1
                        self.obj_alias_name = alias
                        return
                    except ValueError:
                        pass
                
                try:
                    self.component_count = int(obj_name_split[1])
                    self.obj_alias_name = obj_name_split[2]
                except ValueError:
                    LOG.warning(f"ObjDataModel: 无法解析 component_count，物体名称 '{self.obj_name}' 中的 '{obj_name_split[1]}' 不是有效数字")
                    self.obj_alias_name = obj_name_split[2] if len(obj_name_split) > 2 else ""
            elif len(obj_name_split) >= 4:
                self.is_ssmt4 = True
                try:
                    self.index_count = int(obj_name_split[1])
                    self.first_index = int(obj_name_split[2])
                except ValueError:
                    LOG.warning(f"ObjDataModel: 无法解析 index_count 或 first_index，物体名称 '{self.obj_name}' 格式错误")
                    self.index_count = 0
                    self.first_index = 0
                self.component_count = 1
                alias_part = obj_name_split[3]
                if "." in alias_part:
                    self.obj_alias_name = alias_part.split(".", 1)[1]
                else:
                    self.obj_alias_name = alias_part
            else:
                try:
                    self.component_count = int(obj_name_split[1])
                    self.obj_alias_name = obj_name_split[2]
                except (ValueError, IndexError):
                    LOG.warning(f"ObjDataModel: 无法解析物体名称 '{self.obj_name}'，格式不正确")
                    self.obj_alias_name = obj_name_split[2] if len(obj_name_split) > 2 else ""
       
