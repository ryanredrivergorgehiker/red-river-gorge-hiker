"""Prospective bounded source-HTTP resilience; no attempt or reservation reset."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TARGET='backend/scripts/gorge_guarded_worker.py'
TEMPLATE='.github/automation/source-templates/gorge_guarded_worker.py'
ORIGINAL='dc56c0345dcf84af42791433b93e58a16fbafa6d0e44c162020bc83aa28074f9'
REVIEWED='aab930c1f637969a812edb3441a88d7f6e4c5ef25df316d5aea5b5620c20e994'

def digest(raw):return hashlib.sha256(raw).hexdigest()

def expected():
    raw=(ROOT/TEMPLATE).read_bytes()
    if digest(raw)!=REVIEWED:raise ValueError('Reviewed source transport template changed')
    return raw

def install(root):
    target=Path(root)/TARGET
    if digest(target.read_bytes()) not in (ORIGINAL,REVIEWED):raise ValueError('Unreviewed source transport predecessor')
    target.write_bytes(expected())

def validate(root,previous=None):
    if (Path(root)/TARGET).read_bytes()!=expected():raise ValueError('Source transport differs from reviewed template')
    if previous is not None and digest(previous) not in (ORIGINAL,REVIEWED):
        raise ValueError('Source transport publication changed its predecessor')
