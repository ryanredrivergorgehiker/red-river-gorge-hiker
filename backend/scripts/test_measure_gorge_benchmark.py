import io
import tarfile

from measure_gorge_benchmark import archive_bytes, storage_model, tile_counts


def test_padding_matches_real_ustar_for_boundary_sizes():
    for sizes in [[], [0], [1, 511, 512, 513], [8192, 8193], [10240] * 15]:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for n, size in enumerate(sizes):
                info = tarfile.TarInfo(str(n)); info.size = size
                tar.addfile(info, io.BytesIO(bytes(size)))
        assert len(buf.getvalue()) == archive_bytes(sizes)


def test_iphone_retained_archive_staging_and_rollback_accounting():
    m = storage_model(100, 80, [(90, 70), (85, 65)])
    assert m["downloadBytes"] == 100
    assert m["installedLogicalBytes"] == 180
    assert m["cleanInstallPeakLogicalBytes"] == 280
    assert m["updatePeakLogicalBytes"] == 590
    assert m["steadyWithOneRollbackLogicalBytes"] == 340
    assert m["freeSpacePreflightAfterStagingBytes"] == 200
    assert not m["physicalIPhoneStorageMeasured"]


def test_regional_grid_matches_prior_authoritative_audit():
    counts = tile_counts()
    assert sum(r["tileCount"] for r in counts if r["zoom"] <= 16) == 6950
    assert next(r["tileCount"] for r in counts if r["zoom"] == 16) == 5180
