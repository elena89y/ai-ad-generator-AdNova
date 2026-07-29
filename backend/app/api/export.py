from fastapi import APIRouter, HTTPException, status

from app.schemas.export import SNSExportRequest, SNSExportResponse
from app.services.export_service import format_post_text


router = APIRouter(
    prefix="/export",
    tags=["Export"],
)


@router.post(
    "/sns",
    response_model=SNSExportResponse,
    status_code=status.HTTP_200_OK,
)
def export_sns_post(data: SNSExportRequest):
    """
    생성된 광고 이미지와 광고 문구를 SNS 게시용 문구로 변환한다.
    """
    try:
        caption, post_text, hashtags = format_post_text(data)

        return SNSExportResponse(
            platform=data.platform,
            image_url=data.image_url,
            caption=caption,
            hashtags=hashtags,
            post_text=post_text,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )