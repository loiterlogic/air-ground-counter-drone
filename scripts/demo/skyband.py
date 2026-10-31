#!/usr/bin/env python3
"""`skyband.py` —— 判定 Gazebo 帧是**正俯视**还是**斜视**的预登记指标。

## 这个指标在量什么

正俯视（`camera_pose = 0 0 118 0 1.5708 1.5708`，相机铅直向下看）时，画面上方是**远处地面**，
呈现为**大片均匀平灰**（场景 `background_color` / 地面在无纹理处的统一色）。
斜视（3/4 视角）时，画面上方是**天空**，同样是平灰，但占比与过渡带不同。

因此用"顶部**连续**平灰带占高度的比例"区分两者——**这是 Leader 独立核查时用的口径**，
本模块逐字实现同一算法，保证两边数值可比（不是我自己另发明一套）。

## 算法（与审查方一致，逐字）

```python
gray_band = np.abs(rgb.astype(int) - 218).max(axis=2) < 4   # 逐像素是否"平灰 218"
row_frac  = gray_band.mean(axis=1)                          # 每行的命中占比
# 从第 0 行起，连续满足 row_frac > 0.9 的行数 ÷ 图像高度
```

## 预登记阈值（**先登记、后看结果**；2026-10-31 Leader 依历史样本复算后修正）

| 取值 | 判定 |
|---|---|
| ≤ **0.10** | **俯视成立** |
| ≥ **0.20** | **斜视** |
| 0.10–0.20 | **判读模糊**：再补 1 帧（同视角、间隔 ≥2 s）复核，两帧**同侧**才下结论 |

**标定参照**（Leader 复算本机历史样本所得，本轮沿用、不重测）：

| 样本 | skyband | 说明 |
|---|---|---|
| 2026-10-29 原生 GUI `16:25:20` / `16:28:31` | **0.06** | 加 `<gui>` 俯视预设后**用户认可**的画面 |
| `yard_fine_view` | **0.20** | 斜视下界样本 |
| 同批 `16:29:35` / `16:30:41` / `16:15:32` | 0.21 / 0.32 / 0.36 | 斜视 |
| round-2 三帧（本次任务） | **0.28** | 斜视 |
| P1-1 离屏正俯视渲染（1489×999，裁到作业区） | **0.00** | 正俯视下界 |
| P1-4 机载前视帧 | **0.21** | 斜视 |

> 注意"平灰 218"这个常数是**标定过的**：它来自实际帧的天空/背景色，不是随便取的中灰。
> 若换渲染后端或换场景光照，这个常数需要重新标定——**不要**在别的场景里照抄。

## 用法

```bash
python3 scripts/demo/skyband.py --frame <png> [--frame <png> ...]   # 打印数值
```

退出码：`0` 已计算（不代表判定通过）；`2` 用法/读图错误。
"""

import argparse
import json
import sys

GRAY_LEVEL = 218          # 标定过的"平灰"电平（见文件头）
GRAY_TOL = 4              # ±4 容差
ROW_THRESHOLD = 0.9       # 单行命中占比 > 0.9 视为"该行是平灰带"
TOP_BAND_MAX = 0.10       # ≤ 此值 = 俯视成立（Leader 2026-10-31 依历史样本复算修正）
TILT_MIN = 0.20           # ≥ 此值 = 斜视
AMBIGUOUS_RECHECK_S = 2.0  # 判读模糊时补帧的最小间隔


def measure(path):
    """返回 dict：`skyband`（0–1）、像素尺寸、判定标签。读图失败抛异常。"""
    import numpy as np
    from PIL import Image

    with Image.open(path) as im:
        rgb = np.asarray(im.convert('RGB'))
    height = rgb.shape[0]
    gray_band = np.abs(rgb.astype(int) - GRAY_LEVEL).max(axis=2) < GRAY_TOL
    row_frac = gray_band.mean(axis=1)

    run = 0
    for frac in row_frac:
        if frac > ROW_THRESHOLD:
            run += 1
        else:
            break

    skyband = float(run) / float(height) if height else 0.0
    return {
        'path': path,
        'width': int(rgb.shape[1]),
        'height': int(height),
        'skyband': round(skyband, 4),
        'top_gray_rows': int(run),
        'verdict': classify(skyband),
        'params': {
            'gray_level': GRAY_LEVEL, 'gray_tol': GRAY_TOL,
            'row_threshold': ROW_THRESHOLD,
            'top_band_max': TOP_BAND_MAX, 'tilt_min': TILT_MIN,
        },
    }


def classify(skyband):
    """预登记三分类；模糊区间**不**强行归类（须补帧复核，两帧同侧才下结论）。"""
    if skyband <= TOP_BAND_MAX:
        return 'top_down'          # 俯视成立
    if skyband >= TILT_MIN:
        return 'tilted'            # 斜视
    return 'ambiguous'             # 判读模糊 → 须再补 1 帧（间隔 ≥2 s）复核


def classify_pair(first, second):
    """两帧联合判读：**两帧同侧才下结论**，否则仍判模糊。

    规则（预登记）：任一侧 ≥TILT_MIN 且另一侧也 ≥TILT_MIN → tilted；
    两侧都 ≤TOP_BAND_MAX → top_down；其余（含一帧模糊、或跨区间）→ ambiguous。
    """
    if first >= TILT_MIN and second >= TILT_MIN:
        return 'tilted'
    if first <= TOP_BAND_MAX and second <= TOP_BAND_MAX:
        return 'top_down'
    return 'ambiguous'



def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='skyband 视角指标')
    ap.add_argument('--frame', action='append', required=True, metavar='PNG')
    ap.add_argument('--json', action='store_true', help='输出 JSON（默认人读）')
    args = ap.parse_args(argv)

    rows = []
    for path in args.frame:
        try:
            rows.append(measure(path))
        except Exception as exc:      # noqa: BLE001
            print('[skyband] 读图失败 %s：%s' % (path, exc), file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print('[skyband] %-46s %dx%d  skyband=%.4f  → %s'
                  % (r['path'], r['width'], r['height'], r['skyband'], r['verdict']))
        print('[skyband] 预登记：≤%.2f 俯视成立 / ≥%.2f 斜视 / 其间判读模糊（须补帧复核）'
              % (TOP_BAND_MAX, TILT_MIN))
    return 0


if __name__ == '__main__':
    sys.exit(main())
