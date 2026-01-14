"""
共通エラーハンドリング
"""
from fastapi import HTTPException, status
from typing import Literal

ErrorCode = Literal[
    "INVALID_INPUT",
    "NOT_FOUND",
    "TIMEOUT",
    "INTERNAL_ERROR",
]

# エラーコードとHTTPステータスのマッピング
ERROR_STATUS_MAP: dict[ErrorCode, int] = {
    "INVALID_INPUT": status.HTTP_400_BAD_REQUEST,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "TIMEOUT": status.HTTP_408_REQUEST_TIMEOUT,
    "INTERNAL_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


class AppError(HTTPException):
    """アプリケーション共通エラー
    
    FastAPIのHTTPExceptionはdetailをJSONとして返す。
    フロントエンドで期待される形式: { "error": { "code": "...", "message": "..." } }
    """

    def __init__(self, code: ErrorCode, message: str):
        status_code = ERROR_STATUS_MAP[code]
        # detailにJSON形式のエラー情報を設定
        # FastAPIが自動的にJSONレスポンスとして返す
        super().__init__(
            status_code=status_code,
            detail={"error": {"code": code, "message": message}}
        )


def raise_invalid_input(message: str) -> None:
    """INVALID_INPUTエラーを発生させる"""
    raise AppError("INVALID_INPUT", message)


def raise_not_found(message: str) -> None:
    """NOT_FOUNDエラーを発生させる
    
    HTTP 404と { "error": { "code": "NOT_FOUND", "message": "..." } } を返す
    """
    raise AppError("NOT_FOUND", message)


def raise_timeout(message: str) -> None:
    """TIMEOUTエラーを発生させる"""
    raise AppError("TIMEOUT", message)


def raise_internal_error(message: str) -> None:
    """INTERNAL_ERRORエラーを発生させる"""
    raise AppError("INTERNAL_ERROR", message)
