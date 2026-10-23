import random

from tellurium.stealth.human import MOUSE_PROFILES, apply_lognormal_velocity, wind_mouse


def test_wind_mouse_reaches_destination():
    path = wind_mouse(100, 200, 500, 300)
    assert path[-1] == (500, 300)


def test_wind_mouse_starts_near_origin():
    path = wind_mouse(100, 200, 500, 300)
    assert abs(path[0][0] - 100) < 5
    assert abs(path[0][1] - 200) < 5


def test_wind_mouse_path_not_straight():
    # Seeded: unseeded, about 1 path in 40 stays within 5 px of the diagonal.
    random.seed(1234)
    path = wind_mouse(0, 0, 500, 500)
    max_deviation = 0
    for x, y in path:
        deviation = abs(x - y) / 1.414
        max_deviation = max(max_deviation, deviation)
    assert max_deviation > 5  # not a perfectly straight line


def test_wind_mouse_has_multiple_points():
    path = wind_mouse(0, 0, 500, 500)
    assert len(path) > 10


def test_wind_mouse_short_distance():
    path = wind_mouse(0, 0, 5, 5)
    assert path[-1] == (5, 5)
    assert len(path) >= 1


def test_lognormal_velocity_monotonic_timestamps():
    path = wind_mouse(0, 0, 500, 500)
    timed = apply_lognormal_velocity(path)
    for i in range(1, len(timed)):
        assert timed[i][2] > timed[i - 1][2]  # timestamps increase


def test_lognormal_velocity_reaches_destination():
    path = wind_mouse(0, 0, 500, 500)
    timed = apply_lognormal_velocity(path)
    assert timed[-1][0] == 500 or timed[-1][1] == 500  # near destination


def test_mouse_profiles_exist():
    assert "careful" in MOUSE_PROFILES
    assert "normal" in MOUSE_PROFILES
    assert "hasty" in MOUSE_PROFILES


def test_wind_mouse_with_profile():
    params = MOUSE_PROFILES["careful"]["wind"]
    path = wind_mouse(0, 0, 300, 300, **params)
    assert path[-1] == (300, 300)
