"""toolchain_pin_check 的 local_patches 正负例测试。

所有夹具在临时目录构造，不触碰活动 PX4 外部树。
"""
import hashlib
import importlib.util
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'pin_check', Path(__file__).parents[1] / 'toolchain_pin_check.py')
pin_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin_check)


def _run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fixture(tmp_path):
    repo = tmp_path / 'repo'
    (repo / 'src').mkdir(parents=True)
    _run(['git', 'init', '-q'], cwd=repo)
    _run(['git', 'config', 'user.email', 'test@example.invalid'], cwd=repo)
    _run(['git', 'config', 'user.name', 'test'], cwd=repo)
    source = repo / 'src' / 'a.cpp'
    source.write_text('baseline\n')
    _run(['git', 'add', '.'], cwd=repo)
    _run(['git', 'commit', '-qm', 'base'], cwd=repo)

    source.write_text('patched\n')
    diff = _run(['git', 'diff'], cwd=repo).stdout
    (tmp_path / 'patches').mkdir()
    patch = tmp_path / 'patches' / 'p.patch'
    patch.write_text(diff)
    _run(['git', 'checkout', '--', 'src/a.cpp'], cwd=repo)
    _run(['git', 'apply', str(patch)], cwd=repo)
    return repo, source, patch


def _pins(source, patch):
    return {
        'schema': 1,
        'git_repos': [{'id': 'r', 'path': 'repo'}],
        'local_patches': [{
            'id': 'p1',
            'repo': 'r',
            'path': 'patches/p.patch',
            'sha256': _sha(patch),
            'source_files': {'src/a.cpp': _sha(source)},
        }],
    }


def _statuses(tmp_path, pins):
    checks = []
    pin_check.check_local_patches(pins, checks, str(tmp_path))
    return {c['check']: c['status'] for c in checks}


def test_local_patch_valid(tmp_path):
    repo, source, patch = _fixture(tmp_path)
    statuses = _statuses(tmp_path, _pins(source, patch))
    assert statuses['patch:p1:sha256'] == 'PASS'
    assert statuses['patch:p1:source:src/a.cpp'] == 'PASS'
    assert statuses['patch:p1:applies_to_baseline'] == 'PASS'
    assert statuses['patch:p1:worktree_equals_baseline_plus_patch'] == 'PASS'
    assert statuses['patch:p1:extra_dirty'] == 'PASS'


def test_tampered_patch_fails_hash(tmp_path):
    repo, source, patch = _fixture(tmp_path)
    pins = _pins(source, patch)
    patch.write_text(patch.read_text() + '\n# tampered\n')
    statuses = _statuses(tmp_path, pins)
    assert statuses['patch:p1:sha256'] == 'FAIL'


def test_tampered_source_fails_content_and_reverse_apply(tmp_path):
    repo, source, patch = _fixture(tmp_path)
    pins = _pins(source, patch)
    source.write_text('patched plus extra\n')
    statuses = _statuses(tmp_path, pins)
    assert statuses['patch:p1:source:src/a.cpp'] == 'FAIL'
    assert statuses['patch:p1:worktree_equals_baseline_plus_patch'] == 'FAIL'


def test_extra_untracked_file_fails_dirty(tmp_path):
    repo, source, patch = _fixture(tmp_path)
    pins = _pins(source, patch)
    (repo / 'extra.txt').write_text('unregistered\n')
    statuses = _statuses(tmp_path, pins)
    assert statuses['patch:p1:extra_dirty'] == 'FAIL'


def test_unapplied_source_fails(tmp_path):
    repo, source, patch = _fixture(tmp_path)
    pins = _pins(source, patch)
    _run(['git', 'checkout', '--', 'src/a.cpp'], cwd=repo)
    statuses = _statuses(tmp_path, pins)
    assert statuses['patch:p1:source:src/a.cpp'] == 'FAIL'
    assert statuses['patch:p1:worktree_equals_baseline_plus_patch'] == 'FAIL'


def test_missing_patch_fails(tmp_path):
    repo, source, patch = _fixture(tmp_path)
    pins = _pins(source, patch)
    patch.unlink()
    statuses = _statuses(tmp_path, pins)
    assert statuses['patch:p1:sha256'] == 'FAIL'


def test_porcelain_path_handles_rename_and_quote():
    assert pin_check._porcelain_path('R  old.cpp -> new.cpp') == 'new.cpp'
    assert pin_check._porcelain_path(' M "a b.cpp"') == 'a b.cpp'
    assert pin_check._porcelain_path('?? extra.txt') == 'extra.txt'
