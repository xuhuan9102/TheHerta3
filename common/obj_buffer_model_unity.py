import collections
import numpy
import bpy

from dataclasses import dataclass, field

from ..utils.timer_utils import TimerUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from .obj_element_model import ObjElementModel

from ..helper.obj_buffer_helper import ObjBufferHelper

@dataclass
class ObjBufferModelUnity:
    obj:bpy.types.Object
    d3d11_game_type:D3D11GameType

    obj_name:str = field(init=False, repr=False)
    dtype:numpy.dtype = field(init=False, repr=False)
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    # 这三个是最终要得到的输出内容
    ib:list = field(init=False,repr=False)
    category_buffer_dict:dict = field(init=False,repr=False)
    index_vertex_id_dict:dict = field(init=False,repr=False) # 仅用于WWMI的索引顶点ID字典，key是顶点索引，value是顶点ID，默认可以为None
    
    def __post_init__(self) -> None:
        ObjBufferHelper.check_and_verify_attributes(obj=self.obj, d3d11_game_type=self.d3d11_game_type)
        obj_element_model = ObjElementModel(d3d11_game_type=self.d3d11_game_type,obj_name=self.obj.name)

        obj_element_model.element_vertex_ndarray = ObjBufferHelper.convert_to_element_vertex_ndarray(
            original_elementname_data_dict=obj_element_model.original_elementname_data_dict,
            final_elementname_data_dict={},
            mesh=obj_element_model.mesh,
            d3d11_game_type=self.d3d11_game_type
        )

        mesh = obj_element_model.mesh
        # self.obj_name = obj_element_model.obj_name
        dtype = obj_element_model.total_structured_dtype
        self.element_vertex_ndarray = obj_element_model.element_vertex_ndarray

        # 因为只有存在TANGENT时，顶点数才会增加，所以如果是GF2并且存在TANGENT才使用共享TANGENT防止增加顶点数
        if GlobalConfig.logic_name == LogicName.UnityCPU and "TANGENT" in self.d3d11_game_type.OrderedFullElementList:
            self.ib, self.category_buffer_dict, self.index_vertex_id_dict = ObjBufferHelper.calc_index_vertex_buffer_girlsfrontline2(mesh=mesh, element_vertex_ndarray=self.element_vertex_ndarray, d3d11_game_type=self.d3d11_game_type, dtype=dtype)
        else:
            # 计算IndexBuffer和CategoryBufferDict
            self.ib, self.category_buffer_dict, self.index_vertex_id_dict = ObjBufferHelper.calc_index_vertex_buffer_unified(mesh=mesh, element_vertex_ndarray=self.element_vertex_ndarray, d3d11_game_type=self.d3d11_game_type, dtype=dtype,obj=self.obj)

