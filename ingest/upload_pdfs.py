"""
upload_pdfs.py — push the registered source PDFs to the object-storage bucket
(Backblaze B2 / Cloudflare R2 / any S3-compatible store) so `download_url()`
links resolve.

Object keys mirror Documents/ exactly (see doc_registry.blob_key), so a link
built from PDF_BUCKET_BASE points straight at the uploaded file. PDFs are sent
with Content-Type application/pdf and Content-Disposition inline, so the browser
renders them (and the #page=N deep-link works) instead of forcing a save.

Config is read from S3_* env vars (legacy R2_* names still work as a fallback):

Setup (Backblaze B2 → S3 API):
    pip install boto3
    set S3_ENDPOINT=https://s3.us-west-004.backblazeb2.com
    set S3_REGION=us-west-004        # B2 needs the real region (not "auto")
    set S3_ACCESS_KEY_ID=<B2 keyID>
    set S3_SECRET_ACCESS_KEY=<B2 applicationKey>
    set S3_BUCKET=icd-sbi-manuals
Then, so the app builds links to the bucket's public URL:
    set PDF_BUCKET_BASE=https://f004.backblazeb2.com/file/icd-sbi-manuals

Cloudflare R2 is the same with its endpoint and S3_REGION=auto.

    python ingest/upload_pdfs.py            # upload every registered PDF
    python ingest/upload_pdfs.py --only <doc_id>
    python ingest/upload_pdfs.py --overwrite   # re-put even if key exists
"""
import load_env  # noqa: F401  — must precede the S3_*/R2_* reads below

import argparse
import os
import sys

from doc_registry import REGISTRY, pdf_path, blob_key

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _env(*names, default=None):
    """First set value among names (S3_* preferred, R2_* legacy fallback)."""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


def _client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise SystemExit("boto3 not installed — run: pip install boto3")
    endpoint = _env("S3_ENDPOINT", "R2_ENDPOINT")
    key = _env("S3_ACCESS_KEY_ID", "R2_ACCESS_KEY_ID")
    secret = _env("S3_SECRET_ACCESS_KEY", "R2_SECRET_ACCESS_KEY")
    if not (endpoint and key and secret):
        raise SystemExit("set S3_ENDPOINT, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY")
    return boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key, aws_secret_access_key=secret,
        region_name=_env("S3_REGION", "R2_REGION", default="auto"),
        config=Config(signature_version="s3v4"),
    )


def _exists(client, bucket, key):
    from botocore.exceptions import ClientError
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="upload a single doc_id")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-upload even if the key already exists")
    args = ap.parse_args()

    bucket = _env("S3_BUCKET", "R2_BUCKET")
    if not bucket:
        raise SystemExit("set S3_BUCKET")
    client = _client()

    entries = [e for e in REGISTRY if not args.only or e["doc_id"] == args.only]
    if not entries:
        raise SystemExit(f"no registry entry matches --only {args.only}")

    uploaded = skipped = missing = 0
    for entry in entries:
        path = pdf_path(entry)
        if not os.path.exists(path):
            print(f"!! MISSING PDF: {path}")
            missing += 1
            continue
        key = blob_key(entry)
        if not args.overwrite and _exists(client, bucket, key):
            print(f"= exists, skip: {key}")
            skipped += 1
            continue
        client.upload_file(
            path, bucket, key,
            ExtraArgs={"ContentType": "application/pdf",
                       "ContentDisposition": "inline"},
        )
        print(f"↑ {key}")
        uploaded += 1

    print(f"\nDone: {uploaded} uploaded, {skipped} skipped, {missing} missing.")
    if uploaded or skipped:
        print("Reminder: set PDF_BUCKET_BASE to the bucket's public URL and rebuild "
              "the KB (build_kb.py) so chunks carry the links.")


if __name__ == "__main__":
    main()
