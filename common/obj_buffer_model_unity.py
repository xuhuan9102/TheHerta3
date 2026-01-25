import collections
import numpy
import bpy

from dataclasses import dataclass, field

from ..utils.timer_utils import TimerUtils
from ..utils.shapekey_utils import ShapeKeyUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from .obj_element_model import ObjElementModel

from ..helper.obj_buffer_helper import ObjBufferHelper
from ..utils.obj_utils import ObjUtils
from .shapekey_buffer_model import ShapeKeyBufferModel

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

        # 此时根据前面的计算，我们得到了index_vertex_id_dict，这个是用于ShapeKeyBufferModel的生成的关键数据
        # 它记录了每个索引对应的Blender顶点ID，方便后续ShapeKey数据的提取

        self.shape_key_buffer_dict = {}

        if self.obj.data.shape_keys and self.obj.data.shape_keys.key_blocks:
            # 获取所有以 Shape. 开头的形态键
            shape_keys = [sk for sk in self.obj.data.shape_keys.key_blocks if sk.name.startswith("Shape.")]
            
            if shape_keys:
                TimerUtils.Start(f"Processing {len(shape_keys)} ShapeKeys for {self.obj.name}")
                
                # Pre-calculate indices_map explicitly once
                target_count = len(self.element_vertex_ndarray)
                if self.index_vertex_id_dict is not None:
                     indices_map = numpy.zeros(target_count, dtype=int)
                     indices_map[:] = list(self.index_vertex_id_dict.values())
                else:
                     indices_map = numpy.arange(target_count, dtype=int)

                for sk in shape_keys:
                    sk_name = sk.name
                    
                    # 1. 重置所有形态键并激活当前形态键
                    ShapeKeyUtils.reset_shapekey_values(self.obj)
                    sk.value = 1.0
                    
                    # 2. 获取应用了形态键后的 Mesh 数据
                    # 注意：get_mesh_evaluate_from_obj 生成了一个新的 Mesh 数据块，使用完需要移除
                    mesh_eval = ObjUtils.get_mesh_evaluate_from_obj(obj=self.obj)
                    
                    # 3. 必须进行三角化，确保几何结构一致
                    ObjUtils.mesh_triangulate(mesh_eval)
                    
                    # 4. 构建 ShapeKeyBufferModel (它会自动在 __post_init__ 中计算数据)
                    sb_model = ShapeKeyBufferModel(
                        name=sk_name,
                        base_element_vertex_ndarray=self.element_vertex_ndarray,
                        mesh=mesh_eval,
                        indices_map=indices_map,
                        d3d11_game_type=self.d3d11_game_type
                    )
                    self.shape_key_buffer_dict[sk_name] = sb_model
                    
                    # 5. 清理临时 Mesh
                    bpy.data.meshes.remove(mesh_eval)

                # 循环结束后重置状态
                ShapeKeyUtils.reset_shapekey_values(self.obj)
                TimerUtils.End(f"Processing {len(shape_keys)} ShapeKeys for {self.obj.name}")

        