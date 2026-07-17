from app.domains.conversations.schemas import ConversationLocale
from scripts.run_rag_evaluation import locale_for_question


def test_rag_evaluation_selects_locale_from_question() -> None:
    assert locale_for_question("How do I reset my password?") == ConversationLocale.EN
    assert locale_for_question("如何重置密码？") == ConversationLocale.ZH_CN  # noqa: RUF001
