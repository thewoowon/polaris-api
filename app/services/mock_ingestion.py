"""Generate mock Korean banking app reviews for a given AppProfile."""

import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_profile import AppProfile
from app.models.review import Review, ReviewSource

# 금융앱 특화 mock 리뷰 풀 (rating별 분포)
_REVIEW_POOL: list[tuple[int, str]] = [
    # rating 1
    (1, "로그인이 계속 안 됩니다. 공동인증서 가져오기가 자꾸 실패해요."),
    (1, "업데이트하고 앱이 계속 튕깁니다. 다시 설치해도 마찬가지에요."),
    (1, "이체 화면에서 오류가 납니다. 송금을 못 하고 있어요."),
    (1, "카드 신청 중 오류가 납니다. 처음부터 다시 해야 해요."),
    (1, "속도가 너무 느립니다. 잔액 조회 하나 하는 데 10초 넘게 걸려요."),
    (1, "고객센터 연결이 안 됩니다. 전화도 앱 문의도 다 안 돼요."),
    (1, "지문 인식이 안 됩니다. PIN으로 바꿨더니 그것도 안 되네요."),
    (1, "앱이 너무 복잡합니다. 이체 버튼이 어디 있는지 찾기 힘들어요."),
    (1, "알림이 하루에 수십 개 옵니다. 끄는 방법도 모르겠어요."),
    (1, "해지하려고 했더니 오류가 납니다. 고객센터도 연결이 안 되고요."),
    # rating 2
    (2, "공동인증서 이동이 계속 실패합니다. 예전 버전은 잘 됐는데."),
    (2, "업데이트 후 렉이 심해졌습니다. 전보다 훨씬 불편해요."),
    (2, "혜택 찾기가 너무 어렵습니다. 메뉴가 복잡하게 되어 있어요."),
    (2, "대출 신청 화면이 중간에 멈춥니다. 여러 번 시도했어요."),
    (2, "로그인은 되는데 잔액 조회 화면이 안 뜹니다."),
    (2, "송금 한도가 낮아져서 불편합니다. 변경 방법도 복잡하고요."),
    (2, "청약 신청 중 오류가 계속 납니다. 일정이 촉박한데 큰일났어요."),
    (2, "보안 경고가 너무 자주 뜹니다. 사용할 때마다 확인을 요구하네요."),
    (2, "잔액 조회는 빠른데 이체하면 엄청 느립니다."),
    (2, "카카오뱅크보다 메뉴가 복잡합니다. 불편해요."),
    # rating 3
    (3, "기능은 많은데 UI가 너무 복잡합니다. 개선이 필요해요."),
    (3, "로그인은 잘 되는데 가끔 튕깁니다. 아직 안정적이진 않아요."),
    (3, "송금 기능은 괜찮은데 환전 화면이 불편합니다."),
    (3, "대출 이자 계산기가 있었으면 좋겠어요. 기능이 부족합니다."),
    (3, "알림 커스터마이징이 더 세밀했으면 합니다."),
    (3, "토스보다는 불편하지만 그래도 쓸 만합니다."),
    (3, "어르신들이 쓰기엔 글씨가 작습니다. 접근성 개선이 필요해요."),
    (3, "가끔 앱이 느려집니다. 전반적으로는 괜찮아요."),
    (3, "이체 화면은 괜찮은데 메인 화면 디자인이 아쉽습니다."),
    (3, "기본적인 기능은 잘 됩니다. 하지만 경쟁사 대비 불편해요."),
    # rating 4
    (4, "전반적으로 사용하기 좋습니다. 이체가 빠르고 편리해요."),
    (4, "최근 업데이트 후 많이 좋아졌습니다. 속도도 빠르고요."),
    (4, "지문 인식이 잘 됩니다. 빠르게 로그인할 수 있어요."),
    (4, "고객센터 연결이 잘 됩니다. 문제 해결도 빨랐어요."),
    (4, "혜택 섹션이 보기 좋습니다. 포인트 관리가 편해요."),
    (4, "UI가 깔끔하게 개선됐습니다. 사용하기 편해요."),
    (4, "청약 신청이 간편해졌습니다. 예전보다 훨씬 좋네요."),
    (4, "보안이 잘 되어 있습니다. 안심하고 쓸 수 있어요."),
    # rating 5
    (5, "정말 편리한 앱입니다. 이체, 조회 모두 빠르고 좋아요."),
    (5, "업데이트 후 속도가 많이 개선됐습니다. 만족합니다."),
    (5, "UI가 깔끔하고 직관적입니다. 은행 앱 중 최고예요."),
    (5, "지문 인식이 빠르고 안정적입니다. 매일 쓰고 있어요."),
    (5, "고객센터 응대가 친절합니다. 문제가 빨리 해결됐어요."),
    (5, "혜택이 많고 찾기도 쉽습니다. 자주 이용합니다."),
    (5, "보안이 탄탄합니다. 믿고 사용할 수 있어요."),
]

