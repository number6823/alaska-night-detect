"""요청 문장을 키워드 사전으로 해석해 검색어를 만든다. (규칙 기반, 외부 API 없음)"""

# 시간·상황을 나타내는 말. 검색어 앞에 붙는다.
WHEN_WORDS = {
    "야간": ["night"],
}

# 찾을 대상을 나타내는 말. 검색어의 본체가 된다.
WHAT_WORDS = {
    "자전거": ["bicycle", "cyclist"],
    "사람": ["person", "pedestrian"],
}

UNRESOLVED = "해석 불가: 사전에 있는 말(야간, 자전거, 사람)이 없어요."


def _lookup(text, words):
    """문장에 들어 있는 사전 단어의 영어 뜻을 순서대로, 중복 없이 모은다."""
    found = []
    for korean, english_list in words.items():
        if korean in text:
            for english in english_list:
                if english not in found:
                    found.append(english)
    return found


def extract_terms(text):
    """문장에서 {"when": [...], "what": [...]} 를 뽑는다. 없으면 빈 리스트."""
    return {
        "when": _lookup(text, WHEN_WORDS),
        "what": _lookup(text, WHAT_WORDS),
    }


def build_queries(terms):
    """뽑은 말로 검색어 목록을 만든다. 대상 말이 없으면 해석 불가이므로 [] 를 돌려준다."""
    if not terms["what"]:
        return []
    if not terms["when"]:
        return list(terms["what"])
    return [f"{when} {what}" for when in terms["when"] for what in terms["what"]]
