
import math
import bpy
import copy

from ..config.main_config import GlobalConfig, LogicName

from ..utils.obj_utils import ObjUtils
from ..utils.log_utils import LOG
from ..utils.collection_utils import CollectionUtils, CollectionColor
from ..utils.config_utils import ConfigUtils
from ..utils.tips_utils import TipUtils

from ..base.m_key import M_Key
from ..base.m_condition import M_Condition
from ..base.d3d11_gametype import D3D11GameType
from ..base.obj_data_model import ObjDataModel
from ..base.m_global_key_counter import M_GlobalKeyCounter

from ..common.obj_element_model import ObjElementModel
from ..common.obj_buffer_model_unity import ObjBufferModelUnity
from ..helper.obj_buffer_helper import ObjBufferHelper

from .blueprint_export_helper import BlueprintExportHelper

class BluePrintModel:

    
    def __init__(self):
        # 全局按键名称和按键属性字典
        self.keyname_mkey_dict:dict[str,M_Key] = {} 

        # 全局obj_model列表，主要是obj_model里装了每个obj的生效条件。
        self.ordered_draw_obj_data_model_list:list[ObjDataModel] = [] 

        # 从输出节点开始递归解析所有的组节点
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        output_node = BlueprintExportHelper.get_output_node(tree)
        groups = BlueprintExportHelper.get_connected_groups(output_node)
        for group_node in groups:
            self.parse_current_group(group_node)


    def parse_current_group(self, group_node):
        '''
        这个是递归方法，就好像BranchModel中的递归一样

        解析当前组节点，获取其连接的所有Object Info节点的信息
        '''
        


        pass