import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "ecoservice_waste_collection"


def test_hacs_manifest_is_minimal_and_lithuanian():
    assert json.loads((ROOT / "hacs.json").read_text(encoding="utf-8")) == {
        "name": "Waste Collection Ecoservice Lithuania",
        "country": "LT",
    }


def test_manifest_order_and_versions_match():
    manifest = json.loads(
        (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8"),
        object_pairs_hook=dict,
    )
    assert list(manifest) == [
        "domain",
        "name",
        "codeowners",
        "config_flow",
        "documentation",
        "integration_type",
        "iot_class",
        "issue_tracker",
        "version",
    ]
    const_text = (INTEGRATION_DIR / "const.py").read_text(encoding="utf-8")
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^VERSION = "([^\"]+)"$', const_text, re.MULTILINE).group(1) == manifest["version"]
    assert re.search(r'^version = "([^\"]+)"$', pyproject_text, re.MULTILINE).group(1) == manifest["version"]


def test_brand_icons_have_required_png_dimensions():
    for filename, expected_size in (("icon.png", 256), ("icon@2x.png", 512)):
        payload = (INTEGRATION_DIR / "brand" / filename).read_bytes()
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", payload[16:24])
        assert (width, height) == (expected_size, expected_size)
