"""Conservatively load visual-planning guidance for explicit image turns."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from amazon_create.schemas.conversation import ConversationMessage

_EXPLICIT_VISUAL_REQUEST = re.compile(
    r"(?:主图|辅图|副图|图片(?:设计|策划|规划|方案|脚本|优化|分析)|"
    + r"视觉(?:设计|策划|规划|方案|脚本)|详情页(?:设计|策划|规划|方案|脚本)|"
    + r"(?:需要|要|做|制作|生成|继续).{0,8}(?:图片|图组|视觉图)|"
    + r"storyboard|image\s+(?:design|plan|planning|storyboard|optimization|analysis)|"
    + r"visual\s+(?:design|plan|planning|storyboard))",
    re.IGNORECASE,
)
_VISUAL_HANDOFF = re.compile(
    r"(?:是否|要不要|需不需要|需要).*?(?:主图|辅图|副图|图片|视觉|image)|"
    + r"(?:主图|辅图|副图|图片|视觉|image).*?(?:是否|要不要|需不需要|需要)",
    re.IGNORECASE,
)
_AFFIRMATIVE = re.compile(
    r"^(?:需要|要|好|好的|可以|继续|做吧|开始|yes|y|sure|please\s+do)"
    + r"(?:[，。！!,.\s～~]*)$",
    re.IGNORECASE,
)
_NEGATED_VISUAL_REQUEST = re.compile(
    r"(?:不需要|不用|不要|暂不|先不|无需|取消).{0,8}"
    + r"(?:主图|辅图|副图|图片|视觉|image)|"
    + r"(?:without|no)\s+(?:image|visual)",
    re.IGNORECASE,
)


def visual_guidance_requested(messages: Sequence[ConversationMessage]) -> bool:
    """Return true only for an explicit visual request or confirmed handoff."""
    last_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"),
        None,
    )
    if last_user_index is None:
        return False

    user_text = messages[last_user_index].content.strip()
    if not user_text or _NEGATED_VISUAL_REQUEST.search(user_text):
        return False
    if _EXPLICIT_VISUAL_REQUEST.search(user_text):
        return True
    if not _AFFIRMATIVE.fullmatch(user_text):
        return False

    if last_user_index == 0 or messages[last_user_index - 1].role != "assistant":
        return False
    return bool(_VISUAL_HANDOFF.search(messages[last_user_index - 1].content))


def load_visual_guidance() -> str:
    """Load the packaged Amazon-specific visual-planning reference."""
    root = Path(__file__).resolve().parents[1]
    resource = (
        root
        / "resources"
        / "amazon-cosmo-rufus-copywriting"
        / "references"
        / "amazon-image-design.md"
    )
    return resource.read_text(encoding="utf-8").strip()


__all__ = ["load_visual_guidance", "visual_guidance_requested"]
