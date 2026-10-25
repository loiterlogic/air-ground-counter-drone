"""W8 P0 / T3：逐 run 有界 GUI renderer 证据单测（纯 stdlib，不读共享日志）。

覆盖：追加 / 截断 / 缺失 / 新建 / 冲突 / 无变化，以及 startup+final 合并。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import gui_renderer_evidence as ev  # noqa: E402


def _append(path, text, mode='a'):
    with open(path, mode) as f:
        f.write(text)


def test_appended_segment_only_yields_new_renderer(tmp_path):
    path = str(tmp_path / 'ogre2.log')
    _append(path, 'Device Name: OLD\n')
    snap = ev.snapshot(path)
    _append(path, 'Device Name: NEW\n')

    out = ev.probe(snap)

    assert out['read_mode'] == 'appended'
    assert out['status'] == 'ok'
    assert out['renderer'] == 'NEW'
    assert out['renderers'] == ['NEW']
    assert out['offset'] == snap['size']
    assert out['bytes_read'] == len('Device Name: NEW\n')
    assert all('OLD' not in line for line in out['matched_lines'])
    assert out['matched_lines'] == ['Device Name: NEW']


def test_truncate_and_rewrite_reads_whole_file(tmp_path):
    path = str(tmp_path / 'ogre2.log')
    _append(path, 'Device Name: OLD\n')
    snap = ev.snapshot(path)
    _append(path, 'Device Name: NEW\n', mode='w')

    out = ev.probe(snap)

    assert out['read_mode'] == 'whole_after_truncate'
    assert out['status'] == 'ok'
    assert out['renderer'] == 'NEW'
    assert out['offset'] == 0


def test_missing_file_is_absent(tmp_path):
    path = str(tmp_path / 'ogre2.log')
    snap = ev.snapshot(path)
    assert snap['exists'] is False
    assert snap['prefix_sha256'] is None

    out = ev.probe(snap)

    assert out['status'] == 'absent'
    assert out['read_mode'] == 'none'
    assert out['renderer'] is None
    assert out['bytes_read'] == 0


def test_created_after_snapshot_is_whole_created(tmp_path):
    path = str(tmp_path / 'ogre2.log')
    snap = ev.snapshot(path)
    _append(path, 'Device Name: NEW\n')

    out = ev.probe(snap)

    assert out['read_mode'] == 'whole_created'
    assert out['status'] == 'ok'
    assert out['renderer'] == 'NEW'


def test_appended_two_renderers_is_ambiguous(tmp_path):
    path = str(tmp_path / 'ogre2.log')
    _append(path, 'Device Name: OLD\n')
    snap = ev.snapshot(path)
    _append(path, 'Device Name: A\n')
    _append(path, 'GL_RENDERER = B\n')

    out = ev.probe(snap)

    assert out['read_mode'] == 'appended'
    assert out['status'] == 'ambiguous'
    assert out['renderer'] is None
    assert out['renderers'] == ['A', 'B']


def test_no_change_is_no_output(tmp_path):
    path = str(tmp_path / 'ogre2.log')
    _append(path, 'Device Name: OLD\n')
    snap = ev.snapshot(path)

    out = ev.probe(snap)

    assert out['read_mode'] == 'none'
    assert out['status'] == 'no_output'
    assert out['bytes_read'] == 0


def test_combine_conflicting_startup_and_final_is_ambiguous():
    startup = {'status': 'ok', 'renderer': 'A'}
    final = {'status': 'ok', 'renderer': 'B'}

    out = ev.combine(startup, final)

    assert out['status'] == 'ambiguous'
    assert out['renderer'] is None
    assert out['startup'] is startup and out['final'] is final


def test_combine_startup_only_is_ok_at_startup():
    out = ev.combine({'status': 'ok', 'renderer': 'A'},
                     {'status': 'missing_after', 'renderer': None})

    assert out['status'] == 'ok_at_startup'
    assert out['renderer'] == 'A'


def test_combine_without_probes_is_no_output():
    out = ev.combine(None, None)
    assert out['status'] == 'no_output'
    assert out['renderer'] is None
