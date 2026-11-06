#!/usr/bin/env bash
# run_demo.sh —— AGC 一键演示入口
#
# ./run_demo.sh # 默认：full 后端 + yard 地图 + 主场景 s04 + GUI
# ./run_demo.sh --headless # 无头（快跑 / 服务器）
# ./run_demo.sh --map open_field
# ./run_demo.sh --escape # 显式启用目标逃逸
# ./run_demo.sh --backend lightweight
# ./run_demo.sh --gui-render-backend software # auto（默认）| d3d12 | software
# ./run_demo.sh stop|status|doctor|test|compare # 见各子命令
#
# 薄封装：不复制 launch 编排，参数透传 w6.launch.py（ADR-0020）。
# 不新增命令者：不写 /agc/ground/cmd_vel、不写模型位姿（ADR-0020）。
# 进程回收只按记录的 PID/PGID，禁止 pkill -f；stop 不删证据目录。

set -o pipefail

# 原始命令行（写进证据，便于复现；在任何 shift 之前捕获）
ORIG_ARGV="$0 $*"

# 项目根按脚本位置自定位，保证 clone 到任意路径都操作当前仓库。
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DEMO_PY="${ROOT}/scripts/demo"
ROS_SETUP="/opt/ros/jazzy/setup.bash"
WS_SETUP="${ROOT}/install/setup.bash"

# ---------------------------- 人话错误 ----------------------------
fail() { # fail <标题> <第1行> [第2行…]
  local title="$1"; shift
  echo "" >&2
  echo "======================================================================" >&2
  echo "[run_demo] 错误：${title}" >&2
  echo "----------------------------------------------------------------------" >&2
  local line
  for line in "$@"; do echo "  ${line}" >&2; done
  echo "======================================================================" >&2
}

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------- 解析参数 ----------------------------
MODE="start"
HEADLESS=0
WORLD_MAP=""
SCENE=""
DURATION=""
BACKEND=""
GUI_RENDER_BACKEND=""
EXTRA=()
DOCTOR_ONLY=""
ARGS_REST=()

while [ $# -gt 0 ]; do
  case "$1" in
    stop|doctor|status|test|compare)
      MODE="$1"; shift
      while [ $# -gt 0 ]; do ARGS_REST+=("$1"); shift; done
      break ;;
    -h|--help) usage; exit 0 ;;
    --headless) HEADLESS=1; shift ;;
    --gui) HEADLESS=0; shift ;;
    --map) WORLD_MAP="${2:-}"; [ -z "$WORLD_MAP" ] && { fail "--map 需要一个值" "可用：yard | open_field | minimal"; exit 2; }; shift 2 ;;
    --scene) SCENE="${2:-}"; shift 2 ;;
    --duration) DURATION="${2:-}"; shift 2 ;;
    --backend) BACKEND="${2:-}"; shift 2 ;;
    --gui-render-backend) GUI_RENDER_BACKEND="${2:-}"; shift 2 ;;
     --escape) EXTRA+=("escape"); shift ;;
     --dry-run) EXTRA+=("dry-run"); shift ;;
    --follow-timeout) EXTRA+=("follow-timeout:$2"); shift 2 ;;
    --ready-timeout) EXTRA+=("ready-timeout:$2"); shift 2 ;;
    --start-timeout) EXTRA+=("start-timeout:$2"); shift 2 ;;
    --inject-missing-env) EXTRA+=("inject-missing-env"); shift ;;
    *) fail "不认识的参数：$1" "见 ./run_demo.sh --help"; exit 2 ;;
  esac
done

