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

# 离线对照基线（Nav2 planner 插件 + agc_control LQR 插件 + 内建 costmap）
add_executable(ground_baseline src/ground_baseline.cpp)
target_include_directories(ground_baseline PRIVATE include)
target_link_libraries(ground_baseline Eigen3::Eigen)
ament_target_dependencies(ground_baseline
  rclcpp rclcpp_lifecycle geometry_msgs nav_msgs agc_msgs
  agc_control pluginlib tf2_ros nav2_core nav2_costmap_2d nav2_util)

# 无 shield 对照臂的恒等透传（纯仿真；[ADR-0022](../../docs/adr/0022-research-propositions-and-decision-rule.md#top)）

# 几何/直连占位全局规划器（ADR-0013 当前占位阶段）——只发路径，不发速度。
# 不链接 nav2_*、不含 costmap；Navfn 属离线基线（ground_baseline），与本节点无关。
add_executable(placeholder_path_planner src/placeholder_path_planner.cpp)
ament_target_dependencies(placeholder_path_planner
  rclcpp geometry_msgs nav_msgs agc_msgs)

install(TARGETS
  ground_drive_relay
  ground_baseline
  scan_self_filter
  placeholder_path_planner
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
endif()

ament_package()
