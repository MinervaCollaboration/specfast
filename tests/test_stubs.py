import pytest

from specfast import combine, extract


def test_stages_not_implemented_point_to_design():
    with pytest.raises(NotImplementedError, match="DESIGN.md"):
        extract.extract_frame(None, None, {}, None)
    with pytest.raises(NotImplementedError, match="DESIGN.md"):
        combine.combine(None)
