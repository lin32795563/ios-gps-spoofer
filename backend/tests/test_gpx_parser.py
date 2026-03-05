"""Tests for ios_gps_spoofer.simulation.gpx_parser module.

Tests cover:
- Valid GPX 1.1 with namespace (trkpt, rtept, wpt)
- Valid GPX without namespace
- GPX 1.0 namespace
- Multiple tracks and segments
- Malformed XML
- Empty content
- Missing lat/lon attributes
- Non-numeric lat/lon
- Out-of-range coordinates (skipped, not error)
- Empty waypoint lists
- File not found
- Encoding handling (UTF-8 and Latin-1)
"""


import pytest

from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.simulation.exceptions import GPXParseError
from ios_gps_spoofer.simulation.gpx_parser import parse_gpx_file, parse_gpx_string

# =====================================================================
# Valid GPX test data
# =====================================================================

_GPX_11_TRACK = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk>
    <name>Test Track</name>
    <trkseg>
      <trkpt lat="25.0330" lon="121.5654">
        <ele>10</ele>
      </trkpt>
      <trkpt lat="25.0340" lon="121.5664">
        <ele>12</ele>
      </trkpt>
      <trkpt lat="25.0350" lon="121.5674">
        <ele>15</ele>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""

_GPX_11_ROUTE = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <rte>
    <name>Test Route</name>
    <rtept lat="35.6762" lon="139.6503"/>
    <rtept lat="35.6772" lon="139.6513"/>
  </rte>
</gpx>
"""

_GPX_11_WAYPOINTS = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <wpt lat="48.8566" lon="2.3522">
    <name>Paris</name>
  </wpt>
  <wpt lat="51.5074" lon="-0.1278">
    <name>London</name>
  </wpt>
</gpx>
"""

_GPX_NO_NAMESPACE = """\
<?xml version="1.0"?>
<gpx version="1.1">
  <trk>
    <trkseg>
      <trkpt lat="10.0" lon="20.0"/>
      <trkpt lat="10.1" lon="20.1"/>
    </trkseg>
  </trk>
</gpx>
"""

_GPX_10_NAMESPACE = """\
<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/0" version="1.0">
  <trk>
    <trkseg>
      <trkpt lat="40.0" lon="-74.0"/>
      <trkpt lat="40.1" lon="-74.1"/>
    </trkseg>
  </trk>
</gpx>
"""

_GPX_MULTI_SEGMENT = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk>
    <trkseg>
      <trkpt lat="1.0" lon="1.0"/>
      <trkpt lat="2.0" lon="2.0"/>
    </trkseg>
    <trkseg>
      <trkpt lat="3.0" lon="3.0"/>
      <trkpt lat="4.0" lon="4.0"/>
    </trkseg>
  </trk>
</gpx>
"""

_GPX_TRACK_PREFERRED_OVER_ROUTE = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk>
    <trkseg>
      <trkpt lat="10.0" lon="10.0"/>
      <trkpt lat="20.0" lon="20.0"/>
    </trkseg>
  </trk>
  <rte>
    <rtept lat="30.0" lon="30.0"/>
    <rtept lat="40.0" lon="40.0"/>
  </rte>
</gpx>
"""


# =====================================================================
# Tests: parse_gpx_string with valid input
# =====================================================================

class TestParseValidGPX:
    """Tests for parsing well-formed GPX strings."""

    def test_gpx_11_track(self) -> None:
        coords = parse_gpx_string(_GPX_11_TRACK)
        assert len(coords) == 3
        assert coords[0] == Coordinate(latitude=25.0330, longitude=121.5654)
        assert coords[2] == Coordinate(latitude=25.0350, longitude=121.5674)

    def test_gpx_11_route(self) -> None:
        coords = parse_gpx_string(_GPX_11_ROUTE)
        assert len(coords) == 2
        assert coords[0] == Coordinate(latitude=35.6762, longitude=139.6503)

    def test_gpx_11_waypoints(self) -> None:
        coords = parse_gpx_string(_GPX_11_WAYPOINTS)
        assert len(coords) == 2
        assert coords[0] == Coordinate(latitude=48.8566, longitude=2.3522)

    def test_gpx_no_namespace(self) -> None:
        coords = parse_gpx_string(_GPX_NO_NAMESPACE)
        assert len(coords) == 2
        assert coords[0] == Coordinate(latitude=10.0, longitude=20.0)

    def test_gpx_10_namespace(self) -> None:
        coords = parse_gpx_string(_GPX_10_NAMESPACE)
        assert len(coords) == 2
        assert coords[0] == Coordinate(latitude=40.0, longitude=-74.0)

    def test_multi_segment(self) -> None:
        coords = parse_gpx_string(_GPX_MULTI_SEGMENT)
        assert len(coords) == 4
        assert coords[0] == Coordinate(latitude=1.0, longitude=1.0)
        assert coords[3] == Coordinate(latitude=4.0, longitude=4.0)

    def test_track_preferred_over_route(self) -> None:
        """Track points should be preferred when both tracks and routes exist."""
        coords = parse_gpx_string(_GPX_TRACK_PREFERRED_OVER_ROUTE)
        assert len(coords) == 2
        assert coords[0] == Coordinate(latitude=10.0, longitude=10.0)

    def test_all_coordinates_are_coordinate_instances(self) -> None:
        coords = parse_gpx_string(_GPX_11_TRACK)
        for coord in coords:
            assert isinstance(coord, Coordinate)

    def test_order_preserved(self) -> None:
        coords = parse_gpx_string(_GPX_11_TRACK)
        lats = [c.latitude for c in coords]
        assert lats == sorted(lats)  # our test data is sorted


