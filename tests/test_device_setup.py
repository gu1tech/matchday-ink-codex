import base64

import pytest

from matchday.device_setup import config_command

URL = 'http://192.168.1.2:8765/v1/frame.bin'


def test_unicode_credentials_round_trip_without_delimiter_corruption():
    command = config_command('Ev ağı', 'secret word!', URL)
    parts = command.decode().strip().split()
    assert parts[0] == 'MATCHDAY_INK_CONFIG'
    assert [base64.b64decode(p).decode() for p in parts[1:4]] == [
        'Ev ağı', 'secret word!', URL,
    ]
    assert parts[4] == '0'
    assert b'secret word!' not in command


def test_open_network_has_unambiguous_empty_token():
    assert config_command('Open', '', URL).decode().split()[2] == '-'


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/v1/frame.bin', 'http://localhost/v1/frame.bin',
    'http://user:secret@192.168.1.2/v1/frame.bin', 'https://192.168.1.2/v1/frame.bin',
    'http://192.168.1.2:99999/v1/frame.bin',
])
def test_unusable_or_secret_bearing_urls_are_rejected(url):
    with pytest.raises(ValueError):
        config_command('Home', 'password123', url)


def test_ssid_limit_is_bytes_and_bad_input_is_not_reflected():
    for ssid in ['', 'ğ' * 17]:
        with pytest.raises(ValueError):
            config_command(ssid, 'password123', URL)
    with pytest.raises(ValueError) as exc:
        config_command('Home', 'secret', URL)
    assert 'secret' not in str(exc.value)


def test_setup_page_javascript_parses_and_contains_daily_scan_controls(tmp_path):
    import re
    import shutil
    import subprocess

    from matchday.device_setup import PAGE
    assert '/api/scan' in PAGE
    assert 'value="0"' in PAGE
    assert 'full time + 5 minutes' in PAGE
    assert 'RESET/RST' in PAGE
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable for browser-script syntax check')
    source = re.search(r'<script nonce="NONCE">(.*?)</script>', PAGE, re.S)[1]
    path = tmp_path / 'setup.js'
    path.write_text(source.replace('TOKEN', '"test"'))
    subprocess.run([node, '--check', str(path)], check=True, capture_output=True)
