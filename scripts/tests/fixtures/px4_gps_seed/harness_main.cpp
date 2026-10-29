// Host harness: compiles the *production* SensorGpsSim.cpp and exercises its
// private RNG only for seed-protocol verification.  Not a RNG rewrite.
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>

#define private public
#define protected public
#include "SensorGpsSim.cpp"

int main(int argc, char **argv)
{
	if (argc < 2) {
		std::fprintf(stderr, "usage: %s <seq|state|invalid> [seed|UNSET] [n]\n", argv[0]);
		return 2;
	}

	const std::string mode = argv[1];
	const char *seed = (argc > 2) ? argv[2] : "UNSET";
	const int n = (argc > 3) ? std::atoi(argv[3]) : 8;

	if (std::strcmp(seed, "UNSET") == 0) {
		unsetenv("AGC_PX4_SIM_SEED");

	} else {
		setenv("AGC_PX4_SIM_SEED", seed, 1);
	}

	SensorGpsSim gps;
	const bool ok = gps.init();

	if (mode == "invalid") {
		std::printf("%s\n", ok ? "ACCEPTED" : "REJECTED");
		return ok ? 0 : 3;
	}

	if (!ok) {
		std::printf("INVALID\n");
		return 3;
	}

	std::printf("STATE=%u\n", static_cast<unsigned>(gps._rng_state));

	for (int i = 0; i < n; ++i) {
		std::printf("%.9g\n", static_cast<double>(gps.generate_wgn()));
	}

	return 0;
}
