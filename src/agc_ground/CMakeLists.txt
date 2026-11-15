cmake_minimum_required(VERSION 3.8)
project(agc_ground)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(agc_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
# 离线基线：复用 Nav2 planner 插件 + agc_control LQR 控制器插件（ADR-0003/ADR-0004）
find_package(agc_control REQUIRED)
find_package(pluginlib REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(nav2_core REQUIRED)
find_package(nav2_costmap_2d REQUIRED)
find_package(nav2_util REQUIRED)

# 命令源为 agc_rl 的推理节点（Python）；原 ground_policy_placeholder 已退役。
add_executable(ground_drive_relay src/ground_drive_relay.cpp)
ament_target_dependencies(ground_drive_relay rclcpp geometry_msgs)

# 自体过滤（自返回置 inf，供包围式旋转/后向 zone 使用）
add_executable(scan_self_filter src/scan_self_filter.cpp)
ament_target_dependencies(scan_self_filter rclcpp sensor_msgs)

# 地面安全层（自研，ADR-0045）：唯一障碍输入 = 任务1 的 `/agc/map`，不订阅 scan/costmap。
# 判定逻辑在 `include/agc_ground/safety_policy.hpp`（纯类，可脱 ROS 单测）。
# 不链接任何 nav2_*：安全层与 Nav2 运行时彻底解耦。
add_executable(ground_safety_filter src/ground_safety_filter.cpp)
target_include_directories(ground_safety_filter PRIVATE include)
ament_target_dependencies(ground_safety_filter
  rclcpp geometry_msgs nav_msgs std_msgs agc_msgs)

# 离线对照基线（Nav2 planner 插件 + agc_control LQR 插件 + 内建 costmap）
add_executable(ground_baseline src/ground_baseline.cpp)
target_include_directories(ground_baseline PRIVATE include)
target_link_libraries(ground_baseline Eigen3::Eigen)
ament_target_dependencies(ground_baseline
  rclcpp rclcpp_lifecycle geometry_msgs nav_msgs agc_msgs
  agc_control pluginlib tf2_ros nav2_core nav2_costmap_2d nav2_util)

# 无 shield 对照臂的恒等透传（纯仿真；[ADR-0022](../../docs/adr/0022-research-propositions-and-decision-rule.md#top)）

# 地面全局路径规划器（Hybrid A* on SE(2)，ADR-0048）——只发路径，不发速度。
# 不链接 nav2_*、不含 costmap；Navfn 属离线基线（ground_baseline），与本节点无关。
# 核心算法在 `include/agc_ground/planner_*.hpp` 等纯头文件里（不 include ROS），
# 因此可被 gtest 与离线回放直接验证（《测试分层与可测性》）。
add_executable(hybrid_astar_se2_planner src/hybrid_astar_se2_planner.cpp)
target_include_directories(hybrid_astar_se2_planner PRIVATE include)
ament_target_dependencies(hybrid_astar_se2_planner
  rclcpp geometry_msgs nav_msgs std_msgs agc_msgs)

install(TARGETS
  ground_drive_relay
  ground_baseline
  ground_safety_filter
  scan_self_filter
  hybrid_astar_se2_planner
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

install(DIRECTORY include/
  DESTINATION include)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  # 未知空间规划策略：纯逻辑判定（不启 ROS / 不启仿真）。
  # 守护"未知不可走"这条口径 —— 它不依赖任何 Navfn 私有参数（与 Nav2 解绑）。
  ament_add_gtest(test_planning_unknown_policy test/test_planning_unknown_policy.cpp)
  target_include_directories(test_planning_unknown_policy PRIVATE include)
  # 地面安全层判定表：25 例逐条断言"状态 + 输出速度 + 诊断原因"（ADR-0045 配套规范）。
  # 纯逻辑、不启 ROS：判定类若必须起 ROS 才能测，说明它没抽干净。
  ament_add_gtest(test_safety_policy test/test_safety_policy.cpp)
  target_include_directories(test_safety_policy PRIVATE include)
  # 规划器纯算法：13 项判据（数据模型 / 分类 / footprint / 基元 / 剪枝 / 启发式 /
  # 解析连接 / 绕障 / 距离场 / 优化 / 曲率动力学 / 失败分类 / 确定性）。
  # 全部合成小图，不启 ROS、不启仿真。
  ament_add_gtest(test_planner_algorithms test/test_planner_algorithms.cpp)
  target_include_directories(test_planner_algorithms PRIVATE include)
  # 离线回放器（不是测试，是可执行工具）：读一份栅格 + 起终点，跑**生产规划器**，
  # 输出路径与诊断。供真实地图（dense_map / yard）的离线取证用。
  add_executable(planner_replay test/planner_replay.cpp)
  target_include_directories(planner_replay PRIVATE include)
  install(TARGETS planner_replay DESTINATION lib/${PROJECT_NAME})
  # 离线重放器（不是测试，是可执行工具）：把录制的 SafetyInputs 序列喂给**生产判定类**，
  # 逐拍与在线对拍。装到 lib/ 下供联调用；它不订阅任何话题，不构成命令者。
  add_executable(safety_replay test/safety_replay.cpp)
  target_include_directories(safety_replay PRIVATE include)
  install(TARGETS safety_replay DESTINATION lib/${PROJECT_NAME})
endif()

ament_package()
