import bpy
import os
import glob
import re
import shutil

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_UnifyTexture(SSMTNode_PostProcess_Base):
    '''资源引用＆ini修整：统一材质贴图、清理重复贴图、修改mod配置文件增加易读性'''
    bl_idname = 'SSMTNode_PostProcess_UnifyTexture'
    bl_label = '资源引用＆ini修整'
    bl_description = '扫描并修改 INI 文件，将所有 TextureOverride 中的 RabbitFx 贴图引用统一为全局资源块，并支持从 Object Info 节点的替换名称自动重命名 INI 块'

    create_backup: bpy.props.BoolProperty(
        name="创建备份",
        description="处理前为每个 INI 文件创建备份（保存到 Backups 文件夹）",
        default=True
    )
    diffuse_map_path: bpy.props.StringProperty(
        name="漫反射贴图",
        description="自定义漫反射贴图文件（将复制到 Texture/DiffuseMap.dds）",
        subtype='FILE_PATH',
        default=""
    )
    normal_map_path: bpy.props.StringProperty(
        name="法线贴图",
        description="自定义法线贴图文件（将复制到 Texture/NormalMap.dds）",
        subtype='FILE_PATH',
        default=""
    )
    light_map_path: bpy.props.StringProperty(
        name="光照贴图",
        description="自定义光照贴图文件（将复制到 Texture/LightMap.dds）",
        subtype='FILE_PATH',
        default=""
    )
    fx_map_path: bpy.props.StringProperty(
        name="FXMap 贴图",
        description="自定义 FXMap 贴图文件（将复制到 Texture/FXMap.dds）",
        subtype='FILE_PATH',
        default=""
    )
    glow_map_path: bpy.props.StringProperty(
        name="GlowMap 贴图",
        description="自定义 GlowMap 贴图文件（将复制到 Texture/GlowMap.dds）",
        subtype='FILE_PATH',
        default=""
    )
    delete_old_textures: bpy.props.BoolProperty(
        name="删除废弃贴图",
        description="自动删除被统一引用替代的旧贴图文件（需要先备份）",
        default=False
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "create_backup")
        layout.prop(self, "delete_old_textures")
        layout.separator()

        box = layout.box()
        box.label(text="RabbitFx自定义贴图（可选）", icon='TEXTURE')
        box.prop(self, "diffuse_map_path", text="漫反射")
        box.prop(self, "normal_map_path", text="法线")
        box.prop(self, "light_map_path", text="光照")
        box.prop(self, "fx_map_path", text="FXMap")
        box.prop(self, "glow_map_path", text="GlowMap")
        box.label(text="留空则使用原有文件，不复制", icon='INFO')
        box.label(text="注：只有设置了路径的贴图才会被统一引用", icon='INFO')

        layout.separator()
        layout.label(text="此操作会：", icon='INFO')
        layout.label(text="• 统一 TextureOverride 中的贴图引用（仅已设置的）")
        layout.label(text="• 删除独立的 Texture 贴图资源块")
        layout.label(text="• 在文件末尾添加全局贴图资源（仅已设置的）")
        if self.delete_old_textures:
            layout.label(text="• 删除被替代的旧贴图文件", icon='TRASH')
        layout.label(text="• 根据 Object Info 节点的【替换名称】自动重命名 INI 块", icon='SORTALPHA')

    # =========================================================================
    # 收集 Object Info 节点的替换映射
    # =========================================================================
    def collect_replacements_from_blueprint(self):
        """从当前蓝图树及嵌套蓝图中收集所有 Object Info 节点的替换映射"""
        replacements = []
        tree = self.id_data
        if not tree or tree.bl_idname != 'SSMTBlueprintTreeType':
            return replacements

        visited_blueprints = set()

        def collect_from_tree(current_tree):
            if current_tree.name in visited_blueprints:
                return
            visited_blueprints.add(current_tree.name)

            for node in current_tree.nodes:
                if node.mute:
                    continue
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_name = getattr(node, 'object_name', '')
                    replace_name = getattr(node, 'replace_name', '')
                    if obj_name and replace_name:
                        hash_match = re.match(r'^([a-f0-9]{8}-[0-9]+-[0-9]+)', obj_name)
                        if not hash_match:
                            hash_match = re.match(r'^([a-f0-9]{8})', obj_name)
                        if hash_match:
                            raw_hash = hash_match.group(1)
                            pattern_hash = raw_hash.replace('-', '_')
                            replacements.append((pattern_hash, replace_name))
                            print(f"[UnifyTexture] 从 Object Info 节点 '{node.name}' 获取替换: '{pattern_hash}' -> '{replace_name}'")
                        else:
                            print(f"[UnifyTexture] 警告: 无法从物体名称 '{obj_name}' 提取哈希，跳过")
                elif node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    blueprint_name = getattr(node, 'blueprint_name', '')
                    if blueprint_name:
                        nested_tree = bpy.data.node_groups.get(blueprint_name)
                        if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                            collect_from_tree(nested_tree)

        collect_from_tree(tree)
        return replacements

    # =========================================================================
    # 块改名核心方法
    # =========================================================================
    def rename_sections_and_references(self, content, replacements):
        """根据传入的替换列表进行全局替换"""
        if not replacements:
            return content
        for old, new in replacements:
            # 1. 替换节名: [TextureOverride_xxx]
            content = re.sub(r'^(\[TextureOverride_%s)\]' % re.escape(old),
                             rf'[TextureOverride_{new}]', content, flags=re.MULTILINE)
            # 2. 替换节名: [Resource_xxx_...] (保留后缀)
            content = re.sub(r'^(\[Resource_%s)(_[^\]]*)\]' % re.escape(old),
                             rf'[Resource_{new}\2]', content, flags=re.MULTILINE)
            # 3. 替换节名: [CustomShader_xxx_Anim]
            content = re.sub(r'^(\[CustomShader_%s)(_Anim)\]' % re.escape(old),
                             rf'[CustomShader_{new}\2]', content, flags=re.MULTILINE)
            # 4. 替换行内引用: Resource_xxx_
            content = re.sub(r'(Resource_%s)(_[a-zA-Z0-9_]*)' % re.escape(old),
                             rf'Resource_{new}\2', content)
            # 5. 替换行内引用: CustomShader_xxx_
            content = re.sub(r'(CustomShader_%s)(_[a-zA-Z0-9_]*)' % re.escape(old),
                             rf'CustomShader_{new}\2', content)
            # 6. 替换 post run = CustomShader_xxx_Anim
            content = re.sub(r'(post run = CustomShader_%s_Anim)' % re.escape(old),
                             rf'post run = CustomShader_{new}_Anim', content)
            # 7. 替换 post Resource_xxx_Position = copy_desc ...
            content = re.sub(r'(post Resource_%s)(_[^\s=]+)' % re.escape(old),
                             rf'post Resource_{new}\2', content)
        return content

    # =========================================================================
    # 后处理执行入口
    # =========================================================================
    def execute_postprocess(self, mod_export_path):
        print(f"[UnifyTexture] 开始执行，Mod导出路径: {mod_export_path}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("[UnifyTexture] 未找到任何 .ini 文件，跳过")
            return

        # 收集替换映射
        replacements = self.collect_replacements_from_blueprint()
        if replacements:
            print(f"[UnifyTexture] 共收集到 {len(replacements)} 条替换规则")
        else:
            print("[UnifyTexture] 未找到任何替换规则，跳过改名")

        # 收集废弃贴图文件（如果需要删除）
        old_texture_files = set()
        if self.delete_old_textures:
            old_texture_files = self.collect_old_texture_files(ini_files)
            print(f"[UnifyTexture] 发现 {len(old_texture_files)} 个旧贴图文件将被删除")

        # 处理每个 INI 文件
        for ini_file in ini_files:
            self.process_ini_file(ini_file, mod_export_path, replacements)

        # 复制自定义贴图
        self.copy_custom_textures(mod_export_path)

        # 删除废弃贴图
        if self.delete_old_textures and old_texture_files:
            self.delete_old_texture_files(old_texture_files, mod_export_path)

        print("[UnifyTexture] 处理完成")

    def process_ini_file(self, ini_file_path, mod_export_path, replacements):
        print(f"[UnifyTexture] 正在处理: {ini_file_path}")

        if self.create_backup:
            self._create_cumulative_backup(ini_file_path, mod_export_path)

        try:
            with open(ini_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"[UnifyTexture] 读取文件失败: {e}")
            return

        # 执行块改名
        if replacements:
            content = self.rename_sections_and_references(content, replacements)

        # 按行处理统一材质引用
        lines = content.splitlines(keepends=True)
        new_lines = self.process_lines(lines)

        try:
            with open(ini_file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"[UnifyTexture] 已更新: {ini_file_path}")
        except Exception as e:
            print(f"[UnifyTexture] 写入文件失败: {e}")

    # =========================================================================
    # 统一材质引用处理（核心）
    # =========================================================================
    def process_lines(self, lines):
        new_lines = []
        i = 0
        total = len(lines)

        # 定义需要保留的全局资源名称（下划线格式）
        global_resources = set()
        if self.diffuse_map_path:
            global_resources.add('Resource_DiffuseMap')
        if self.normal_map_path:
            global_resources.add('Resource_NormalMap')
        if self.light_map_path:
            global_resources.add('Resource_LightMap')
        if self.fx_map_path:
            global_resources.add('Resource_FXMap')
        if self.glow_map_path:
            global_resources.add('Resource_GlowMap')

        while i < total:
            line = lines[i]
            stripped = line.strip()

            # 处理 TextureOverride 块
            if stripped.startswith("[TextureOverride_"):
                header = line
                i += 1
                block_lines = []
                while i < total and not lines[i].strip().startswith('['):
                    block_lines.append(lines[i])
                    i += 1
                processed_block = self.process_texture_override_block(header, block_lines)
                new_lines.extend(processed_block)
                # 添加节之间的空行
                new_lines.append('\n')
                continue

            # 处理 Resource 块（非贴图资源）
            if (stripped.startswith("[Resource_") or stripped.startswith("[Resource-")) and not stripped.startswith("[ResourceID"):
                block_name = stripped[1:-1]
                block_lines = []
                i += 1
                while i < total and not lines[i].strip().startswith('['):
                    block_lines.append(lines[i])
                    i += 1
                # 判断是否为贴图资源
                is_texture_resource = False
                for bline in block_lines:
                    if bline.strip().startswith('filename ='):
                        path_part = bline.split('=', 1)[1].strip()
                        if path_part.startswith('Texture/'):
                            is_texture_resource = True
                        break
                if is_texture_resource:
                    # 废弃贴图资源，跳过（不输出）
                    continue
                else:
                    # 非贴图资源（模型缓冲等）保留
                    new_lines.append(line)
                    new_lines.extend(block_lines)
                    new_lines.append('\n')   # 添加空行分隔
                    continue

            # 其他行直接复制（如 ;MARK:... 等）
            new_lines.append(line)
            i += 1

        # 在文件末尾添加全局贴图定义（原方法会处理，但需要确保添加后也有空行）
        new_lines = self.append_global_texture_defs(new_lines)
        # 可选：去除文件末尾多余的空行（保留一个即可）
        while new_lines and new_lines[-1] == '\n':
            new_lines.pop()
        new_lines.append('\n')   # 保证文件以换行结尾
        return new_lines

    def _needs_texture_processing(self, block_lines):
        """判断一个TextureOverride块是否需要处理贴图（即是否包含ib/vb等渲染资源）"""
        for line in block_lines:
            stripped = line.strip()
            if stripped.startswith(('ib =', 'vb0 =', 'vb1 =', 'vb2 =', 'vb3 =', 'drawindexedinstanced =')):
                return True
        return False

    def process_texture_override_block(self, header, block_lines):
        """
        处理 TextureOverride 块：
        1. 跳过没有 ib/vb 的块（纯粹的 skip 块）
        2. 提取头部（hash, match_*, handling）和渲染资源（ib, vb, draw...）
        3. 重新生成标准的贴图处理部分（三个 run 命令 + 用户设置的贴图引用）
        4. 按正确顺序组合：头部 + 贴图处理 + 渲染资源
        """
        # 检查是否为需要渲染的网格块
        if not self._needs_texture_processing(block_lines):
            # 不需要处理，原样返回
            return [header] + block_lines

        head_lines = []      # 存储 hash, match_*, handling 等行
        resource_lines = []  # 存储 ib, vb, draw, 注释等行
        # 其他行（旧的 run, 贴图引用）将被丢弃

        for line in block_lines:
            stripped = line.strip()
            if stripped.startswith(('hash =', 'match_first_index =', 'match_index_count =', 'handling =')):
                head_lines.append(line)
            elif stripped.startswith(('ib =', 'vb0 =', 'vb1 =', 'vb2 =', 'vb3 =', 'drawindexedinstanced =', ';')):
                resource_lines.append(line)
            # 忽略其他所有行（旧的 run 和贴图引用）

        # 确保头部行末尾有换行（可选，但保持格式）
        if head_lines and not head_lines[-1].endswith('\n'):
            head_lines[-1] += '\n'

        # 构建新的贴图处理部分
        texture_block = []
        # 第一个 run
        texture_block.append('run = CommandList\\EFMIv1\\OverrideTextures\n')
        # 用户设置的贴图引用
        if self.diffuse_map_path:
            texture_block.append('Resource\\RabbitFx\\Diffuse = ref Resource_DiffuseMap\n')
        if self.normal_map_path:
            texture_block.append('Resource\\RabbitFx\\NormalMap = ref Resource_NormalMap\n')
        if self.light_map_path:
            texture_block.append('Resource\\RabbitFx\\LightMap = ref Resource_LightMap\n')
        if self.fx_map_path:
            texture_block.append('Resource\\RabbitFX\\FXMap = ref Resource_FXMap\n')
        if self.glow_map_path:
            texture_block.append('Resource\\RabbitFX\\GlowMap = ref Resource_GlowMap\n')
        # 第二个 run
        texture_block.append('run = CommandList\\RabbitFx\\SetTextures\n')
        # 第三个 run
        texture_block.append('run = CommandList\\RabbitFX\\Run\n')

        # 组合最终输出
        result = [header]
        result.extend(head_lines)
        result.extend(texture_block)
        result.extend(resource_lines)

        # 确保最后有一个空行（可选）
        if result and not result[-1].endswith('\n'):
            result[-1] += '\n'
        return result


    def append_global_texture_defs(self, lines):
        """在文件末尾添加全局贴图定义块，仅添加用户已设置的贴图"""
        # 检查是否已存在全局定义块（通过检查是否存在任意一个用户设置的资源）
        need_append = False
        for res_name in ['Resource_DiffuseMap', 'Resource_NormalMap', 'Resource_LightMap', 'Resource_FXMap', 'Resource_GlowMap']:
            if res_name in lines and any(line.strip() == f'[{res_name}]' for line in lines):
                # 已存在，跳过追加
                print(f"[UnifyTexture] 全局贴图定义已存在，跳过追加")
                return lines

        # 构建要追加的内容
        append_lines = []
        if self.diffuse_map_path:
            append_lines.append(';MARK:ResourceTexture\n')
            append_lines.append('[Resource_DiffuseMap]\n')
            append_lines.append('filename = Texture/DiffuseMap.dds\n')
            append_lines.append('\n')
        if self.normal_map_path:
            if not append_lines:  # 如果前面没有添加过标记，则添加
                append_lines.append(';MARK:ResourceTexture\n')
            append_lines.append('[Resource_NormalMap]\n')
            append_lines.append('filename = Texture/NormalMap.dds\n')
            append_lines.append('\n')
        if self.light_map_path:
            if not append_lines:
                append_lines.append(';MARK:ResourceTexture\n')
            append_lines.append('[Resource_LightMap]\n')
            append_lines.append('filename = Texture/LightMap.dds\n')
            append_lines.append('\n')
        if self.fx_map_path:
            if not append_lines:
                append_lines.append(';MARK:ResourceTexture\n')
            append_lines.append('[Resource_FXMap]\n')
            append_lines.append('filename = Texture/FXMap.dds\n')
            append_lines.append('\n')
        if self.glow_map_path:
            if not append_lines:
                append_lines.append(';MARK:ResourceTexture\n')
            append_lines.append('[Resource_GlowMap]\n')
            append_lines.append('filename = Texture/GlowMap.dds\n')
            append_lines.append('\n')

        if append_lines:
            if lines and lines[-1].strip() != '':
                lines.append('\n')
            lines.extend(append_lines)
        return lines

    # =========================================================================
    # 旧贴图文件收集（包括 [Resource- 和 [Resource_ 格式）
    # =========================================================================
    def collect_old_texture_files(self, ini_files):
        old_files = set()
        global_resources = set()
        if self.diffuse_map_path:
            global_resources.add('Resource_DiffuseMap')
        if self.normal_map_path:
            global_resources.add('Resource_NormalMap')
        if self.light_map_path:
            global_resources.add('Resource_LightMap')
        if self.fx_map_path:
            global_resources.add('Resource_FXMap')
        if self.glow_map_path:
            global_resources.add('Resource_GlowMap')

        for ini_file in ini_files:
            try:
                with open(ini_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                i = 0
                total = len(lines)
                while i < total:
                    line = lines[i]
                    stripped = line.strip()
                    if (stripped.startswith("[Resource_") or stripped.startswith("[Resource-")) and not stripped.startswith("[ResourceID"):
                        block_name = stripped[1:-1]
                        i += 1
                        filename_line = None
                        while i < total and not lines[i].strip().startswith('['):
                            if lines[i].strip().startswith('filename ='):
                                filename_line = lines[i]
                                break
                            i += 1
                        if filename_line:
                            file_rel = filename_line.split('=', 1)[1].strip()
                            if file_rel.startswith('Texture/'):
                                abs_path = os.path.abspath(os.path.join(os.path.dirname(ini_file), file_rel.replace('/', os.sep)))
                                if os.path.exists(abs_path):
                                    # 如果这个资源不是用户设置的全局资源，则标记删除
                                    if block_name not in global_resources:
                                        old_files.add(abs_path)
                        continue
                    i += 1
            except Exception as e:
                print(f"[UnifyTexture] 扫描文件 {ini_file} 时出错: {e}")
        return old_files

    def copy_custom_textures(self, mod_export_path):
        texture_dir = os.path.join(mod_export_path, "Texture")
        os.makedirs(texture_dir, exist_ok=True)

        mappings = [
            (self.diffuse_map_path, "DiffuseMap.dds"),
            (self.normal_map_path, "NormalMap.dds"),
            (self.light_map_path, "LightMap.dds"),
            (self.fx_map_path, "FXMap.dds"),
            (self.glow_map_path, "GlowMap.dds"),
        ]

        for src_path, dest_name in mappings:
            if src_path and os.path.isfile(src_path):
                dest_path = os.path.join(texture_dir, dest_name)
                try:
                    shutil.copy2(src_path, dest_path)
                    print(f"[UnifyTexture] 已复制自定义贴图: {src_path} -> {dest_path}")
                except Exception as e:
                    print(f"[UnifyTexture] 复制贴图失败: {e}")
            elif src_path:
                print(f"[UnifyTexture] 自定义贴图文件不存在，跳过: {src_path}")

    def delete_old_texture_files(self, old_files, mod_export_path):
        deleted_count = 0
        mod_export_abs = os.path.abspath(mod_export_path)
        for file_path in old_files:
            abs_file = os.path.abspath(file_path)
            if not abs_file.startswith(mod_export_abs):
                print(f"[UnifyTexture] 警告: 文件不在导出目录内，跳过删除: {abs_file}")
                continue
            try:
                os.remove(abs_file)
                deleted_count += 1
                print(f"[UnifyTexture] 已删除旧贴图: {os.path.relpath(abs_file, mod_export_abs)}")
            except Exception as e:
                print(f"[UnifyTexture] 删除文件失败: {abs_file}, 错误: {e}")
        print(f"[UnifyTexture] 共删除 {deleted_count} 个废弃贴图文件")


# =============================================================================
# Registration
# =============================================================================
classes = (
    SSMTNode_PostProcess_UnifyTexture,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)