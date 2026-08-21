import uuid
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.api.config import get_settings


def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def build_object_key(source_id: uuid.UUID, filename: str) -> str:
    safe_name = (filename or "source.pdf").replace("/", "_")
    return f"sources/{source_id}/{safe_name}"


def upload_pdf(object_key: str, file_obj: BinaryIO, content_type: str = "application/pdf") -> None:
    settings = get_settings()
    client = get_s3_client()
    client.upload_fileobj(
        file_obj,
        settings.s3_bucket_name,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )


def generate_presigned_url(object_key: str) -> str:
    settings = get_settings()
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": object_key},
        ExpiresIn=settings.s3_presigned_url_expiry_seconds,
    )


def delete_pdf(object_key: str) -> None:
    """Убрать файл источника из хранилища.

    Ошибку хранилища глушим намеренно: запись в базе уже удалена, и падать
    из-за осиротевшего объекта в бакете нельзя — источник тогда останется
    наполовину удалённым. Осиротевший файл никому не виден: ссылка на него
    выдаётся только по записи источника.
    """
    settings = get_settings()
    try:
        get_s3_client().delete_object(Bucket=settings.s3_bucket_name, Key=object_key)
    except Exception:  # noqa: BLE001 — см. пояснение выше
        pass
