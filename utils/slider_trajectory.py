"""Generated drag trajectories used when no successful recording is available."""
import math
import random
from typing import List, Tuple

from loguru import logger


def generate_trajectory(distance: float, attempt: int = 1) -> List[Tuple[float, float, float]]:
    distance = max(1.0, float(distance))
    points: List[Tuple[float, float, float]] = [(0.0, 0.0, random.uniform(100, 200))]
    steps = random.randint(10, 15)
    jitter = 2.0 + max(1, attempt) * 0.8
    for index in range(steps):
        progress = (index + 1) / steps
        if progress <= 0.2:
            t = progress / 0.2
            eased = 0.02 + 0.13 * (t ** 1.8)
        elif progress <= 0.6:
            eased = 0.15 + 0.60 * ((progress - 0.2) / 0.4)
        elif progress <= 0.85:
            eased = 0.75 + 0.20 * ((progress - 0.6) / 0.25)
        else:
            eased = 0.95 + 0.05 * ((progress - 0.85) / 0.15)
        x = distance * eased
        y = -0.5 - progress * 4.0 + math.sin(
            progress * math.pi * random.uniform(1.5, 3.5)
        ) * jitter * (0.4 + 0.6 * progress)
        if random.random() < 0.06:
            y += random.uniform(-jitter * 1.8, jitter * 1.8)
        if index == 0:
            delay = random.uniform(35, 55)
        elif index >= steps - 2:
            delay = random.uniform(40, 60)
        elif random.random() < 0.07:
            delay = random.uniform(55, 75)
        else:
            delay = random.uniform(25, 45)
        points.append((x, y, delay))
    points.append((distance, 0.0, random.uniform(50, 120)))
    logger.debug("slider trajectory generated: distance={} steps={} attempt={}", distance, len(points), attempt)
    return points


def trajectory_to_points(trajectory, start_x: float, start_y: float):
    return [(start_x + x, start_y + y, delay) for x, y, delay in trajectory]


__all__ = ["generate_trajectory", "trajectory_to_points"]
