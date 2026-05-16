"""Seed Phase 2 data: 7 Korean banking companies + apps + mock reviews.

Run: poetry run python scripts/seed_phase2.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.models.app_profile import AppProfile, Platform
from app.models.company import Company, Industry
from app.services.mock_ingestion import MockIngestionService

SEED_DATA = [
    {
        "company": {
            "name": "KB국민은행",
            "industry": Industry.FINANCE,
            "homepage_url": "https://www.kbstar.com",
            "memo": "KB금융그룹 계열 주요 시중은행",
        },
        "apps": [
            {
                "app_name": "KB스타뱅킹",
                "platform": Platform.BOTH,
                "play_store_package": "com.kbstar.kbbank",
                "category": "finance",
                "is_target": True,
            }
        ],
    },
    {
        "company": {
            "name": "신한은행",
            "industry": Industry.FINANCE,
            "homepage_url": "https://www.shinhan.com",
            "memo": "신한금융그룹 계열 주요 시중은행",
        },
        "apps": [
            {
                "app_name": "신한 SOL",
                "platform": Platform.BOTH,
                "play_store_package": "com.shinhan.sbanking",
                "category": "finance",
                "is_competitor": True,
            }
        ],
    },
    {
        "company": {
            "name": "카카오뱅크",
            "industry": Industry.FINTECH,
            "homepage_url": "https://www.kakaobank.com",
            "memo": "인터넷전문은행, 간편함을 강점으로 하는 핀테크 은행",
        },
        "apps": [
            {
                "app_name": "카카오뱅크",
                "platform": Platform.BOTH,
                "play_store_package": "com.kakaobank.channel",
                "category": "finance",
                "is_competitor": True,
            }
        ],
    },
    {
        "company": {
            "name": "토스",
            "industry": Industry.FINTECH,
            "homepage_url": "https://toss.im",
            "memo": "비바리퍼블리카 운영, UX 강점의 종합금융 슈퍼앱",
        },
        "apps": [
            {
                "app_name": "토스",
                "platform": Platform.BOTH,
                "play_store_package": "viva.republica.toss",
                "category": "finance",
                "is_competitor": True,
            }
        ],
    },
    {
        "company": {
            "name": "우리은행",
            "industry": Industry.FINANCE,
            "homepage_url": "https://www.wooribank.com",
            "memo": "우리금융그룹 계열 주요 시중은행",
        },
        "apps": [
            {
                "app_name": "우리WON뱅킹",
                "platform": Platform.BOTH,
                "play_store_package": "com.wooribank.smart.won",
                "category": "finance",
                "is_competitor": True,
            }
        ],
    },
    {
        "company": {
            "name": "하나은행",
            "industry": Industry.FINANCE,
            "homepage_url": "https://www.hanabank.com",
            "memo": "하나금융그룹 계열 주요 시중은행",
        },
        "apps": [
            {
                "app_name": "하나원큐",
                "platform": Platform.BOTH,
                "play_store_package": "com.hanabank.ebk.channel.android.hananbank",
                "category": "finance",
                "is_competitor": True,
            }
        ],
    },
    {
        "company": {
            "name": "NH농협은행",
            "industry": Industry.FINANCE,
            "homepage_url": "https://www.nonghyup.com",
            "memo": "NH농협금융지주 계열 주요 시중은행",
        },
        "apps": [
            {
                "app_name": "NH올원뱅크",
                "platform": Platform.BOTH,
                "play_store_package": "nh.smart.allonebank",
                "category": "finance",
                "is_competitor": True,
            }
        ],
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        created_companies = 0
        created_apps = 0
        created_reviews = 0

        for entry in SEED_DATA:
            # Create company
            company = Company(**entry["company"])
            db.add(company)
            await db.flush()
            created_companies += 1
            print(f"  Company: {company.name} ({company.id})")

            # Create apps
            for app_data in entry["apps"]:
                app = AppProfile(company_id=company.id, **app_data)
                db.add(app)
                await db.flush()
                created_apps += 1
                print(f"    App: {app.app_name} ({app.id})")

                # Generate mock reviews
                svc = MockIngestionService(db)
                count = await svc.generate(app, count=120)
                created_reviews += count
                print(f"      Reviews: {count}건 생성")

        await db.commit()
        print(f"\n완료: 회사 {created_companies}개, 앱 {created_apps}개, 리뷰 {created_reviews}건")


if __name__ == "__main__":
    asyncio.run(main())
