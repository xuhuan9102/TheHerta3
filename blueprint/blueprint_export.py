import bpy
import os

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils
from ..utils.obj_utils import ObjUtils, get_user_context, set_user_context
from ..utils.performance_stats import start_operation, end_operation, print_performance_report, save_performance_report_to_editor, reset_performance_stats, set_performance_stats_enabled, is_performance_stats_enabled
from ..utils.preprocess_cache import get_cache_manager, FingerprintCalculator, reset_cache_manager

from ..config.main_config import GlobalConfig, LogicName
from ..base.m_global_key_counter import M_GlobalKeyCounter

from ..config.properties_generate_mod import Properties_GenerateMod
from ..config.properties_import_model import Properties_ImportModel

from .blueprint_model import BluePrintModel
from .blueprint_export_helper import BlueprintExportHelper


'''
TODO 

1.现在咱们不是有一个可以选择生成Mod的目标文件夹的按钮嘛
后续改成输出节点的一个属性，这样用户就可以在蓝图里动态控制Mod生成路径了
这样每个工作空间都可以指定独特的生成Mod位置

2.对于之前用户说的生成mod要有备份的问题，也可以在输出节点新增一个备份文件夹的属性
'''
class SSMTSelectGenerateModFolder(bpy.types.Operator):
    '''
    来一个按钮来选择生成Mod的位置,部分用户有这个需求但是这个设计是不优雅的
    正常流程就是应该生成在Mods文件夹中,以便于游戏内F10刷新可以直接生效
    后续观察如果使用人数过少就移除掉
    '''
    bl_idname = "ssmt.select_generate_mod_folder"
    bl_label = "选择生成Mod的位置文件夹"
    bl_description = "选择生成Mod的位置文件夹"

    directory: bpy.props.StringProperty(
        subtype='DIR_PATH'
    ) # type: ignore

    def execute(self, context):
        # 将选择的文件夹路径保存到属性组中
        context.scene.properties_generate_mod.generate_mod_folder_path = self.directory
        self.report({'INFO'}, f"已选择文件夹: {self.directory}")
        return {'FINISHED'}

    def invoke(self, context, event):
        # 打开文件浏览器，只允许选择文件夹
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class SSMTClearPreprocessCache(bpy.types.Operator):
    """清理预处理缓存"""
    bl_idname = "ssmt.clear_preprocess_cache"
    bl_label = "清理预处理缓存"
    bl_description = "清理所有预处理缓存，释放磁盘空间"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        from ..utils.preprocess_cache import get_cache_manager
        
        blend_file = bpy.data.filepath
        cache_manager = get_cache_manager(blend_file)
        stats = cache_manager.get_cache_stats()
        
        cache_manager.clear_cache()
        reset_cache_manager()
        
        self.report({'INFO'}, f"已清理 {stats['total_entries']} 个缓存文件，释放 {stats['total_size_mb']:.2f} MB")
        return {'FINISHED'}


