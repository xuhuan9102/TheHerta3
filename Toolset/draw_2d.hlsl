// **** RESPONSIVE UI SHADER ****
// Contributors: SinsOfSeven
// Inspired by VV_Mod_Maker

Texture1D<float4> IniParams : register(t120);

#define SIZE IniParams[87].xy
#define OFFSET IniParams[87].zw

struct vs2ps {
    float4 pos : SV_Position0;
    float2 uv : TEXCOORD1;
};

#ifdef VERTEX_SHADER
void main(
        out vs2ps output,
        uint vertex : SV_VertexID)
{
    float2 BaseCoord,Offset;
    Offset.x = OFFSET.x*2-1;
    Offset.y = (1-OFFSET.y)*2-1;
    BaseCoord.xy = float2((2*SIZE.x),(2*(-SIZE.y)));
    switch(vertex) {
        case 0:
            output.pos.xy = float2(BaseCoord.x+Offset.x, BaseCoord.y+Offset.y);
            output.uv = float2(1,0);
            break;
        case 1:
            output.pos.xy = float2(BaseCoord.x+Offset.x, 0+Offset.y);
            output.uv = float2(1,1);
            break;
        case 2:
            output.pos.xy = float2(0+Offset.x, BaseCoord.y+Offset.y);
            output.uv = float2(0,0);
            break;
        case 3:
            output.pos.xy = float2(0+Offset.x, 0+Offset.y);
            output.uv = float2(0,1);
            break;
        default:
            output.pos.xy = 0;
            output.uv = float2(0,0);
            break;
    };
    output.pos.zw = float2(0, 1);
}
#endif

#ifdef PIXEL_SHADER
Texture2D<float4> tex : register(t100);

SamplerState linearSampler {
    Filter = MIN_MAG_MIP_LINEAR;
    AddressU = Clamp;
    AddressV = Clamp;
};

// 可选：从 INI 参数读取亮度调节值（默认 1.0）
// 如果将来想在 INI 中动态调节，可以取消下面注释并设置对应的 x/y/z/w
// #define UI_BRIGHTNESS IniParams[88].x

void main(vs2ps input, out float4 result : SV_Target0)
{
    float2 dims;
    tex.GetDimensions(dims.x, dims.y);
    if (!dims.x || !dims.y) discard;
    input.uv.y = 1 - input.uv.y;
    
    float4 texColor = tex.Sample(linearSampler, input.uv);
    
    // ========== 颜色校正（根据实际显示效果调整系数） ==========
    // 方法1：简单亮度提升（推荐先试这个）
    // float brightness = 1.15;  // 范围 1.0 ~ 1.3，越大越亮
    // texColor.rgb *= brightness;
    
    // 方法2：伽马校正（近似 sRGB 显示伽马）
    float gamma = 1.0 / 1.2;  // 若需启用，注释掉方法1并取消本行注释
    texColor.rgb = pow(texColor.rgb, gamma);
    // =====================================================
    
    result = texColor;
}
#endif