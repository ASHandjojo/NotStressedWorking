# C++ Vitals Binary

## Overview

The C++ layer is responsible for one thing: **writing vitals JSON to stdout**.

The Python server spawns this binary as a child process (`subprocess.Popen`) and reads its stdout line-by-line in a background thread. The two processes communicate exclusively through this pipe — no sockets, no shared memory.

---

## Output Contract

One JSON object per line, newline-terminated, **flushed immediately** after each write:

```
{"pulse": 72.4, "breathing": 14.1, "timestamp": 1709123456.789}
{"pulse": 75.1, "breathing": 13.8, "timestamp": 1709123457.791}
...
```

| Field | Type | Unit |
|-------|------|------|
| `pulse` | float | beats per minute (bpm) |
| `breathing` | float | breaths per minute |
| `timestamp` | float | Unix epoch seconds (millisecond precision) |

> ⚠️ `fflush(stdout)` after every `printf` is **critical**. Without it, the C runtime buffers output and the Python `readline()` call will block until the buffer is full.

---

## How to Compile the Stub

```bash
cd cpp
g++ -O2 -o vitals_stub vitals_binary_stub.cpp

# Test manually — should print one JSON line per second:
./vitals_stub
```

To use the compiled stub with the server, ensure `.env` contains:
```
CPP_BINARY_PATH=./cpp/vitals_stub
```

---

## How to Replace the Stub with the Real Presage SmartSpectra SDK

The stub file `vitals_binary_stub.cpp` has `[STUB]` comments marking every section that needs to be replaced. Here is the mapping:

| Stub code | Real SDK replacement |
|-----------|---------------------|
| `srand(...)` seed setup | `SmartSpectra::SDK sdk; sdk.setLicense("KEY"); sdk.init(0); sdk.start();` |
| `60.0 + rand() % 41` (pulse) | `sdk.getPulseRate()` — returns `double` (bpm) or `NaN` if not ready |
| `10.0 + rand() % 11` (breathing) | `sdk.getBreathingRate()` — returns `double` (br/min) or `NaN` if not ready |
| `sleep(1)` loop delay | SDK callback / event loop (consult SDK docs for recommended polling rate) |

### Steps

1. Obtain the Presage SmartSpectra SDK (headers + libs) from [https://presagetech.com/smartspectra](https://presagetech.com/smartspectra).
2. Copy `vitals_binary_stub.cpp` to `vitals_main.cpp` (keep the stub for reference).
3. Replace the `[STUB]` sections as shown in the table above.
4. Compile with the SDK:
   ```bash
   g++ -O2 -o vitals_presage vitals_main.cpp -I/path/to/sdk/include -L/path/to/sdk/lib -lSmartSpectra
   ```
5. Update `.env`:
   ```
   CPP_BINARY_PATH=./cpp/vitals_presage
   ```
6. Restart the server — no Python code changes needed.

### Handling NaN from SDK

If the SDK returns `NaN` before the camera is warmed up, guard the output:

```cpp
double pulse = sdk.getPulseRate();
if (!std::isnan(pulse)) {
    // printf the JSON line
}
// else: skip this tick — Python will keep the previous valid value
```

---

## Why a Separate Process?

- **Isolation:** a C++ crash does not take down the Python server.
- **Language boundary:** Presage SDK is C++ — no Python bindings needed.
- **Simplicity:** stdout pipe is the simplest possible IPC; easy to test by running the binary manually.
- **Replaceability:** any vitals source that writes the same JSON format to stdout works without changing the server.
