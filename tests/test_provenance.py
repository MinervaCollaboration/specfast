import hashlib

from specfast import __version__
from specfast.provenance import Provenance, sha256_file


def test_record_round_trip(tmp_path):
    f = tmp_path / "in.dat"
    f.write_bytes(b"abc" * 1000)
    p = Provenance.create("test", config_sha256="0" * 64, inputs={"raw": f})
    assert p.package_version == __version__
    assert p.inputs[0].sha256 == hashlib.sha256(b"abc" * 1000).hexdigest()
    assert sha256_file(f) == p.inputs[0].sha256
    assert Provenance.from_json(p.to_json()) == p
