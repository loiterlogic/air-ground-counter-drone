// Minimal PX4 host stubs used only to compile the production SensorGpsSim
// translation unit for RNG tests.  These are not a RNG reimplementation.
#pragma once

#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define __EXPORT
#define PX4_OK 0
#define PX4_ERROR -1
#define MODULE_NAME "sensor_gps_sim"
#define DRV_GPS_DEVTYPE_SIM 0x1234
#define ORB_ID(name) 0
#define PRINT_MODULE_DESCRIPTION(x)
#define PRINT_MODULE_USAGE_NAME(a, b)
#define PRINT_MODULE_USAGE_COMMAND(a)
#define PRINT_MODULE_USAGE_DEFAULT_COMMANDS()
#define PX4_WARN(...) do {} while (0)
#define PX4_ERR(...) do {} while (0)
#define PX4_INFO(...) do {} while (0)
#define DEFINE_PARAMETERS(...)

static constexpr int task_id_is_work_queue = -2;

inline uint64_t hrt_absolute_time() { return 0; }

namespace time_literals {
constexpr long double operator""_s(unsigned long long v) { return static_cast<long double>(v); }
constexpr long double operator""_ms(unsigned long long v) { return static_cast<long double>(v); }
}

namespace matrix {
class Vector3f {
public:
	Vector3f() : _d{0.f, 0.f, 0.f} {}
	Vector3f(float x, float y, float z) : _d{x, y, z} {}
	float &operator()(int i) { return _d[i]; }
	const float &operator()(int i) const { return _d[i]; }
	Vector3f operator+(const Vector3f &other) const
	{
		return Vector3f(_d[0] + other._d[0], _d[1] + other._d[1], _d[2] + other._d[2]);
	}
private:
	float _d[3];
};
}

namespace px4 {
namespace wq_configurations {
struct hp_default_t {};
inline constexpr hp_default_t hp_default{};
}

class ScheduledWorkItem {
public:
	ScheduledWorkItem(const char *, const wq_configurations::hp_default_t &) {}
	virtual ~ScheduledWorkItem() = default;
	virtual void Run() = 0;
	void ScheduleOnInterval(long double) {}
	void ScheduleClear() {}
	bool should_exit() const { return false; }
};
}

template <typename T>
class ModuleBase {
public:
	static std::atomic<T *> _object;
	static int _task_id;
	static int main(int, char **) { return 0; }
	static void exit_and_cleanup() {}
};
template <typename T> std::atomic<T *> ModuleBase<T>::_object{nullptr};
template <typename T> int ModuleBase<T>::_task_id = -1;

class ModuleParams {
public:
	ModuleParams() = default;
	explicit ModuleParams(void *) {}
	void updateParams() {}
};

namespace px4 {
namespace params {
struct SIM_GPS_USED {};
}
}

inline int agc_stub_sim_gps_used = 10;

template <typename T>
class ParamInt {
public:
	int get() const { return agc_stub_sim_gps_used; }
};

inline ParamInt<px4::params::SIM_GPS_USED> _sim_gps_used;

typedef void *perf_counter_t;
enum { PC_ELAPSED = 0 };
inline perf_counter_t perf_alloc(int, const char *) { return nullptr; }
inline void perf_free(perf_counter_t) {}
inline void perf_begin(perf_counter_t) {}
inline void perf_end(perf_counter_t) {}

namespace device {
class Device {
public:
	enum DeviceBusType : uint8_t { DeviceBusType_SIMULATION = 0 };
	union DeviceId {
		struct {
			uint8_t bus_type;
			uint8_t bus;
			uint8_t address;
			uint16_t devtype;
		} devid_s;
		uint32_t devid;
	};
};
}

constexpr double CONSTANTS_RADIUS_OF_EARTH = 6371000.0;

namespace math {
inline double degrees(double rad) { return rad * 180.0 / 3.14159265358979323846; }
}

struct parameter_update_s {};

struct sensor_gps_s {
	uint64_t timestamp{0};
	uint64_t timestamp_sample{0};
	uint64_t time_utc_usec{0};
	uint32_t device_id{0};
	double latitude_deg{0};
	double longitude_deg{0};
	double altitude_msl_m{0};
	double altitude_ellipsoid_m{0};
	float s_variance_m_s{0};
	float c_variance_rad{0};
	float eph{0};
	float epv{0};
	float hdop{0};
	float vdop{0};
	int32_t noise_per_ms{0};
	int32_t jamming_indicator{0};
	float vel_m_s{0};
	float vel_n_m_s{0};
	float vel_e_m_s{0};
	float vel_d_m_s{0};
	float cog_rad{0};
	int32_t timestamp_time_relative{0};
	float heading{0};
	float heading_offset{0};
	float heading_accuracy{0};
	int32_t automatic_gain_control{0};
	uint8_t fix_type{0};
	uint8_t jamming_state{0};
	uint8_t spoofing_state{0};
	bool vel_ned_valid{false};
	uint8_t satellites_used{0};
};

struct vehicle_global_position_s {
	double lat{0};
	double lon{0};
	double alt{0};
	uint64_t timestamp_sample{0};
};

struct vehicle_local_position_s {
	float vx{0};
	float vy{0};
	float vz{0};
	uint64_t timestamp_sample{0};
};

namespace uORB {
class Subscription {
public:
	explicit Subscription(int = 0) {}
	bool updated() { return false; }
	bool copy(void *) { return false; }
};

class SubscriptionInterval {
public:
	SubscriptionInterval(int, long double) {}
	bool updated() { return false; }
	bool copy(void *) { return false; }
};

template <typename T>
class PublicationMulti {
public:
	explicit PublicationMulti(int = 0) {}
	void publish(const T &) {}
};
}
