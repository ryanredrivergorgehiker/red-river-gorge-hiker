"""Regression coverage for the actual GNU-tar layout, entirely offline."""
import contextlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from gorge_checkpoint import digest
from gorge_stage_inputs import base_member_index, extract_base_inputs, BaseValidationError


class AcceptedBaseTarTests(unittest.TestCase):
    def archive(self, entries):
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w') as t:
            for name,kind in entries:
                m=tarfile.TarInfo(name);m.type=kind
                if kind==tarfile.REGTYPE:m.size=2
                if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE):m.linkname='../outside'
                t.addfile(m,io.BytesIO(b'{}') if m.isfile() else None)
        raw.seek(0);return tarfile.open(fileobj=raw,mode='r:')

    def test_deployed_gnu_tar_dot_root_full_input_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);root=p/'root';root.mkdir()
            vector=b'{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[-83.6,37.8]},"properties":{}}]}'
            weather=b'{"products":[]}'
            (root/'vector.geojson').write_bytes(vector);(root/'weather.json').write_bytes(weather)
            manifest={'packageID':'gorge-base','packageVersion':'2026.10.08.1','schemaVersion':3,
                'vectors':[{'id':'test-fixture','path':'vector.geojson','sha256':digest(vector)}],
                'weatherManifest':{'path':'weather.json','sha256':digest(weather)},'staticAssets':[]}
            (root/'NATIVE-MAP.json').write_text(json.dumps(manifest))
            archive=p/'accepted.rrghpkg'
            subprocess.run(['tar','--sort=name','--mtime=UTC 2026-10-07 00:00:00','--owner=0','--group=0','--numeric-owner','-cf',str(archive),'-C',str(root),'.'],check=True)
            with tarfile.open(archive) as t:self.assertIn('./NATIVE-MAP.json',t.getnames())
            with contextlib.redirect_stdout(io.StringIO()):result=extract_base_inputs(archive,p/'extracted')
            self.assertEqual(result['vectorFeatures'],1)
            self.assertEqual((p/'extracted/vector.geojson').read_bytes(),vector)

    def test_existing_plain_member_layout_still_supported(self):
        with self.archive([('NATIVE-MAP.json',tarfile.REGTYPE)]) as t:
            self.assertEqual(set(base_member_index(t)),{'NATIVE-MAP.json'})

    def test_alias_collision_rejected(self):
        with self.archive([('NATIVE-MAP.json',tarfile.REGTYPE),('./NATIVE-MAP.json',tarfile.REGTYPE)]) as t:
            with self.assertRaisesRegex(BaseValidationError,'base-archive-duplicate'):base_member_index(t)

    def test_unsafe_paths_rejected(self):
        for name in ('../escape','./../escape','/absolute','././nested','folder/../escape','folder//file','folder\\file'):
            with self.subTest(name=name),self.archive([(name,tarfile.REGTYPE)]) as t:
                with self.assertRaisesRegex(BaseValidationError,'base-archive-path'):base_member_index(t)

    def test_links_and_devices_rejected_including_unused_members(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.FIFOTYPE):
            with self.subTest(kind=kind),self.archive([('./unused',kind)]) as t:
                with self.assertRaisesRegex(BaseValidationError,'base-archive-type'):base_member_index(t)

    def test_directory_file_alias_collision_rejected(self):
        with self.archive([('./path',tarfile.DIRTYPE),('path',tarfile.REGTYPE)]) as t:
            with self.assertRaisesRegex(BaseValidationError,'base-archive-duplicate'):base_member_index(t)

    def test_missing_manifest_has_safe_finite_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);archive=p/'missing.tar'
            with tarfile.open(archive,'w'):pass
            with self.assertRaisesRegex(BaseValidationError,'base-required-member'):extract_base_inputs(archive,p/'out')


if __name__=='__main__':unittest.main()
