"""Forward-only, exact reviewed credential refresh migration."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TARGET='backend/scripts/run_gorge_checkpoint_slot.py'
MODULE='rrgh_wif_credentials.py'
PREVIOUS_MODULE_SHA256='8ab59ae0c3b7400a75bbdffabaf74a049273f2c611a8cf32a02f7206c32439d1'
BASE='2600cab47124a977ec97163393f06c55a81fdadf16da231669ceb7e685bae730'
START='# Direct WIF access-token lifetime'
END='\n\ndef execute('
REPLACEMENT='from rrgh_wif_credentials import token\n'


def augment(code):
    if REPLACEMENT in code:
        # The full migrated file is checked against the template derived from
        # the pinned predecessor, not accepted by an import substring alone.
        original=(ROOT/'.github/automation/source-templates/run_gorge_checkpoint_slot.py').read_text()
        if hashlib.sha256(original.encode()).hexdigest()!=BASE:raise ValueError('Credential baseline changed')
        expected=augment(original)
        if code!=expected:raise ValueError('Unreviewed credential code')
        return code
    if hashlib.sha256(code.encode()).hexdigest()!=BASE:raise ValueError('Unreviewed credential predecessor')
    start=code.index(START);end=code.index(END,start)
    return code[:start]+REPLACEMENT+code[end:]


def install(root):
    root=Path(root);path=root/TARGET
    code=augment(path.read_text())
    template=(ROOT/'.github/automation'/MODULE).read_bytes()
    target=root/'backend/scripts'/MODULE
    if target.exists():validate_module(target.read_bytes(),template)
    path.write_text(code);target.write_bytes(template)


def validate(root,original_code):
    root=Path(root)
    if (root/TARGET).read_text()!=augment(original_code):raise ValueError('Credential migration changed')
    if (root/'backend/scripts'/MODULE).read_bytes()!=(ROOT/'.github/automation'/MODULE).read_bytes():
        raise ValueError('Credential module is not reviewed template')


def validate_module(before,after):
    expected=(ROOT/'.github/automation'/MODULE).read_bytes()
    if after!=expected or (before!=after and hashlib.sha256(before).hexdigest()!=PREVIOUS_MODULE_SHA256):
        raise ValueError('Unreviewed credential module migration')