# 앱별 특화 리뷰 (경쟁사 비교 등)
_APP_SPECIFIC: dict[str, list[tuple[int, str]]] = {
    "토스": [
        (5, "토스는 역시 UX가 최고입니다. 송금이 너무 간편해요."),
        (5, "토스 이체 속도가 정말 빠릅니다. 다른 앱이랑 비교가 안 됩니다."),
        (4, "토스페이 연동이 편합니다. 생활금융 앱 중 1등이에요."),
        (2, "최근 업데이트 후 가끔 오류가 납니다. 예전이 더 좋았어요."),
    ],
    "카카오뱅크": [
        (5, "카카오뱅크는 정말 편합니다. 계좌 개설도 간단하고요."),
        (5, "UI가 깔끔하고 이체가 빠릅니다. 계속 쓸 것 같아요."),
        (4, "26주 적금이 재미있습니다. 저축 습관 만들기 좋아요."),
        (3, "대출 한도가 낮습니다. 그 외에는 다 좋아요."),
    ],
    "신한 SOL": [
        (3, "토스보다 불편합니다. UX 개선이 필요해요."),
        (2, "SOL 업데이트 후 공동인증서 오류가 납니다."),
        (4, "신한 포인트 관리가 편합니다. 혜택도 많고요."),
    ],
    "KB스타뱅킹": [
        (2, "카카오뱅크보다 메뉴가 복잡합니다."),
        (1, "KB스타뱅킹 로그인이 자꾸 실패합니다."),
        (4, "KB Pay 연동이 편합니다. 포인트리 쓰기 좋아요."),
    ],
}


class MockIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def generate(self, app: AppProfile, count: int = 100) -> int:
        """Generate `count` mock reviews for the given app."""
        pool = list(_REVIEW_POOL)
        specific = _APP_SPECIFIC.get(app.app_name, [])
        pool.extend(specific * 3)  # 앱 특화 리뷰 가중치 부여

        now = datetime.now(timezone.utc)
        created = 0

        for i in range(count):
            rating, text = random.choice(pool)
            # 약간의 텍스트 변형으로 중복 방지
            if random.random() < 0.3:
                text = text + " " + random.choice(["정말 불편해요.", "개선 좀 해주세요.", "빨리 고쳐줬으면 합니다.", "잘 부탁드립니다.", "감사합니다."])

            days_ago = random.randint(0, 90)
            ingested_at = now - timedelta(days=days_ago)

            review = Review(
                source=ReviewSource.INTERNAL,
                source_review_id=f"mock_{app.id}_{uuid.uuid4().hex[:8]}",
                rating=rating,
                raw_text=text,
                normalized_text=text,
                locale="ko",
                ingested_at=ingested_at,
                app_id=app.id,
                extra={"mock": True, "app_name": app.app_name},
            )
            self._db.add(review)
            created += 1

        await self._db.commit()
        return created
