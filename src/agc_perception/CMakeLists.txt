cmake_minimum_required(VERSION 3.8)
project(agc_perception)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(agc_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_geometry REQUIRED)
find_package(OpenCV REQUIRED)
find_package(yaml-cpp REQUIRED)
# gz 真值旁路（gt_bypass）：经 gz-transport 直读 dynamic_pose/info（见 
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)

set(DEPS rclcpp nav_msgs geometry_msgs std_msgs tf2 tf2_ros agc_msgs)

# ---- · 适配层 ----
add_executable(gt_bypass src/gt_bypass.cpp)
ament_target_dependencies(gt_bypass rclcpp geometry_msgs)
target_include_directories(gt_bypass PRIVATE
  ${gz-transport13_INCLUDE_DIRS} ${gz-msgs10_INCLUDE_DIRS})
target_link_libraries(gt_bypass ${gz-transport13_LIBRARIES} ${gz-msgs10_LIBRARIES})

add_executable(ground_odom_adapter src/ground_odom_adapter.cpp)
ament_target_dependencies(ground_odom_adapter ${DEPS})
target_include_directories(ground_odom_adapter PRIVATE include)

add_executable(gt_adapter src/gt_adapter.cpp)
ament_target_dependencies(gt_adapter ${DEPS})
target_include_directories(gt_adapter PRIVATE include)

# ---- · 感知与融合已于 2026-11-06 退役（用户裁定）----
# `air_perception` 节点（发布 /agc/air/obs）自 air_fusion 退役后无消费者，已整体删除：
# 源文件 / 可执行 / sensors_file 通道配置 / perception 场景轴 / 承载者解析链一并移除。
# 防复活闸门见 scripts/tests/test_retirement_ledger.py。

# ---- · 地图 ----
add_executable(map_adapter src/map_adapter.cpp)
# sensor_msgs：2026-11-09 起 map_adapter 订阅 camera_info 推导地面画幅
# （不写死 hfov，避免与 SDF 静默漂移）。
ament_target_dependencies(map_adapter ${DEPS} sensor_msgs)
target_include_directories(map_adapter PRIVATE include)
target_link_libraries(map_adapter yaml-cpp)

# ---- · 正下视语义分割 → 地面 2D 占据观测 ----
add_executable(nadir_projection src/nadir_projection.cpp)
ament_target_dependencies(nadir_projection
  rclcpp sensor_msgs nav_msgs geometry_msgs agc_msgs cv_bridge tf2)
target_include_directories(nadir_projection PRIVATE include ${OpenCV_INCLUDE_DIRS})
target_link_libraries(nadir_projection ${OpenCV_LIBS})

install(TARGETS
  gt_bypass ground_odom_adapter gt_adapter
  map_adapter nadir_projection
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

# 2026-11-04：α-β 速度滤波的可执行判据。
# 此前 `AlphaBeta` 藏在 gt_adapter.cpp 的匿名命名空间里，任何测试都引用不到，
# "σ_v 被抑制 40–100 倍"只能写在 ADR 里而无法复核。现抽到
# include/agc_perception/alpha_beta.hpp，单测直接跑蒙特卡洛。
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_alpha_beta test/test_alpha_beta.cpp)
  target_include_directories(test_alpha_beta PRIVATE include)

  # 正下视投影纯几何（L2：不启 ROS / 不启仿真）
  ament_add_gtest(test_log_odds_grid test/test_log_odds_grid.cpp)
  target_include_directories(test_log_odds_grid PRIVATE include)

  ament_add_gtest(test_nadir_geometry test/test_nadir_geometry.cpp)
  ament_target_dependencies(test_nadir_geometry sensor_msgs image_geometry)
  target_include_directories(test_nadir_geometry PRIVATE include ${OpenCV_INCLUDE_DIRS})
  target_link_libraries(test_nadir_geometry ${OpenCV_LIBS})

  # 多分辨率派生层 + 米制膨胀（L2：纯 header，不启 ROS / 不启仿真）
  ament_add_gtest(test_multi_res_grid test/test_multi_res_grid.cpp)
  target_include_directories(test_multi_res_grid PRIVATE include)
  # 源码层判据需要读 map_adapter.cpp 的原文（"未知格必须短路成 -1"）
  target_compile_definitions(test_multi_res_grid PRIVATE
    AGC_MAP_ADAPTER_SRC="${CMAKE_CURRENT_SOURCE_DIR}/src/map_adapter.cpp")

  # 障碍实例层（几何模型 + 生命周期；L2：纯 header）
  ament_add_gtest(test_obstacle_instances test/test_obstacle_instances.cpp)
  target_include_directories(test_obstacle_instances PRIVATE include)

  # 逐点位置协方差 + 观测视角（ADR-0042；L2：纯 header，不启 ROS / 不启仿真）
  ament_add_gtest(test_point_uncertainty test/test_point_uncertainty.cpp)
  target_include_directories(test_point_uncertainty PRIVATE include)
endif()

ament_package()
