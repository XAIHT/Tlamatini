# ArduinoTemplateProject

The bundled scaffold the **Arduiner** agent (Tlamatini) copies when you run
`action='create_project'`. It is the Arduino-family analog of STM32er's *STM32
Template Project* and ESP32er's `pio project init` scaffold — the uniform
"template-project" scheme shared by all three microcontroller agents.

## Layout

```
ArduinoTemplateProject/
├── ArduinoTemplateProject.ino   # primary sketch (renamed to <folder>.ino on scaffold)
├── sketch.yaml                  # board identity profile (peer of platformio.ini)
├── README.md
└── src/
    ├── Heartbeat.h              # board-agnostic non-blocking LED blinker
    └── Heartbeat.cpp
```

`arduino-cli` automatically compiles and links any `.h`/`.cpp` under `src/`, so
this demonstrates a clean multi-file sketch — not just a single `.ino`.

## What it does

Blinks `LED_BUILTIN` once per second and prints a `[heartbeat] beat #N` line over
`Serial` at 115200 baud. Using only `LED_BUILTIN` + `Serial`, it compiles and runs
unchanged on **AVR** (Uno/Nano/Mega/Leonardo), **ESP32/ESP8266**, **SAMD**, and
**RP2040** targets — so it is a safe default for any board the FQBN selects.

The serial heartbeat is deliberate hardware-in-the-loop (HIL) evidence: Arduiner's
bounded `monitor` action drains it to prove the firmware is actually running on the
board, not merely that the upload returned success.

## How Arduiner uses it

1. `create_project` copies this folder to your `sketch_path`, renames the `.ino`
   to match the destination folder name, and stamps `default_fqbn` / `default_port`
   into `sketch.yaml` from the agent's `fqbn` / `port` config.
2. `write_source` overwrites `<folder>.ino` (or any `src/*` file) with your firmware.
3. `build` compiles for the FQBN (auto-installing the core if missing).
4. `upload` / `build_and_upload` flashes it over USB-serial.
5. `monitor` / `monitor_session` streams the serial output back.
