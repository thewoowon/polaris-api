"""Reply templates (blueprint §11.2).

Phrasing is deliberately hedged — never asserts fault, fix timing, or refund
(blueprint §20.3 forbidden language).
"""

from dataclasses import dataclass

from app.models.classification import ReviewCategory


@dataclass(frozen=True)
class Template:
    id: str
    category: ReviewCategory
    text: str


TEMPLATES: dict[str, Template] = {
    "bug_ack_v1": Template(
        id="bug_ack_v1",
        category=ReviewCategory.BUG,
        text=(
            "안녕하세요. 이용에 불편을 드려 죄송합니다. "
            "말씀해주신 현상은 확인이 필요한 이슈로 전달하겠습니다. "
            "가능하시다면 앱 버전과 발생 상황을 함께 남겨주시면 확인에 도움이 됩니다."
        ),
    ),
    "payment_ack_v1": Template(
        id="payment_ack_v1",
        category=ReviewCategory.PAYMENT,
        text=(
            "안녕하세요. 결제 관련 불편을 겪으셨다니 죄송합니다. "
            "결제/환불 이슈는 계정 및 거래 정보 확인이 필요할 수 있어 "
            "고객센터 또는 앱 내 문의를 통해 접수 부탁드립니다."
        ),
    ),
    "praise_ack_v1": Template(
        id="praise_ack_v1",
        category=ReviewCategory.PRAISE,
        text=(
            "안녕하세요. 소중한 의견 감사합니다. "
            "좋은 경험을 드릴 수 있어 기쁩니다. 앞으로도 더 나은 서비스를 제공하겠습니다."
        ),
    ),
    "generic_ack_v1": Template(
        id="generic_ack_v1",
        category=ReviewCategory.OTHER,
        text=(
            "안녕하세요. 의견 주셔서 감사합니다. "
            "내부에서 확인 후 개선에 반영할 수 있도록 전달드리겠습니다."
        ),
    ),
}


# Category → preferred template id.
CATEGORY_TEMPLATE: dict[ReviewCategory, str] = {
    ReviewCategory.BUG: "bug_ack_v1",
    ReviewCategory.PAYMENT: "payment_ack_v1",
    ReviewCategory.REFUND: "payment_ack_v1",
    ReviewCategory.LOGIN_ACCOUNT: "payment_ack_v1",
    ReviewCategory.PRAISE: "praise_ack_v1",
}


def pick_template(categories: list[ReviewCategory]) -> Template:
    for c in categories:
        tid = CATEGORY_TEMPLATE.get(c)
        if tid:
            return TEMPLATES[tid]
    return TEMPLATES["generic_ack_v1"]
