import pytest

from specfast import extract


def test_stages_not_implemented_point_to_design():
    with pytest.raises(NotImplementedError, match="DESIGN.md"):
        extract.extract_frame(None, None, {}, None)
