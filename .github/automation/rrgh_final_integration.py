"""Install exact final-overview helpers and narrowly scoped edge verification."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MODULES=('rrgh_overview_coverage.py','rrgh_seed_children.py','rrgh_final_overviews.py',
    'rrgh_final_dependencies.py','rrgh_final_overview_render.py','rrgh_final_overview_runtime.py')
COORDINATOR='gorge_stage_coordinator.py'
ORIGINAL='8fde5081ac604de9d6ab65b44fbd37f5c2ffa66bde8de32b8b805d6da107bac7'
REVIEWED='3f1be57e6ee69a376a8637c2788481910a76bcb6ea2bdae1aa94da0b6991e1a7'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)

def coordinator():
    raw=(ROOT/'.github/automation/source-templates'/COORDINATOR).read_bytes()
    require(digest(raw)==REVIEWED,'Final coverage verifier template changed')
    return raw

def install(root):
    scripts=Path(root)/'backend/scripts'
    target=scripts/COORDINATOR
    require(digest(target.read_bytes()) in (ORIGINAL,REVIEWED),'Unreviewed coverage verifier predecessor')
    target.write_bytes(coordinator())
    for name in MODULES:
        raw=(ROOT/'.github/automation'/name).read_bytes();target=scripts/name
        require(not target.exists() or target.read_bytes()==raw,'Unreviewed final helper transition')
        target.write_bytes(raw)

def validate(root,previous_coordinator=None):
    scripts=Path(root)/'backend/scripts'
    require((scripts/COORDINATOR).read_bytes()==coordinator(),'Final output coverage verifier differs')
    if previous_coordinator is not None:
        require(digest(previous_coordinator) in (ORIGINAL,REVIEWED),'Unreviewed prior output verifier')
    for name in MODULES:
        require((scripts/name).read_bytes()==(ROOT/'.github/automation'/name).read_bytes(),'Final helper differs: '+name)
