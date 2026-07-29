from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


SNSPlatform = Literal["instagram", "facebook", "x", "threads"]


class SNSExportRequest(BaseModel):
    platform: SNSPlatform = Field(
        ...,
        description="SNS 플랫폼 선택",
        examples=["instagram"],
    )

    image_url: HttpUrl = Field(
        ...,
        description="SNS 게시용 광고 이미지 URL",
        examples=["https://example.com/results/ad_001.png"],
    )

    product_name: str = Field(
        ...,
        min_length=1,
        max_length=80,
        description="상품명",
        examples=["수제 딸기 생크림 케이크"],
    )

    headline: str | None = Field(
        default=None,
        max_length=80,
        description="광고 제목 또는 핵심 문구",
        examples=["오늘을 달콤하게 채우는 한 조각"],
    )

    description: str | None = Field(
        default=None,
        max_length=300,
        description="광고 설명 문구",
        examples=["부드러운 생크림과 신선한 딸기가 어우러진 디저트입니다."],
    )

    custom_message: str | None = Field(
        default=None,
        max_length=300,
        description="사용자가 SNS 게시글에 추가하고 싶은 문구",
        examples=["이번 주말 한정 할인 중이에요!\nDM 문의 주세요."],
    )

    style: str | None = Field(
        default=None,
        max_length=50,
        description="선택된 광고 스타일",
        examples=["warm"],
    )


class SNSExportResponse(BaseModel):
    platform: SNSPlatform = Field(
        ...,
        examples=["instagram"],
    )

    image_url: HttpUrl = Field(
        ...,
        examples=["https://example.com/results/ad_001.png"],
    )

    caption: str = Field(
        ...,
        description="SNS 게시용 캡션",
        examples=["수제 딸기 생크림 케이크 🍓"],
    )

    hashtags: list[str] = Field(
        default_factory=list,
        description="SNS 게시용 해시태그 목록",
        examples=[["#수제케이크", "#딸기케이크", "#디저트맛집", "#카페추천"]],
    )

    post_text: str = Field(
        ...,
        description="최종 SNS 게시글",
        examples=[
            """수제 딸기 생크림 케이크 🍓

부드러운 생크림과 신선한 딸기가 어우러진 디저트입니다.

이번 주말 한정 할인 중이에요!
DM 문의 주세요.

#수제케이크 #딸기케이크 #디저트맛집 #카페추천"""
        ],
    )