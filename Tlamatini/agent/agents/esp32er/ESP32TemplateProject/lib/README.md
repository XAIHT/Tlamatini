# `lib/` — private project libraries

Each subdirectory here is compiled as its own static library and linked in
automatically. A library is just a folder with a `src/` inside it:

```
lib/
└── Blinker/
    ├── src/
    │   ├── Blinker.cpp
    │   └── Blinker.h
    └── library.json      (optional metadata)
```

…then from `src/main.cpp`:

```cpp
#include <Blinker.h>
```

PlatformIO scans `lib/` and builds only the libraries actually `#include`d, so an
unused library here costs nothing at build time.

**Third-party libraries do NOT go here.** Install those with the package manager
so versions are recorded in `platformio.ini`:

```bash
pio pkg install -l "bblanchon/ArduinoJson@^7"
```

…or from Tlamatini chat: ESP32er with `action='pkg_install'` and
`pkg_spec='bblanchon/ArduinoJson@^7'`.
