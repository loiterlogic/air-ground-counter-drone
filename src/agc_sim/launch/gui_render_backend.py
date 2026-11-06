"""GUI 渲染后端选择（W8 / ADR-0021）。

`gui_render_backend`:
 * ``auto``（项目默认）—— WSL2 + ``/dev/dxg`` + X11 时使用 Mesa D3D12；
 其它环境保持系统默认 GL（原生 Linux 走硬件 GL，无 GPU 时自然回退软件）。
 * ``d3d12`` —— 强制 Mesa D3D12 + X11（显式选择；不支持时 GUI 可能起不来）。
 * ``software`` —— 强制 llvmpipe 软件渲染（受限 GUI 条件，便于复现旧的软件 GUI 基线）。

只在 GUI（``gz sim -r``）下有影响；headless（``gz sim -s``）没有渲染客户端。
调用方（``world_bringup.launch.py``）把返回的 dict 转成 ``SetEnvironmentVariable``。
"""

import os

BACKENDS = ('auto', 'd3d12', 'software')

D3D12_ENV = {
    'MESA_LOADER_DRIVER_OVERRIDE': 'd3d12',
    'GALLIUM_DRIVER': 'd3d12',
}

SOFTWARE_ENV = {
    'LIBGL_ALWAYS_SOFTWARE': '1',
    'MESA_LOADER_DRIVER_OVERRIDE': 'swrast',
    'GALLIUM_DRIVER': 'llvmpipe',
}


def is_wsl(osrelease=None):
    """WSL2 内核串包含 ``microsoft`` / ``wsl``。"""
    if osrelease is None:
        try:
            with open('/proc/sys/kernel/osrelease', 'r') as f:
                osrelease = f.read()
        except OSError:
            return False
    text = (osrelease or '').lower()
    return 'microsoft' in text or 'wsl' in text


def has_dxg():
    """WSL GPU 直通设备。"""
    return os.path.exists('/dev/dxg')


def is_x11(display=None):
    """X11 / XWayland 路径（`:0`、`localhost:10.0`）；Wayland-only 不在此列。"""
    if display is None:
        display = os.environ.get('DISPLAY', '')
    text = str(display or '')
    return bool(text) and ':' in text and not text.startswith('wayland')


def select_gui_render_env(backend='auto', *, is_wsl_fn=is_wsl, has_dxg_fn=has_dxg,
                          display=None):
    """返回要注入 gz GUI 进程的环境变量 dict；``auto`` 不满足条件时返回空 dict。"""
    backend = (backend or 'auto').lower()
    if backend not in BACKENDS:
        raise ValueError('未知 gui_render_backend=%r（可用：%s）'
                         % (backend, ' | '.join(BACKENDS)))
    if backend == 'd3d12':
        return dict(D3D12_ENV)
    if backend == 'software':
        return dict(SOFTWARE_ENV)
    # auto：只在 WSL2 + /dev/dxg + X11 上强制 D3D12；其它环境保持系统默认。
    if is_wsl_fn() and has_dxg_fn() and is_x11(display):
        return dict(D3D12_ENV)
    return {}


def describe(backend, env):
    """人类可读的 backend 摘要（用于 launch 日志）。"""
    if env == D3D12_ENV:
        actual = 'd3d12'
    elif env == SOFTWARE_ENV:
        actual = 'software'
    else:
        actual = 'system-default'
    return 'gui_render_backend=%s -> %s' % (backend, actual)
