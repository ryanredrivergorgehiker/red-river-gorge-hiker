"""Fail-closed partition of an immutable ordered batch for resumable planning.

This pure validator is not a producer/recovery authorization. Call only after
independent checkpoint and attempt-ledger verification has authenticated inputs.
"""
from dataclasses import dataclass


class PartitionError(ValueError):
    pass


@dataclass(frozen=True)
class Partition:
    accepted: tuple[str, ...]
    attempted_not_accepted: tuple[str, ...]
    unattempted: tuple[str, ...]


def partition(approved, attempted, accepted, quarantined, *, clean_closed, receipt_verified):
    """Only a verified clean close permits carrying a contiguous untouched suffix.

    attempted is the durable, ordered reservation ledger, not merely jobs with
    output. Any ambiguous reservation/closure must fail closed.
    """
    if not clean_closed or not receipt_verified:
        raise PartitionError('No verified clean closure; do not reallocate')
    vectors = (approved, attempted, accepted, quarantined)
    if any(not isinstance(v, (list, tuple)) or any(not isinstance(x, str) or not x for x in v) for v in vectors):
        raise PartitionError('Invalid job identifiers')
    approved, attempted, accepted, quarantined = map(tuple, vectors)
    if any(len(set(v)) != len(v) for v in vectors):
        raise PartitionError('Duplicate job identifier')
    if not approved or not attempted or approved[:len(attempted)] != attempted:
        raise PartitionError('Attempt ledger is not a nonempty ordered prefix')
    attempted_set = set(attempted)
    if not set(accepted) <= attempted_set or not set(quarantined) <= attempted_set:
        raise PartitionError('Output/quarantine outside attempted prefix')
    if set(accepted) & set(quarantined):
        raise PartitionError('Accepted and quarantined overlap')
    return Partition(tuple(x for x in attempted if x in set(accepted)),
                     tuple(x for x in attempted if x not in set(accepted)),
                     approved[len(attempted):])
