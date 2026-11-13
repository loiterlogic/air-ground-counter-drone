"""agc_demo.rviz 的静态交互与可视化契约（L2，不启 RViz）。"""

from __future__ import annotations

import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
RVIZ = os.path.join(ROOT, 'src', 'agc_task', 'config', 'agc_demo.rviz')


def _load():
    with open(RVIZ, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _displays(vm):
    out = []
    for item in vm.get('Displays') or []:
        out.append(item)
        if item.get('Class') == 'rviz_common/Group':
            out.extend(item.get('Displays') or [])
    return out


def test_tools_are_registered_for_view_interaction():
    vm = _load()['Visualization Manager']
    tools = vm.get('Tools') or []
    classes = [t['Class'] for t in tools]
    assert 'rviz_default_plugins/Interact' in classes
    assert 'rviz_default_plugins/MoveCamera' in classes
    assert 'rviz_default_plugins/Select' in classes
    assert all(c.startswith('rviz_default_plugins/') for c in classes)


def test_visualization_layers_have_safe_defaults():
    vm = _load()['Visualization Manager']
    displays = _displays(vm)
    by_topic = [d for d in displays if d.get('Topic', {}).get('Value')]

    planning = [d for d in by_topic if d['Topic']['Value'] == '/agc/map']
    evidence = [d for d in by_topic if d['Topic']['Value'] == '/agc/map/evidence']
    markers = [d for d in by_topic if d['Topic']['Value'] == '/agc/viz/markers']
    assert len(planning) == 1 and planning[0]['Enabled'] is True
    assert len(evidence) == 1 and evidence[0]['Enabled'] is False
    assert len(markers) == 1
    assert planning[0]['Color Scheme'].lower() != 'rainbow'
    assert 0.0 < planning[0]['Alpha'] < 0.85
    assert evidence[0]['Alpha'] < planning[0]['Alpha']
    assert all('/agc/map/obstacles' not in str(d) for d in displays)


def test_globals_and_views_are_parseable():
    vm = _load()['Visualization Manager']
    assert vm['Global Options']['Fixed Frame'] == 'map'
    assert vm['Views']['Current']['Class'] == 'rviz_default_plugins/Orbit'
    displays = _displays(vm)
    assert len(displays) >= 11
    groups = [d for d in vm['Displays'] if d.get('Class') == 'rviz_common/Group']
    assert len(groups) == 3
    saved = vm['Views'].get('Saved') or []
    assert len(saved) == 3
    names = {v.get('Name') for v in saved}
    assert {'正俯视（北朝上）', '斜视 3/4', '近景跟随车'} <= names
