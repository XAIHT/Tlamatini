/*
 * Heartbeat.h — a tiny, board-agnostic non-blocking LED blinker.
 *
 * Demonstrates the multi-file sketch layout that arduino-cli compiles: any
 * .h/.cpp under the sketch's src/ folder is built and linked automatically.
 * Pure C++ + Arduino core API only (no board-specific headers), so it works on
 * every Arduino-compatible target.
 */
#ifndef ARDUINO_TEMPLATE_PROJECT_HEARTBEAT_H
#define ARDUINO_TEMPLATE_PROJECT_HEARTBEAT_H

#include <Arduino.h>

class Heartbeat {
 public:
  Heartbeat(uint8_t pin, unsigned long periodMs);

  // Configure the pin. Call from setup().
  void begin();

  // Non-blocking tick. Call from loop(). Returns the (incremented) beat count
  // on the loop iteration where a full beat just completed, else 0.
  unsigned long update();

  unsigned long beats() const { return beatCount_; }

 private:
  uint8_t pin_;
  unsigned long periodMs_;
  unsigned long lastToggleMs_;
  bool ledOn_;
  unsigned long beatCount_;
};

#endif  // ARDUINO_TEMPLATE_PROJECT_HEARTBEAT_H
