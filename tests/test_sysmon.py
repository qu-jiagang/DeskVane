from unittest import mock

import deskvane.sysmon as sysmon


def test_read_cpu_status_primes_first_sample_with_short_interval() -> None:
    with mock.patch.object(sysmon, "_read_cpu_totals", side_effect=[(100, 1000), (120, 1100)]), \
         mock.patch.object(sysmon, "_read_max_cpu_temp", return_value=55.5), \
         mock.patch.object(sysmon.os, "cpu_count", return_value=8), \
         mock.patch.object(sysmon._time, "sleep") as sleep_mock:
        sysmon._prev_idle = None
        sysmon._prev_total = None

        status = sysmon._read_cpu_status()

    assert status is not None
    assert status.usage_pct == 80.0
    assert status.temp_c == 55.5
    assert status.core_count == 8
    sleep_mock.assert_called_once_with(sysmon._CPU_PRIME_INTERVAL_SECONDS)
    assert sysmon._prev_idle == 120
    assert sysmon._prev_total == 1100


def test_read_cpu_status_uses_previous_sample_after_prime() -> None:
    with mock.patch.object(sysmon, "_read_cpu_totals", return_value=(150, 1200)), \
         mock.patch.object(sysmon, "_read_max_cpu_temp", return_value=48.0), \
         mock.patch.object(sysmon.os, "cpu_count", return_value=16), \
         mock.patch.object(sysmon._time, "sleep") as sleep_mock:
        sysmon._prev_idle = 120
        sysmon._prev_total = 1100

        status = sysmon._read_cpu_status()

    assert status is not None
    assert status.usage_pct == 70.0
    assert status.temp_c == 48.0
    assert status.core_count == 16
    sleep_mock.assert_not_called()
    assert sysmon._prev_idle == 150
    assert sysmon._prev_total == 1200
