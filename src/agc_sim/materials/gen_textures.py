#!/usr/bin/env python3
"""gen_textures —— 程序化 albedo 贴图生成器（**自产资产，不引外部素材**）。

为什么是"自产 + 程序化"：
 * 项目纪律不引入外部 3D 资产 / 贴图（ADR-0007 / ADR-0005 的 provenance 纪律）；
 * 自产 == 来源可解释、可复现（固定种子 + 本脚本 + 输出哈希）。

为什么只做**噪声/斑驳类**贴图，不做分格/拉缝图案：
 本机 sdformat 的 `<albedo_map>` **没有 UV 缩放字段**，`box` / `plane` 图元的面 UV 固定 0–1。
 一张贴图会被拉伸到整个面：200 m 的基层地面与 12×9 的场坪用同一张图，纹理密度差 20 倍。
 → 只生成**尺度不敏感**的低频斑驳 + 细颗粒，分格/拉缝这类"有绝对尺度"的信息继续用
 真几何表达（路缘石 / 排水沟 / 停车位线，见 agc_world.sdf 地面语义层）。

输出：albedo/<name>.png（512×512，sRGB）+ manifest.json（sha256 / 尺寸 / 种子）。
"""
import hashlib
import json
import os

import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'albedo')
SEED = 20261030
SIZE = 512

# name -> (基色 sRGB 0–1, 低频斑驳幅度, 细颗粒幅度, 低频格数)
SPECS = {
    'concrete_ground': ([0.40, 0.395, 0.39], 0.150, 0.030, 5),
    'asphalt':         ([0.20, 0.21, 0.23],  0.140, 0.045, 7),
    'apron_concrete':  ([0.52, 0.515, 0.50], 0.140, 0.028, 5),
    'gravel':          ([0.34, 0.335, 0.32], 0.050, 0.075, 14),
}


def value_noise(n, cells, rng):
    """可平铺的低频 value noise：cells×cells 随机格 → 双线性放大到 n×n（周期回绕）。"""
    g = rng.random((cells, cells)).astype(np.float32)
    idx = (np.arange(n) * cells / n)
    i0 = np.floor(idx).astype(int) % cells
    i1 = (i0 + 1) % cells
    t = (idx - np.floor(idx)).astype(np.float32)
    t = t * t * (3 - 2 * t)                      # smoothstep
    a = g[np.ix_(i0, i0)]; b = g[np.ix_(i0, i1)]
    c = g[np.ix_(i1, i0)]; d = g[np.ix_(i1, i1)]
    tx = t[None, :]; ty = t[:, None]
    return (a * (1 - tx) * (1 - ty) + b * tx * (1 - ty)
            + c * (1 - tx) * ty + d * tx * ty)


def build(name, base, lo_amp, hi_amp, cells, rng):
    n = SIZE
    lo = value_noise(n, cells, rng) - 0.5
    hi = rng.normal(0.0, 1.0, (n, n)).astype(np.float32)
    # 高频做一次 3×3 平滑，避免纯白噪声在远距离处出现摩尔纹
    k = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], np.float32) / 16.0
    hi = np.stack([np.convolve(hi.ravel(), k.ravel(), 'same').reshape(n, n)])
    hi = hi[0]
    delta = lo * (lo_amp * 2.0) + hi * hi_amp
    img = np.empty((n, n, 3), np.float32)
    for i in range(3):
        img[:, :, i] = np.clip(base[i] * (1.0 + delta), 0.0, 1.0)
    # **关键**：SDF 的 <diffuse> 是**线性**色，而 PNG 被渲染器按 **sRGB** 解释。
    # 直接把线性值写进 PNG 会整体压暗一档（本轮实测：场坪 150 → 106）。
    # 故落盘前做线性 → sRGB 编码，取样后再解码回同一线性值。
    img = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(img, 1 / 2.4) - 0.055)
    return np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8)


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {'generator': 'gen_textures.py', 'seed': SEED, 'size': SIZE,
                'license': 'self-generated (project-owned)', 'textures': {}}
    for name, (base, lo, hi, cells) in SPECS.items():
        # 用 crc32 派生每张贴图的种子：**不能用内置 hash**，它受 PYTHONHASHSEED 随机化，
        # 会导致同一脚本两次运行产出不同贴图（不可复现）。
        rng = np.random.default_rng(SEED + zlib.crc32(name.encode()) % 100000)
        arr = build(name, base, lo, hi, cells, rng)
        path = os.path.join(OUT, name + '.png')
        Image.fromarray(arr, 'RGB').save(path)
        with open(path, 'rb') as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        manifest['textures'][name] = {'file': 'albedo/%s.png' % name, 'sha256': sha,
                                      'base_srgb': base, 'bytes': os.path.getsize(path)}
        print('%-18s %6d bytes  %s' % (name, os.path.getsize(path), sha[:16]))
    with open(os.path.join(HERE, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('manifest.json 已写')


if __name__ == '__main__':
    main()
