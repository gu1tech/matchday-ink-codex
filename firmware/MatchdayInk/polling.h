#pragma once
#include <stdint.h>
// A zero saved interval means kickoff-driven scheduling. Missing/invalid headers
// fall back to one hour. Fixed legacy intervals still cannot miss an earlier kickoff.
inline uint32_t matchdayInkPollSeconds(uint32_t saved, long serverSeconds) {
  uint32_t fallback = saved >= 180 && saved <= 86400 ? saved : 3600;
  if (serverSeconds > 0 && serverSeconds <= 21600) {
    uint32_t server = (uint32_t)serverSeconds;
    return saved == 0 || server < fallback ? server : fallback;
  }
  return fallback;
}
