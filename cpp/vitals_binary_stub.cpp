/**
 * vitals_binary_stub.cpp — Simulated vitals output for development.
 *
 * ── What This Is ──────────────────────────────────────────────────────────────
 * A stand-in for the real Presage SmartSpectra SDK camera process.
 * Outputs one JSON line per second to stdout. The Python server reads this
 * via subprocess.Popen with stdout=PIPE and a background readline() thread.
 *
 * ── Output Format ─────────────────────────────────────────────────────────────
 * One JSON object per line, newline-terminated, flushed immediately:
 *   {"pulse": 72.4, "breathing": 14.1, "timestamp": 1709123456.789}
 *
 * Fields:
 *   pulse      — heart rate in beats per minute (bpm)
 *   breathing  — breathing rate in breaths per minute
 *   timestamp  — Unix epoch time in seconds (float, millisecond precision)
 *
 * ── How to Compile ────────────────────────────────────────────────────────────
 *   cd cpp
 *   g++ -O2 -o vitals_stub vitals_binary_stub.cpp
 *   ./vitals_stub          # test manually — you should see JSON every second
 *
 * ── Replacing With the Real Presage SmartSpectra SDK ─────────────────────────
 * Each stub section below is marked [STUB]. Replace them as follows:
 *
 *   [STUB] srand / seed setup
 *     → SmartSpectra::SDK sdk;
 *       sdk.setLicense("YOUR_LICENSE_KEY");   // from Presage dashboard
 *       sdk.init(0);   // camera_index = 0
 *       sdk.start();
 *
 *   [STUB] random pulse / breathing generation
 *     → double pulse     = sdk.getPulseRate();       // returns bpm or NaN if not ready
 *       double breathing = sdk.getBreathingRate();   // returns br/min or NaN if not ready
 *       // Optionally check sdk.isReady() before reading values
 *
 *   [STUB] sleep(1) main loop delay
 *     → Use the SDK's native event/callback loop if it provides one, or
 *       poll at a rate recommended in the SDK docs (typically 1–5 Hz).
 *
 * SDK reference:  https://presagetech.com/smartspectra
 * SDK header:     SmartSpectra.h (provided in the SDK distribution package)
 *
 * ── Important: stdout flushing ────────────────────────────────────────────────
 * fflush(stdout) after every printf is CRITICAL. Without it, the C runtime
 * buffers output and Python's readline() will block indefinitely.
 * The real SDK integration must preserve this fflush() call.
 */

#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <unistd.h>   // sleep()

int main() {
    // [STUB] Seed the random number generator with current time.
    // TODO (real SDK): replace the three lines below with SDK init:
    //   SmartSpectra::SDK sdk;
    //   sdk.setLicense("YOUR_LICENSE_KEY");
    //   sdk.init(0);   // camera index 0
    //   sdk.start();
    srand(static_cast<unsigned int>(time(nullptr)));

    while (true) {
        // [STUB] Simulate pulse: random value in [60, 100] bpm.
        // TODO (real SDK): double pulse = sdk.getPulseRate();
        double pulse = 60.0 + (rand() % 41);

        // [STUB] Simulate breathing: random value in [10, 20] breaths/min.
        // TODO (real SDK): double breathing = sdk.getBreathingRate();
        double breathing = 10.0 + (rand() % 11);

        // Get current Unix timestamp with sub-second precision.
        // Keep this in the real SDK integration — Python uses it for DB timestamps.
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        double timestamp = static_cast<double>(ts.tv_sec) + ts.tv_nsec / 1.0e9;

        // Output one JSON line — format MUST stay stable (Python parses these keys).
        printf("{\"pulse\": %.1f, \"breathing\": %.1f, \"timestamp\": %.3f}\n",
               pulse, breathing, timestamp);

        // CRITICAL: flush stdout immediately so Python readline() receives the line.
        // Without this, output is buffered and the Python reader thread will stall.
        fflush(stdout);

        // [STUB] Wait 1 second before the next reading.
        // TODO (real SDK): replace with SDK callback / event loop as appropriate.
        sleep(1);
    }

    return 0;
}