# =====================================================================
# Tests: error handling
# =====================================================================

class TestParseErrors:
    """Tests for GPX parse error handling."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(GPXParseError, match="Empty GPX content"):
            parse_gpx_string("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(GPXParseError, match="Empty GPX content"):
            parse_gpx_string("   \n\t  ")

    def test_malformed_xml_raises(self) -> None:
        with pytest.raises(GPXParseError, match="Malformed XML"):
            parse_gpx_string("<gpx><unclosed")

    def test_not_xml_raises(self) -> None:
        with pytest.raises(GPXParseError, match="Malformed XML"):
            parse_gpx_string("this is not XML at all")

    def test_valid_xml_but_no_waypoints_raises(self) -> None:
        gpx = '<gpx xmlns="http://www.topografix.com/GPX/1/1"><metadata/></gpx>'
        with pytest.raises(GPXParseError, match="No waypoints found"):
            parse_gpx_string(gpx)

    def test_empty_track_segment_raises(self) -> None:
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg></trkseg></trk>
        </gpx>"""
        with pytest.raises(GPXParseError, match="No waypoints found"):
            parse_gpx_string(gpx)

    def test_source_included_in_error(self) -> None:
        with pytest.raises(GPXParseError) as exc_info:
            parse_gpx_string("", source="test.gpx")
        assert "test.gpx" in str(exc_info.value)


# =====================================================================
# Tests: invalid points (skipped, not error)
# =====================================================================

class TestInvalidPointsSkipped:
    """Points with bad lat/lon are skipped; the rest are still parsed."""

    def test_missing_lat_skipped(self) -> None:
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lon="121.0"/>
            <trkpt lat="25.0" lon="121.5"/>
            <trkpt lat="25.1" lon="121.6"/>
          </trkseg></trk>
        </gpx>"""
        coords = parse_gpx_string(gpx)
        assert len(coords) == 2

    def test_missing_lon_skipped(self) -> None:
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="25.0"/>
            <trkpt lat="25.0" lon="121.5"/>
            <trkpt lat="25.1" lon="121.6"/>
          </trkseg></trk>
        </gpx>"""
        coords = parse_gpx_string(gpx)
        assert len(coords) == 2

    def test_non_numeric_lat_skipped(self) -> None:
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="abc" lon="121.0"/>
            <trkpt lat="25.0" lon="121.5"/>
          </trkseg></trk>
        </gpx>"""
        coords = parse_gpx_string(gpx)
        assert len(coords) == 1

    def test_out_of_range_lat_skipped(self) -> None:
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="91.0" lon="121.0"/>
            <trkpt lat="25.0" lon="121.5"/>
          </trkseg></trk>
        </gpx>"""
        coords = parse_gpx_string(gpx)
        assert len(coords) == 1
        assert coords[0].latitude == 25.0

    def test_out_of_range_lon_skipped(self) -> None:
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="25.0" lon="181.0"/>
            <trkpt lat="25.0" lon="121.5"/>
          </trkseg></trk>
        </gpx>"""
        coords = parse_gpx_string(gpx)
        assert len(coords) == 1

    def test_all_points_invalid_raises(self) -> None:
        """If ALL points are invalid, should raise GPXParseError."""
        gpx = """\
        <gpx xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="abc" lon="def"/>
            <trkpt lat="91.0" lon="181.0"/>
          </trkseg></trk>
        </gpx>"""
        with pytest.raises(GPXParseError, match="No waypoints found"):
            parse_gpx_string(gpx)


# =====================================================================
# Tests: parse_gpx_file
# =====================================================================

class TestParseGPXFile:
    """Tests for file-based GPX parsing."""

    def test_valid_file(self, tmp_path: pytest.TempPathFactory) -> None:
        gpx_file = tmp_path / "test.gpx"  # type: ignore[operator]
        gpx_file.write_text(_GPX_11_TRACK, encoding="utf-8")
        coords = parse_gpx_file(str(gpx_file))
        assert len(coords) == 3

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_gpx_file("/nonexistent/path/to/file.gpx")

    def test_latin1_encoding(self, tmp_path: pytest.TempPathFactory) -> None:
        """GPX files with Latin-1 encoding should be handled."""
        gpx_content = '<?xml version="1.0"?>\n<gpx><trk><trkseg>\n'
        gpx_content += '<trkpt lat="25.0" lon="121.0"/>\n'
        gpx_content += '<trkpt lat="25.1" lon="121.1"/>\n'
        gpx_content += '</trkseg></trk></gpx>'

        gpx_file = tmp_path / "latin1.gpx"  # type: ignore[operator]
        gpx_file.write_bytes(gpx_content.encode("latin-1"))
        coords = parse_gpx_file(str(gpx_file))
        assert len(coords) == 2

    def test_path_object_accepted(self, tmp_path: pytest.TempPathFactory) -> None:
        from pathlib import Path

        gpx_file = tmp_path / "pathobj.gpx"  # type: ignore[operator]
        gpx_file.write_text(_GPX_NO_NAMESPACE, encoding="utf-8")
        coords = parse_gpx_file(Path(str(gpx_file)))
        assert len(coords) == 2
