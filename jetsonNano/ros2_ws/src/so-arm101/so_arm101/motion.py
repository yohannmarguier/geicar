"""Small position offsets for an SO-101 follower's base and wrist."""

import math


def targets_at(start_ticks, amplitudes_ticks, frequency_hz, elapsed_seconds):
    """Return raw servo targets; opposing joints form a smooth wave.

    Cubing the sine makes velocity zero at the start and each centre crossing.
    No target can be farther from its measured start than its amplitude.
    """
    wave = math.sin(2.0 * math.pi * frequency_hz * elapsed_seconds) ** 3
    return [
        round(start + (1 if index % 2 == 0 else -1) * amplitude * wave)
        for index, (start, amplitude) in enumerate(zip(start_ticks, amplitudes_ticks))
    ]


def within_limits(start_ticks, amplitudes_ticks, minimum_tick, maximum_tick):
    """Check every possible dance target against conservative raw tick limits."""
    return all(
        minimum_tick <= start - amplitude and start + amplitude <= maximum_tick
        for start, amplitude in zip(start_ticks, amplitudes_ticks)
    )
