import collections
import numpy
import bpy

from dataclasses import dataclass, field
from typing import Dict

from ..base.d3d11_gametype import D3D11GameType
from ..helper.obj_buffer_helper import ObjBufferHelper

@dataclass
class ShapeKeyBufferModel:
    '''
    逻辑和ObjElementModel以及ObjBufferModelUnity类似
    不过呢，只处理得到Position分类的数据
    每个ObjElementModel都有一个形态键名称为key，ShapeKeyBufferModel为value的字典
    里面装着每个以Shape.开头的形态键对应的应用值到1的Position数据
    最终这些数据会在ObjBufferModelUnity中被合并到每个DrawIB最终的ShapeKey数据中
    然后变成对应的Buffer文件

    TODO
    除此之外需要注意，必须确保ShapeKey应用后，重复的顶点也被看做是独立的顶点以避免合并导致的顶点顺序错误的问题。

    '''

    name: str # 形态键名称
    base_element_vertex_ndarray: numpy.ndarray = field(repr=False) 
    mesh:bpy.types.Mesh = field(repr=False) 
    indices_map: numpy.ndarray = field(repr=False) 
    d3d11_game_type:D3D11GameType = field(repr=False)

    element_vertex_ndarray: numpy.ndarray = field(init=False, repr=False) # 存储了该形态键形态下的顶点数据

    def __post_init__(self) -> None:
        # 1. 复制基础数据
        self.element_vertex_ndarray = self.base_element_vertex_ndarray.copy()

        # 2. 提取并映射 Position 数据
        d3d11_element = self.d3d11_game_type.ElementNameD3D11ElementDict.get('POSITION')
        if d3d11_element:
            final_positions = ObjBufferHelper._parse_position(
                mesh_vertices=self.mesh.vertices,
                mesh_vertices_length=len(self.mesh.vertices),
                loop_vertex_indices=self.indices_map,
                d3d11_element=d3d11_element
            )
            self.element_vertex_ndarray['POSITION'] = final_positions
    