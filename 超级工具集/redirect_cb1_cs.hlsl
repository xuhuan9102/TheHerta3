// =========================================================
// 纯净版：redirect_cb1_cs.hlsl (指针篡改器)
// 彻底删除了 Texture1D t120，再也不会有绑定报错了！
// =========================================================
StructuredBuffer<uint4> DumpedCB1  : register(t0);
Buffer<uint> TargetPartID          : register(t2); 

RWStructuredBuffer<uint4> FakeCB1_UAV : register(u0); 

[numthreads(1024, 1, 1)] 
void main(uint3 tid : SV_DispatchThreadID) {
    uint id = tid.x;
    if (id >= 4096) return; 

    uint4 cb_data = DumpedCB1[id];
    
    if (id == 5) {
        uint dim;
        TargetPartID.GetDimensions(dim);
        uint target_offset = dim - 1; 
        
        // 🌟【究极简化】：永远只读基础位置的数据！
        cb_data.x = target_offset;               
        cb_data.y = target_offset + 100000;      
    }
    FakeCB1_UAV[id] = cb_data; 
}