class SSMTGenerateModBlueprint(bpy.types.Operator):
    bl_idname = "ssmt.generate_mod_blueprint"
    bl_label = TR.translate("生成Mod(蓝图架构)")
    bl_description = "根据当前工作空间对应的蓝图架构生成对应的Mod文件"
    bl_options = {'REGISTER','UNDO'}

    node_tree_name: bpy.props.StringProperty(name="Node Tree Name", default="") # type: ignore

    def invoke(self, context, event):
        target_tree_name = self.node_tree_name
        
        if not target_tree_name:
            space_data = getattr(context, "space_data", None)
            if space_data and (space_data.type == 'NODE_EDITOR'):
                tree = getattr(space_data, "edit_tree", None)
                if not tree:
                    tree = getattr(space_data, "node_tree", None)
                if tree:
                    target_tree_name = tree.name
        
        if target_tree_name:
            BlueprintExportHelper.forced_target_tree_name = target_tree_name
        
        has_special_nodes, node_types = BlueprintExportHelper.has_special_postprocess_nodes()
        
        if has_special_nodes:
            mod_export_path = GlobalConfig.path_generate_mod_folder()
            
            if mod_export_path and os.path.exists(mod_export_path):
                if os.listdir(mod_export_path):
                    self._special_node_types = node_types
                    self._export_path = mod_export_path
                    return context.window_manager.invoke_props_dialog(self, width=400)
        
        BlueprintExportHelper.forced_target_tree_name = None
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.label(text="导出目录不为空！", icon='ERROR')
        layout.label(text=f"路径: {getattr(self, '_export_path', '未知')}")
        layout.label(text=f"检测到特殊节点: {', '.join(getattr(self, '_special_node_types', []))}")
        layout.separator()
        layout.label(text="继续导出可能会覆盖现有文件，是否继续？")

    def execute(self, context):
        TimerUtils.Start("GenerateMod Mod")
        
        # 根据配置设置性能统计开关
        set_performance_stats_enabled(Properties_GenerateMod.enable_performance_stats())
        
        # 重置性能统计
        reset_performance_stats()
        start_operation("GenerateMod_Total")
        
        # 记录原始上下文状态
        original_user_context = get_user_context(context)
        
        # 确保在物体模式下进行导出操作（兼容编辑模式、姿态模式等）
        # 这样可以避免模式限制导致的导出问题
        try:
            if context.active_object and context.active_object.mode != 'OBJECT':
                original_mode = context.active_object.mode
                active_obj = context.active_object
                
                # 在切换模式前，保存编辑模式的修改（如删除面、修改顶点等）
                if original_mode == 'EDIT':
                    active_obj.update_from_editmode()
                    print(f"[Export] 已保存编辑模式的修改")
                
                # 权重模式下修改的权重数据会自动保存，但需要确保切换模式
                # 姿态模式下的修改也会在切换模式时自动保存
                bpy.ops.object.mode_set(mode='OBJECT')
                print(f"[Export] 已从 {original_mode} 模式切换到物体模式")
        except Exception as e:
            print(f"[Export] 模式切换警告: {e}")
        
        wm = context.window_manager

        target_tree_name = self.node_tree_name

        # Fallback: 如果没有通过参数传递树名，尝试从当前上下文推断
        if not target_tree_name:
            # 尝试获取当前编辑器中的 NodeTree
            space_data = getattr(context, "space_data", None)
            if space_data and (space_data.type == 'NODE_EDITOR'):
                 # 优先检查 edit_tree (这通常是用户正在查看的 Group 或 Tree)
                 tree = getattr(space_data, "edit_tree", None)
                 if not tree:
                     tree = getattr(space_data, "node_tree", None)
                 
                 if tree:
                     target_tree_name = tree.name

        # Config Override Logic
        if target_tree_name:
            print(f"Generating Mod from specified Node Tree: {target_tree_name}")
            BlueprintExportHelper.forced_target_tree_name = target_tree_name
        else:
            print("Warning: No Node Tree specified for Mod Generation. Using default workspace name logic.")
            BlueprintExportHelper.forced_target_tree_name = None

        # 获取所有要导出的物体及其对应的节点/项目
        start_operation("GetExportObjects")
        obj_node_mapping = self._get_export_objects_with_nodes()
        total_objects = len(obj_node_mapping)
        end_operation("GetExportObjects")
        
        # 检测是否存在形态键控制器变体（三元组标记）
        has_sk_variants = any(len(item) == 3 for item in obj_node_mapping)
        
        if total_objects == 0:
            self.report({'WARNING'}, "没有找到要导出的物体")
            end_operation("GenerateMod_Total")
            set_user_context(context, original_user_context)
            return {'CANCELLED'}
        
        # 如果有形态键变体，构建变体导出计划
        sk_variant_plan = None
        if has_sk_variants:
            sk_variant_plan = self._build_shapekey_variant_plan(obj_node_mapping)
            if sk_variant_plan:
                print(f"[形态键变体] 检测到形态键控制器，共 {len(sk_variant_plan['variants'])} 轮变体导出")
                print(f"  基准变体(全0): buffer0000")
                for i, v in enumerate(sk_variant_plan['variants'], 1):
                    print(f"  变体{i} (槽位 {v['slot_index']}): buffer{1000 + v['slot_index'] + 1:04d}")
        
        use_parallel = Properties_ImportModel.use_parallel_export()
        blend_file_saved = bpy.data.is_saved
        blend_file_dirty = bpy.data.is_dirty
        blend_file = bpy.data.filepath
        mirror_workflow_enabled = Properties_ImportModel.use_mirror_workflow()
        
        preview_export_only = Properties_GenerateMod.preview_export_only()
        
        if preview_export_only:
            print("[PreviewExport] 配置表预导出模式：跳过物体处理，仅生成 INI")
            wm.progress_begin(0, 100)
            wm.progress_update(0)
            copy_mapping = {}
        else:
            if use_parallel:
                if not blend_file_saved:
                    print("[ParallelPreprocess] 工程未保存，自动保存工程...")
                    try:
                        bpy.ops.wm.save_mainfile()
                        blend_file_saved = True
                        blend_file_dirty = False
                        blend_file = bpy.data.filepath
                        print(f"[ParallelPreprocess] 工程已保存: {blend_file}")
                    except Exception as e:
                        self.report({'ERROR'}, f"自动保存工程失败: {e}")
                        end_operation("GenerateMod_Total")
                        set_user_context(context, original_user_context)
                        return {'CANCELLED'}
                elif blend_file_dirty:
                    print("[ParallelPreprocess] 工程有未保存的修改，自动保存工程...")
                    try:
                        bpy.ops.wm.save_mainfile()
                        blend_file_dirty = False
                        print(f"[ParallelPreprocess] 工程已保存: {blend_file}")
                    except Exception as e:
                        self.report({'ERROR'}, f"自动保存工程失败: {e}")
                        end_operation("GenerateMod_Total")
                        set_user_context(context, original_user_context)
                        return {'CANCELLED'}
            
            wm.progress_begin(0, 100)
            wm.progress_update(0)
            print(f"开始处理 {total_objects} 个物体...")
            
            copy_mapping = {}
            
            if use_parallel and blend_file_saved and not blend_file_dirty and total_objects >= 1:
                print(f"[ParallelPreprocess] 启用并行预处理，物体数量: {total_objects}")
                start_operation("ParallelPreprocess")
                copy_mapping = self._parallel_preprocess(context, obj_node_mapping, mirror_workflow_enabled)
                end_operation("ParallelPreprocess")
                if not copy_mapping:
                    print("[ParallelPreprocess] 并行预处理失败，回退到单进程模式")
                    start_operation("SequentialPreprocess")
                    copy_mapping = self._sequential_preprocess(obj_node_mapping, mirror_workflow_enabled, wm, total_objects, blend_file)
                    end_operation("SequentialPreprocess")
            else:
                start_operation("SequentialPreprocess")
                copy_mapping = self._sequential_preprocess(obj_node_mapping, mirror_workflow_enabled, wm, total_objects, blend_file)
                end_operation("SequentialPreprocess")
        
        try:
            # ============================================================
            # 形态键控制器变体多轮导出模式
            # ============================================================
            if sk_variant_plan:
                self._execute_shapekey_variant_exports(
                    context, obj_node_mapping, sk_variant_plan,
                    original_user_context, wm, preview_export_only,
                    use_parallel, blend_file_saved, blend_file_dirty,
                    blend_file, mirror_workflow_enabled
                )
                return {'FINISHED'}   # 添加这一行，变体导出完成后直接返回
            else:
                # 标准导出流程
                max_export_count = BlueprintExportHelper.calculate_max_export_count()

                print(f"最大导出次数: {max_export_count}")
                
                # 重置导出状态
                BlueprintExportHelper.reset_export_state()
            
                # 应用物体名称修改节点的映射到跨IB节点
                start_operation("ApplyNameModifyToCrossIB")
                BlueprintExportHelper.apply_name_modify_to_crossib_nodes()
                end_operation("ApplyNameModifyToCrossIB")
            
            # 循环执行多次导出
            for export_index in range(1, max_export_count + 1):
                BlueprintExportHelper.current_export_index = export_index
                print(f"开始第 {export_index}/{max_export_count} 次导出")
                
                # 更新进度 (50-90%)
                progress = 50 + int(export_index / max_export_count * 40)
                wm.progress_update(progress)
                
                # 更新多文件导出节点的当前物体
                BlueprintExportHelper.update_multifile_export_nodes(export_index)
                
                # 更新导出路径
                BlueprintExportHelper.update_export_path(export_index)
                
                M_GlobalKeyCounter.initialize()

                # 调用对应游戏的生成Mod逻辑
                start_operation(f"GenerateMod_Export_{export_index}")
                if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
                    from ..games.wwmi import ModModelWWMI
                    migoto_mod_model = ModModelWWMI()
                    migoto_mod_model.generate_unreal_vs_config_ini()
                elif GlobalConfig.logic_name == LogicName.YYSLS:
                    from ..games.yysls import ModModelYYSLS
                    migoto_mod_model = ModModelYYSLS()
                    migoto_mod_model.generate_unity_vs_config_ini()

                elif GlobalConfig.logic_name == LogicName.CTXMC or GlobalConfig.logic_name == LogicName.IdentityV2 or GlobalConfig.logic_name == LogicName.NierR:
                    from ..games.identityv import ModModelIdentityV
                    migoto_mod_model = ModModelIdentityV()

                    migoto_mod_model.generate_unity_vs_config_ini()
                
                # 老米四件套
                elif GlobalConfig.logic_name == LogicName.HIMI:
                    from ..games.himi import ModModelHIMI
                    migoto_mod_model = ModModelHIMI()
                    migoto_mod_model.generate_unity_vs_config_ini()
                elif GlobalConfig.logic_name == LogicName.GIMI:
                    from ..games.gimi import ModModelGIMI
                    migoto_mod_model = ModModelGIMI()
                    migoto_mod_model.generate_unity_vs_config_ini()
                elif GlobalConfig.logic_name == LogicName.SRMI:
                    from ..games.srmi import ModModelSRMI
                    migoto_mod_model = ModModelSRMI()
                    migoto_mod_model.generate_unity_cs_config_ini()
                elif GlobalConfig.logic_name == LogicName.ZZMI:
                    from ..games.zzmi import ModModelZZMI
                    migoto_mod_model = ModModelZZMI(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()

                # 强兼支持
                elif GlobalConfig.logic_name == LogicName.EFMI:
                    from ..games.efmi import ModModelEFMI
                    use_ssmt4 = Properties_ImportModel.use_ssmt4()
                    migoto_mod_model = ModModelEFMI(skip_buffer_export=preview_export_only, use_ssmt4=use_ssmt4)
                    migoto_mod_model.generate_unity_vs_config_ini()

                # 终末地测试AEMI，到时候老外的EFMI发布之后，再开一套新逻辑兼容他们的，咱们用这个先测试
                elif GlobalConfig.logic_name == LogicName.AEMI:
                    from ..games.yysls import ModModelYYSLS
                    migoto_mod_model = ModModelYYSLS(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()
                # UnityVS
                elif GlobalConfig.logic_name == LogicName.UnityVS:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()

                # AILIMIT
                elif GlobalConfig.logic_name == LogicName.AILIMIT or GlobalConfig.logic_name == LogicName.UnityCS:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_cs_config_ini()
                
                # UnityCPU 例如少女前线2、虚空之眼等等，绝大部分手游都是UnityCPU
                elif GlobalConfig.logic_name == LogicName.UnityCPU:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()
                
                # UnityCSM
                elif GlobalConfig.logic_name == LogicName.UnityCSM:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_cs_config_ini()

                # 尘白禁区、卡拉比丘
                elif GlobalConfig.logic_name == LogicName.SnowBreak:
                    from ..games.snowbreak import ModModelSnowBreak
                    migoto_mod_model = ModModelSnowBreak()
                    migoto_mod_model.generate_ini()
                else:
                    self.report({'ERROR'},"当前逻辑暂不支持生成Mod")
                    set_user_context(context, original_user_context)
                    return {'FINISHED'}
                end_operation(f"GenerateMod_Export_{export_index}")

                print(f"第 {export_index}/{max_export_count} 次导出完成")
            
                # 标准模式完成
                # 更新进度到 90%
                wm.progress_update(90)

                self.report({'INFO'},TR.translate("Generate Mod Success!"))
                TimerUtils.End("GenerateMod Mod")

                mod_export_path = GlobalConfig.path_generate_mod_folder()
                print(f"Mod导出路径: {mod_export_path}")

                start_operation("PostProcessNodes")
                BlueprintExportHelper.clear_postprocess_caches()
                BlueprintExportHelper.execute_postprocess_nodes(mod_export_path)
                end_operation("PostProcessNodes")

                # 恢复跨IB节点的原始参数
                start_operation("RestoreCrossIBParams")
                BlueprintExportHelper.restore_crossib_nodes_params()
                end_operation("RestoreCrossIBParams")

                # 完成进度
                wm.progress_update(100)
                wm.progress_end()

                CommandUtils.OpenGeneratedModFolder()
        finally:
            # Clean up override
            BlueprintExportHelper.forced_target_tree_name = None
            # 恢复原始导出路径
            BlueprintExportHelper.restore_export_path()
            
            if preview_export_only:
                print("[PreviewExport] 配置表预导出完成，跳过清理步骤")
            else:
                # 恢复节点引用并删除副本
                if copy_mapping:
                    print("恢复节点引用并删除三角化副本...")
                    start_operation("CleanupCopies")
                    for original_name, (copy_obj, node_list) in copy_mapping.items():
                        # 恢复所有节点/项目引用到原始物体
                        for node_or_item in node_list:
                            node_or_item.object_name = original_name
                        
                        # 删除副本（可能已被 submesh_model 合并删除）
                        if copy_obj:
                            try:
                                mesh_data = copy_obj.data
                                bpy.data.objects.remove(copy_obj, do_unlink=True)
                                if mesh_data:
                                    bpy.data.meshes.remove(mesh_data, do_unlink=True)
                            except (ReferenceError, ValueError):
                                pass
                            
                    print(f"已清理 {len(copy_mapping)} 个三角化副本")
                    end_operation("CleanupCopies")
            
            # 打印性能报告到控制台和文本编辑器
            end_operation("GenerateMod_Total")
            print_performance_report()
            save_performance_report_to_editor("性能统计报告")
            
            # 恢复用户原本的上下文状态（例如权重模式及选中的物体）
            set_user_context(context, original_user_context)
        
        return {'FINISHED'}
    
    def _get_export_objects_with_nodes(self):
        """获取当前蓝图中所有要导出的物体及其对应的节点，支持递归扫描嵌套蓝图
        
        注意：此方法不检查物体的隐藏状态，隐藏物体也会被收集
        隐藏状态的处理在预处理阶段进行
        """
        result = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return result
        
        output_nodes = [node for node in tree.nodes if node.bl_idname == 'SSMTNode_Result_Output']
        
        if not output_nodes:
            return result
        
        valid_nodes = set()
        visited_blueprints = set()
        
        def collect_valid_nodes(node, current_tree):
            """递归收集所有有效连接的节点，包括嵌套蓝图中的节点
            
            对于形态键控制器(SSMTNode_ShapeKeyController)，不继续向上遍历其输入，
            因为它会将输入物体增殖为多个变体，应作为叶子节点处理。
            """
            if node in valid_nodes:
                return
            
            if node.mute:
                return
            
            valid_nodes.add(node)
            
            # # 形态键控制器是增殖节点，不再向上追溯（避免重复收集上游Object_Info）
            # if getattr(node, 'bl_idname', '') == 'SSMTNode_ShapeKeyController':
            #     return
            
            for input_socket in node.inputs:
                for link in input_socket.links:
                    from_node = link.from_node
                    if from_node:
                        collect_valid_nodes(from_node, current_tree)
        
        def collect_nested_blueprint_nodes(nest_node, current_tree):
            """递归收集嵌套蓝图中的所有节点"""
            blueprint_name = getattr(nest_node, 'blueprint_name', '')
            if not blueprint_name:
                return
            
            if blueprint_name in visited_blueprints:
                return
            
            visited_blueprints.add(blueprint_name)
            
            nested_tree = bpy.data.node_groups.get(blueprint_name)
            if not nested_tree or nested_tree.bl_idname != 'SSMTBlueprintTreeType':
                return
            
            print(f"[Blueprint Nest] 扫描嵌套蓝图: {blueprint_name}")
            
            nested_output_nodes = [n for n in nested_tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
            
            if not nested_output_nodes:
                print(f"[Blueprint Nest] 警告: 嵌套蓝图 {blueprint_name} 没有输出节点")
                return
            
            for nested_output_node in nested_output_nodes:
                collect_valid_nodes(nested_output_node, nested_tree)
            
            for nested_node in nested_tree.nodes:
                if nested_node in valid_nodes and nested_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    collect_nested_blueprint_nodes(nested_node, nested_tree)
        
        for output_node in output_nodes:
            collect_valid_nodes(output_node, tree)
        
        for node in tree.nodes:
            if node not in valid_nodes:
                continue
            if node.bl_idname == 'SSMTNode_Blueprint_Nest':
                collect_nested_blueprint_nodes(node, tree)
        
        for node in valid_nodes:
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj and obj.type == 'MESH':
                        result.append((obj, node))
            elif node.bl_idname == 'SSMTNode_MultiFile_Export':
                for item in node.object_list:
                    obj_name = getattr(item, 'object_name', '')
                    if obj_name:
                        obj = bpy.data.objects.get(obj_name)
                        if obj and obj.type == 'MESH':
                            result.append((obj, item))
            elif node.bl_idname == 'SSMTNode_ShapeKeyController':
                # 使用新方法获取 (物体, 原始节点, 形态键名)
                if hasattr(node, 'get_connected_objects_with_nodes'):
                    expanded = node.get_connected_objects_with_nodes()
                    for obj, src_node, sk_name in expanded:
                        if obj and obj.type == 'MESH':
                            # 三元组：物体, 原始节点, 形态键名
                            result.append((obj, src_node, sk_name))
                else:
                    # 兼容旧版本（不应发生，但保留）
                    expanded = node.get_expanded_objects()
                    for obj, sk_name in expanded:
                        if obj and obj.type == 'MESH':
                            result.append((obj, node, sk_name))
        
        print(f"[Blueprint Nest] 共扫描 {len(visited_blueprints)} 个嵌套蓝图，找到 {len(result)} 个物体")
        return result
    
    # =========================================================================
    # 形态键变体导出相关方法
    # =========================================================================
    
    def _build_shapekey_variant_plan(self, obj_node_mapping):
        """从 obj_node_mapping 中构建形态键变体导出计划
        
        分析哪些物体来自形态键控制器，收集所有唯一的形态键槽序号，
        按槽序号排序后生成变体列表。
        
        Returns:
            dict 或 None:
            {
                'variants': [
                    {'slot_index': 0, ...},
                    {'slot_index': 1, ...},
                ],
                'has_base': True,   # 是否有全0基准变体
                'sk_controllers': [node, ...],  # 涉及的形态键控制器节点
            }
            如果没有有效的形态键变体则返回 None
        """
        import collections as _collections
        
        sk_entries = []       # (slot_index, sk_name, original_obj, node)
        sk_controllers = set()
        non_sk_objects = []
        
        for item in obj_node_mapping:
            if len(item) == 3:
                obj, node, sk_name = item
                # 检查 node 是否来自形态键控制器（通过 node 的 bl_idname 无法直接判断，因为现在是原始节点）
                # 改为：只要存在 sk_name 或 物体有形态键且 sk_name 为 None 的情况都视为变体
                if sk_name is not None:
                    sk_controllers.add(node)  # 这里只是标记，实际使用时会根据物体查找形态键
                    slot_index = self._get_shapekey_slot_index(obj, sk_name)
                    sk_entries.append((slot_index, sk_name, obj, node))
                else:
                    # 基准变体（全0）
                    pass
            else:
                non_sk_objects.append(item)
        
        if not sk_entries and not sk_controllers:
            return None
        
        # 按槽序号去重并排序
        seen = set()
        unique_variants = []
        for slot_index, sk_name, obj, node in sorted(sk_entries, key=lambda x: x[0]):
            if slot_index not in seen:
                seen.add(slot_index)
                unique_variants.append({
                    'slot_index': slot_index,
                })
        
        if not unique_variants:
            return None
        
        return {
            'variants': unique_variants,
            'has_base': True,
            'sk_controllers': list(sk_controllers),
        }
    
    def _get_shapekey_slot_index(self, obj, sk_name):
        """获取形态键在 key_blocks 中的序号（排除 reference_key）"""
        if not obj or not obj.data or not obj.data.shape_keys:
            return 0
        ref = obj.data.shape_keys.reference_key
        for i, kb in enumerate(obj.data.shape_keys.key_blocks):
            if kb == ref:
                continue
            if kb.name == sk_name:
                return i - 1  # 排除 reference_key 后的索引从 0 开始
        return 0
    
    def _execute_shapekey_variant_exports(self, context, obj_node_mapping, sk_variant_plan,
                                        original_user_context, wm, preview_export_only,
                                        use_parallel, blend_file_saved, blend_file_dirty,
                                        blend_file, mirror_workflow_enabled):
        import os
        import shutil
        # ... 其余代码
        """
        执行形态键控制器变体的多轮导出
        
        导出顺序：
        1. 先处理每个形态键为1的变体（buffer1001, buffer1002, ...）
        2. 最后处理全0基准变体（Buffer → 复制为 buffer0000）
        """
        variants = sk_variant_plan['variants']
        total_rounds = len(variants) + 1  # 变体数 + 基准
        mod_folder = GlobalConfig.path_generate_mod_folder()
        
        print(f"\n{'='*60}")
        print(f"[形态键变体] 开始多轮变体导出")
        print(f"  总轮数: {total_rounds} ({len(variants)} 个SK变体 + 1 基准)")
        print(f"{'='*60}\n")
        
        saved_original_sk_values = {}
        all_copy_mappings = {}  # 轮次 -> copy_mapping
        
        try:
            # ================================================================
            # 第1阶段：处理所有 SK=1 的变体（buffer1001, buffer1002, ...）
            # ================================================================
            for round_idx, variant in enumerate(variants):
                variant_num = round_idx + 1  # 1-based
                slot_index = variant['slot_index']
                buffer_suffix = f"{1000 + (slot_index + 1):04d}"
                
                print(f"\n--- 变体轮 {variant_num}/{len(variants)}: 槽位 {slot_index} -> Buffer{buffer_suffix} ---\n")
                
                # 设置形态键值：目标槽位=1, 其余=0
                self._apply_variant_state(obj_node_mapping, target_slot=slot_index, value=1.0)
                
                # 预处理此状态下的物体
                wm.progress_update(int((variant_num) / total_rounds * 80))
                
                if preview_export_only:
                    current_copy_mapping = {}
                else:
                    if use_parallel and blend_file_saved and not blend_file_dirty:
                        current_copy_mapping = self._parallel_preprocess(
                            context, obj_node_mapping, mirror_workflow_enabled)
                        if not current_copy_mapping:
                            current_copy_mapping = self._sequential_preprocess(
                                obj_node_mapping, mirror_workflow_enabled, wm,
                                len(obj_node_mapping), blend_file)
                    else:
                        current_copy_mapping = self._sequential_preprocess(
                            obj_node_mapping, mirror_workflow_enabled, wm,
                            len(obj_node_mapping), blend_file)
                
                all_copy_mappings[variant_num] = current_copy_mapping
                
                # 导出为 Buffer{suffix}
                GlobalConfig.buffer_folder_suffix = buffer_suffix
                BlueprintExportHelper.reset_export_state()
                M_GlobalKeyCounter.initialize()
                BlueprintExportHelper.apply_name_modify_to_crossib_nodes()
                
                self._run_single_export(preview_export_only)
                
                print(f"✓ 变体 '槽位 {slot_index}' 导出完成 → Buffer{buffer_suffix}")
            
            # ================================================================
            # 第2阶段：处理全0基准变体 (原始Buffer → 复制为 buffer0000)
            # ================================================================
            base_round = total_rounds
            base_suffix = "0000"
            print(f"\n--- 基准轮 {base_round}/{total_rounds}: 全0基准 -> Buffer -> buffer0000 ---\n")
            
            # 设置所有形态键归零
            self._apply_variant_state(obj_node_mapping, target_slot=None, value=0.0)
            
            wm.progress_update(int(total_rounds / total_rounds * 85))
            
            if preview_export_only:
                base_copy_mapping = {}
            else:
                if use_parallel and blend_file_saved and not blend_file_dirty:
                    base_copy_mapping = self._parallel_preprocess(
                        context, obj_node_mapping, mirror_workflow_enabled)
                    if not base_copy_mapping:
                        base_copy_mapping = self._sequential_preprocess(
                            obj_node_mapping, mirror_workflow_enabled, wm,
                            len(obj_node_mapping), blend_file)
                else:
                    base_copy_mapping = self._sequential_preprocess(
                        obj_node_mapping, mirror_workflow_enabled, wm,
                        len(obj_node_mapping), blend_file)
            
            all_copy_mappings[base_round] = base_copy_mapping
            
            # 先以标准 "Buffer" 名称导出
            GlobalConfig.buffer_folder_suffix = ""
            BlueprintExportHelper.reset_export_state()
            M_GlobalKeyCounter.initialize()
            BlueprintExportHelper.apply_name_modify_to_crossib_nodes()
            
            self._run_single_export(preview_export_only)
            
            if not preview_export_only:
                src_buffer = os.path.join(mod_folder, "Buffer")
                dst_buffer = os.path.join(mod_folder, "buffer0000")
                if os.path.exists(src_buffer):
                    # 处理已存在的目标目录
                    if os.path.exists(dst_buffer):
                        try:
                            shutil.rmtree(dst_buffer)
                        except PermissionError:
                            # 无法删除时重命名备份
                            import time
                            backup_name = f"{dst_buffer}_backup_{int(time.time())}"
                            os.rename(dst_buffer, backup_name)
                            print(f"已将原 buffer0000 重命名为 {backup_name}")
                    # 创建目标目录
                    os.makedirs(dst_buffer, exist_ok=True)
                    # 逐个文件复制，跳过被占用的文件
                    copied_count = 0
                    skipped_count = 0
                    for root, dirs, files in os.walk(src_buffer):
                        rel_path = os.path.relpath(root, src_buffer)
                        dest_dir = os.path.join(dst_buffer, rel_path)
                        os.makedirs(dest_dir, exist_ok=True)
                        for file in files:
                            src_file = os.path.join(root, file)
                            dst_file = os.path.join(dest_dir, file)
                            try:
                                shutil.copy2(src_file, dst_file)
                                copied_count += 1
                            except PermissionError:
                                print(f"  跳过无法复制的文件: {src_file}")
                                skipped_count += 1
                            except Exception as e:
                                print(f"  复制文件 {src_file} 失败: {e}")
                                skipped_count += 1
                    print(f"✓ 基准 Buffer 已复制为 buffer0000 (成功: {copied_count}, 跳过: {skipped_count})")
                else:
                    print(f"⚠ 未找到 Buffer 目录: {src_buffer}")
            
            print(f"\n{'='*60}")
            print(f"[形态键变体] 全部 {total_rounds} 轮导出完成！")
            print(f"{'='*60}\n")
            
            # ---- 收尾 ----
            wm.progress_update(90)
            self.report({'INFO'}, TR.translate("Generate Mod Success!"))
            TimerUtils.End("GenerateMod Mod")
            print(f"Mod导出路径: {mod_folder}")
            
            start_operation("PostProcessNodes")
            BlueprintExportHelper.clear_postprocess_caches()
            BlueprintExportHelper.execute_postprocess_nodes(mod_folder)
            end_operation("PostProcessNodes")
            
            start_operation("RestoreCrossIBParams")
            BlueprintExportHelper.restore_crossib_nodes_params()
            end_operation("RestoreCrossIBParams")
            
            wm.progress_update(100)
            wm.progress_end()
            CommandUtils.OpenGeneratedModFolder()
            
        finally:
            # 恢复原始形态键值
            self._restore_original_sk_values(saved_original_sk_values)
            BlueprintExportHelper.forced_target_tree_name = None
            BlueprintExportHelper.restore_export_path()
            
            # 清理所有轮次的副本
            if not preview_export_only:
                for round_idx, cm in all_copy_mappings.items():
                    if cm:
                        for orig_name, (copy_obj, node_list) in cm.items():
                            for n in node_list:
                                n.object_name = orig_name
                            if copy_obj:
                                try:
                                    mesh_data = copy_obj.data
                                    bpy.data.objects.remove(copy_obj, do_unlink=True)
                                    if mesh_data:
                                        bpy.data.meshes.remove(mesh_data, do_unlink=True)
                                except (ReferenceError, ValueError):
                                    pass
    
    def _apply_variant_state(self, obj_node_mapping, target_slot=None, value=0.0):
        """
        应用形态键变体状态到所有涉及物体
        
        Args:
            obj_node_mapping: 物体-节点映射
            target_slot: 目标槽序号（None表示全部归零）
            value: 目标形态键值
        """
        processed_objs = set()
        
        for item in obj_node_mapping:
            if len(item) == 3:
                obj = item[0]
            else:
                obj = item[0]
            
            if id(obj) in processed_objs:
                continue
            processed_objs.add(id(obj))
            
            if not obj or obj.type != 'MESH' or not obj.data or not obj.data.shape_keys:
                continue
            
            sk = obj.data.shape_keys
            
            # 应用变体状态
            for i, kb in enumerate(sk.key_blocks):
                if kb == sk.reference_key:
                    continue
                slot_idx = i - 1  # 排除 reference_key 后的索引从 0 开始
                if target_slot is not None and slot_idx == target_slot:
                    kb.value = value  # 目标槽位的形态键设为指定值
                else:
                    kb.value = 0.0  # 其余全部归零
            
            sk.key_blocks.update()
            obj.data.update_tag()
    
    def _restore_original_sk_values(self, saved_values):
        """恢复之前保存的形态键值"""
        pass  # 当前使用 apply_variant_state 直接操作，无需额外保存/恢复
    
    def _run_single_export(self, preview_export_only=False):
        """执行单次游戏导出（调用对应游戏的生成逻辑）"""
        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            from ..games.wwmi import ModModelWWMI
            migoto_mod_model = ModModelWWMI()
            migoto_mod_model.generate_unreal_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.YYSLS:
            from ..games.yysls import ModModelYYSLS
            migoto_mod_model = ModModelYYSLS(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.CTXMC or GlobalConfig.logic_name == LogicName.IdentityV2 or GlobalConfig.logic_name == LogicName.NierR:
            from ..games.identityv import ModModelIdentityV
            migoto_mod_model = ModModelIdentityV()
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.HIMI:
            from ..games.himi import ModModelHIMI
            migoto_mod_model = ModModelHIMI()
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.GIMI:
            from ..games.gimi import ModModelGIMI
            migoto_mod_model = ModModelGIMI()
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.SRMI:
            from ..games.srmi import ModModelSRMI
            migoto_mod_model = ModModelSRMI()
            migoto_mod_model.generate_unity_cs_config_ini()
        elif GlobalConfig.logic_name == LogicName.ZZMI:
            from ..games.zzmi import ModModelZZMI
            migoto_mod_model = ModModelZZMI(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.EFMI:
            from ..games.efmi import ModModelEFMI
            use_ssmt4 = Properties_ImportModel.use_ssmt4() if hasattr(Properties_ImportModel, 'use_ssmt4') else False
            migoto_mod_model = ModModelEFMI(skip_buffer_export=preview_export_only, use_ssmt4=use_ssmt4)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.AEMI:
            from ..games.yysls import ModModelYYSLS
            migoto_mod_model = ModModelYYSLS(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.UnityVS:
            from ..games.unity import ModModelUnity
            migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.AILIMIT or GlobalConfig.logic_name == LogicName.UnityCS:
            from ..games.unity import ModModelUnity
            migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_cs_config_ini()
        elif GlobalConfig.logic_name == LogicName.UnityCPU:
            from ..games.unity import ModModelUnity
            migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.UnityCSM:
            from ..games.unity import ModModelUnity
            migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
            migoto_mod_model.generate_unity_cs_config_ini()
        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            from ..games.snowbreak import ModModelSnowBreak
            migoto_mod_model = ModModelSnowBreak()
            migoto_mod_model.generate_ini()

    def _sequential_preprocess(self, obj_node_mapping, mirror_workflow_enabled, wm, total_objects, blend_file=None):
        """
        顺序预处理（单进程模式，支持缓存）
        
        Args:
            obj_node_mapping: 物体-节点映射列表
            mirror_workflow_enabled: 是否启用非镜像工作流
            wm: window_manager
            total_objects: 物体总数
            blend_file: blend 文件路径（用于缓存目录）
        
        Returns:
            copy_mapping: {原始物体名: (副本物体, [节点/项目列表])}
        """
        from ..utils.obj_utils import mesh_triangulate_beauty
        
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        
        cache_manager = get_cache_manager(blend_file)
        use_cache = Properties_ImportModel.use_preprocess_cache() if hasattr(Properties_ImportModel, 'use_preprocess_cache') else True
        
        copy_mapping = {}
        cache_hits = 0
        cache_misses = 0
        
        print(f"开始创建三角化副本（缓存: {'启用' if use_cache else '禁用'}）...")
        
        for i, item in enumerate(obj_node_mapping):
            progress = int((i + 1) / total_objects * 50)
            wm.progress_update(progress)
            
            # 兼容形态键控制器返回的三元组 (obj, node, sk_name)
            if len(item) == 2:
                original_obj, node_or_item = item
            else:
                original_obj, node_or_item = item[0], item[1]  # 忽略 sk_name
            
            if original_obj and original_obj.type == 'MESH':
                obj_name = original_obj.name
                
                original_name = original_obj.name
                
                if original_name in copy_mapping:
                    copy_obj, node_list = copy_mapping[original_name]
                    node_list.append(node_or_item)
                    node_or_item.original_object_name = original_name
                    node_or_item.object_name = copy_obj.name
                    print(f"复用副本: {original_name} -> {copy_obj.name} (节点数: {len(node_list)})")
                    continue
                
                if original_name.endswith("-Original"):
                    copy_name = original_name.replace("-Original", "-copy_Original")
                else:
                    copy_name = f"{original_name}_copy"
                
                copy_obj = None
                cache_used = False
                
                if use_cache:
                    fingerprint = FingerprintCalculator.calculate_fingerprint(original_obj, mirror_workflow_enabled)
                    print(f"[Cache] 物体 {obj_name} 指纹: v={fingerprint.vertex_count}, vh={fingerprint.vertex_hash[:8]}...")
                    
                    start_operation("CacheCheck", obj_name)
                    cached_obj = cache_manager.load_cache(obj_name, fingerprint, bpy.context.scene)
                    end_operation("CacheCheck")
                    
                    if cached_obj:
                        cached_obj.name = copy_name
                        copy_obj = cached_obj
                        cache_used = True
                        cache_hits += 1
                        print(f"[Cache] 命中: {obj_name}")
                
                if not copy_obj:
                    cache_misses += 1
                    
                    start_operation("CreateCopy", obj_name)
                    copy_obj = original_obj.copy()
                    copy_obj.data = original_obj.data.copy()
                    end_operation("CreateCopy")
                    
                    start_operation("LinkCopy", obj_name)
                    copy_obj.name = copy_name
                    bpy.context.scene.collection.objects.link(copy_obj)
                    copy_obj.hide_set(False)
                    if copy_obj.name in bpy.context.view_layer.objects:
                        bpy.context.view_layer.objects[copy_obj.name].hide_viewport = False
                    end_operation("LinkCopy")
                    
                    has_armature = any(mod.type == 'ARMATURE' for mod in copy_obj.modifiers)
                    
                    if mirror_workflow_enabled:
                        start_operation("MirrorWorkflow_Pre", obj_name)
                        ObjUtils.prepare_copy_for_mirror_workflow(copy_obj)
                        end_operation("MirrorWorkflow_Pre")
                    elif has_armature:
                        start_operation("ApplyArmature", obj_name)
                        ObjUtils._apply_all_modifiers(copy_obj)
                        end_operation("ApplyArmature")
                    
                    start_operation("Triangulate", obj_name)
                    mesh_triangulate_beauty(copy_obj)
                    end_operation("Triangulate")
                    
                    start_operation("ApplyTransforms", obj_name)
                    ObjUtils.apply_all_transforms(copy_obj)
                    end_operation("ApplyTransforms")
                    
                    if mirror_workflow_enabled:
                        start_operation("MirrorWorkflow_Post", obj_name)
                        ObjUtils.apply_mirror_transform(copy_obj)
                        ObjUtils.flip_face_normals(copy_obj)
                        end_operation("MirrorWorkflow_Post")
                    
                    start_operation("ClearMaterials", obj_name)
                    ObjUtils.clear_materials(copy_obj)
                    end_operation("ClearMaterials")
                    
                    if use_cache:
                        start_operation("CacheStore", obj_name)
                        cache_manager.store_cache(obj_name, fingerprint, copy_obj)
                        end_operation("CacheStore")
                
                node_or_item.original_object_name = original_name
                copy_mapping[original_name] = (copy_obj, [node_or_item])
                
                if not cache_used:
                    print(f"创建副本: {original_name} -> {copy_obj.name}")
        
        print(f"[Cache] 统计: 命中={cache_hits}, 未命中={cache_misses}")
        
        if copy_mapping:
            self._execute_processing_chain_for_objects(copy_mapping, tree)
        
        return copy_mapping
    
    def _execute_processing_chain_for_objects(self, copy_mapping, tree):
        """
        按处理链顺序执行所有处理节点（支持多线程）
        
        逻辑：
        1. 收集所有处理节点（顶点组处理节点和名称修改节点），按连接顺序排序
        2. 对于每个处理节点，收集所有连接到它的物体
        3. 按顺序执行每个处理节点
        4. 对于顶点组处理节点，使用多线程处理多个物体
        """
        all_process_nodes = []
        visited = set()
        
        def collect_all_process_nodes(node, current_tree):
            """从输出节点开始，收集所有处理节点（顶点组处理节点和名称修改节点）"""
            if node in visited:
                return
            visited.add(node)
            
            if node.mute:
                return
            
            if node.bl_idname == 'SSMTNode_VertexGroupProcess':
                all_process_nodes.append((node, 'vg_process'))
            elif node.bl_idname == 'SSMTNode_Object_Name_Modify':
                all_process_nodes.append((node, 'name_modify'))
            
            for input_socket in node.inputs:
                for link in input_socket.links:
                    collect_all_process_nodes(link.from_node, current_tree)
        
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        for output_node in output_nodes:
            collect_all_process_nodes(output_node, tree)
        
        all_process_nodes.reverse()
        
        print(f"[ProcessingChain] 收集到 {len(all_process_nodes)} 个处理节点")
        
        for node, node_type in all_process_nodes:
            connected_objects = []
            for original_name, (copy_obj, node_list) in copy_mapping.items():
                if self._is_object_connected_to_node(original_name, node, tree):
                    connected_objects.append((original_name, copy_obj, node_list))
            
            if not connected_objects:
                continue
            
            if node_type == 'name_modify':
                for original_name, copy_obj, node_list in connected_objects:
                    if hasattr(node, 'is_valid') and node.is_valid():
                        current_name = copy_obj.name
                        new_name = node.get_modified_object_name(current_name)
                        if new_name != current_name:
                            copy_obj.name = new_name
                            print(f"[NameModify] {original_name}: {current_name} -> {new_name}")
            
            elif node_type == 'vg_process':
                start_operation(f"VGProcess_{node.name}", "batch")
                
                objects_to_process = [copy_obj for _, copy_obj, _ in connected_objects]
                
                if len(objects_to_process) > 1:
                    print(f"[VGProcess] 节点 {node.name}: 多线程处理 {len(objects_to_process)} 个物体")
                    try:
                        all_stats = node.process_objects_batch(objects_to_process, max_workers=4)
                        for obj_name, stats in all_stats.items():
                            if any(v > 0 for v in stats.values()):
                                print(f"[VGProcess] {obj_name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                    except Exception as e:
                        print(f"[VGProcess] 批量处理节点 {node.name} 时出错: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    for original_name, copy_obj, _ in connected_objects:
                        try:
                            stats = node.process_object(copy_obj)
                            if any(v > 0 for v in stats.values()):
                                print(f"[VGProcess] {original_name} 节点 {node.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                        except Exception as e:
                            print(f"[VGProcess] 处理物体 {original_name} 时出错: {e}")
                            import traceback
                            traceback.print_exc()
                
                end_operation(f"VGProcess_{node.name}")
        
        for original_name, (copy_obj, node_list) in copy_mapping.items():
            for node_or_item in node_list:
                node_or_item.object_name = copy_obj.name
    
    def _parallel_preprocess(self, context, obj_node_mapping, mirror_workflow_enabled):
        """
        并行预处理（多进程模式，支持缓存）
        
        仅处理第3步：模型预处理
        预处理完成后将结果加载回当前场景继续后续流程
        
        Args:
            context: Blender 上下文
            obj_node_mapping: 物体-节点映射列表
            mirror_workflow_enabled: 是否启用非镜像工作流
        
        Returns:
            copy_mapping: {原始物体名: (副本物体, [节点/项目列表])}
        """
        from ..utils.parallel_preprocess import ParallelPreprocessManager, load_preprocessed_objects
        
        wm = context.window_manager
        blend_file = bpy.data.filepath
        
        cache_manager = get_cache_manager(blend_file)
        use_cache = Properties_ImportModel.use_preprocess_cache() if hasattr(Properties_ImportModel, 'use_preprocess_cache') else True
        
        object_names = []
        for item in obj_node_mapping:
            if len(item) == 2:
                obj, _ = item
            else:
                obj = item[0]
            if obj:
                object_names.append(obj.name)

        node_mapping = {}
        for item in obj_node_mapping:
            if len(item) == 2:
                obj, node = item
            else:
                obj, node = item[0], item[1]
            if obj:
                if obj.name not in node_mapping:
                    node_mapping[obj.name] = (obj, [node])
                else:
                    node_mapping[obj.name][1].append(node)
        
        cached_objects = {}
        objects_to_process = []
        fingerprints = {}
        manager = None
        loaded_objects = None
        
        if use_cache:
            print(f"[ParallelPreprocess] 检查缓存...")
            for obj_name in object_names:
                original_obj = node_mapping[obj_name][0]
                fingerprint = FingerprintCalculator.calculate_fingerprint(original_obj, mirror_workflow_enabled)
                fingerprints[obj_name] = fingerprint
                
                cached_obj = cache_manager.load_cache(obj_name, fingerprint, bpy.context.scene)
                if cached_obj:
                    cached_objects[obj_name] = cached_obj
                    print(f"[Cache] 命中: {obj_name}")
                else:
                    objects_to_process.append(obj_name)
            
            print(f"[Cache] 统计: 命中={len(cached_objects)}, 未命中={len(objects_to_process)}")
        else:
            objects_to_process = object_names[:]
        
        if objects_to_process:
            num_workers = Properties_ImportModel.get_parallel_worker_count()
            manager = ParallelPreprocessManager(num_workers=num_workers)
            
            def progress_callback(progress):
                wm.progress_update(int(progress * 0.5 * len(objects_to_process) / len(object_names)))
            
            print(f"[ParallelPreprocess] 开始并行预处理 {len(objects_to_process)} 个物体...")
            print(f"[ParallelPreprocess] 工作进程数: {num_workers}")
            
            object_blend_map = manager.preprocess_parallel(
                blend_file=blend_file,
                object_names=objects_to_process,
                mirror_workflow=mirror_workflow_enabled,
                progress_callback=progress_callback
            )
            
            if manager.validation_error:
                self.report({'ERROR'}, manager.validation_error)
                manager.cleanup()
                return None
            
            if not object_blend_map:
                manager.cleanup()
                if cached_objects:
                    pass
                else:
                    return None
            
            if object_blend_map:
                wm.progress_update(45)
                print(f"[ParallelPreprocess] 加载预处理结果...")
                
                try:
                    start_operation("LoadPreprocessedObjects")
                    loaded_objects = load_preprocessed_objects(object_blend_map)
                    print(f"[ParallelPreprocess] loaded_objects: {list(loaded_objects.keys()) if loaded_objects else 'None'}")
                    end_operation("LoadPreprocessedObjects")
                except Exception as e:
                    print(f"[ParallelPreprocess] 加载失败: {e}")
                    import traceback
                    traceback.print_exc()
                    manager.cleanup()
                    if not cached_objects:
                        return None
                    loaded_objects = {}
                
                if use_cache and loaded_objects:
                    print(f"[ParallelPreprocess] 存储缓存...")
                    for obj_name in objects_to_process:
                        if obj_name in fingerprints:
                            original_name = obj_name
                            if original_name.endswith("-Original"):
                                copy_name = original_name.replace("-Original", "-copy_Original")
                            else:
                                copy_name = f"{original_name}_copy"
                            
                            if copy_name in loaded_objects:
                                cache_manager.store_cache(obj_name, fingerprints[obj_name], loaded_objects[copy_name])
                
                manager.cleanup()
        else:
            print(f"[ParallelPreprocess] 所有物体都命中缓存，跳过并行预处理")
        
        wm.progress_update(50)
        
        copy_mapping = {}
        for original_name, (original_obj, node_list) in node_mapping.items():
            if original_name.endswith("-Original"):
                copy_name = original_name.replace("-Original", "-copy_Original")
            else:
                copy_name = f"{original_name}_copy"
            
            copy_obj = None
            
            if original_name in cached_objects:
                cached_obj = cached_objects[original_name]
                cached_obj.name = copy_name
                copy_obj = cached_obj
            
            if copy_obj is None and loaded_objects:
                if copy_name in loaded_objects:
                    copy_obj = loaded_objects[copy_name]
            
            if copy_obj:
                for node_or_item in node_list:
                    node_or_item.original_object_name = original_name
                    node_or_item.object_name = copy_obj.name
                copy_mapping[original_name] = (copy_obj, node_list)
                
                print(f"[ParallelPreprocess] 加载预处理结果: {original_name} -> {copy_obj.name} (节点数: {len(node_list)})")
            else:
                print(f"[ParallelPreprocess] 警告: 副本 {copy_name} 未在预处理结果中找到")
        
        if not copy_mapping:
            print(f"[ParallelPreprocess] copy_mapping 为空，加载失败")
            if manager:
                manager.cleanup()
            return None
        
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        
        print(f"[ParallelPreprocess] 开始按处理链执行...")
        
        if copy_mapping:
            self._execute_processing_chain_for_objects(copy_mapping, tree)
        
        if manager:
            start_operation("ParallelCleanup")
            manager.cleanup()
            end_operation("ParallelCleanup")
        wm.progress_update(50)
        
        return copy_mapping
    
    def _get_export_objects(self):
        """获取当前蓝图中所有要导出的物体"""
        objects = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return objects
        
        for node in tree.nodes:
            if node.mute:
                continue
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj and obj.type == 'MESH':
                        objects.append(obj)
        
        return objects
    
    def _get_vg_process_nodes(self):
        """获取当前蓝图中所有顶点组处理节点，按照连接顺序排序"""
        nodes = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return nodes
        
        visited_blueprints = set()
        visited_nodes = set()
        
        def collect_vg_process_nodes_in_order(current_node, current_tree):
            """按照连接顺序递归收集顶点组处理节点"""
            if current_node in visited_nodes:
                return
            visited_nodes.add(current_node)
            
            if current_node.mute:
                return
            
            if current_node.bl_idname == 'SSMTNode_VertexGroupProcess':
                nodes.append(current_node)
            elif current_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(current_node, 'blueprint_name', '')
                if blueprint_name and blueprint_name not in visited_blueprints:
                    visited_blueprints.add(blueprint_name)
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        nested_output = None
                        for n in nested_tree.nodes:
                            if n.bl_idname == 'SSMTNode_Result_Output':
                                nested_output = n
                                break
                        if nested_output:
                            collect_vg_process_nodes_in_order(nested_output, nested_tree)
            
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    collect_vg_process_nodes_in_order(link.from_node, current_tree)
        
        for output_node in tree.nodes:
            if output_node.bl_idname == 'SSMTNode_Result_Output':
                collect_vg_process_nodes_in_order(output_node, tree)
                break
        
        nodes.reverse()
        
        print(f"[VGProcess] 收集到 {len(nodes)} 个顶点组处理节点，顺序: {[n.name for n in nodes]}")
        return nodes
    
    def _get_name_modify_nodes(self):
        """获取所有名称修改节点（按照连接顺序）"""
        result = []
        
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return result
        
        visited = set()
        
        def collect_name_modify_nodes_in_order(node, current_tree):
            """按照连接顺序收集名称修改节点"""
            if node in visited:
                return
            visited.add(node)
            
            if node.mute:
                return
            
            # 如果是名称修改节点，添加到结果中
            if node.bl_idname == 'SSMTNode_Object_Name_Modify':
                result.append(node)
                print(f"[NameModify] 找到名称修改节点: {node.name}")
            
            # 递归检查连接的节点
            for input_socket in node.inputs:
                if input_socket.is_linked:
                    for link in input_socket.links:
                        from_node = link.from_node
                        collect_name_modify_nodes_in_order(from_node, current_tree)
        
        def collect_nested_blueprint_nodes(nest_node, current_tree):
            """递归收集嵌套蓝图中的名称修改节点"""
            if nest_node.mute:
                return
            
            blueprint_name = getattr(nest_node, 'blueprint_name', '')
            if not blueprint_name:
                return
            
            if blueprint_name in visited:
                return
            
            visited.add(blueprint_name)
            
            nested_tree = bpy.data.node_groups.get(blueprint_name)
            if not nested_tree or nested_tree.bl_idname != 'SSMTBlueprintTreeType':
                return
            
            print(f"[NameModify] 扫描嵌套蓝图: {blueprint_name}")
            
            nested_output_nodes = [n for n in nested_tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
            
            if not nested_output_nodes:
                print(f"[NameModify] 警告: 嵌套蓝图 {blueprint_name} 没有输出节点")
                return
            
            for nested_output_node in nested_output_nodes:
                collect_name_modify_nodes_in_order(nested_output_node, nested_tree)
            
            for nested_node in nested_tree.nodes:
                if nested_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    collect_nested_blueprint_nodes(nested_node, nested_tree)
        
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        for output_node in output_nodes:
            collect_name_modify_nodes_in_order(output_node, tree)
        
        for node in tree.nodes:
            if node.bl_idname == 'SSMTNode_Blueprint_Nest':
                collect_nested_blueprint_nodes(node, tree)
        
        # 反转结果，因为是从输出节点开始递归的，所以需要反转顺序
        result.reverse()
        
        print(f"[NameModify] 共找到 {len(result)} 个名称修改节点，顺序: {[n.name for n in result]}")
        return result
    
    def _get_vg_process_nodes_for_object(self, obj_name, vg_process_nodes):
        """获取应该应用于指定物体的顶点组处理节点列表"""
        result = []
        
        for node in vg_process_nodes:
            node_tree = node.id_data
            is_connected = self._is_object_connected_to_vg_process(obj_name, node, node_tree)
            print(f"[VGProcess] 检查节点 {node.name} 是否连接到物体 {obj_name}: {is_connected}")
            if is_connected:
                result.append(node)
        
        return result
    
    def _is_object_connected_to_vg_process(self, obj_name, vg_process_node, node_tree):
        """检查物体是否连接到指定的顶点组处理节点（支持嵌套蓝图）"""
        visited = set()
        
        def find_all_object_names_for_vg_process(current_node, current_tree, depth=0):
            """从顶点组处理节点开始，找到所有连接的物体名称"""
            if current_node in visited:
                return []
            visited.add(current_node)
            
            if current_node.mute:
                return []
            
            indent = "  " * depth
            print(f"[VGProcess]{indent} 搜索节点: {current_node.name} (类型: {current_node.bl_idname})")
            
            object_names = []
            
            if current_node.bl_idname == 'SSMTNode_Object_Info':
                found_name = getattr(current_node, 'original_object_name', '') or getattr(current_node, 'object_name', '')
                if found_name:
                    print(f"[VGProcess]{indent} 找到物体节点: {found_name}")
                    return [found_name]
            
            elif current_node.bl_idname == 'SSMTNode_MultiFile_Export':
                object_list = getattr(current_node, 'object_list', [])
                for item in object_list:
                    item_name = getattr(item, 'original_object_name', '') or getattr(item, 'object_name', '')
                    if item_name:
                        object_names.append(item_name)
                if object_names:
                    print(f"[VGProcess]{indent} 找到多文件导出节点，包含 {len(object_names)} 个物体")
                    return object_names
            
            elif current_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(current_node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for nested_node in nested_tree.nodes:
                            if nested_node.bl_idname == 'SSMTNode_Result_Output':
                                names = find_all_object_names_for_vg_process(nested_node, nested_tree, depth+1)
                                object_names.extend(names)
            
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    names = find_all_object_names_for_vg_process(link.from_node, current_tree, depth+1)
                    object_names.extend(names)
            
            return object_names
        
        def get_connected_object_names(vg_node, tree):
            """获取顶点组处理节点连接的所有物体名称"""
            object_names = []
            for input_socket in vg_node.inputs:
                if input_socket.name == "物体" and input_socket.is_linked:
                    for link in input_socket.links:
                        from_node = link.from_node
                        print(f"[VGProcess] 物体输入连接到: {from_node.name} (类型: {from_node.bl_idname})")
                        names = find_all_object_names_for_vg_process(from_node, tree, 1)
                        object_names.extend(names)
            return list(set(object_names))
        
        connected_objects = get_connected_object_names(vg_process_node, node_tree)
        print(f"[VGProcess] 顶点组处理节点 '{vg_process_node.name}' 连接的物体: {connected_objects}")
        
        return obj_name in connected_objects
    
    def _get_processing_chain_for_object(self, obj_name, tree):
        """
        获取指定物体经过的处理链（按连接顺序）
        返回: [(节点, 节点类型), ...] 其中节点类型为 'name_modify' 或 'vg_process'
        
        新逻辑：从输出节点开始反向收集所有处理节点，然后过滤出连接到当前物体的节点
        """
        result = []
        visited = set()
        all_process_nodes = []
        
        def collect_all_process_nodes(node, current_tree):
            """从输出节点开始，收集所有处理节点（顶点组处理节点和名称修改节点）"""
            if node in visited:
                return
            visited.add(node)
            
            if node.bl_idname == 'SSMTNode_VertexGroupProcess':
                all_process_nodes.append((node, 'vg_process'))
            elif node.bl_idname == 'SSMTNode_Object_Name_Modify':
                all_process_nodes.append((node, 'name_modify'))
            
            for input_socket in node.inputs:
                for link in input_socket.links:
                    collect_all_process_nodes(link.from_node, current_tree)
        
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        for output_node in output_nodes:
            collect_all_process_nodes(output_node, tree)
        
        all_process_nodes.reverse()
        
        for node, node_type in all_process_nodes:
            if self._is_object_connected_to_node(obj_name, node, tree):
                result.append((node, node_type))
        
        print(f"[ProcessingChain] 物体 {obj_name} 的处理链: {[(n.name, t) for n, t in result]}")
        return result
    
    def _is_object_connected_to_node(self, obj_name, target_node, node_tree):
        """检查物体是否连接到指定的节点（支持嵌套蓝图）"""
        visited = set()
        
        def find_all_object_names(current_node, current_tree, depth=0):
            """从节点开始，找到所有连接的物体名称"""
            if current_node in visited:
                return []
            visited.add(current_node)
            
            if current_node.mute:
                return []
            
            object_names = []
            
            if current_node.bl_idname == 'SSMTNode_Object_Info':
                found_name = getattr(current_node, 'original_object_name', '') or getattr(current_node, 'object_name', '')
                if found_name:
                    return [found_name]
            
            elif current_node.bl_idname == 'SSMTNode_MultiFile_Export':
                object_list = getattr(current_node, 'object_list', [])
                for item in object_list:
                    item_name = getattr(item, 'original_object_name', '') or getattr(item, 'object_name', '')
                    if item_name:
                        object_names.append(item_name)
                if object_names:
                    return object_names
            
            elif current_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(current_node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for nested_node in nested_tree.nodes:
                            if nested_node.bl_idname == 'SSMTNode_Result_Output':
                                names = find_all_object_names(nested_node, nested_tree, depth+1)
                                object_names.extend(names)
            
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    names = find_all_object_names(link.from_node, current_tree, depth+1)
                    object_names.extend(names)
            
            return object_names
        
        object_names = find_all_object_names(target_node, node_tree)
        return obj_name in object_names
    
    def _apply_vg_process_nodes(self, obj, vg_process_nodes):
        """应用顶点组处理节点到物体"""
        if not vg_process_nodes or not obj or obj.type != 'MESH':
            return
        
        applicable_nodes = self._get_vg_process_nodes_for_object(obj.name, vg_process_nodes)
        
        for i, node in enumerate(applicable_nodes):
            try:
                start_operation(f"VGProcess_{node.name}", obj.name)
                stats = node.process_object(obj)
                if any(v > 0 for v in stats.values()):
                    print(f"[VGProcess] {obj.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                end_operation(f"VGProcess_{node.name}")
            except Exception as e:
                print(f"[Process] 处理物体 {obj.name} 时出错: {e}")
                import traceback
                traceback.print_exc()
                end_operation(f"VGProcess_{node.name}")
    
    def _apply_vg_process_batch(self, pending_tasks, max_workers=4):
        """批量处理顶点组任务（多线程优化版）
        
        Args:
            pending_tasks: [(obj, node), ...] 待处理的物体-节点对
            max_workers: 最大线程数
        """
        if not pending_tasks:
            return
        
        node_to_objects = {}
        for obj, node in pending_tasks:
            if node not in node_to_objects:
                node_to_objects[node] = []
            node_to_objects[node].append(obj)
        
        for node, objs in node_to_objects.items():
            if len(objs) > 1:
                print(f"[VGProcess] 节点 {node.name}: 多线程处理 {len(objs)} 个物体")
                try:
                    all_stats = node.process_objects_batch(objs, max_workers=max_workers)
                    for obj_name, stats in all_stats.items():
                        if any(v > 0 for v in stats.values()):
                            print(f"[VGProcess] {obj_name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[VGProcess] 批量处理节点 {node.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
            elif len(objs) == 1:
                obj = objs[0]
                try:
                    stats = node.process_object(obj)
                    if any(v > 0 for v in stats.values()):
                        print(f"[VGProcess] {obj.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[Process] 处理物体 {obj.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
    
    def _apply_vg_process_nodes_batch(self, objects, vg_process_nodes, max_workers=4):
        """批量应用顶点组处理节点到多个物体（多线程优化版）"""
        if not vg_process_nodes or not objects:
            return
        
        mesh_objects = [obj for obj in objects if obj and obj.type == 'MESH']
        if not mesh_objects:
            return
        
        print(f"[VGProcess] 开始批量处理 {len(mesh_objects)} 个网格物体（多线程模式）")
        
        node_to_objects = {}
        for obj in mesh_objects:
            applicable_nodes = self._get_vg_process_nodes_for_object(obj.name, vg_process_nodes)
            for node in applicable_nodes:
                if node not in node_to_objects:
                    node_to_objects[node] = []
                node_to_objects[node].append(obj)
        
        for node, objs in node_to_objects.items():
            if len(objs) > 1:
                print(f"[VGProcess] 节点 {node.name}: 多线程处理 {len(objs)} 个物体")
                start_operation(f"VGProcess_{node.name}", "batch")
                try:
                    all_stats = node.process_objects_batch(objs, max_workers=max_workers)
                    for obj_name, stats in all_stats.items():
                        if any(v > 0 for v in stats.values()):
                            print(f"[VGProcess] {obj_name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[VGProcess] 批量处理节点 {node.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
                end_operation(f"VGProcess_{node.name}")
            elif len(objs) == 1:
                obj = objs[0]
                start_operation(f"VGProcess_{node.name}", obj.name)
                try:
                    stats = node.process_object(obj)
                    if any(v > 0 for v in stats.values()):
                        print(f"[VGProcess] {obj.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[Process] 处理物体 {obj.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
                end_operation(f"VGProcess_{node.name}")
    

class SSMTQuickPartialExport(bpy.types.Operator):
    bl_idname = "ssmt.quick_partial_export"
    bl_label = TR.translate("快速局部导出")
    bl_description = "对当前选中的物体进行快速导出，自动创建临时蓝图架构"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "请先选择要导出的网格物体")
            return {'CANCELLED'}
        
        print(f"[QuickExport] 开始快速局部导出，选中物体数量: {len(selected_objects)}")
        
        use_ssmt4 = Properties_ImportModel.use_ssmt4()
        if use_ssmt4:
            GlobalConfig.read_from_main_json_ssmt4()
        else:
            GlobalConfig.read_from_main_json()
        
        temp_tree_name = f"_QuickExport_Temp_{GlobalConfig.workspacename}" if GlobalConfig.workspacename else "_QuickExport_Temp"
        
        temp_tree = bpy.data.node_groups.get(temp_tree_name)
        if temp_tree:
            bpy.data.node_groups.remove(temp_tree)
        
        temp_tree = bpy.data.node_groups.new(name=temp_tree_name, type='SSMTBlueprintTreeType')
        temp_tree.use_fake_user = False
        
        try:
            output_node = temp_tree.nodes.new('SSMTNode_Result_Output')
            output_node.location = (600, 0)
            
            obj_nodes = []
            y_offset = 0
            
            for obj in selected_objects:
                obj_node = temp_tree.nodes.new('SSMTNode_Object_Info')
                obj_node.object_name = obj.name
                obj_node.location = (0, y_offset)
                
                if use_ssmt4:
                    obj_name = obj.name
                    if "." in obj_name:
                        obj_name_total_split = obj_name.split(".")
                        obj_name_split = obj_name_total_split[0].split("-")
                        
                        if len(obj_name_split) >= 3:
                            obj_node.draw_ib = obj_name_split[0]
                            obj_node.index_count = obj_name_split[1]
                            obj_node.first_index = obj_name_split[2]
                        elif len(obj_name_split) >= 2:
                            obj_node.draw_ib = obj_name_split[0]
                            obj_node.index_count = obj_name_split[1]
                        elif len(obj_name_split) >= 1:
                            obj_node.draw_ib = obj_name_split[0]
                        
                        if len(obj_name_total_split) >= 2:
                            obj_node.alias_name = ".".join(obj_name_total_split[1:])
                    elif "-" in obj_name:
                        obj_name_split = obj_name.split("-")
                        obj_node.draw_ib = obj_name_split[0]
                        if len(obj_name_split) >= 2:
                            obj_node.index_count = obj_name_split[1]
                        if len(obj_name_split) >= 3:
                            obj_node.first_index = obj_name_split[2]
                    
                    print(f"[QuickExport] SSMT4模式，物体: {obj_name}, DrawIB: {obj_node.draw_ib}, IndexCount: {obj_node.index_count}")
                
                obj_nodes.append(obj_node)
                y_offset -= 200
            
            if len(obj_nodes) == 1:
                temp_tree.links.new(obj_nodes[0].outputs[0], output_node.inputs[0])
            else:
                group_node = temp_tree.nodes.new('SSMTNode_Object_Group')
                group_node.location = (300, 0)
                
                for i, obj_node in enumerate(obj_nodes):
                    while len(group_node.inputs) <= i:
                        group_node.inputs.new('SSMTSocketObject', f"Input {len(group_node.inputs) + 1}")
                    temp_tree.links.new(obj_node.outputs[0], group_node.inputs[i])
                
                temp_tree.links.new(group_node.outputs[0], output_node.inputs[0])
            
            print(f"[QuickExport] 临时蓝图树创建完成: {temp_tree_name}")
            print(f"[QuickExport] 节点数量: {len(temp_tree.nodes)}, 连接数量: {len(temp_tree.links)}")
            
            bpy.ops.ssmt.generate_mod_blueprint(node_tree_name=temp_tree_name)
            
            self.report({'INFO'}, f"已导出 {len(selected_objects)} 个物体")
            
        except Exception as e:
            print(f"[QuickExport] 导出失败: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"导出失败: {e}")
            
        finally:
            if temp_tree:
                try:
                    bpy.data.node_groups.remove(temp_tree)
                    print(f"[QuickExport] 已清理临时蓝图树: {temp_tree_name}")
                except Exception as e:
                    print(f"[QuickExport] 清理临时蓝图树失败: {e}")
        
        return {'FINISHED'}


def register():
    bpy.utils.register_class(SSMTGenerateModBlueprint)
    bpy.utils.register_class(SSMTSelectGenerateModFolder)
    bpy.utils.register_class(SSMTQuickPartialExport)
    bpy.utils.register_class(SSMTClearPreprocessCache)


def unregister():
    bpy.utils.unregister_class(SSMTGenerateModBlueprint)
    bpy.utils.unregister_class(SSMTSelectGenerateModFolder)
    bpy.utils.unregister_class(SSMTQuickPartialExport)
    bpy.utils.unregister_class(SSMTClearPreprocessCache)