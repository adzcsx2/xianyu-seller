"""Optional OpenCV gap detection used before the DOM distance fallback."""
from typing import Optional

from loguru import logger

try:
    import cv2
    import numpy as np
except ImportError:  # DOM distance remains usable when OpenCV is not installed.
    cv2 = None
    np = None


class SliderImageMatcher:
    @staticmethod
    def find_gap_position(background, puzzle_piece, offset_correction: int = -35) -> Optional[int]:
        if cv2 is None:
            logger.warning("OpenCV 未安装，跳过滑块图像匹配")
            return None
        try:
            bg_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY) if len(background.shape) == 3 else background
            piece_gray = cv2.cvtColor(puzzle_piece, cv2.COLOR_BGR2GRAY) if len(puzzle_piece.shape) == 3 else puzzle_piece
            edge_bg = cv2.Canny(bg_gray, 100, 200)
            edge_piece = cv2.Canny(piece_gray, 100, 200)
            result = cv2.matchTemplate(edge_bg, edge_piece, cv2.TM_CCOEFF_NORMED)
            _, confidence, _, max_loc = cv2.minMaxLoc(result)
            piece_height, piece_width = edge_piece.shape[:2]
            center_x = max_loc[0] + piece_width // 2
            gap_x = max(0, center_x + int(offset_correction))
            logger.info("滑块图像匹配: x={} confidence={:.3f}", gap_x, confidence)
            return gap_x
        except Exception as exc:
            logger.warning("滑块图像匹配失败: {}", exc)
            return None

    @staticmethod
    def find_gap_from_bytes(bg_bytes: bytes, piece_bytes: bytes, offset_correction: int = -35) -> Optional[int]:
        if cv2 is None or np is None:
            return None
        try:
            background = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
            puzzle_piece = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_COLOR)
            if background is None or puzzle_piece is None:
                return None
            return SliderImageMatcher.find_gap_position(background, puzzle_piece, offset_correction)
        except Exception as exc:
            logger.warning("滑块图片解码失败: {}", exc)
            return None


find_gap = SliderImageMatcher.find_gap_position
find_gap_from_bytes = SliderImageMatcher.find_gap_from_bytes

__all__ = ["SliderImageMatcher", "find_gap", "find_gap_from_bytes"]
