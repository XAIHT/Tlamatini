# `test/` — unit tests

PlatformIO's test runner (Unity) picks up tests from this directory. Run them with:

```bash
pio test                 # on the connected board (hardware-in-the-loop)
pio test -e native       # on the host, if you add a [env:native] to platformio.ini
```

…or from Tlamatini chat: ESP32er with `action='test'`.

A test file looks like this:

```cpp
#include <unity.h>

void test_blink_interval_is_sane(void) {
    TEST_ASSERT_GREATER_THAN(0, BLINK_INTERVAL_MS);
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_blink_interval_is_sane);
    return UNITY_END();
}
```

Note that a test run **flashes the board**, replacing the blink firmware. Re-run
`pio run -t upload` (ESP32er `action='upload'`) to put it back.
