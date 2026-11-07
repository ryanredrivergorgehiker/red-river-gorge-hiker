"""Generation-pinned GCS callback for the isolated cross-wave readback contract.

The caller must supply an already authenticated, least-privilege GCS client and
an approved private bucket name. This module never creates credentials or
establishes catalog/receipt authenticity. Not a production enrollment.
"""
import re


def generation_pinned_gcs_reader(client, bucket_name):
    """Return (key, generation, maximum_bytes) -> bytes, with no unpinned fallback."""
    if not isinstance(bucket_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,221}", bucket_name):
        raise ValueError("Explicit approved private GCS bucket required")
    if client is None or not callable(getattr(client, "bucket", None)):
        raise ValueError("Authenticated GCS client required")
    bucket = client.bucket(bucket_name)

    def read(key, generation, maximum_bytes):
        if (not isinstance(key, str) or not re.fullmatch(
                r"engineering/map-production/plans/[0-9a-f]{64}/slots/[0-9]{5}/[A-Za-z0-9_./-]+", key)
                or any(segment in ("", ".", "..") for segment in key.split("/"))):
            raise ValueError("Protected production object key required")
        if not isinstance(generation, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", generation):
            raise ValueError("Exact numeric generation required")
        if type(maximum_bytes) is not int or maximum_bytes < 1:
            raise ValueError("Positive read ceiling required")
        version = int(generation)
        blob = bucket.blob(key, generation=version)
        # Read at most ceiling + 1 bytes. A truncated/oversize object fails closed
        # at the caller's exact size/hash verification; no retry at latest generation.
        data = blob.download_as_bytes(start=0, end=maximum_bytes,
                                      if_generation_match=version,
                                      timeout=30, retry=None)
        if type(data) is not bytes or len(data) > maximum_bytes:
            raise ValueError("Protected GCS read exceeded byte ceiling")
        return data

    return read
