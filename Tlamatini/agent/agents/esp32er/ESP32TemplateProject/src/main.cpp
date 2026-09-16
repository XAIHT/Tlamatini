// ═══════════════════════════════════════════════════════════════════════════
//   ✦  T L A M A T I N I  ✦   —   "one who knows"
//   Created by  Angela López Mendoza   ·   @angelahack1
//   Developer · Architect · Creator of Tlamatini
// ═══════════════════════════════════════════════════════════════════════════
//
// ESP32TemplateProject — the whole firmware.
//
// WHAT IT DOES: blinks the onboard LED and prints its state over serial at
// 115200 baud. Printing the state matters — it means you can prove the board is
// alive from the serial monitor even when you cannot see the physical LED
// (board in a case, LED not populated, or a variant whose LED is on another pin).
//
// This is deliberately the smallest firmware that exercises the ENTIRE chain:
// toolchain → compile → link → flash over USB → run on silicon → talk back.
// If this builds, uploads and prints, your ESP32 setup is healthy and any
// failure in your own firmware is in your firmware, not your environment.

#include <Arduino.h>

// Both come from `build_flags` in platformio.ini. The #ifndef guards keep this
// file compilable on its own (e.g. pasted into the Arduino IDE) if the flags
// are ever absent — a source file that only builds under one build system is a
// trap for the next person who opens it.
#ifndef BLINK_LED_PIN
#define BLINK_LED_PIN 2
#endif

#ifndef BLINK_INTERVAL_MS
#define BLINK_INTERVAL_MS 500
#endif

static bool led_on = false;

void setup() {
    pinMode(BLINK_LED_PIN, OUTPUT);
    digitalWrite(BLINK_LED_PIN, LOW);

    Serial.begin(115200);

    // Give the USB-serial bridge a moment to enumerate on the host before the
    // first print. Without this the opening banner is routinely lost, which
    // reads as "the board is dead" when it is merely early.
    delay(300);

    Serial.println();
    Serial.println("ESP32TemplateProject :: blink starting");
    Serial.printf("LED pin = %d, interval = %d ms\n",
                  (int)BLINK_LED_PIN, (int)BLINK_INTERVAL_MS);
}

void loop() {
    led_on = !led_on;
    digitalWrite(BLINK_LED_PIN, led_on ? HIGH : LOW);
    Serial.println(led_on ? "LED ON" : "LED OFF");
    delay(BLINK_INTERVAL_MS);
}
