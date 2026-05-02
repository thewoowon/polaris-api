"""Seed the local dev DB with synthetic reviews + run the full pipeline.

Usage:
    poetry run python scripts/seed.py           # wipe + reseed (~150 reviews)
    poetry run python scripts/seed.py --keep    # append without wipe

Pipeline coverage:
    Review ingest → StubClassifier → RuleBasedPolicyEngine → TemplateReplyGenerator
    Every state transition is written to audit_logs.

Deterministic: uses a fixed random seed so repeated runs produce the same data.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models import (
    AuditLog,
    ClassificationResult,
    PolicyAction,
    PolicyDecision,
    ReplyDraft,
    ReplyStatus,
    Review,
    ReviewSource,
)
from app.services.audit.logger import AuditLogger
from app.services.classification.stub import StubClassifier
from app.services.generation.default import TemplateReplyGenerator
from app.services.normalization import normalize_text
from app.services.policy.engine import RuleBasedPolicyEngine

RNG_SEED = 42


# ─── synthetic review corpus ────────────────────────────────────────────────
# Shape: (raw_text, rating, weight)  — weight is roughly relative frequency.
BUGS = [
    "업데이트 후 앱이 자꾸 튕깁니다. 계속 로딩만 되고 사용이 불가해요.",
    "로그인 후 메인 화면에서 바로 크래시 납니다. 재설치도 해봤지만 동일합니다.",
    "알림 누르면 앱이 꺼지는 버그 확인 부탁드려요.",
    "상세 페이지에서 스크롤하면 이미지가 깨집니다.",
    "푸시가 와도 클릭하면 빈 화면으로 진입합니다. 앱 버전 3.2.1입니다.",
    "데이터 저장이 안 되는 오류가 있습니다. 입력한 내용이 다 사라져요.",
    "검색 버튼이 반응하지 않습니다.",
    "앱 시작 후 몇 초 뒤에 무조건 튕깁니다. 안드로이드 14입니다.",
    "카메라 기능이 간헐적으로 멈춥니다.",
    "로그아웃 버튼이 동작하지 않아요.",
    "프로필 사진 업로드가 계속 실패합니다. 네트워크는 정상인데 에러만 떠요.",
    "앱 설정에서 언어 바꾸면 크래시납니다.",
    "결제 완료 화면에서 뒤로가기 누르면 오류 메시지 뜹니다.",
    "QR 스캐너가 카메라를 인식하지 못합니다.",
    "공유 버튼 누르면 앱이 바로 꺼집니다.",
]
PAYMENT_REFUND = [
    "결제했는데 구독이 적용 안 됐어요. 환불 부탁드립니다.",
    "두 번 결제된 것 같습니다. 영수증 번호 확인 후 환불 요청합니다.",
    "자동결제 해지했는데 다음 달에도 결제됐습니다.",
    "환불 요청했는데 처리가 안 돼서 답답합니다.",
    "가격이 안내와 다르게 청구됐어요. 확인해 주세요.",
    "결제 오류 후 재시도했더니 중복 결제됐습니다. 환불 처리 바랍니다.",
    "상품권 적용이 안 돼요. 결제 환불이라도 해주세요.",
    "프로모션 적용이 안 된 채로 결제됐습니다. 차액 환불 가능한가요?",
]
LOGIN = [
    "구글 로그인이 계속 실패합니다. 브라우저에서는 되는데 앱에서는 안 됩니다.",
    "계정이 갑자기 잠겼어요. 해제 방법 알려주세요.",
    "비밀번호를 여러 번 틀렸더니 로그인이 막혔습니다. 본인인증은 정상입니다.",
    "SNS 연동 후 기존 계정 데이터가 사라졌습니다.",
    "2단계 인증 코드가 오지 않습니다.",
    "애플 로그인 후 이름이 '이름 없음'으로 들어갔어요. 수정 불가합니다.",
    "기기 변경 후 로그인이 안 됩니다. 인증 메일도 안 오네요.",
]
PERFORMANCE = [
    "업데이트 후 앱이 너무 느려졌어요. 리스트 스크롤이 렉 걸립니다.",
    "이미지 로딩 속도가 이전보다 확연히 느려진 느낌입니다.",
    "배터리가 빠르게 닳습니다. 다른 앱보다 발열이 심해요.",
    "데이터 사용량이 갑자기 많아졌어요.",
    "저가형 안드로이드에서 버벅거리는 현상이 있습니다.",
    "앱 시작까지 10초 가까이 걸립니다.",
    "필터 적용하면 화면이 멈춥니다.",
    "무한 스크롤 내릴수록 점점 느려지네요.",
]
UX_UI = [
    "다크모드에서 버튼이 잘 안 보입니다. 색 대비가 약해요.",
    "홈 화면 구성을 예전 방식으로 되돌려주세요. 새 디자인은 불편합니다.",
    "폰트가 너무 작아서 읽기 힘들어요. 크기 설정 옵션 추가해주세요.",
    "뒤로가기 버튼 위치가 바뀌어서 많이 헷갈립니다.",
    "아이콘이 직관적이지 않아서 뭔지 알기 어려워요.",
    "설정 메뉴 깊이가 너무 깊어요. 주요 설정은 한 번에 접근 가능하면 좋겠어요.",
]
FEATURE_REQUEST = [
    "다국어 지원 추가 부탁드립니다. 영어가 필수입니다.",
    "위젯이 있으면 좋겠어요. 홈 화면에서 바로 확인하고 싶습니다.",
    "데이터 내보내기(CSV) 기능이 필요합니다.",
    "오프라인 모드 지원해주세요.",
    "태블릿 UI가 스마트폰 그대로라 큰 화면 활용이 안 됩니다.",
    "폴더블 기기 화면 비율 대응이 필요합니다.",
]
PRAISE = [
    "정말 잘 쓰고 있어요. 유용합니다. 감사합니다.",
    "업데이트되고 훨씬 좋아졌어요!",
    "디자인이 깔끔하고 직관적이라 좋습니다.",
    "기능이 딱 필요한 만큼만 있어서 좋아요. 최고입니다.",
    "한 달째 쓰고 있는데 만족합니다.",
    "UI가 감각 있어서 마음에 듭니다. 앞으로도 잘 부탁드려요.",
    "가볍고 빠릅니다. 다른 앱보다 훨씬 좋아요.",
    "무료인데 광고도 적당히만 나와서 고맙습니다.",
    "필요한 기능 다 있고 속도도 좋고 완벽합니다.",
    "추천할 만합니다. 감사합니다.",
]
SPAM = [
    "asdfasdfasdf qweqweqwe",
    "aaaaaaaaaa",
    "visit mybestsite.example.com !!! free gift card!!!!",
    "광고 쪽지 보내실 분 dm 부탁드려요",
    "...",
]
COMPLAINT_GENERIC = [
    "고객센터 답이 너무 늦어요.",
    "서비스 품질 관리 좀 부탁드립니다.",
    "전반적으로 불편한 점이 많습니다.",
    "신규 기능보다 안정화에 신경 써주세요.",
    "공지 없이 약관이 바뀌는 건 좀 아닌 것 같네요.",
]
POLICY_INQUIRY = [
    "개인정보 처리방침 어디서 확인하나요?",
    "탈퇴 시 데이터가 얼마나 보관되는지 알려주세요.",
    "만 14세 미만 이용이 가능한지 궁금합니다.",
]


BUCKETS: list[tuple[list[str], int, tuple[int, int]]] = [
    # (corpus, count_per_run, rating_range)
    (BUGS, 26, (1, 2)),
    (PAYMENT_REFUND, 16, (1, 2)),
    (LOGIN, 12, (1, 3)),
    (PERFORMANCE, 14, (1, 3)),
    (UX_UI, 12, (2, 4)),
    (FEATURE_REQUEST, 10, (3, 4)),
    (PRAISE, 24, (4, 5)),
    (SPAM, 6, (1, 5)),
    (COMPLAINT_GENERIC, 12, (1, 3)),
    (POLICY_INQUIRY, 8, (3, 4)),
]


SOURCES = [ReviewSource.GOOGLE_PLAY, ReviewSource.APP_STORE, ReviewSource.INTERNAL]
APP_VERSIONS = ["3.0.0", "3.1.0", "3.2.0", "3.2.1", "3.3.0", "3.3.1"]
LOCALES = ["ko-KR", "ko-KR", "ko-KR", "en-US", "ja-JP"]
OSES = ["android", "android", "ios", "ios", "web"]


async def _wipe(db) -> None:
    for model in (AuditLog, ReplyDraft, PolicyDecision, ClassificationResult, Review):
        await db.execute(delete(model))
    await db.commit()


async def _build_reviews(rng: random.Random) -> list[dict]:
    items: list[dict] = []
    for corpus, count, (r_lo, r_hi) in BUCKETS:
        for _ in range(count):
            text = rng.choice(corpus)
            items.append(
                {
                    "raw_text": text,
                    "rating": rng.randint(r_lo, r_hi),
                    "source": rng.choice(SOURCES),
                    "app_version": rng.choice(APP_VERSIONS),
                    "locale": rng.choice(LOCALES),
                    "os": rng.choice(OSES),
                    "author_name": rng.choice(["익명", "김영희", "이철수", "박하나", None]),
                    "offset_days": rng.randint(0, 21),
                    "offset_minutes": rng.randint(0, 60 * 24),
                }
            )
    rng.shuffle(items)
    return items


async def seed(*, keep: bool) -> None:
    rng = random.Random(RNG_SEED)

    async with AsyncSessionLocal() as db:
        if not keep:
            print("[seed] wiping existing reviews + pipeline data…")
            await _wipe(db)

        audit = AuditLogger(db=db, actor="seed")
        classifier = StubClassifier()
        policy = RuleBasedPolicyEngine()
        generator = TemplateReplyGenerator()

        items = await _build_reviews(rng)
        now = datetime.now(timezone.utc)

        print(f"[seed] inserting {len(items)} reviews…")
        reviews: list[Review] = []
        for it in items:
            ts = now - timedelta(days=it["offset_days"], minutes=it["offset_minutes"])
            review = Review(
                source=it["source"],
                raw_text=it["raw_text"],
                normalized_text=normalize_text(it["raw_text"]),
                rating=it["rating"],
                app_version=it["app_version"],
                locale=it["locale"],
                os=it["os"],
                author_name=it["author_name"],
                ingested_at=ts,
            )
            db.add(review)
            reviews.append(review)
        await db.flush()

        for r in reviews:
            await audit.record(
                entity_type="review", entity_id=r.id, action="ingest",
                after={"source": r.source.value, "rating": r.rating},
            )

        print("[seed] classifying + evaluating policy + generating drafts…")
        draft_count = 0
        skipped_ignore = 0
        approved_count = 0
        published_count = 0

        for r in reviews:
            # classify
            c = await classifier.classify(review_text=r.normalized_text, review_id=r.id)
            cr = ClassificationResult(
                review_id=r.id,
                categories=[x.value for x in c.categories],
                sentiment=c.sentiment,
                urgency=c.urgency,
                confidence=c.confidence,
                entropy=c.entropy,
                ambiguity_score=c.ambiguity_score,
                top_candidates=(
                    [t.model_dump() for t in c.top_candidates] if c.top_candidates else None
                ),
                needs_clarification=c.needs_clarification,
                out_of_distribution=c.out_of_distribution,
                model_version=c.model_version,
            )
            db.add(cr)
            await db.flush()
            await audit.record(
                entity_type="classification_result", entity_id=cr.id, action="classify",
                after={"categories": cr.categories, "confidence": cr.confidence},
            )

            # policy
            p = await policy.evaluate(classification=c, rating=r.rating, app_version=r.app_version)
            pd = PolicyDecision(
                review_id=r.id,
                action=p.action,
                risk_score=p.risk_score,
                reason_codes=p.reason_codes,
                policy_version=p.policy_version,
            )
            db.add(pd)
            await db.flush()
            await audit.record(
                entity_type="policy_decision", entity_id=pd.id, action="evaluate",
                after={"action": pd.action.value, "risk_score": pd.risk_score},
            )

            if p.action == PolicyAction.IGNORE:
                skipped_ignore += 1
                continue

            if p.action == PolicyAction.AUTO_REPLY or p.action == PolicyAction.DRAFT_REPLY:
                g = await generator.generate(classification=c, review_text=r.normalized_text)
                draft = ReplyDraft(
                    review_id=r.id,
                    tone=g.tone,
                    template_id=g.template_id,
                    generated_text=g.text,
                    requires_human_approval=g.requires_human_approval,
                    model_version=g.model_version,
                    status=ReplyStatus.PENDING,
                )
                db.add(draft)
                await db.flush()
                draft_count += 1
                await audit.record(
                    entity_type="reply_draft", entity_id=draft.id, action="generate",
                    after={"template_id": draft.template_id, "status": draft.status.value},
                )

                # auto-move some through the state machine so we have data in each bucket.
                if p.action == PolicyAction.AUTO_REPLY and not draft.requires_human_approval:
                    draft.status = ReplyStatus.APPROVED
                    draft.approved_at = now
                    await audit.record(
                        entity_type="reply_draft", entity_id=draft.id, action="approve",
                        after={"status": draft.status.value},
                    )
                    approved_count += 1
                    # publish a few of these
                    if rng.random() < 0.5:
                        draft.status = ReplyStatus.PUBLISHED
                        draft.published_at = now
                        await audit.record(
                            entity_type="reply_draft", entity_id=draft.id, action="publish",
                            after={"status": draft.status.value},
                        )
                        published_count += 1

        await db.commit()

        print(
            f"[seed] done — reviews={len(reviews)} drafts={draft_count} "
            f"ignored={skipped_ignore} approved={approved_count} published={published_count}"
        )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keep", action="store_true", help="Do not wipe existing data first.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(seed(keep=args.keep))
