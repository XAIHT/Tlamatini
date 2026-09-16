<!--
═══════════════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove
═══════════════════════════════════════════════════════════════════════════
-->

# ESP32TemplateProject

A known-good **ESP32 firmware baseline**: it blinks the onboard LED and prints
`LED ON` / `LED OFF` over serial at 115200 baud.

This is the project **ESP32er scaffolds** when you run `action: create_project`.
It is a plain PlatformIO project — not a server, not a framework — so you can use
it from Tlamatini, from the `pio` command line, or from VS Code + PlatformIO IDE,
whichever you prefer.

## Why it prints as well as blinks

The smallest useful firmware is the one that proves the **whole chain** works:
toolchain → compile → link → flash over USB → run on silicon → talk back to the
host. If this project builds, uploads and prints, your ESP32 setup is healthy,
and any failure in your own firmware is in *your firmware*, not your environment.

Printing the LED state (rather than only toggling the pin) means you can confirm
the board is alive even when you cannot see the LED — a board in a case, a
variant with no populated LED, or one whose LED sits on a different GPIO.

## Layout

```
ESP32TemplateProject/
├── platformio.ini     board, framework and the two build flags
├── src/main.cpp       the entire firmware
├── include/           your project headers        (see its README)
├── lib/               your private libraries      (see its README)
└── test/              Unity unit tests            (see its README)
```

## Use it from Tlamatini (ESP32er)

ESP32er auto-installs PlatformIO Core on first use, so the only thing you install
yourself is your board's USB-serial driver (CP210x or CH34x).

One `action` per run:

| `action` | What it does | Board needed? |
|---|---|---|
| `validate` | Preflight: is `pio` resolvable, is there a `platformio.ini`, is a port connected? Refuses rather than mis-run. | no |
| `create_project` | Scaffolds **this** project into `project_dir`. | no |
| `build` | `pio run` — compile and link. | no |
| `upload` / `build_and_upload` | `pio run -t upload` — flash over USB. | **yes** |
| `monitor` | Bounded serial monitor for `monitor_seconds`. | **yes** |
| `monitor_session` | Upload, then monitor — "flash it and watch it blink" in one run. | **yes** |
| `scaffold_build_upload` | The whole lifecycle in ONE run: create → build → upload → monitor. | optional |
| `write_source` / `read_source` / `list_sources` | Author or inspect files under `project_dir`. | no |
| `boards` | Search the board database. | no |

A natural chat prompt:

> *Using ESP32er, scaffold an ESP32 project at `C:\Development\MyBlink`, build it,
> upload it to my board on COM5, then monitor the serial port for 8 seconds.*

## Use it standalone (no Tlamatini)

You need [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/)
and your board's USB driver. From this folder:

```bash
pio run                 # compile  (the FIRST build downloads the espressif32
                        # platform + toolchain — several hundred MB — once)
pio run -t upload       # flash over the onboard USB-serial bootloader (no JTAG)
pio device monitor      # watch the log at 115200 baud   (Ctrl+] to quit)
```

Expected output:

```
ESP32TemplateProject :: blink starting
LED pin = 2, interval = 500 ms
LED ON
LED OFF
LED ON
...
```

## Retargeting another ESP32 variant

1. List the boards: `pio boards espressif32` (or ESP32er `action='boards'`).
2. Change `board =` in `platformio.ini` — e.g. `esp32-s3-devkitc-1`, `esp32-c3-devkitm-1`.
3. If that board's LED is on a different GPIO, change `-DBLINK_LED_PIN=` to match
   (S3 DevKitC is usually GPIO 48; C3 DevKitM is usually GPIO 8).

No source edit is needed for either change — that is what the build flags are for.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Could not open COMx` / access denied | The port is held by another program. | Close the other serial monitor / IDE, then retry. |
| Upload stalls at `Connecting...` | The board is not in bootloader mode. | Hold **BOOT**, tap **EN/RST**, release **BOOT**, retry. Some boards need this every time. |
| No serial output at all | Baud mismatch. | `monitor_speed` in `platformio.ini` must equal `Serial.begin()` in `src/main.cpp` (both 115200 here). |
| Garbled characters | Wrong baud rate. | Same as above. |
| Board not listed at all | Missing USB-serial driver. | Install CP210x (Silicon Labs) or CH34x, then re-plug. |
| First build takes forever | It is downloading the toolchain. | Expected, once. Later builds are seconds. |

## License

MIT — see `LICENSE` in the standalone repository distribution.
