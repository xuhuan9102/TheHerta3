import bpy


class Properties_WWMI(bpy.types.PropertyGroup):
    import_merged_vgmap:bpy.props.BoolProperty(
        name="使用融合统一顶点组",
        description="导入时是否导入融合后的顶点组 (Unreal的合并顶点组技术会用到)，一般鸣潮Mod需要勾选来降低制作Mod的复杂度",
        default=True
    ) # type: ignore

    @classmethod
    def import_merged_vgmap(cls):
        '''
        bpy.context.scene.properties_wwmi.import_merged_vgmap
        '''
        return bpy.context.scene.properties_wwmi.import_merged_vgmap

    ignore_muted_shape_keys:bpy.props.BoolProperty(
        name="忽略未启用的形态键",
        description="勾选此项后，未勾选启用的形态键在生成Mod时会被忽略，勾选的形态键会参与生成Mod",
        default=True
    ) # type: ignore

    # ignore_muted_shape_keys
    @classmethod
    def ignore_muted_shape_keys(cls):
        '''
        bpy.context.scene.properties_wwmi.ignore_muted_shape_keys
        '''
        return bpy.context.scene.properties_wwmi.ignore_muted_shape_keys
    
    # apply_all_modifiers
    apply_all_modifiers:bpy.props.BoolProperty(
        name="应用所有修改器",
        description="勾选此项后，生成Mod之前会自动对物体应用所有修改器",
        default=False
    ) # type: ignore
    
    @classmethod
    def apply_all_modifiers(cls):
        '''
        bpy.context.scene.properties_wwmi.apply_all_modifiers
        '''
        return bpy.context.scene.properties_wwmi.apply_all_modifiers
    
    # import_skip_empty_vertex_groups
    import_skip_empty_vertex_groups:bpy.props.BoolProperty(
        name="跳过空顶点组",
        description="勾选此项后，导入时会跳过空的顶点组",
        default=True
    ) # type: ignore

    @classmethod
    def import_skip_empty_vertex_groups(cls):
        '''
        bpy.context.scene.properties_wwmi.import_skip_empty_vertex_groups
        '''
        return bpy.context.scene.properties_wwmi.import_skip_empty_vertex_groups
    
    # export_add_missing_vertex_groups
    export_add_missing_vertex_groups:bpy.props.BoolProperty(
        name="导出时添加缺失顶点组",
        description="勾选此项后，生成Mod时会自动重新排列并填补数字顶点组间的间隙空缺",
        default=True
    ) # type: ignore

    @classmethod
    def export_add_missing_vertex_groups(cls):
        '''
        bpy.context.scene.properties_wwmi.export_add_missing_vertex_groups
        '''
        return bpy.context.scene.properties_wwmi.export_add_missing_vertex_groups
    
    dedup_options_expanded:bpy.props.BoolProperty(
        name="顶点去重精度控制",
        description="展开/收缩顶点去重精度控制选项",
        default=False
    ) # type: ignore

    @classmethod
    def dedup_options_expanded(cls):
        return bpy.context.scene.properties_wwmi.dedup_options_expanded
    
    dedup_include_position:bpy.props.BoolProperty(
        name="位置参与去重",
        description="顶点位置是否参与去重判断。关闭后位置不同的顶点也可能被合并",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_position(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_position
    
    dedup_include_normal:bpy.props.BoolProperty(
        name="法线参与去重",
        description="顶点法线是否参与去重判断。关闭后法线不同的顶点（硬边）也会被合并",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_normal(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_normal
    
    dedup_include_tangent:bpy.props.BoolProperty(
        name="切线参与去重",
        description="顶点切线是否参与去重判断",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_tangent(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_tangent
    
    dedup_include_texcoord:bpy.props.BoolProperty(
        name="UV参与去重",
        description="UV坐标是否参与去重判断。关闭后UV不同的顶点（UV接缝）也会被合并",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_texcoord(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_texcoord
    
    dedup_include_color:bpy.props.BoolProperty(
        name="顶点色参与去重",
        description="顶点色是否参与去重判断",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_color(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_color
    
    dedup_include_blend:bpy.props.BoolProperty(
        name="骨骼权重参与去重",
        description="骨骼权重和索引是否参与去重判断",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_blend(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_blend
    
    dedup_include_vertex_id:bpy.props.BoolProperty(
        name="顶点索引参与去重",
        description="Blender顶点索引是否参与去重判断。关闭可能导致ShapeKey失效，但会增加顶点合并率",
        default=True
    ) # type: ignore

    @classmethod
    def dedup_include_vertex_id(cls):
        return bpy.context.scene.properties_wwmi.dedup_include_vertex_id
    
def register():
    bpy.utils.register_class(Properties_WWMI)
    bpy.types.Scene.properties_wwmi = bpy.props.PointerProperty(type=Properties_WWMI)

def unregister():
    del bpy.types.Scene.properties_wwmi
    bpy.utils.unregister_class(Properties_WWMI)
