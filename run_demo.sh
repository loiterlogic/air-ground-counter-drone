#!/usr/bin/env bash
# run_demo.sh —— AGC 一键演示入口（P1-2）
#
#   ./run_demo.sh                 # 默认：full 后端 + yard 地图 + 主场景 s04 + GUI
#   ./run_demo.sh --headless      # 无头（快跑 / 服务器）
#   ./run_demo.sh --map open_field
#   ./run_demo.sh --duration 120  # 到时自动停
#   ./run_demo.sh --backend lightweight
#   ./run_demo.sh stop            # 停掉本脚本起的全部进程（可在另一个终端执行）
#   ./run_demo.sh status          # 看当前实例与残留（只读）
#   ./run_demo.sh doctor          # 只做环境预检，不启动任何仿真
#   ./run_demo.sh compare <gui> <headless>   # GUI ↔ headless 等价核验
#
# 真源：docs/plan/p1-2-一键演示入口.md#p1-2-goal
# 口径：默认 full + yard + s04 + observe_yaw_mode=target
#       observe_yaw_mode=target 是**显式 oracle 指向臂**（机头对准真值方位），
#       不是默认 velocity，也不代表真实视觉识别；目标测量仍走 air_fusion。
#       依据：.coordination/archive/20261029-006-p1-1-scene-assets/round-7/review.md#p1-1-r7-acceptance
#
# 纪律：
#   * 薄封装：不复制 launch 编排，参数一律透传 w6.launch.py（ADR-0061）；
#   * 不新增命令者：不写 /agc/ground/cmd_vel、不写模型位姿（#execution-port）；
#   * 进程组回收只按记录的 PID/PGID，**禁止 pkill -f**（整链排障速查#0-三条环境铁律）；
#   * stop 不删除任何证据目录。

set -o pipefail

# 原始命令行（写进证据，便于复现；在任何 shift 之前捕获）
ORIG_ARGV="$0 $*"

ROOT="/home/chen/AGC"
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
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------- 解析参数 ----------------------------
MODE="start"
HEADLESS=0
WORLD_MAP=""
SCENE=""
DURATION=""
BACKEND=""
EXTRA=()
DOCTOR_ONLY=""
ARGS_REST=()

while [ $# -gt 0 ]; do
  case "$1" in
    stop|doctor|status|compare)
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

# 两处会**直接抛异常**的前置：脚本负责补齐，不让使用者背 export（MAP_DESIGN_PLAYBOOK 14.2）
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
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
  --argv "${ORIG_ARGV}" \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
