# materials/ — 自产程序化贴图（R6，2026-10-30）

## 这是什么

地面 / 场坪 / 沥青路的 **albedo 贴图**，由 [`gen_textures.py`](gen_textures.py) 生成。
**自产、不引外部素材**（守 [ADR-0007](../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)
的"不引入外部资产"与 [ADR-0005](../../../docs/adr/0005-px4-toolchain-and-link.md#top)
的 provenance 纪律）。

## 生成与复现

```bash
python3 src/agc_sim/materials/gen_textures.py # 固定种子 20261030，输出 albedo/*.png + manifest.json
```

**必须可复现**：种子由 `zlib.crc32(name)` 派生，**不能用内置 `hash`**（它受 `PYTHONHASHSEED`
随机化，同一脚本两次运行会产出不同贴图）。

`manifest.json` 记录每张图的 sha256 / 尺寸 / 基色 / 字节数，供溯源与回归比对。

## 为什么只做"低频斑驳 + 细颗粒"，不做分格/拉缝图案

本机 `sdformat 1.11` 的 `<albedo_map>` **没有 UV 缩放字段**，`box` / `plane` 图元的面 UV 固定 0–1。
一张贴图会被拉伸到整个面 —— 200 m 的基层地面与 12×9 的场坪用同一张图，纹理密度差 20 倍。
所以：

- 贴图只承担**尺度不敏感**的信息（斑驳、颗粒、色泽不均）；
- 分格 / 拉缝 / 车位线这类**有绝对尺度**的信息继续用**真几何**表达（见 `agc_world.sdf` 的地面语义层）。

## 两条踩过的坑（本轮实测）

1. **贴图与基色相乘**：`<albedo_map>` 会乘上 `<diffuse>` / `<ambient>`。基色仍是 0.52 时，
   渲染均值从 150 掉到 **76**。→ 带贴图的材质必须把基色置**白**（`1 1 1 1`），颜色交给贴图。
2. **PNG 是 sRGB、`<diffuse>` 是线性**：把线性值直接写进 PNG 会整体压暗一档（150 → 106）。
   → 落盘前做**线性 → sRGB 编码**（`gen_textures.py` 里已实现）。

## 路径策略

世界文件在 launch 时被生成到 `/tmp`，相对路径会失效 → SDF 里用**安装目录下的绝对路径**：

```
/home/chen/AGC/install/agc_sim/share/agc_sim/materials/albedo/<name>.png
```

本机项目根固定，可接受；若要可迁移，需改走 `GZ_SIM_RESOURCE_PATH` 资源查找（未做）。
