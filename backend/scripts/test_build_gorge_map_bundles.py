import json
from pathlib import Path

import pytest
import build_gorge_map_bundles as bundles

from cached_cog_source import digest
from build_gorge_map_bundles import build, partition, part_size, PROFILE, safe_path, validate_regional


def groups(tmp_path, count=12):
    result={}
    for group,levels in PROFILE.items():
        result[group]=[]
        for i in range(count):
            layer=next(iter(levels));raw=(group+str(i)).encode()*500
            path=tmp_path/(group+str(i));path.write_bytes(raw)
            result[group].append({'path':f'tiles/{layer}/16/1/{i}.jpg','source':str(path),'bytes':len(raw),
                                  'sha256':digest(raw),'layer':layer,'z':16,'x':1,'y':i})
    return result


def test_actual_tar_caps_and_group_separation(tmp_path):
    data=groups(tmp_path);out=tmp_path/'out'
    report=build(data,out,'test',max_bytes=30720,max_entries=6)
    for group in PROFILE:
        index=json.loads((out/group/'MAP-BUNDLE.json').read_text())
        assert len(index['parts'])>1
        assert not index['regionalReady'] and index['required']==(group=='core')
        for part in index['parts']:
            assert part['byteCount']<=30720 and part['fileCount']<=6
            assert part['requiredEntitlement']=='base'
            assert part['packageType']=='offline_base'
            assert len(part['packageID'])<=128


def test_unchanged_parts_reused_across_release_versions(tmp_path):
    data=groups(tmp_path);a=tmp_path/'one';b=tmp_path/'two'
    build(data,a,'v1',max_bytes=30720);build(data,b,'v2',max_bytes=30720)
    for group in PROFILE:
        aa=json.loads((a/group/'MAP-BUNDLE.json').read_text());bb=json.loads((b/group/'MAP-BUNDLE.json').read_text())
        assert aa['release']!=bb['release']
        assert aa['parts']==bb['parts']


def test_completed_parts_resume_without_repacking_and_reject_corruption(tmp_path,monkeypatch):
    data=groups(tmp_path);out=tmp_path/'resume'
    first=build(data,out,'v1')
    def no_repack(*args,**kwargs):raise AssertionError('Completed archive was repacked')
    monkeypatch.setattr(bundles.tarfile,'open',no_repack)
    assert build(data,out,'v1')==first
    next((out/'core').glob('*.rrghpkg')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='integrity'):build(data,out,'v1')


@pytest.mark.parametrize('path',['../x','/x','x//y','x/./y','x\\y','x/../../y'])
def test_path_rejection(path):
    with pytest.raises(ValueError):safe_path(path)


def test_corruption_and_duplicate_members_fail_closed(tmp_path):
    data=groups(tmp_path);data['core'].append(data['core'][0])
    with pytest.raises(ValueError,match='Duplicate'):build(data,tmp_path/'duplicate','v1')
    data['core'].pop();Path(data['core'][0]['source']).write_bytes(b'bad')
    with pytest.raises(ValueError,match='hash'):build(data,tmp_path/'corrupt','v1')


def test_aerial_cannot_become_required_core(tmp_path):
    data=groups(tmp_path);data['core'].append(data['leaf-on'][0])
    with pytest.raises(ValueError,match='Layer'):build(data,tmp_path/'mixed','v1')


def test_benchmark_not_promoted_as_regional_coverage(tmp_path):
    data=groups(tmp_path)
    with pytest.raises(ValueError,match='coverage'):build(data,tmp_path/'regional','v1',scope='regional')


def test_single_file_over_budget_is_not_silently_oversized(tmp_path):
    data=groups(tmp_path,1)
    entry=data['core'][0];raw=b'x'*20000
    Path(entry['source']).write_bytes(raw);entry.update(bytes=len(raw),sha256=digest(raw))
    with pytest.raises(ValueError,match='exceeds'):partition('core',data['core'],max_bytes=10240)


def test_catalog_candidates_require_complete_governed_sources(tmp_path):
    data=groups(tmp_path)
    with pytest.raises(ValueError,match='provenance'):
        build(data,tmp_path/'incomplete','v1',provenance={})
    fields=('sourceID','sourceURL','provider','vintageOrRetrievedAt','areaOfInterestOrSourceObjects',
            'processingMethod','rightsBasis','attributionOrDisclaimer','outputVersion','integritySHA256')
    provenance={g:[dict.fromkeys(fields,'test-source')] for g in PROFILE}
    out=tmp_path/'governed';build(data,out,'v1',provenance=provenance)
    for g in PROFILE:
        index=json.loads((out/g/'MAP-BUNDLE.json').read_text())
        assert index['provenanceComplete']
        for part in index['parts']:
            candidate=json.loads((out/g/(part['sha256']+'.catalog-candidate.json')).read_text())
            assert not candidate['active'] and not candidate['contentReady']
            assert candidate['offlineManifest']['sha256']==part['sha256']
            assert candidate['offlineManifest']['sources']==provenance[g]
