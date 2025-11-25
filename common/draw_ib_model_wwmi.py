import struct
import numpy
import os

from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import *
from ..config.main_config import *
from ..utils.json_utils import *
from ..utils.timer_utils import TimerUtils
from ..utils.format_utils import Fatal
from ..utils.obj_utils import *
from ..utils.shapekey_utils import ShapeKeyUtils
from ..utils.log_utils import LOG

from .extracted_object import ExtractedObject, ExtractedObjectHelper
from ..base.obj_data_model import ObjDataModel
from ..base.component_model import ComponentModel
from ..base.d3d11_gametype import D3D11GameType
from ..base.m_draw_indexed import M_DrawIndexed

from ..config.import_config import ImportConfig
from .obj_buffer_model import ObjBufferModel

from .branch_model import BranchModel

from ..config.properties_wwmi import Properties_WWMI


# 配置常量（按项目实际情况调整）
DEFAULT_VG_SLOTS = 8          # 每顶点写多少个 VG id（与 Blend.buf 的槽数一致），仅作回退值
BLOCK_SIZE = 512       # forward/reverse block 大小（WWMI 默认为 512）
REMAPP_SKIP_THRESHOLD = 256  # 超过多少个 VG 才启用 Remap（WWMI 默认为 256）


def _detect_vg_slots_from_gametype(d3d11_game_type, default=DEFAULT_VG_SLOTS):
    """
    Try to detect number of blend index slots from a D3D11GameType instance.
    Falls back to `default` when detection fails.
    """
    try:
        for elem in getattr(d3d11_game_type, 'D3D11ElementList', []):
            name = (getattr(elem, 'SemanticName', '') or '').lower()
            if 'blend' in name and ('index' in name or 'indices' in name):
                byte_width = int(getattr(elem, 'ByteWidth', 0) or 0)
                fmt = (getattr(elem, 'Format', '') or '').upper()
                if 'R8' in fmt:
                    comp_bytes = 1
                elif 'R16' in fmt:
                    comp_bytes = 2
                elif 'R32' in fmt:
                    comp_bytes = 4
                else:
                    comp_bytes = 1
                if comp_bytes > 0 and byte_width > 0:
                    slots = max(1, byte_width // comp_bytes)
                    return int(slots)
    except Exception:
        pass
    return int(default)


def collect_component_mesh_data(obj, vg_slots=None):
    """
    输入：一个 component 的已合并对象（component_obj），返回：
    - vertex_count
    - index_data (list of vertex indices, flattened triangles)
    - vg_ids (list of lists) 每顶点 vg_slots 个 uint (原始 group indices)
    - vg_weights (list of lists) 每顶点对应权重 0..255
    """
    if vg_slots is None:
        vg_slots = DEFAULT_VG_SLOTS

    mesh = ObjUtils.get_mesh_evaluate_from_obj(obj)
    mesh.calc_loop_triangles()

    # index_data: flatten all triangles' vertex indices
    index_list = []
    for tri in mesh.loop_triangles:
        index_list.extend(list(tri.vertices))
    index_data = index_list
    vertex_count = len(mesh.vertices)

    # Build per-vertex vg id and weights, fixed vg_slots
    vg_ids = [[0]*vg_slots for _ in range(vertex_count)]
    vg_weights = [[0]*vg_slots for _ in range(vertex_count)]

    for vi, v in enumerate(mesh.vertices):
        slot = 0
        # v.groups: Blender's collection of vertex group weights for this vertex
        for g in v.groups:
            if slot >= vg_slots:
                break
            # g.group is the group index (int), g.weight is 0..1
            vg_ids[vi][slot] = int(g.group)
            vg_weights[vi][slot] = int(round(max(0.0, min(1.0, g.weight)) * 255))
            slot += 1

    return vertex_count, index_data, vg_ids, vg_weights



def export_blendremap_for_components_v2_wwmi(components_objs, out_dir, vg_slots=None, d3d11_game_type=None):
    """
    WWMI-exact v2 implementation.
    Builds BlendRemapVertexVG.buf using loop/element-based unique-first-occurrence rows
    (matching WWMI-Tools), pads/truncates to `vg_slots`, writes uint16 rows, and
    constructs BlendRemapForward/Reverse/Layout buffers.
    This function is added as a new v2 variant and does not modify existing v2/v3.
    """
    os.makedirs(out_dir, exist_ok=True)

    if vg_slots is None:
        vg_slots = _detect_vg_slots_from_gametype(d3d11_game_type or D3D11GameType(), default=DEFAULT_VG_SLOTS)

    concatenated_vg_ids = []
    concatenated_vg_weights = []
    concatenated_index_data = []
    index_layout = []

    vertex_offset = 0

    def _normalize_rows(indices_arr, weights_arr, slots):
        arr = numpy.asarray(indices_arr)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        M = arr.shape[1]
        if M >= slots:
            vg_rows = arr[:, :slots]
        else:
            pad = numpy.zeros((arr.shape[0], slots - M), dtype=numpy.uint32)
            vg_rows = numpy.concatenate((arr, pad), axis=1)

        if weights_arr is None:
            weights = numpy.zeros((vg_rows.shape[0], slots), dtype=numpy.uint8)
        else:
            w = numpy.asarray(weights_arr)
            if w.ndim == 1:
                w = w.reshape(-1, 1)
            if w.dtype != numpy.uint8:
                w = (w * 255.0).round().astype(numpy.uint8)
            if w.shape[1] >= slots:
                weights = w[:, :slots]
            else:
                wp = numpy.zeros((vg_rows.shape[0], slots), dtype=numpy.uint8)
                wp[:, :w.shape[1]] = w
                weights = wp

        return vg_rows.astype(numpy.uint32), weights.astype(numpy.uint8)

    for comp_obj in components_objs:
        # Try to use ObjBufferModel loop/element rows; fallback to mesh-based
        try:
            obj_buf = ObjBufferModel(d3d11_game_type=(d3d11_game_type or D3D11GameType()), obj_name=comp_obj.name)
        except Exception:
            vertex_count, index_data, vg_ids, vg_weights = collect_component_mesh_data(comp_obj, vg_slots=vg_slots)
            concatenated_vg_ids.extend(vg_ids)
            concatenated_vg_weights.extend(vg_weights)
            if index_data:
                adjusted = [int(i) + vertex_offset for i in index_data]
                concatenated_index_data.extend(adjusted)
                index_layout.append(len(index_data))
            else:
                index_layout.append(0)
            vertex_offset += vertex_count
            continue

        # extract contiguous element rows and dedupe by full-row bytes preserving first occurrence
        try:
            vb = numpy.ascontiguousarray(obj_buf.element_vertex_ndarray)
            n_rows = len(vb)
            row_size = vb.dtype.itemsize
            try:
                row_bytes = vb.view(numpy.uint8).reshape(n_rows, row_size)
            except Exception:
                raw = vb.tobytes()
                row_bytes = numpy.frombuffer(raw, dtype=numpy.uint8).reshape(n_rows, row_size)

            _, unique_first_indices = numpy.unique(row_bytes, axis=0, return_index=True)
            unique_first_indices = numpy.sort(unique_first_indices)
            print(f'[v2_wwmi-debug] component={comp_obj.name} element_rows={n_rows} unique_first_indices={len(unique_first_indices)}')
        except Exception:
            unique_first_indices = None

        try:
            all_blendindices = numpy.asarray(obj_buf.element_vertex_ndarray.get('BLENDINDICES'))
        except Exception:
            all_blendindices = None
        try:
            all_blendweights = numpy.asarray(obj_buf.element_vertex_ndarray.get('BLENDWEIGHT', None))
        except Exception:
            all_blendweights = None

        if all_blendindices is None or unique_first_indices is None:
            print(f'[v2_wwmi-debug] component={comp_obj.name} falling back to mesh-based collection')
            vertex_count, index_data, vg_ids, vg_weights = collect_component_mesh_data(comp_obj, vg_slots=vg_slots)
            concatenated_vg_ids.extend(vg_ids)
            concatenated_vg_weights.extend(vg_weights)
            if index_data:
                adjusted = [int(i) + vertex_offset for i in index_data]
                concatenated_index_data.extend(adjusted)
                index_layout.append(len(index_data))
            else:
                index_layout.append(0)
            vertex_offset += vertex_count
            continue

        unique_blendindices = all_blendindices[unique_first_indices]
        unique_blendweights = None if all_blendweights is None else all_blendweights[unique_first_indices]
        print(f'[v2_wwmi-debug] component={comp_obj.name} unique_blendindices_rows={len(unique_blendindices)}')

        vg_rows, vw = _normalize_rows(unique_blendindices, unique_blendweights, vg_slots)
        print(f'[v2_wwmi-debug] component={comp_obj.name} vg_rows={vg_rows.shape[0]} slots={vg_rows.shape[1]}')
        concatenated_vg_ids.extend(vg_rows.tolist())
        concatenated_vg_weights.extend(vw.tolist())

        comp_ib = list(obj_buf.ib) if hasattr(obj_buf, 'ib') else []
        if comp_ib:
            adjusted = [int(i) + vertex_offset for i in comp_ib]
            concatenated_index_data.extend(adjusted)
            index_layout.append(len(comp_ib))
        else:
            index_layout.append(0)

        vertex_offset += vg_rows.shape[0]

    # ensure we have vertices
    if len(concatenated_vg_ids) == 0:
        print('No vertices found when exporting BlendRemap (v2_wwmi).')
        return {'vertex_vg_count': 0, 'blocks_count': 0, 'counts': []}

    # build numpy arrays
    vg_ids_np = numpy.array(concatenated_vg_ids, dtype=numpy.uint16)
    try:
        vg_ids_np = vg_ids_np.reshape((-1, vg_slots))
    except Exception:
        vg_ids_np = numpy.array([(list(r) + [0]*vg_slots)[:vg_slots] for r in concatenated_vg_ids], dtype=numpy.uint16)

    vg_weights_np = numpy.array(concatenated_vg_weights, dtype=numpy.uint8)
    try:
        vg_weights_np = vg_weights_np.reshape((-1, vg_slots))
    except Exception:
        vg_weights_np = numpy.array([(list(r) + [0]*vg_slots)[:vg_slots] for r in concatenated_vg_weights], dtype=numpy.uint8)

    index_data_np = numpy.array(concatenated_index_data, dtype=numpy.uint32)

    # write BlendRemapVertexVG.buf (uint16 per slot, little-endian)
    vg_out = vg_ids_np.astype(numpy.uint16)
    with open(os.path.join(out_dir, 'BlendRemapVertexVG.buf'), 'wb') as f:
        vg_out.tofile(f)
    vertex_vg_count = int(vg_out.shape[0])
    print(f'Wrote BlendRemapVertexVG.buf ({vertex_vg_count} vertices, {vg_out.shape[1]} slots each)')
    # debug summary
    try:
        print(f'[v2_wwmi-debug] total_concatenated_rows={len(concatenated_vg_ids)} vertex_vg_count={vertex_vg_count} index_layout={index_layout}')
    except Exception:
        pass

    # construct remap forward/reverse/layout following WWMI policy
    blend_remap_forward = numpy.empty(0, dtype=numpy.uint16)
    blend_remap_reverse = numpy.empty(0, dtype=numpy.uint16)
    remapped_vgs_counts = []

    idx_offset = 0
    for index_count in index_layout:
        if index_count <= 0:
            remapped_vgs_counts.append(0)
            continue

        vertex_ids = index_data_np[idx_offset: idx_offset + index_count]
        vertex_ids = numpy.unique(vertex_ids)

        if vertex_ids.size == 0:
            remapped_vgs_counts.append(0)
            idx_offset += index_count
            continue

        obj_vg_ids = vg_ids_np[vertex_ids].flatten()

        if obj_vg_ids.size == 0 or numpy.max(obj_vg_ids) < REMAPP_SKIP_THRESHOLD:
            remapped_vgs_counts.append(0)
            idx_offset += index_count
            continue

        obj_vg_weights = vg_weights_np[vertex_ids].flatten()
        non_zero_idx = numpy.nonzero(obj_vg_weights > 0)[0]

        if non_zero_idx.size == 0:
            remapped_vgs_counts.append(0)
            idx_offset += index_count
            continue

        obj_vg_ids = obj_vg_ids[non_zero_idx]
        obj_vg_ids = numpy.unique(obj_vg_ids)

        if obj_vg_ids.size == 0 or numpy.max(obj_vg_ids) < REMAPP_SKIP_THRESHOLD:
            remapped_vgs_counts.append(0)
            idx_offset += index_count
            continue

        if numpy.max(obj_vg_ids) >= BLOCK_SIZE:
            print(f'WARNING: component has VG id >= {BLOCK_SIZE}, skipping remap for that component.')
            remapped_vgs_counts.append(0)
            idx_offset += index_count
            continue

        remapped_vgs_counts.append(int(obj_vg_ids.size))

        forward = numpy.zeros(BLOCK_SIZE, dtype=numpy.uint16)
        forward[numpy.arange(obj_vg_ids.size, dtype=numpy.int32)] = obj_vg_ids.astype(numpy.uint16)

        reverse = numpy.zeros(BLOCK_SIZE, dtype=numpy.uint16)
        reverse[obj_vg_ids.astype(numpy.int32)] = numpy.arange(obj_vg_ids.size, dtype=numpy.uint16)

        blend_remap_forward = numpy.concatenate((blend_remap_forward, forward), axis=0)
        blend_remap_reverse = numpy.concatenate((blend_remap_reverse, reverse), axis=0)

        idx_offset += index_count

    # write remap files if any
    if blend_remap_forward.size > 0:
        with open(os.path.join(out_dir, 'BlendRemapForward.buf'), 'wb') as f:
            blend_remap_forward.tofile(f)
        with open(os.path.join(out_dir, 'BlendRemapReverse.buf'), 'wb') as f:
            blend_remap_reverse.tofile(f)
        with open(os.path.join(out_dir, 'BlendRemapLayout.buf'), 'wb') as f:
            numpy.array(remapped_vgs_counts, dtype=numpy.uint32).tofile(f)
        print(f'Wrote BlendRemapForward.buf and BlendRemapReverse.buf with {int(len(blend_remap_forward)/BLOCK_SIZE)} blocks')
    else:
        print('No remap blocks required (all components have VG ids < 256).')

    return {
        'vertex_vg_count': vertex_vg_count,
        'blocks_count': int(len(blend_remap_forward)/BLOCK_SIZE),
        'counts': remapped_vgs_counts
    }

class DrawIBModelWWMI:
    '''
    这个代表了一个DrawIB的Mod导出模型
    Mod导出可以调用这个模型来进行业务逻辑部分
    每个游戏的DrawIBModel都是不同的，但是一部分是可以复用的
    (例如WWMI就有自己的一套DrawIBModel) 
    '''

    # 通过default_factory让每个类的实例的变量分割开来，不再共享类的静态变量
    def __init__(self,draw_ib:str,branch_model:BranchModel):
        # (1) 读取工作空间下的Config.json来设置当前DrawIB的别名
        draw_ib_alias_name_dict = ConfigUtils.get_draw_ib_alias_name_dict()
        self.draw_ib = draw_ib
        self.draw_ib_alias = draw_ib_alias_name_dict.get(draw_ib,draw_ib)

        # (2) 读取工作空间中配置文件的配置项
        self.import_config = ImportConfig(draw_ib=self.draw_ib)
        self.d3d11GameType:D3D11GameType = self.import_config.d3d11GameType
        # 读取WWMI专属配置
        self.extracted_object:ExtractedObject = ExtractedObjectHelper.read_metadata(GlobalConfig.path_extract_gametype_folder(draw_ib=self.draw_ib,gametype_name=self.d3d11GameType.GameTypeName)  + "Metadata.json")

        '''
        这里是要得到每个Component对应的obj_data_model列表
        '''
        self.ordered_obj_data_model_list:list[ObjDataModel] = branch_model.get_obj_data_model_list_by_draw_ib(draw_ib=draw_ib)
        
        # (3) 组装成特定格式？
        self._component_model_list:list[ComponentModel] = []
        self.component_name_component_model_dict:dict[str,ComponentModel] = {}

        for part_name in self.import_config.part_name_list:
            print("part_name: " + part_name)
            component_obj_data_model_list = []
            for obj_data_model in self.ordered_obj_data_model_list:
                if part_name == str(obj_data_model.component_count):
                    component_obj_data_model_list.append(obj_data_model)
                    print("obj_data_model: " + obj_data_model.obj_name)

            component_model = ComponentModel(component_name="Component " + part_name,final_ordered_draw_obj_model_list=component_obj_data_model_list)
            
            self._component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = component_model
        LOG.newline()


        # (4) 根据之前解析集合架构的结果，读取obj对象内容到字典中
        self.mesh_vertex_count = 0 # 每个DrawIB都有总的顶点数，对应CategoryBuffer里的顶点数。

        # (5) 对所有obj进行融合，得到一个最终的用于导出的临时obj
        self.merged_object = self.build_merged_object(
            extracted_object=self.extracted_object
        )

        # (6) 填充每个obj的drawindexed值，给每个obj的属性统计好，后面就能直接用了。
        self.obj_name_drawindexed_dict:dict[str,M_DrawIndexed] = {} 
        for comp in self.merged_object.components:
            for comp_obj in comp.objects:
                draw_indexed_obj = M_DrawIndexed()
                draw_indexed_obj.DrawNumber = str(comp_obj.index_count)
                draw_indexed_obj.DrawOffsetIndex = str(comp_obj.index_offset)
                draw_indexed_obj.AliasName = comp_obj.name
                self.obj_name_drawindexed_dict[comp_obj.name] = draw_indexed_obj
        
        # (7) 填充到component_name为key的字典中，方便后续操作
        for component_model in self._component_model_list:
            new_ordered_obj_model_list = []
            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_model.drawindexed_obj = self.obj_name_drawindexed_dict[obj_model.obj_name]
                new_ordered_obj_model_list.append(obj_model)
            component_model.final_ordered_draw_obj_model_list = new_ordered_obj_model_list
            self.component_name_component_model_dict[component_model.component_name] = component_model
        
        # (8) 选中当前融合的obj对象，计算得到ib和category_buffer，以及每个IndexId对应的VertexId
        merged_obj = self.merged_object.object

        merged_obj.name
        
        TimerUtils.Start("构建ObjBufferModel")
        obj_buffer_model = ObjBufferModel(d3d11_game_type=self.d3d11GameType,obj_name=merged_obj.name)
        TimerUtils.End("构建ObjBufferModel")

        # TODO 如果Merged架构下，顶点组数量超过了255，则必须使用Remap技术
        # 在这里遍历获取每个Component的obj列表，然后对这些obj进行统计，统计BLENDINDICES和BLENDWEIGHTS
        # 生成BlendRemapForward.buf中的内容
        # 每个Component 每512个数字为一组，有几个Component就有几组 格式：R16_UINT
        # 对应的位数就是局部顶点索引
        # 对应的位上的内容就是原始的顶点组索引
        
        # 需要一个方法，能够获取指定obj的所有的d3d11Element内容。
        # 其次就是可能要考虑到先声明数据类型，后进行执行的问题，比如WWMI就是把所有的数据类型提前全部声明好
        # 最后需要的时候只执行一次就把所有的内容都拿到了，本质上是数据类型设计的比较好。

        # 因为MergedObj已经全部合并在一起了
        # 也许我们可以更改一下合并的流程，让它们先把每个Component的合并在一起，得到一个Obj列表
        # 此时就可以根据这个obj列表，获取其属性，然后决定是否要使用remap技术
        # 然后记录在mergedobj的属性里，然后再把这几个单独component的合并在一起
        # 最后得到mergedobj，同时也把生成BlendRemapForward.buf和BlendRemapReverse.buf的信息获取到了
        # 最后再根据mergedobj来获取生成BlendRemapVertexVG.buf的信息
        # 大概就是这个思路，所以build_merged_obj这个流程还需要深入理解并且做一些修改，才能实现remap技术
        

        # 写出到文件
        self.write_out_index_buffer(ib=obj_buffer_model.ib)
        self.write_out_category_buffer(category_buffer_dict=obj_buffer_model.category_buffer_dict)
        self.write_out_shapekey_buffer(merged_obj=merged_obj, index_vertex_id_dict=obj_buffer_model.index_vertex_id_dict)

        # 删除临时融合的obj对象
        bpy.data.objects.remove(merged_obj, do_unlink=True)


    def write_out_index_buffer(self,ib):
        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()

        packed_data = struct.pack(f'<{len(ib)}I', *ib)
        with open(buf_output_folder + self.draw_ib + "-Component1.buf", 'wb') as ibf:
            ibf.write(packed_data) 

    def write_out_category_buffer(self,category_buffer_dict):
        __categoryname_bytelist_dict = {} 
        for category_name in self.d3d11GameType.OrderedCategoryNameList:
            if category_name not in __categoryname_bytelist_dict:
                __categoryname_bytelist_dict[category_name] =  category_buffer_dict[category_name]
            else:
                existing_array = __categoryname_bytelist_dict[category_name]
                buffer_array = category_buffer_dict[category_name]

                # 确保两个数组都是NumPy数组
                existing_array = numpy.asarray(existing_array)
                buffer_array = numpy.asarray(buffer_array)

                # 使用 concatenate 连接两个数组，确保传递的是一个序列（如列表或元组）
                concatenated_array = numpy.concatenate((existing_array, buffer_array))

                # 更新字典中的值
                __categoryname_bytelist_dict[category_name] = concatenated_array

        # 顺便计算一下步长得到总顶点数
        position_stride = self.d3d11GameType.CategoryStrideDict["Position"]
        position_bytelength = len(__categoryname_bytelist_dict["Position"])
        self.mesh_vertex_count = int(position_bytelength/position_stride)

        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()
            
        for category_name, category_buf in __categoryname_bytelist_dict.items():
            buf_path = buf_output_folder + self.draw_ib + "-" + category_name + ".buf"
             # 将 list 转换为 numpy 数组
            # category_array = numpy.array(category_buf, dtype=numpy.uint8)
            with open(buf_path, 'wb') as ibf:
                category_buf.tofile(ibf)

    def write_out_shapekey_buffer(self,merged_obj,index_vertex_id_dict):
        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()

        self.shapekey_offsets = []
        self.shapekey_vertex_ids = []
        self.shapekey_vertex_offsets = []

        # (11) 拼接ShapeKey数据
        if merged_obj.data.shape_keys is None or len(getattr(merged_obj.data.shape_keys, 'key_blocks', [])) == 0:
            print(f'No shapekeys found to process!')
        else:
            shapekey_offsets,shapekey_vertex_ids,shapekey_vertex_offsets_np = ShapeKeyUtils.extract_shapekey_data(merged_obj=merged_obj,index_vertex_id_dict=index_vertex_id_dict)
            # extract_shapekey_data_v2
            # shapekey_offsets,shapekey_vertex_ids,shapekey_vertex_offsets_np = ShapeKeyUtils.extract_shapekey_data_v2(mesh=mesh,index_vertex_id_dict=index_vertex_id_dict)

            self.shapekey_offsets = shapekey_offsets
            self.shapekey_vertex_ids = shapekey_vertex_ids
            self.shapekey_vertex_offsets = shapekey_vertex_offsets_np

            # 鸣潮的ShapeKey三个Buffer的导出
            if len(self.shapekey_offsets) != 0:
                with open(buf_output_folder + self.draw_ib + "-" + "ShapeKeyOffset.buf", 'wb') as file:
                    for number in self.shapekey_offsets:
                        # 假设数字是32位整数，使用'i'格式符
                        # 根据实际需要调整数字格式和相应的格式符
                        data = struct.pack('i', number)
                        file.write(data)
            
            if len(self.shapekey_vertex_ids) != 0:
                with open(buf_output_folder + self.draw_ib + "-" + "ShapeKeyVertexId.buf", 'wb') as file:
                    for number in self.shapekey_vertex_ids:
                        # 假设数字是32位整数，使用'i'格式符
                        # 根据实际需要调整数字格式和相应的格式符
                        data = struct.pack('i', number)
                        file.write(data)
            
            if len(self.shapekey_vertex_offsets) != 0:
                # 将列表转换为numpy数组，并改变其数据类型为float16
                float_array = numpy.array(self.shapekey_vertex_offsets, dtype=numpy.float32).astype(numpy.float16)
                with open(buf_output_folder + self.draw_ib + "-" + "ShapeKeyVertexOffset.buf", 'wb') as file:
                    float_array.tofile(file)

    def build_merged_object(self,extracted_object:ExtractedObject):
        '''
        extracted_object 用于读取配置
        
        此方法用于为当前DrawIB构建MergedObj对象
        '''
        print("build_merged_object::")

        # 1.Initialize components
        components = []
        for component in extracted_object.components: 
            components.append(
                MergedObjectComponent(
                    objects=[],
                    index_count=0,
                )
            )
        
        # 2.import_objects_from_collection
        # 这里是获取所有的obj，需要用咱们的方法来进行集合架构的遍历获取所有的obj
        # Nico: 添加缓存机制，一个obj只处理一次
        workspace_collection = bpy.context.collection

        processed_obj_name_list:list[str] = []
        for component_model in self._component_model_list:
            component_count = str(component_model.component_name)[10:]
            print("ComponentCount: " + component_count)

            # 这里减去1是因为我们的Compoennt是从1开始的,但是WWMITools的逻辑是从0开始的
            component_id = int(component_count) - 1 
            print("component_id: " + str(component_id))
            
            for obj_data_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_data_model.obj_name
                print("obj_name: " + obj_name)
                
                # Nico: 如果已经处理过这个obj，则跳过
                if obj_name in processed_obj_name_list:
                    print(f"Skipping already processed object: {obj_name}")
                    continue
                processed_obj_name_list.append(obj_name)

                obj = ObjUtils.get_obj_by_name(obj_name)

                # 复制出一个TEMP_为前缀的obj出来
                # 这里我们设置collection为None，不链接到任何集合中，防止干扰
                temp_obj = ObjUtils.copy_object(bpy.context, obj, name=f'TEMP_{obj.name}', collection=workspace_collection)

                # 添加到当前component的objects列表中，添加的是复制出来的TEMP_的obj
                try:
                    components[component_id].objects.append(TempObject(
                        name=obj.name,
                        object=temp_obj,
                    ))
                except Exception as e:
                    print(f"Error appending object to component: {e}")

        print("准备临时对象::")
        # 3.准备临时对象
        index_offset = 0
        # 这里的component_id是从0开始的，务必注意
        for component_id, component in enumerate(components):
            
            # 排序以确保obj的命名符合规范而不是根据集合中的位置来进行
            component.objects.sort(key=lambda x: x.name)

            for temp_object in component.objects:
                temp_obj = temp_object.object
                print("Processing temp_obj: " + temp_obj.name)

                # Remove muted shape keys
                if Properties_WWMI.ignore_muted_shape_keys() and temp_obj.data.shape_keys:
                    print("Removing muted shape keys for object: " + temp_obj.name)
                    muted_shape_keys = []
                    for shapekey_id in range(len(temp_obj.data.shape_keys.key_blocks)):
                        shape_key = temp_obj.data.shape_keys.key_blocks[shapekey_id]
                        if shape_key.mute:
                            muted_shape_keys.append(shape_key)
                    for shape_key in muted_shape_keys:
                        print("Removing shape key: " + shape_key.name)
                        temp_obj.shape_key_remove(shape_key)

                # Apply all modifiers to temporary object
                if Properties_WWMI.apply_all_modifiers():
                    print("Applying all modifiers for object: " + temp_obj.name)
                    with OpenObject(bpy.context, temp_obj) as obj:
                        selected_modifiers = [modifier.name for modifier in get_modifiers(obj)]
                        ShapeKeyUtils.apply_modifiers_for_object_with_shape_keys(bpy.context, selected_modifiers, None)

                # Triangulate temporary object, this step is crucial as export supports only triangles
                ObjUtils.triangulate_object(bpy.context, temp_obj)

                # Handle Vertex Groups
                vertex_groups = ObjUtils.get_vertex_groups(temp_obj)

                # Remove ignored or unexpected vertex groups
                if Properties_WWMI.import_merged_vgmap():
                    print("Remove ignored or unexpected vertex groups for object: " + temp_obj.name)
                    # Exclude VGs with 'ignore' tag or with higher id VG count from Metadata.ini for current component
                    total_vg_count = sum([component.vg_count for component in extracted_object.components])
                    ignore_list = [vg for vg in vertex_groups if 'ignore' in vg.name.lower() or vg.index >= total_vg_count]
                else:
                    # Exclude VGs with 'ignore' tag or with higher id VG count from Metadata.ini for current component
                    extracted_component = extracted_object.components[component_id]
                    total_vg_count = len(extracted_component.vg_map)
                    ignore_list = [vg for vg in vertex_groups if 'ignore' in vg.name.lower() or vg.index >= total_vg_count]
                remove_vertex_groups(temp_obj, ignore_list)

                # Rename VGs to their indicies to merge ones of different components together
                for vg in ObjUtils.get_vertex_groups(temp_obj):
                    vg.name = str(vg.index)

                # Calculate vertex count of temporary object
                temp_object.vertex_count = len(temp_obj.data.vertices)
                # Calculate index count of temporary object, IB stores 3 indices per triangle
                temp_object.index_count = len(temp_obj.data.polygons) * 3
                # Set index offset of temporary object to global index_offset
                temp_object.index_offset = index_offset
                # Update global index_offset
                index_offset += temp_object.index_count
                # Update vertex and index count of custom component
                component.vertex_count += temp_object.vertex_count
                component.index_count += temp_object.index_count

        # 上面的内容为每个component里的每个obj都移除了不必要的顶点组，以及统计好了vertex_count和index_count
        # TODO 感觉可以再遍历一次来获取ReMap技术所需的信息




        # build_merged_object:
        drawib_merged_object = []
        drawib_vertex_count, drawib_index_count = 0, 0

        component_obj_list = []
        for component in components:
            
            component_merged_object:list[bpy.types.Object] = []

            # for temp_object in component.objects:
            #     drawib_merged_object.append(temp_object.object)
            # 改为先把component的obj组合在一起，得到当前component的obj
            # 然后就能获取每个component是否使用remap技术的信息了
            # 然后最后再融合到drawib级别的mergedobj中，也不影响最终结果
            for temp_object in component.objects:
                component_merged_object.append(temp_object.object)

            ObjUtils.join_objects(bpy.context, component_merged_object)

            component_obj = component_merged_object[0]
            component_obj_list.append(component_obj)
            
            drawib_merged_object.append(component_obj)

            drawib_vertex_count += component.vertex_count
            drawib_index_count += component.index_count
            
        # component_obj_list 写出
        # components_objs 是你在循环中得到的每个 component_obj 的列表（顺序与 drawib_merged_object 一致）
        # Use WWMI-exact v2 implementation (loop-based unique-first rows).
        # Replaces previous v3 call to ensure BlendRemapVertexVG.buf matches WWMI-Tools.
        vg_slots = _detect_vg_slots_from_gametype(self.d3d11GameType, default=DEFAULT_VG_SLOTS)
        summary = export_blendremap_for_components_v2_wwmi(component_obj_list, GlobalConfig.path_generatemod_buffer_folder(), vg_slots=vg_slots)
        print('BlendRemap export summary:', summary)

        ObjUtils.join_objects(bpy.context, drawib_merged_object)

        obj = drawib_merged_object[0]

        ObjUtils.rename_object(obj, 'TEMP_EXPORT_OBJECT')

        deselect_all_objects()
        select_object(obj)
        set_active_object(bpy.context, obj)

        mesh = ObjUtils.get_mesh_evaluate_from_obj(obj)

        drawib_merged_object = MergedObject(
            object=obj,
            mesh=mesh,
            components=components,
            vertex_count=len(obj.data.vertices),
            index_count=len(obj.data.polygons) * 3,
            vg_count=len(ObjUtils.get_vertex_groups(obj)),
            shapekeys=MergedObjectShapeKeys(),
        )

        if drawib_vertex_count != drawib_merged_object.vertex_count:
            raise ValueError('vertex_count mismatch between merged object and its components')

        if drawib_index_count != drawib_merged_object.index_count:
            raise ValueError('index_count mismatch between merged object and its components')
        
        LOG.newline()
        return drawib_merged_object
    

