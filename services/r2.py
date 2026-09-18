"""Cloudflare R2 service with multipart / streaming upload, and resumable
uploads: if the connection drops mid-transfer, in-progress multipart state
(upload_id + completed part ETags) is checkpointed to disk so a retry can
continue from the last completed part instead of starting over."""
import json
import logging
import uuid
import time
from pathlib import Path
from typing import Optional, Tuple, Callable, BinaryIO, List, Dict
from config import (
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_ENDPOINT,
    R2_BUCKET_NAME,
)

logger = logging.getLogger(__name__)

# 8 MB parts — good balance for R2 multipart. R2/S3 allow up to 10,000 parts
# per upload, so 8MB parts support files up to ~80GB.
PART_SIZE = 8 * 1024 * 1024

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_STATE_DIR = ROOT / "data" / "upload_state"
UPLOAD_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _state_path(resume_id: str) -> Path:
    safe = "".join(c for c in resume_id if c.isalnum() or c in "-_")[:120]
    return UPLOAD_STATE_DIR / f"{safe}.json"


def load_resume_state(resume_id: str) -> Optional[Dict]:
    """Returns {key, upload_id, parts, uploaded_bytes} if a resumable upload
    exists for this id, else None."""
    p = _state_path(resume_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_resume_state(resume_id: str, state: Dict):
    try:
        _state_path(resume_id).write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not save upload resume state: %s", e)


def clear_resume_state(resume_id: str):
    try:
        p = _state_path(resume_id)
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _object_key(file_name: str, user_id: int = 0) -> str:
    """Organize R2: users/{id}/videos|audio|files/{uuid}_{name}"""
    import uuid as _uuid
    ext = Path(file_name).suffix.lower()
    if ext in (".mp4", ".mkv", ".webm", ".mov", ".ts"):
        folder = "videos"
    elif ext in (".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"):
        folder = "audio"
    else:
        folder = "files"
    uid = user_id or "public"
    return f"users/{uid}/{folder}/{_uuid.uuid4().hex[:12]}_{file_name}"


class R2Service:
    def __init__(self):
        self.client = None
        self.bucket = R2_BUCKET_NAME
        self.last_error: str = ""
        self._init_client()

    def _init_client(self):
        if not all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET_NAME]):
            self.last_error = "بيانات R2 ناقصة في .env"
            logger.warning(self.last_error)
            return
        try:
            import boto3
            from botocore.config import Config
            self.client = boto3.client(
                "s3",
                endpoint_url=R2_ENDPOINT,
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 5, "mode": "standard"},
                ),
                region_name="auto",
            )
            logger.info("R2 client initialized")
            self.last_error = ""
        except Exception as e:
            self.last_error = str(e)[:200]
            logger.error("Failed to init R2: %s", e)
            self.client = None

    def _ensure(self) -> bool:
        if not self.client:
            self._init_client()
        return self.client is not None

    def generate_presigned_url(self, key: str, expires: int = 86400 * 7) -> Optional[str]:
        if not self._ensure():
            return None
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires,
            )
        except Exception as e:
            logger.error("Presign error: %s", e)
            return None

    def delete_object(self, key: str) -> bool:
        if not self._ensure():
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            logger.error("R2 delete error: %s", e)
            return False

    def upload_fileobj(
        self,
        file_obj,
        file_name: str,
        content_type: str = None,
        progress_callback: Callable[[int], None] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Simple full upload (small files)."""
        if not self._ensure():
            return None, None
        key = _object_key(file_name)
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        try:
            class _PR:
                def __init__(self, raw, cb):
                    self._raw, self._cb = raw, cb
                def read(self, amt=-1):
                    data = self._raw.read(amt)
                    if data and self._cb:
                        try:
                            self._cb(len(data))
                        except Exception:
                            pass
                    return data
                def seek(self, *a, **k):
                    return self._raw.seek(*a, **k)
                def tell(self):
                    return self._raw.tell()

            body = _PR(file_obj, progress_callback) if progress_callback else file_obj
            try:
                file_obj.seek(0)
            except Exception:
                pass
            self.client.upload_fileobj(
                body, self.bucket, key, ExtraArgs=extra or None
            )
            url = self.generate_presigned_url(key) or f"{R2_ENDPOINT}/{self.bucket}/{key}"
            return key, url
        except Exception as e:
            self.last_error = str(e)[:250]
            logger.error("R2 upload error: %s", e)
            return None, None

    def multipart_upload_from_iter(
        self,
        chunks_iter,
        file_name: str,
        total_size: int = 0,
        content_type: str = None,
        progress_callback: Callable[[int, int], None] = None,
        resume_id: Optional[str] = None,
        user_id: int = 0,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Streaming multipart upload. chunks_iter yields bytes chunks starting
        from whatever byte offset the caller resumed from (see resume_id).
        progress_callback(uploaded_bytes, total_size). Only keeps one part in
        memory at a time — never the full file.

        Resumability: if resume_id is given, in-progress state (upload_id +
        completed part ETags) is checkpointed to disk after every part. If the
        transfer dies, calling again with the same resume_id and a
        chunks_iter that starts at the already-uploaded byte offset
        (state["uploaded_bytes"]) continues the SAME multipart upload instead
        of starting from zero.
        """
        if not self._ensure():
            return None, None

        resumed_state = load_resume_state(resume_id) if resume_id else None

        if resumed_state:
            key = resumed_state["key"]
            upload_id = resumed_state["upload_id"]
            parts = resumed_state.get("parts", [])
            uploaded = resumed_state.get("uploaded_bytes", 0)
            part_number = len(parts) + 1
            logger.info(
                "Resuming multipart upload key=%s upload_id=%s from %s bytes (%s parts done)",
                key, upload_id, uploaded, len(parts),
            )
        else:
            key = _object_key(file_name, user_id)
            upload_id = None
            parts = []
            part_number = 1
            uploaded = 0

        buffer = bytearray()

        try:
            if upload_id is None:
                create_args = {"Bucket": self.bucket, "Key": key}
                if content_type:
                    create_args["ContentType"] = content_type
                resp = self.client.create_multipart_upload(**create_args)
                upload_id = resp["UploadId"]
                logger.info("Multipart started key=%s upload_id=%s", key, upload_id)

            def checkpoint():
                if resume_id:
                    _save_resume_state(resume_id, {
                        "key": key, "upload_id": upload_id,
                        "parts": parts, "uploaded_bytes": uploaded,
                        "total_size": total_size, "file_name": file_name,
                        "updated_at": time.time(),
                    })

            def flush_part(data: bytes):
                nonlocal part_number, uploaded
                if not data:
                    return
                part = self.client.upload_part(
                    Bucket=self.bucket,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=bytes(data),
                )
                parts.append({"ETag": part["ETag"], "PartNumber": part_number})
                uploaded += len(data)
                part_number += 1
                checkpoint()
                if progress_callback:
                    try:
                        progress_callback(uploaded, total_size)
                    except Exception:
                        pass

            for chunk in chunks_iter:
                if not chunk:
                    continue
                buffer.extend(chunk)
                while len(buffer) >= PART_SIZE:
                    piece = bytes(buffer[:PART_SIZE])
                    del buffer[:PART_SIZE]
                    flush_part(piece)

            if buffer:
                flush_part(bytes(buffer))
                buffer.clear()

            if not parts:
                self.client.abort_multipart_upload(
                    Bucket=self.bucket, Key=key, UploadId=upload_id
                )
                self.client.put_object(Bucket=self.bucket, Key=key, Body=b"")
            else:
                self.client.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )

            if resume_id:
                clear_resume_state(resume_id)

            url = self.generate_presigned_url(key) or f"{R2_ENDPOINT}/{self.bucket}/{key}"
            logger.info("Multipart complete key=%s parts=%s size=%s", key, len(parts), uploaded)
            self.last_error = ""
            return key, url

        except Exception as e:
            self.last_error = str(e)[:250]
            logger.error("Multipart upload error: %s", e)
            # NOTE: we deliberately do NOT abort the multipart upload here when
            # resume_id is set — the checkpoint (already-uploaded parts) stays
            # valid on R2's side and a later resume attempt reuses it. Without
            # resume_id we clean up immediately since nothing can continue it.
            if upload_id and not resume_id:
                try:
                    self.client.abort_multipart_upload(
                        Bucket=self.bucket, Key=key, UploadId=upload_id
                    )
                except Exception:
                    pass
            return None, None


r2_service = R2Service()