# ---------------------------- 环境 ----------------------------
# 自动 source（这是**脚本自身的职责**；"少 source 的故障提示"另用隔离 env 测试，见 doctor 的 inject 项）
source_ros() {
  if [ ! -f "$ROS_SETUP" ]; then
    fail "ROS 2 Jazzy 未安装" "缺少 ${ROS_SETUP}" "先装 ROS 2 Jazzy：https://docs.ros.org/en/jazzy/"
    exit 1
  fi
  # shellcheck disable=SC1090
  . "$ROS_SETUP" >/dev/null 2>&1
}
source_ws() {
  if [ ! -f "$WS_SETUP" ]; then
    fail "工作区未构建" "缺少 ${WS_SETUP}" "先构建：cd ${ROOT} && colcon build --symlink-install"
    exit 1
  fi
  # shellcheck disable=SC1090
  . "$WS_SETUP" >/dev/null 2>&1
}

source_ros
source_ws

# DDS 发现范围 / 传输由 scripts/demo/dds_transport.py 按 lo 能力探测（ADR-0028）；
# 不写死 LOCALHOST。需要钉死时：AGC_DDS_TRANSPORT_POLICY=localhost-udp|subnet-shm|subnet-udp
_dds_env="$(python3 -c '
import os, sys
sys.path.insert(0, os.path.join("'"${ROOT}"'", "scripts", "demo"))
import dds_transport as d
try:
    print(d.describe())
    resolved = d.resolve()
except ValueError as exc:
    sys.stderr.write("[run_demo] 错误：%s\n" % exc); raise SystemExit(2)
for key, value in d.env_for(resolved).items():
    print("%s=%s" % (key, "" if value is None else value))
')" || exit 2
echo "[run_demo] ${_dds_env%%$'\n'*}"
unset ROS_AUTOMATIC_DISCOVERY_RANGE FASTDDS_BUILTIN_TRANSPORTS
while IFS= read -r _line; do
  case "$_line" in *=*) export "${_line?}";; esac
done <<< "${_dds_env#*$'\n'}"
if [ -z "${ROS_DOMAIN_ID:-}" ]; then export ROS_DOMAIN_ID=0; fi
export GZ_SIM_SYSTEM_PLUGIN_PATH="${ROOT}/install/agc_sim/lib${GZ_SIM_SYSTEM_PLUGIN_PATH:+:${GZ_SIM_SYSTEM_PLUGIN_PATH}}"

# 故障注入：模拟"少 source"（仅用于证明提示链路，**不影响**正常路径）
if [[ " ${EXTRA[*]-} " == *" inject-missing-env "* ]]; then
  EXTRA=("${EXTRA[@]/inject-missing-env}")
  unset AMENT_PREFIX_PATH
  export AMENT_PREFIX_PATH=""
  export COLCON_PREFIX_PATH=""
fi

export PYTHONPATH="${DEMO_PY}:${PYTHONPATH:-}"

# ---------------------------- 子命令 ----------------------------
case "$MODE" in
  doctor)
    exec python3 "${DEMO_PY}/main.py" doctor "$@"
    ;;
  stop)
    exec python3 "${DEMO_PY}/main.py" stop
    ;;
  status)
    exec python3 "${DEMO_PY}/main.py" status
    ;;
  compare)
    exec python3 "${DEMO_PY}/main.py" compare "${ARGS_REST[@]}"
    ;;
  test)
    # 冒烟门槛：离线、只读、不启仿真；语义见 tests/run_smoke.py
    exec python3 "${ROOT}/tests/run_smoke.py" ${ARGS_REST[@]+"${ARGS_REST[@]}"}
    ;;
esac

# start：先跑预检（失败即停，不启动仿真）
# 注意：doctor 项在这里**复用**，但 start 不重跑全部重型检查，只做阻断性检查。
python3 "${DEMO_PY}/main.py" preflight --headless "$HEADLESS" || exit $?

# 组装参数
EXTRA_ARGS=()
for e in "${EXTRA[@]-}"; do [ -n "$e" ] && EXTRA_ARGS+=("$e"); done

exec python3 "${DEMO_PY}/main.py" start \
  --headless "$HEADLESS" \
  --map "${WORLD_MAP}" \
  --scene "${SCENE}" \
  --duration "${DURATION}" \
  --backend "${BACKEND}" \
  --gui-render-backend "${GUI_RENDER_BACKEND}" \
  --argv "${ORIG_ARGV}" \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
