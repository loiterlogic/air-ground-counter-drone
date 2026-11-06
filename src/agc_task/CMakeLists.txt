cmake_minimum_required(VERSION 3.8)
project(agc_task)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(agc_msgs REQUIRED)
find_package(ros_gz_interfaces REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

add_executable(task_manager src/task_manager.cpp)
ament_target_dependencies(task_manager
  rclcpp geometry_msgs nav_msgs std_msgs std_srvs agc_msgs)

add_executable(scenario_reset src/scenario_reset.cpp)
ament_target_dependencies(scenario_reset
  rclcpp geometry_msgs nav_msgs std_msgs std_srvs agc_msgs ros_gz_interfaces)

add_executable(run_logger src/run_logger.cpp)
ament_target_dependencies(run_logger
  rclcpp geometry_msgs nav_msgs sensor_msgs nav2_msgs trajectory_msgs std_msgs agc_msgs
  ros_gz_interfaces)
target_include_directories(run_logger PRIVATE include)

add_executable(capture_adjudicator src/capture_adjudicator.cpp)

# 2026-11-03：目标机"是否真的起飞"的启动期守卫（见该文件头部的病灶说明）。
add_executable(target_takeoff_guard src/target_takeoff_guard.cpp)
ament_target_dependencies(target_takeoff_guard rclcpp std_msgs geometry_msgs)
ament_target_dependencies(capture_adjudicator
  rclcpp nav_msgs std_msgs agc_msgs)
target_include_directories(capture_adjudicator PRIVATE include)

install(TARGETS task_manager scenario_reset run_logger capture_adjudicator target_takeoff_guard
  DESTINATION lib/${PROJECT_NAME})

# 前置 P / 拦截裁决：Python 节点（入侵者驱动 + 干扰注入）
install(PROGRAMS scripts/intruder_driver.py DESTINATION lib/${PROJECT_NAME} RENAME intruder_driver)
install(PROGRAMS scripts/jammer.py DESTINATION lib/${PROJECT_NAME} RENAME jammer)
# R6：演示叠加层（RViz marker 层）。GUI 保持纯场景，语义层单独一个节点。
install(PROGRAMS scripts/viz_markers.py DESTINATION lib/${PROJECT_NAME} RENAME viz_markers)
install(FILES config/agc_demo.rviz DESTINATION share/${PROJECT_NAME}/config)

install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

# ADR-0014：场景配置不变量（纯配置，不启仿真）——防止"授权射击 + 里程碑仍为终态"的
# 自相矛盾配置让捕获结局永不可达（实测 s08 曾 20/20 落 TRACKING_SUCCESS）。
if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(scene_config_invariants "test/test_scene_config_invariants.py")
  # ADR-0011：目标运动估计（静止阈值 / 时间窗回归 / 新息门 / 提前量上限）单测
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_target_motion_filter test/test_target_motion_filter.cpp)
  target_include_directories(test_target_motion_filter PRIVATE include)
  # ADR-0011：火控在飞生命周期（在飞推进 / 落地 / 超时 / 中止）确定性单测
  ament_add_gtest(test_dynamic_fire_control test/test_dynamic_fire_control.cpp)
  target_include_directories(test_dynamic_fire_control PRIVATE include)
  # P0 / T2：summary.json epoch 秒精度回归（17 位有效数字，防退化为科学计数法）
  ament_add_gtest(test_epoch_seconds test/test_epoch_seconds.cpp)
  target_include_directories(test_epoch_seconds PRIVATE include)
  # 证据 JSON 的标量序列化（转义 / 非有限 → null / 数值往返）；无 ROS 依赖
  ament_add_gtest(test_json_value test/test_json_value.cpp)
  target_include_directories(test_json_value PRIVATE include)
  # P3 / ADR-0021：固定预算任务 FCO 积分器（手算确定性案例）
  ament_add_gtest(test_mission_fco_fixed_budget test/test_mission_fco_fixed_budget.cpp)
  target_include_directories(test_mission_fco_fixed_budget PRIVATE include)
  # P3 / ADR-0021：真实 run_logger 节点级合成 /clock + 消息链
  ament_add_pytest_test(test_run_logger_mission_fco "test/test_run_logger_mission_fco.py")
endif()

ament_package()