# `include/` — project header files

> Latest released version: **[v1.93.5](../../../../../../docs/changes/2026-11-12-v1.93.5.md)**.


Put your own `.h` / `.hpp` files here. PlatformIO adds this directory to the
compiler's include path automatically, so a header placed here is reachable as:

```cpp
#include "MyHeader.h"
```

from anywhere in `src/`.

Use this for headers that belong to **this project**. Reusable code meant to be
shared between projects belongs in `lib/` instead (see `lib/README.md`).
