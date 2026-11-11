#pragma once
#include <stdint.h>
// A deadline is at most 24 hours ahead (< INT32_MAX ms). Expiry latches false,
// so a long-offline device cannot become 'fresh' again on the millis wraparound.
inline bool matchdayInkFreshnessActive(bool &known, uint32_t deadline, uint32_t now) {
  if (!known) return false;
  if ((int32_t)(deadline - now) <= 0) { known = false; return false; }
  return true;
}
