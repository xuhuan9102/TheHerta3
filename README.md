# TheHerta 3.0系列

此插件仅适配SSMT 3.0系列

# 工具版本选择

- SSMT3和TheHerta3的版本几乎是同步更新，尽量全部使用最新版防止功能无法一一对应。
- Blender最低使用4.5LTS版本，最高可使用Nightly Build，如遇到BUG请提交issue。

# 注意事项
- 仅支持Blender最新版本，功能不向下兼容低版本，所有开发都在Blender Nightly Build的Alpha版本中进行。
- 仅适配SSMT 3.0系列，不兼容SSMT 2.0系列。
- 几乎所有流程都与旧版本SSMT不相同，请勿在生产环境中使用。


# 插件开发
开发插件请使用VSCode，严禁使用PyCharm开发

请使用以下VSCode插件:
- Blender Development (作者是 Jacques Lucke)

# AI辅助开发

如果看不懂代码或者不知道怎么写代码

请在VSCode中选择侧边栏的Agent Sessions，选择LOCAL CHAT AGENT,

随后可以在右侧对话框中让AI理解代码并讲解原理，或者直接让它帮你实现功能，当前时间2025/11/24推荐使用GPT5 mini，效果是最好的。

但是注意，使用AI生成的代码务必经过完全测试再提交，因为AI可能会产生幻觉输出。

代码规范：

对于AI来说，代码拆分的越细，分析的越快，所以要尽可能把代码拆分为基础的功能单元类，基础功能单元方法等等

避免一个方法里几百行代码的情况，否则AI思考花费的时间会指数上升且准确率严重下降。