import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from matchday.render import PALETTE, draw_status_icons, encode_frame

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def native_icons(tmp_path_factory):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    folder = tmp_path_factory.mktemp('native-icons')
    source = folder / 'icons.cpp'
    source.write_text('''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "frame_status.h"
int main(int argc, char **argv) {
  unsigned char f[9472]; memset(f, 255, sizeof(f));
  matchdayInkStatusIcons(f, atoi(argv[1]), atoi(argv[2]));
  fwrite(f, 1, sizeof(f), stdout);
}''')
    binary = folder / 'icons'
    subprocess.run([compiler, '-std=c++11', '-I', str(ROOT/'firmware/MatchdayInk'),
                    str(source), '-o', str(binary)], check=True, capture_output=True)
    return binary


@pytest.mark.parametrize('connected,fresh', [(False, False), (False, True), (True, False), (True, True)])
def test_physical_cpp_icons_equal_python_panel_encoding(native_icons, connected, fresh):
    image = Image.new('RGB', (296, 128), PALETTE[3])
    draw_status_icons(image, connected, fresh)
    actual = subprocess.check_output([str(native_icons), str(int(connected)), str(int(fresh))])
    assert actual == encode_frame(image)


def test_icons_cannot_overwrite_match_or_footer():
    image = Image.new('RGB', (296, 128), PALETTE[3])
    draw_status_icons(image, False, False)
    for y in range(128):
        for x in range(296):
            if not (6 <= y <= 18 and (263 <= x <= 275 or 280 <= x <= 292)):
                assert image.getpixel((x, y)) == PALETTE[3]


def test_daily_interval_is_in_device_protocol():
    from matchday.device_setup import config_command
    assert config_command('Home', 'password123', 'http://192.168.1.2:8765/v1/frame.bin',
                          86400).endswith(b' 86400\n')


def test_icon_asset_has_only_supported_inks():
    icons = json.loads((ROOT/'src/matchday/assets/status-icons.json').read_text())
    assert all(len(pixels) == 169 and set(pixels) <= {0, 1, 2, 3} for pixels in icons.values())


def test_freshness_expiry_survives_uptime_wrap_without_false_green(tmp_path):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    source = tmp_path / 'fresh.cpp'
    source.write_text('''#include "freshness.h"
int main() {
  bool known = false;
  if (matchdayInkFreshnessActive(known, 0, 0x80000001u)) return 1;
  known = true;
  if (!matchdayInkFreshnessActive(known, 0x100u, 0xffffff00u)) return 2;
  if (matchdayInkFreshnessActive(known, 0x100u, 0x101u)) return 3;
  if (known) return 4;
  if (matchdayInkFreshnessActive(known, 0x100u, 0x90000100u)) return 5;
  return 0;
}''')
    binary = tmp_path / 'fresh'
    subprocess.run([compiler, '-std=c++11', '-I', str(ROOT/'firmware/MatchdayInk'),
                    str(source), '-o', str(binary)], check=True, capture_output=True)
    subprocess.run([str(binary)], check=True)
