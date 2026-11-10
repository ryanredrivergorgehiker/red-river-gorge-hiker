import pathlib, subprocess, sys, unittest

class MetadataImportTests(unittest.TestCase):
    def test_phase_authority_loads_before_image_dependencies_are_installed(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, '-S', '-c',
            "import sys; sys.path.insert(0, '.github/automation'); import rrgh_final_overviews as f; "
            "assert f.POLICY['remainingOverviewTiles'] == 691; assert 'PIL' not in sys.modules"],
            cwd=root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__': unittest.main()
