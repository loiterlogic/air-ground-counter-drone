#!/usr/bin/env python3
"""`gui_capture.py` —— 从 **Gazebo GUI 的 3D 视图相机**取真实帧（截图 / 逐帧录制）。

## 为什么必须带 GUI（2026-10-31 实测）

headless（`gz sim -s`）**不启动渲染客户端**，根本不会生成画面——截图必须带 GUI。
但本机抓屏这条路是**堵的**：

| 手段 | 实测结果 |
|---|---|
| `xwd` / `import` / `scrot` / `maim` / `gnome-screenshot` | **全部未安装** |
| `ffmpeg` / `gst-launch-1.0` | **未安装** |
| PyQt5 `grabWindow(0)` 抓 X root | 返回 2664×1200，**非黑像素 0**（`DISPLAY=:0` 是 Wayland，XWayland 根窗口不含窗口内容） |
| Xlib `XGetImage(root)` | `BadMatch`（合成器不暴露窗口像素） |
| `Xvfb` / `xephyr` / `x11vnc` | **未安装**，无法自建无合成器 X server |
| GNOME Shell DBus 截图 | `ServiceUnknown`（非 GNOME 会话） |

**可行路径**：Gazebo 自带的 `Screenshot` GUI 插件（服务 `/gui/screenshot`）。它用 **ogre2 从 3D 视图
的相机**直接取帧，**不经过**窗口合成器——所以 Wayland 也取得到。实测本仓 `agc_world.sdf` 的
`<gui>` 块**覆盖**了发行版默认 `gui.config`，里面**没有** Screenshot 插件，故：

1. 从世界 SDF 的 `<gui>` 块**派生**一份 gui-config（不手抄、不复制整份默认配置）；
2. 在派生的配置里**追加** `Screenshot` 插件（只加这一个，其余原样）；
3. `gz sim` 用 `--gui-config` 加载它 → 服务 `/gui/screenshot` 上线；
4. 发 `gz.msgs.StringMsg{data: "<输出路径>"}` → 插件把该相机视图存成 PNG。

## 与 P1-1 round-6 结论的关系（必须写清，不得改写历史）

P1-1 round-6 记录"本机无可用截屏工具（xwd/import/ffmpeg/scrot 全缺），故不宣称像素级截图证据"。
那条结论**在当时成立且未被推翻**：它列的工具确实全缺。本脚本是**新增的第四条路径**
（Gazebo 内部相机取帧），不在原清单内。**不追溯改写** round-6 的结论，只补一条可用的新手段。

## 纪律

* **只取真实帧**：本脚本不合成、不裁剪、不叠字；取到的就是 ogre2 渲染出的画面。
* **取不到就报失败**：服务不在、响应 false、文件没生成 → 非 0 退出，**不得**用旧图或示意图冒充。
* **不启停仿真**：本脚本只发服务调用，进程生命周期仍归 `run_demo.sh` / `start.py`。
* 输出目录由调用方给，本脚本不写项目内文件（`docs/plan/assets/` 由调用方显式指定）。

## 用法

```bash
# 一次性：派生 gui-config（调试用；正常由 start.py 自动做）
python3 scripts/demo/gui_capture.py derive-config --world <sdf> --out /tmp/gui.config

# 取一帧（GUI 已在跑）
python3 scripts/demo/gui_capture.py snap --out experiments/p2-1/run/shot.png

# 逐帧录（10–15 s GIF 用；每帧一个 PNG，后续由 make_gif.py 合成）
python3 scripts/demo/gui_capture.py frames --outdir experiments/p2-1/run/frames \
    --count 30 --interval 0.5
```

退出码：`0` 成功；`1` 取帧失败（服务缺失 / 响应 false / 文件未生成）；`2` 用法错误。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
SCREENSHOT_SERVICE = '/gui/screenshot'
SCREENSHOT_REQ_TYPE = 'gz.msgs.StringMsg'
SCREENSHOT_REP_TYPE = 'gz.msgs.Boolean'

# 追加的插件块：只加 Screenshot，**不改**世界 SDF 里已有的任何 GUI 插件。
# 字段取自发行版默认 `gui.config` 的同一插件块（`Screenshot` 是 gz-gui 内置插件，
# 不依赖本仓代码，故此处照抄其必要属性；属性只影响工具条外观，不影响取到的画面）。
SCREENSHOT_PLUGIN = '''  <plugin filename="Screenshot" name="Screenshot">
    <gz-gui>
      <property key="resizable" type="bool">false</property>
      <property key="x" type="double">250</property>
      <property key="y" type="double">50</property>
      <property key="width" type="double">50</property>
      <property key="height" type="double">50</property>
      <property key="state" type="string">floating</property>
      <property key="showTitleBar" type="bool">false</property>
      <property key="cardBackground" type="string">#777777</property>
    </gz-gui>
  </plugin>
'''


def _blank_comments(text):
    """把 XML 注释替换成等长空白（**保持偏移不变**），避免在注释里的示例标签上匹配。

    实测踩坑：`agc_world.sdf` 的 `<gui>` 上方注释里写了 `<gui><plugin MinimalScene>…`
    这样的**说明文字**，直接用正则 `re.search(r'<gui\\b')` 会先命中注释里的那一处，
    派生出以注释片段开头的非法 XML（`xmllint` 报 `Specification mandates value`）。
    """
    return re.sub(r'<!--.*?-->', lambda m: ' ' * len(m.group(0)), text, flags=re.S)


def _find_gui_block(text):
    """返回真实 `<gui>…</gui>` 块体的 (start, end) 偏移；找不到返回 None。

    只在**注释之外**查找（见 `_blank_comments` 的实测踩坑说明）。
    """
    clean = _blank_comments(text)
    m = re.search(r'<gui\b[^>]*>', clean)
    if not m:
        return None
    start = m.end()
    end = clean.find('</gui>', start)
    if end < 0:
        return None
    return start, end


def derive_config(world_sdf, out_path):
    """从世界 SDF 的 `<gui>` 块派生 gui-config，并追加 Screenshot 插件。

    返回 (ok, detail)。世界里已有 Screenshot 时**不重复追加**（幂等）。
    """
    with open(world_sdf, encoding='utf-8') as f:
        text = f.read()
    span = _find_gui_block(text)
    if span is None:
        return False, '世界 SDF 里没有 <gui> 块：%s' % world_sdf
    body = text[span[0]:span[1]]
    if 'filename="Screenshot"' in body:
        config_body = body
        appended = False
    else:
        config_body = body.rstrip() + '\n' + SCREENSHOT_PLUGIN
        appended = True
    config = ('<?xml version="1.0"?>\n'
              '<!-- 由 scripts/demo/gui_capture.py 从世界 SDF 派生；'
              '仅追加 Screenshot 插件，其余原样。 -->\n'
              '<gui fullscreen="false">\n' + config_body + '\n</gui>\n')
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(config)
    return True, ('已追加 Screenshot 插件' if appended else '世界 SDF 已含 Screenshot 插件（未追加）')


def _gz():
    exe = shutil.which('gz')
    return exe


def service_present(timeout_ms=3000):
    """`/gui/screenshot` 是否在线（GUI 未起或插件未加载时为 False）。"""
    gz = _gz()
    if not gz:
        return False, '找不到 `gz` 命令'
    try:
        proc = subprocess.run([gz, 'service', '-l'], capture_output=True, text=True,
                              timeout=timeout_ms / 1000.0 + 1.0)
    except subprocess.TimeoutExpired:
        return False, 'gz service -l 超时'
    if proc.returncode != 0:
        return False, 'gz service -l 失败：%s' % (proc.stderr or '').strip()[:200]
    listed = [ln.strip() for ln in (proc.stdout or '').splitlines() if ln.strip()]
    return (SCREENSHOT_SERVICE in listed,
            '服务清单里%s %s（共 %d 条）'
            % ('有' if SCREENSHOT_SERVICE in listed else '没有', SCREENSHOT_SERVICE, len(listed)))


def snap(out_path, timeout_ms=15000, retries=1, wait_s=6.0):
    """请求一帧并落到 out_path。返回 (ok, detail)。

    ## 服务的真实语义（读上游源码后确认，2026-10-31）

    `gz-gui` 的 `Screenshot::ScreenshotService`（`gz-gui8/src/plugins/screenshot/Screenshot.cc`）：

    ```cpp
    bool Screenshot::ScreenshotService(const msgs::StringMsg &_msg, msgs::Boolean &_res)
    {
      if (!_msg.data().empty())
        this->dataPtr->directory = _msg.data();   // ← data 是**目录**，不是文件路径
      this->dataPtr->dirty = true;
      _res.set_data(true);                        // ← **立即**返回 true，尚未存盘
      return true;
    }
    ```

    存盘发生在**下一个 Render 事件**里（`eventFilter` 收到 `events::Render::kType` 且 dirty）：

    ```cpp
    std::string time = common::systemTimeISO() + ".png";
    std::string savePath = common::joinPaths(this->dataPtr->directory, time);
    ```

    **两个后果，都踩过**：

    1. 把**完整文件路径**当 `data` 传进去 → 插件把它当目录名，文件实际落在
       `<那个"路径">/<ISO时间戳>.png`，**永远不会**出现在我等的那个文件名上 → 0 帧；
    2. 服务**立刻**返回 `true` → 不能把"响应 true"当作"已存盘"，必须**轮询新文件出现**。

    本实现因此：`data` 传**目录**（`out_path` 的父目录），调用前后记录目录内文件集合，
    轮询**新增**的那个 `.png`，再把它移动/改名成调用方要的 `out_path`。
    """
    gz = _gz()
    if not gz:
        return False, '找不到 `gz` 命令'
    out_abs = os.path.abspath(out_path)
    save_dir = os.path.dirname(out_abs)
    os.makedirs(save_dir, exist_ok=True)
    if os.path.exists(out_abs):
        os.remove(out_abs)          # 防止把旧文件当本次结果
    present, detail = service_present()
    if not present:
        return False, '取帧服务不可用：%s' % detail

    last = ''
    for attempt in range(retries + 1):
        before = set(_png_files(save_dir))
        try:
            proc = subprocess.run(
                [gz, 'service', '-s', SCREENSHOT_SERVICE,
                 '--reqtype', SCREENSHOT_REQ_TYPE, '--reptype', SCREENSHOT_REP_TYPE,
                 '--timeout', str(timeout_ms),
                 '--req', 'data: "%s"' % save_dir],
                capture_output=True, text=True, timeout=timeout_ms / 1000.0 + 3.0)
        except subprocess.TimeoutExpired:
            last = 'gz service 调用超时'
            continue
        text = ((proc.stdout or '') + (proc.stderr or '')).strip()
        responded = bool(re.search(r'\bdata:\s*true\b', text, re.I))
        if proc.returncode != 0 or not responded:
            last = '第 %d 次：rc=%d，响应 %r' % (attempt + 1, proc.returncode, text[:200])
            time.sleep(0.3)
            continue
        # 存盘在下一个 Render 事件，轮询**新增**文件（不能只看"响应 true"）
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            new_files = sorted(set(_png_files(save_dir)) - before)
            if new_files:
                src = os.path.join(save_dir, new_files[-1])
                # 文件可能**还在写**：插件 `SavePNG` 不是原子操作，刚出现时只写了头部，
                # 直接读会得到 `OSError: image file is truncated`（实测踩到）。
                # 判据：文件大小连续两次采样相同且 > 0，才认为写完。
                prev = -1
                for _ in range(60):
                    try:
                        size = os.path.getsize(src)
                    except OSError:
                        size = -1
                    if size > 0 and size == prev:
                        break
                    prev = size
                    time.sleep(0.1)
                try:
                    os.replace(src, out_abs)
                except OSError as exc:      # noqa: BLE001
                    return False, '新帧改名失败：%s（源 %s）' % (exc, src)
                return True, '%s（%d 字节）' % (out_abs, os.path.getsize(out_abs))
            time.sleep(0.1)
        last = '第 %d 次：服务返回 true，但 %.0f s 内目录内无新 png（%s）' % (
            attempt + 1, wait_s, save_dir)
    return False, last or '取帧失败'


def _png_files(directory):
    """目录内的 .png 文件名集合（不存在时返回空集）。"""
    try:
        return {n for n in os.listdir(directory) if n.lower().endswith('.png')}
    except OSError:
        return set()


def record_frames(outdir, count, interval_s, prefix='frame', timeout_ms=15000):
    """逐帧录：每 interval_s 取一帧，共 count 帧。返回 (ok, frames, detail)。"""
    os.makedirs(outdir, exist_ok=True)
    frames = []
    for i in range(count):
        path = os.path.join(outdir, '%s-%03d.png' % (prefix, i))
        ok, detail = snap(path, timeout_ms=timeout_ms)
        if not ok:
            return False, frames, '第 %d/%d 帧失败：%s' % (i + 1, count, detail)
        frames.append(path)
        if i + 1 < count:
            time.sleep(interval_s)
    return True, frames, '取到 %d 帧（间隔 %.2f s）' % (len(frames), interval_s)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='Gazebo GUI 3D 视图取帧')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('derive-config', help='从世界 SDF 派生 gui-config（追加 Screenshot 插件）')
    p.add_argument('--world', required=True)
    p.add_argument('--out', required=True)

    p = sub.add_parser('snap', help='取一帧')
    p.add_argument('--out', required=True)
    p.add_argument('--timeout-ms', type=int, default=15000)

    p = sub.add_parser('frames', help='逐帧录')
    p.add_argument('--outdir', required=True)
    p.add_argument('--count', type=int, default=30)
    p.add_argument('--interval', type=float, default=0.5)
    p.add_argument('--prefix', default='frame')
    p.add_argument('--timeout-ms', type=int, default=15000)

    p = sub.add_parser('probe', help='只查取帧服务是否在线')
    p.add_argument('--timeout-ms', type=int, default=3000)

    args = ap.parse_args(argv)

    if args.cmd == 'derive-config':
        ok, detail = derive_config(args.world, args.out)
        print('[gui_capture] %s → %s' % (detail, args.out))
        return 0 if ok else 1

    if args.cmd == 'probe':
        present, detail = service_present(args.timeout_ms)
        print('[gui_capture] %s：%s' % ('在线' if present else '不可用', detail))
        return 0 if present else 1

    if args.cmd == 'snap':
        ok, detail = snap(args.out, timeout_ms=args.timeout_ms)
        print('[gui_capture] %s：%s' % ('取帧成功' if ok else '取帧失败', detail))
        return 0 if ok else 1

    if args.cmd == 'frames':
        ok, frames, detail = record_frames(args.outdir, args.count, args.interval,
                                           prefix=args.prefix, timeout_ms=args.timeout_ms)
        print('[gui_capture] %s：%s' % ('录制成功' if ok else '录制失败', detail))
        if frames:
            print('[gui_capture] 首帧 %s；末帧 %s' % (frames[0], frames[-1]))
        return 0 if ok else 1

    return 2


if __name__ == '__main__':
    sys.exit(main())
