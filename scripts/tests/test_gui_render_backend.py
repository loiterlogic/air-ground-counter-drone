"""W8 / ADR-0021：GUI 渲染后端选择单测（不启动 ROS / gz）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src', 'agc_sim', 'launch'))

from gui_render_backend import (  # noqa: E402
    D3D12_ENV, SOFTWARE_ENV, is_x11, select_gui_render_env,
)


def test_auto_wsl_dxg_x11_selects_d3d12():
    env = select_gui_render_env(
        'auto', is_wsl_fn=lambda: True, has_dxg_fn=lambda: True, display=':0')
    assert env == D3D12_ENV


def test_auto_native_or_no_dxg_keeps_system_default():
    assert select_gui_render_env(
        'auto', is_wsl_fn=lambda: False, has_dxg_fn=lambda: True, display=':0') == {}
    assert select_gui_render_env(
        'auto', is_wsl_fn=lambda: True, has_dxg_fn=lambda: False, display=':0') == {}
    assert select_gui_render_env(
        'auto', is_wsl_fn=lambda: True, has_dxg_fn=lambda: True, display='') == {}


def test_d3d12_and_software_force():
    assert select_gui_render_env(
        'd3d12', is_wsl_fn=lambda: False, has_dxg_fn=lambda: False, display='') == D3D12_ENV
    assert select_gui_render_env(
        'software', is_wsl_fn=lambda: True, has_dxg_fn=lambda: True, display=':0') == SOFTWARE_ENV


def test_unknown_backend_rejected():
    try:
        select_gui_render_env('vulkan', is_wsl_fn=lambda: False, has_dxg_fn=lambda: False, display='')
    except ValueError as exc:
        assert 'vulkan' in str(exc)
    else:
        raise AssertionError('未知 backend 应抛 ValueError')


def test_x11_detection():
    assert is_x11(':0')
    assert is_x11('localhost:10.0')
    assert not is_x11('')
    assert not is_x11('wayland-0')
