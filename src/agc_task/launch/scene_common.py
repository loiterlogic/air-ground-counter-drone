#!/usr/bin/env python3
"""scene_common —— 场景配置链里**跨域共用**的小工具（无业务语义）。

只收"多个子模块都要用、且实现唯一"的东西；有业务归属的函数不放这里
（几何派生在 `scene_geometry`、出生布局在 `scene_spawn`、高度在 `scene_altitude`）。
"""

import os
import random
import time


def new_run_token():
    """ADR-0006：每次调用生成唯一 token（时刻 + 进程 + 随机），供临时文件命名避免并发 / 重复覆盖。"""
    return '%s-%s-%d-%04d' % (time.strftime('%Y%m%d'), time.strftime('%H%M%S'),
                              os.getpid(), random.randint(0, 9999))
