"""Seed the KB with ~14 synthetic documents covering all doc_types.

Content is hand-written to be plausibly realistic for a generic Korean
mobile app. No proprietary text is copied from any real company's KB —
patterns are generic (app-store refund windows, account recovery steps,
outage comms, CS tone guidelines from blueprint §20).

Usage:
    poetry run python scripts/seed_kb.py           # wipe + reseed
    poetry run python scripts/seed_kb.py --keep    # append
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.kb import DocType, KbChunk, KbDocument
from app.services.audit.logger import AuditLogger


DOCS: list[dict] = [
    # --- FAQ (5) ---
    {
        "title": "결제 후 구독이 적용되지 않을 때",
        "doc_type": DocType.FAQ,
        "tags": ["faq", "결제", "구독"],
        "content": (
            "결제 완료 후 구독이 즉시 반영되지 않는 경우, 아래 순서대로 확인해 주세요.\n\n"
            "1. 앱 종료 후 재실행\n"
            "2. 설정 > 구독 상태에서 '새로고침' 탭\n"
            "3. 스토어 영수증 번호와 결제 시각 확인\n\n"
            "10분이 지나도 반영되지 않으면 영수증 번호와 함께 고객센터에 문의해 주세요. "
            "중복 결제 의심 건은 환불 조치가 가능합니다."
        ),
    },
    {
        "title": "자동결제(정기결제) 해지 방법",
        "doc_type": DocType.FAQ,
        "tags": ["faq", "결제", "해지", "정기결제"],
        "content": (
            "자동결제는 결제한 스토어에서만 해지할 수 있습니다.\n\n"
            "• iOS: 설정 앱 > 사용자 이름 > 구독 > 해당 서비스 > 구독 취소\n"
            "• Android: Play 스토어 > 프로필 > 결제 및 구독 > 구독 > 해당 서비스 > 정기결제 해지\n\n"
            "해지 후 이미 결제된 기간은 만료일까지 이용할 수 있으며, 해지 시점부터는 "
            "추가 과금이 발생하지 않습니다."
        ),
    },
    {
        "title": "환불 요청 절차 및 기간",
        "doc_type": DocType.FAQ,
        "tags": ["faq", "환불", "결제"],
        "content": (
            "환불은 원칙적으로 결제일로부터 7일 이내, 콘텐츠를 이용하지 않은 경우에 한해 가능합니다.\n\n"
            "요청 경로:\n"
            "• 앱 내 '마이페이지 > 결제 내역 > 환불 요청'\n"
            "• 스토어 직접 환불: iOS는 reportaproblem.apple.com, Android는 Play 스토어 내 환불 요청\n\n"
            "스토어 결제는 당사가 직접 환불을 처리할 수 없으며, 스토어 환불 정책에 따라 처리됩니다. "
            "운영자는 해당 경로 안내까지만 응답합니다 — 환불 확정 표현은 금지."
        ),
    },
    {
        "title": "로그인이 반복 실패할 때",
        "doc_type": DocType.FAQ,
        "tags": ["faq", "로그인", "계정"],
        "content": (
            "로그인 실패가 반복되면 아래를 확인해 주세요.\n\n"
            "1. 가입 시 사용한 계정 종류(이메일/소셜 로그인)가 맞는지\n"
            "2. 최근 비밀번호 변경 여부\n"
            "3. 기기 시각이 실제 시각과 5분 이상 차이나는지 (2단계 인증 오류의 원인)\n"
            "4. 네트워크 상태 (VPN 사용 중이면 해제 후 재시도)\n\n"
            "5회 이상 실패하면 계정이 일시 잠금될 수 있습니다. "
            "잠금 해제는 '로그인 > 비밀번호 재설정' 또는 고객센터를 통해 가능합니다."
        ),
    },
    {
        "title": "계정 잠김 해제 요청",
        "doc_type": DocType.FAQ,
        "tags": ["faq", "계정", "보안"],
        "content": (
            "계정이 잠긴 경우 보안 확인 후 해제해 드립니다.\n\n"
            "필요 정보:\n"
            "• 가입 이메일\n"
            "• 최근 결제 내역(있는 경우) 또는 로그인 기기 정보\n\n"
            "본인 확인이 필요한 민감 건이므로, 운영자는 절대 직접 해제하지 말고 "
            "고객센터 문의 경로로 안내해 주세요."
        ),
    },
    # --- Release notes (3) ---
    {
        "title": "v3.3.1 업데이트 노트",
        "doc_type": DocType.RELEASE_NOTE,
        "tags": ["release", "v3.3.1"],
        "content": (
            "릴리즈 일자: 2026-03-15\n\n"
            "개선\n"
            "• 알림 탭 후 앱이 꺼지던 이슈 수정\n"
            "• 다크모드에서 일부 버튼 색 대비 강화\n"
            "• 무한 스크롤 성능 개선 (30% 빨라짐)\n\n"
            "신규\n"
            "• 프로필 사진 크롭 기능\n"
            "• 로그인 기기 관리 화면 추가"
        ),
    },
    {
        "title": "v3.3.0 업데이트 노트",
        "doc_type": DocType.RELEASE_NOTE,
        "tags": ["release", "v3.3.0"],
        "content": (
            "릴리즈 일자: 2026-02-20\n\n"
            "신규\n"
            "• 홈 화면 개편\n"
            "• 주간 활동 요약 카드\n\n"
            "버그 수정\n"
            "• 일부 안드로이드 14 기기에서 시작 시 크래시 발생하던 이슈 수정\n"
            "• 업데이트 후 언어 설정이 초기화되던 이슈 수정"
        ),
    },
    {
        "title": "v3.2.1 업데이트 노트",
        "doc_type": DocType.RELEASE_NOTE,
        "tags": ["release", "v3.2.1"],
        "content": (
            "릴리즈 일자: 2026-01-28\n\n"
            "긴급 수정\n"
            "• 결제 직후 뒤로가기 시 오류 메시지가 뜨던 이슈 수정\n"
            "• QR 스캐너가 간헐적으로 카메라 인식 실패하던 이슈 수정\n\n"
            "성능\n"
            "• 이미지 로딩 속도 약 15% 개선"
        ),
    },
    # --- Announcements (2) ---
    {
        "title": "[공지] 정기 점검 안내",
        "doc_type": DocType.ANNOUNCEMENT,
        "tags": ["announcement", "점검"],
        "content": (
            "서비스 안정성 개선을 위해 정기 점검이 진행됩니다.\n\n"
            "• 일시: 매월 첫째 주 화요일 03:00 ~ 05:00 (KST)\n"
            "• 영향: 로그인 및 결제 일시 중단\n\n"
            "점검 시간은 앱 내 공지 및 웹사이트에서 미리 공지합니다."
        ),
    },
    {
        "title": "[공지] 이용약관 개정 안내",
        "doc_type": DocType.ANNOUNCEMENT,
        "tags": ["announcement", "약관"],
        "content": (
            "더 나은 서비스 제공을 위해 이용약관이 일부 개정됩니다.\n\n"
            "• 시행일: 개정 약관 공지일로부터 30일 이후\n"
            "• 주요 변경 사항: 결제/환불 정책 문구 명확화, 계정 휴면 기준 조정\n\n"
            "개정 약관에 동의하지 않으시는 경우 시행일 전에 탈퇴가 가능합니다. "
            "상세 내용은 앱 내 '설정 > 약관 및 정책'에서 확인해 주세요."
        ),
    },
    # --- Incident response (2) ---
    {
        "title": "장애 대응 문안 — 일반 서비스 지연",
        "doc_type": DocType.INCIDENT_RESPONSE,
        "tags": ["incident", "장애"],
        "content": (
            "일부 사용자분들께 서비스 이용 지연 현상이 확인되어 긴급 점검 중입니다. "
            "불편을 드려 죄송합니다.\n\n"
            "• 원인: 내부 확인 중\n"
            "• 예상 복구 시각: 확인 후 앱 내 공지로 안내\n\n"
            "운영자 지침: 원인이 확정되기 전에는 '내부 확인 중'까지만 언급. "
            "'서버가 다운되었다' 등 원인 단정 표현 금지 (blueprint §20.3)."
        ),
    },
    {
        "title": "장애 대응 문안 — 결제 시스템 지연",
        "doc_type": DocType.INCIDENT_RESPONSE,
        "tags": ["incident", "결제", "장애"],
        "content": (
            "결제 처리 지연이 발생한 경우 아래 문안을 기본 템플릿으로 사용합니다.\n\n"
            "---\n"
            "안녕하세요. 결제 처리 지연으로 이용에 불편을 드려 죄송합니다. "
            "중복 결제가 확인된 건은 확인 후 순차적으로 조치될 예정입니다. "
            "영수증 번호와 함께 고객센터로 문의 주시면 확인 후 안내드리겠습니다.\n"
            "---\n\n"
            "금지: '환불해 드렸습니다', '곧 복구됩니다' 등 확정 표현."
        ),
    },
    # --- CS policy (1) ---
    {
        "title": "고객응대 응답 원칙 v1",
        "doc_type": DocType.CS_POLICY,
        "tags": ["policy", "cs", "응대"],
        "content": (
            "Polaris 응답 자동화의 기본 원칙 (blueprint §20)\n\n"
            "1. 고위험 카테고리(결제/환불/계정잠김/개인정보/법적·보안)는 자동 게시 금지. "
            "항상 초안 생성 후 사람 검수.\n"
            "2. 원인 단정 금지: '버그입니다', '서버 다운입니다' 사용하지 않음.\n"
            "3. 일정 확정 금지: '곧 수정됩니다', '다음 주 안에' 등 금지.\n"
            "4. 권한 없는 확정 금지: '환불해 드리겠습니다' 금지. 경로 안내까지만.\n"
            "5. 공감 표현 우선: '불편을 드려 죄송합니다', '확인이 필요합니다' 등 사용.\n"
            "6. 모든 자동 결정은 audit log에 기록되어야 함."
        ),
    },
    # --- Forbidden expression (1) ---
    {
        "title": "금지 표현 리스트 v1",
        "doc_type": DocType.FORBIDDEN_EXPRESSION,
        "tags": ["policy", "금지표현"],
        "content": (
            "아래 표현은 자동 생성된 초안에 포함되어서는 안 됩니다 (blueprint §20.3).\n\n"
            "금지:\n"
            "• '확인했습니다' (실제로 확인하지 않은 경우)\n"
            "• '환불 처리해드리겠습니다' (운영자에게 권한이 없는 경우)\n"
            "• '버그가 맞습니다' (원인이 확정되기 전)\n"
            "• '곧 수정됩니다' (일정이 확정되기 전)\n"
            "• '서버가 다운되었습니다' (원인 단정)\n\n"
            "권장 대체 표현:\n"
            "• '확인이 필요합니다'\n"
            "• '상세 확인을 위해 고객센터 문의 부탁드립니다'\n"
            "• '전달하여 검토하겠습니다'\n"
            "• '불편을 드려 죄송합니다'"
        ),
    },
]


async def _wipe(db) -> None:
    await db.execute(delete(KbChunk))
    await db.execute(delete(KbDocument))
    await db.commit()


async def seed(*, keep: bool) -> None:
    async with AsyncSessionLocal() as db:
        if not keep:
            print("[kb-seed] wiping existing KB…")
            await _wipe(db)

        audit = AuditLogger(db=db, actor="seed")

        print(f"[kb-seed] inserting {len(DOCS)} documents…")
        for d in DOCS:
            doc = KbDocument(
                title=d["title"],
                doc_type=d["doc_type"],
                tags=d["tags"],
                content=d["content"],
                version=1,
                active=True,
            )
            db.add(doc)
            await db.flush()
            await audit.record(
                entity_type="kb_document",
                entity_id=doc.id,
                action="seed",
                after={"title": doc.title, "doc_type": doc.doc_type.value},
            )
        await db.commit()
        print(f"[kb-seed] done — {len(DOCS)} docs")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keep", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(seed(keep=_parse_args().keep))
