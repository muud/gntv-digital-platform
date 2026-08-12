"""Rule-based chat moderation for Sprint 7.1."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.modules.chat.models import ChatModerationAction, ChatModerationRule, ChatRuleMatchType


@dataclass(frozen=True)
class ModerationDecision:
    action: ChatModerationAction | None
    reason: str | None = None
    rule_id: str | None = None

    @property
    def publishable(self) -> bool:
        return self.action not in {ChatModerationAction.BLOCK, ChatModerationAction.MUTE, ChatModerationAction.BAN}


class ChatModerationEngine:
    """Evaluate exact and regex rules without interpreting user text as HTML."""

    def evaluate(self, text: str, rules: list[ChatModerationRule]) -> ModerationDecision:
        lowered = text.casefold()
        try:
            for rule in rules:
                matched = False
                if rule.match_type == ChatRuleMatchType.EXACT:
                    matched = rule.pattern.casefold() in lowered
                elif rule.match_type == ChatRuleMatchType.REGEX:
                    matched = re.search(rule.pattern, text, flags=re.IGNORECASE) is not None
                elif rule.match_type == ChatRuleMatchType.FUZZY:
                    matched = self._safe_boundary_match(rule.pattern, lowered)
                if matched:
                    return ModerationDecision(
                        action=rule.action,
                        reason=f"Matched moderation rule {rule.pattern}",
                        rule_id=str(rule.id),
                    )
        except Exception:
            return ModerationDecision(
                action=ChatModerationAction.FLAG,
                reason="Moderation evaluation failed",
            )
        return ModerationDecision(action=None)

    def _safe_boundary_match(self, pattern: str, lowered_text: str) -> bool:
        normalized = pattern.casefold().strip()
        if not normalized or len(normalized) < 4:
            return False
        return re.search(rf"(^|\W){re.escape(normalized)}(\W|$)", lowered_text) is not None
