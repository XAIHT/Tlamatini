/*
 * ArduinoTemplateProject.ino — Tlamatini Arduiner template sketch.
 *
 * This is the bundled scaffold that the Arduiner agent copies when you run
 * action='create_project'. On copy, this .ino is renamed to match the
 * destination folder (arduino-cli requires the primary .ino basename to equal
 * the sketch folder name), and the board identity is stamped into sketch.yaml.
 *
 * It is intentionally board-portable: it uses only LED_BUILTIN + Serial, so it
 * compiles and runs unchanged on AVR (Uno/Nano/Mega/Leonardo), ESP32/ESP8266,
 * SAMD, and RP2040 targets. Replace the body with your firmware.
 *
 * Hardware-in-the-loop (HIL) proof: it blinks the on-board LED AND prints a
 * heartbeat line over Serial every second, so Arduiner's bounded `monitor`
 * action captures evidence the firmware is actually running on the board.
 */

#include "src/Heartbeat.h"

// One heartbeat per second on the built-in LED.
static Heartbeat heartbeat(LED_BUILTIN, 1000UL);

void setup() {
  Serial.begin(115200);
  // Give USB-serial (native-USB boards) a moment to enumerate; harmless on UART boards.
  unsigned long start = millis();
  while (!Serial && (millis() - start) < 2000UL) {
    // wait briefly for the serial port
  }
  heartbeat.begin();
  Serial.println(F("[ArduinoTemplateProject] boot OK — Tlamatini Arduiner template"));
}

void loop() {
  unsigned long beats = heartbeat.update();
  if (beats > 0) {
    Serial.print(F("[heartbeat] beat #"));
    Serial.println(beats);
  }
}
