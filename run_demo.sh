#!/usr/bin/env bash
# run_demo.sh —— AGC 一键演示入口
#
# ./run_demo.sh # 默认：full 后端 + yard 地图 + 主场景 s04 + GUI
# ./run_demo.sh --headless # gz 无渲染客户端（-s）；RViz 语义层仍起（固定）
# ./run_demo.sh --map open_field # yard（默认）| open_field | dense_map | minimal
# ./run_demo.sh --scene s01_static_none_nominal_track # 场景 id（见 src/agc_task/config/scenarios.yaml）
# ./run_demo.sh --backend lightweight # full（默认）| lightweight
# ./run_demo.sh --duration 90 # 到时触发 stop（默认跟到终态）
# ./run_demo.sh --escape # 显式启用目标逃逸
# ./run_demo.sh --gui-render-backend software # auto（默认）| d3d12 | software
# ./run_demo.sh --px4-sim-model gz_agc_x500 # 换机型（默认已是带相机的 gz_agc_x500_nadir）
# ./run_demo.sh --dry-run # 只落参数与证据，不启进程
# ./run_demo.sh --ready-timeout 240 # 就绪门超时（s）；另有 --start-timeout / --follow-timeout
# ./run_demo.sh --spawn-verify-timeout 180 # 世界实体就绪上界（s）；dense_map 需调大
# ./run_demo.sh --reset-max-attempts 240 --reset-timeout 240 # 复位就绪门（取先到者）
# ./run_demo.sh stop|status|doctor|test|compare # 见各子命令
#
# 薄封装：不复制 launch 编排，参数透传 main.launch.py（ADR-0020）。
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
  # 打印文件头注释块：第 2 行起，到**第二个空 `#` 行**之前（第一个空行紧跟标题，是分隔）。
  # **不写死行号**——原先写死 `2,14p`，新增参数后帮助就静默漏项（实测 --scene 因此不可见）。
  awk 'NR<2{next}
       /^#$/ { blanks++; if (blanks >= 2) exit; next }
       { sub(/^# ?/, ""); print }' "$0"
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
    --map) WORLD_MAP="${2:-}"; [ -z "$WORLD_MAP" ] && { fail "--map 需要一个值" "可用：yard | open_field | dense_map | minimal"; exit 2; }; shift 2 ;;
    --scene) SCENE="${2:-}"; shift 2 ;;
    --duration) DURATION="${2:-}"; shift 2 ;;
    --backend) BACKEND="${2:-}"; shift 2 ;;
    --gui-render-backend) GUI_RENDER_BACKEND="${2:-}"; shift 2 ;;
    # 透传既有 launch 参数 `px4_sim_model`（机型/资产选择，非路线分支）。
    # 不新增 launch 参数、不改编排：经 EXTRA → main.py opts['extra'] → launch_argv 的
    # argv.extend(extra) 原样成为 ros2 launch 实参。仅放行已知机型，拒绝乱传。
    --px4-sim-model)
      PX4_MODEL="${2:-}"
      case "$PX4_MODEL" in
        gz_agc_x500|gz_x500|gz_x500_mono_cam|gz_agc_x500_nadir) ;;
        *) fail "--px4-sim-model 只接受已知机型" \
             "可用：gz_agc_x500_nadir（默认，带相机）| gz_agc_x500（旧默认，无相机）| gz_x500 | gz_x500_mono_cam" \
             "实际：${PX4_MODEL:-<空>}"; exit 2 ;;
      esac
      EXTRA+=("px4_sim_model:=${PX4_MODEL}"); shift 2 ;;
     --escape) EXTRA+=("escape"); shift ;;
     --dry-run) EXTRA+=("dry-run"); shift ;;
    --follow-timeout) EXTRA+=("follow-timeout:$2"); shift 2 ;;
    --ready-timeout) EXTRA+=("ready-timeout:$2"); shift 2 ;;
    # 世界 spawn 门限（**上界，不是延时**）。密障碍地图（dense_map，620 个障碍）
    # 实测 create 会连续超时约 50 s 才恢复应答，agc_car 需 +68 s —— 默认 60 s 不够。
    # 这是数值参数，不是路线分支。
    --spawn-verify-timeout) EXTRA+=("spawn-verify-timeout:$2"); shift 2 ;;
    # 场景复位就绪门（**两个上界取先到者**）。dense_map 实测实体上线需 90 s+，
    # 默认 60 次 × 1 s = 60 s 必然失败。数值参数，不是路线分支。
    --reset-max-attempts) EXTRA+=("reset-max-attempts:$2"); shift 2 ;;
    --reset-timeout) EXTRA+=("reset-timeout:$2"); shift 2 ;;
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
# 取环境走该模块的**命令行入口**，不在 shell 里内嵌 Python 源码（内嵌写法无法被测试直接调用，
# 且嵌套引号极易在批量改名中被打坏）。
_dds_env="$(python3 "${DEMO_PY}/dds_transport.py")" || exit 2
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
