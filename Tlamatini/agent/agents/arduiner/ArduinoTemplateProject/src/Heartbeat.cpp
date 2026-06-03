#include "Heartbeat.h"

Heartbeat::Heartbeat(uint8_t pin, unsigned long periodMs)
    : pin_(pin),
      periodMs_(periodMs),
      lastToggleMs_(0),
      ledOn_(false),
      beatCount_(0) {}

void Heartbeat::begin() {
  pinMode(pin_, OUTPUT);
  digitalWrite(pin_, LOW);
  lastToggleMs_ = millis();
}

unsigned long Heartbeat::update() {
  const unsigned long now = millis();
  if ((now - lastToggleMs_) < periodMs_) {
    return 0;
  }
  lastToggleMs_ = now;
  ledOn_ = !ledOn_;
  digitalWrite(pin_, ledOn_ ? HIGH : LOW);
  // Count one full beat each time the LED returns to OFF (a complete on/off cycle).
  if (!ledOn_) {
    ++beatCount_;
    return beatCount_;
  }
  return 0;
}
