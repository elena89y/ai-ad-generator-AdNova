from app.schemas.export import SNSExportRequest


PLATFORM_CONFIG = {
    "instagram": {
        "max_length": None,
        "max_hashtags": 30,
    },
    "facebook": {
        "max_length": None,
        "max_hashtags": 30,
    },
    "x": {
        "max_length": 280,
        "max_hashtags": 15,
    },
    "threads": {
        "max_length": None,
        "max_hashtags": 30,
    },
}


def clean_text(value: str | None) -> str:
    """
    입력값의 앞뒤 공백을 제거하고,
    값이 없을 경우 빈 문자열을 반환한다.
    """
    if not value:
        return ""

    return value.strip()


def make_hashtag(value: str) -> str:
    """
    입력 문자열을 SNS 해시태그 형식으로 변환한다.

    공백은 제거하고,
    영문/숫자/한글만 남긴 뒤 앞에 #을 붙인다.
    """
    cleaned = value.strip().replace(" ", "")

    cleaned = "".join(
        char
        for char in cleaned
        if char.isalnum() or "\uAC00" <= char <= "\uD7A3"
    )

    if not cleaned:
        return ""

    return f"#{cleaned}"


def generate_hashtags(
    product_name: str,
    style: str | None = None,
) -> list[str]:
    """
    상품명과 광고 스타일을 기반으로
    SNS 게시용 해시태그를 생성한다.
    """
    hashtags = []

    product_tag = make_hashtag(product_name)

    if product_tag:
        hashtags.append(product_tag)

    if style:
        style_tag = make_hashtag(style)

        if style_tag:
            hashtags.append(style_tag)

    hashtags.extend(
        [
            "#신상품",
            "#추천",
            "#광고",
        ]
    )
        # TODO:
        # 현재는 기본 해시태그를 사용하지만,
        # 향후 AI 기반 또는 상품 카테고리 기반 해시태그 생성으로 개선 예정.
        
    return list(dict.fromkeys(hashtags))


def create_caption(data: SNSExportRequest) -> str:
    """
    SNS 게시글 상단에 표시될 캡션을 생성한다.
    """
    product_name = clean_text(data.product_name)
    headline = clean_text(data.headline)

    if headline:
        return f"{product_name} ✨\n{headline}"

    return f"{product_name} ✨"


def format_post_text(
    data: SNSExportRequest,
) -> tuple[str, str, list[str]]:
    """
    플랫폼별 SNS 게시글을 생성한다.

    Returns
    -------
    tuple
        (
            caption,
            post_text,
            hashtags
        )
    """

    caption = create_caption(data)

    style = clean_text(data.style)

    hashtags = generate_hashtags(
        data.product_name,
        style,
    )

    config = PLATFORM_CONFIG[data.platform]

    hashtags = hashtags[: config["max_hashtags"]]

    parts = [caption]

    description = clean_text(data.description)
    custom_message = clean_text(data.custom_message)

    if description:
        parts.append(description)

    if custom_message:
        parts.append(custom_message)

    if hashtags:
        parts.append(" ".join(hashtags))

    post_text = "\n\n".join(parts)

    if (
        config["max_length"] is not None
        and len(post_text) > config["max_length"]
    ):
        raise ValueError(
            f"{data.platform.upper()}는 최대 {config['max_length']}자까지 작성할 수 있습니다."
        )

    return (
        caption,
        post_text,
        hashtags,
    )