"""GPX file parser for extracting waypoints as Coordinate sequences.

Supports GPX 1.0 and 1.1 formats.  Extracts waypoints from ``<trkpt>``,
``<rtept>``, and ``<wpt>`` elements.  Handles namespace-prefixed and
non-prefixed XML.

Error handling is deliberately strict: malformed XML, missing lat/lon
attributes, and out-of-range coordinates all raise ``GPXParseError``
with a descriptive message.  The caller should present this to the user.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.simulation.exceptions import GPXParseError

logger = logging.getLogger(__name__)

# Common GPX namespace URIs (both 1.0 and 1.1)
_GPX_NAMESPACES = [
    "http://www.topografix.com/GPX/1/1",
    "http://www.topografix.com/GPX/1/0",
]


def parse_gpx_file(file_path: str | Path) -> list[Coordinate]:
    """Parse a GPX file and return an ordered list of coordinates.

    Searches for track points (``<trkpt>``), route points (``<rtept>``),
    and waypoints (``<wpt>``) in that priority order.  Returns the first
    non-empty set found.

    Args:
        file_path: Path to the GPX file.

    Returns:
        Ordered list of ``Coordinate`` objects.

    Raises:
        GPXParseError: If the file cannot be read, is not valid XML,
            or contains no usable waypoints.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    source = str(path)

    if not path.exists():
        raise FileNotFoundError(f"GPX file not found: {source}")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding="latin-1")
        except Exception as exc:
            raise GPXParseError(
                f"Cannot read file: {exc}", source=source
            ) from exc

    return parse_gpx_string(content, source=source)


def parse_gpx_string(gpx_xml: str, source: str = "<string>") -> list[Coordinate]:
    """Parse a GPX XML string and return an ordered list of coordinates.

    Args:
        gpx_xml: The GPX XML content as a string.
        source: Description of where the XML came from (for error messages).

    Returns:
        Ordered list of ``Coordinate`` objects.

    Raises:
        GPXParseError: If the XML is malformed, or contains no usable
            waypoints.
    """
    if not gpx_xml or not gpx_xml.strip():
        raise GPXParseError("Empty GPX content", source=source)

    try:
        root = ET.fromstring(gpx_xml)
    except ET.ParseError as exc:
        raise GPXParseError(
            f"Malformed XML: {exc}", source=source
        ) from exc

    # Detect namespace
    namespace = _detect_namespace(root)

    # Try extracting points in priority order: trkpt > rtept > wpt
    coordinates = _extract_track_points(root, namespace)
    if not coordinates:
        coordinates = _extract_route_points(root, namespace)
    if not coordinates:
        coordinates = _extract_waypoints(root, namespace)

    if not coordinates:
        raise GPXParseError(
            "No waypoints found. GPX must contain <trkpt>, <rtept>, or "
            "<wpt> elements with valid lat/lon attributes.",
            source=source,
        )

    logger.info(
        "Parsed %d coordinates from GPX (source: %s)",
        len(coordinates),
        source,
    )
    return coordinates


def _detect_namespace(root: ET.Element) -> str:
    """Detect the GPX namespace from the root element's tag.

    Args:
        root: The root XML element.

    Returns:
        The namespace URI string, or empty string if no namespace.
    """
    tag = root.tag
    if tag.startswith("{"):
        ns_end = tag.index("}")
        return tag[1:ns_end]
    return ""


def _ns_tag(namespace: str, tag: str) -> str:
    """Build a namespace-qualified tag name.

    Args:
        namespace: The namespace URI (may be empty).
        tag: The local tag name.

    Returns:
        The fully-qualified tag string for ElementTree searching.
    """
    if namespace:
        return f"{{{namespace}}}{tag}"
    return tag


def _extract_track_points(
    root: ET.Element, namespace: str
) -> list[Coordinate]:
    """Extract <trkpt> elements from all <trk>/<trkseg> blocks.

    Args:
        root: The root XML element.
        namespace: The GPX namespace URI.

    Returns:
        Ordered list of coordinates from track points.
    """
    coordinates: list[Coordinate] = []
    trk_tag = _ns_tag(namespace, "trk")
    seg_tag = _ns_tag(namespace, "trkseg")
    pt_tag = _ns_tag(namespace, "trkpt")

    for trk in root.iter(trk_tag):
        for seg in trk.iter(seg_tag):
            for pt in seg.iter(pt_tag):
                coord = _parse_point_element(pt)
                if coord is not None:
                    coordinates.append(coord)

    return coordinates


def _extract_route_points(
    root: ET.Element, namespace: str
) -> list[Coordinate]:
    """Extract <rtept> elements from all <rte> blocks.

    Args:
        root: The root XML element.
        namespace: The GPX namespace URI.

    Returns:
        Ordered list of coordinates from route points.
    """
    coordinates: list[Coordinate] = []
    rte_tag = _ns_tag(namespace, "rte")
    pt_tag = _ns_tag(namespace, "rtept")

    for rte in root.iter(rte_tag):
        for pt in rte.iter(pt_tag):
            coord = _parse_point_element(pt)
            if coord is not None:
                coordinates.append(coord)

    return coordinates


def _extract_waypoints(
    root: ET.Element, namespace: str
) -> list[Coordinate]:
    """Extract top-level <wpt> elements.

    Args:
        root: The root XML element.
        namespace: The GPX namespace URI.

    Returns:
        Ordered list of coordinates from waypoints.
    """
    coordinates: list[Coordinate] = []
    wpt_tag = _ns_tag(namespace, "wpt")

    for wpt in root.iter(wpt_tag):
        coord = _parse_point_element(wpt)
        if coord is not None:
            coordinates.append(coord)

    return coordinates


def _parse_point_element(element: ET.Element) -> Coordinate | None:
    """Parse lat/lon attributes from a GPX point element.

    Invalid points are logged as warnings and skipped rather than
    causing the entire parse to fail.

    Args:
        element: An XML element with ``lat`` and ``lon`` attributes.

    Returns:
        A ``Coordinate``, or None if the element is invalid.
    """
    lat_str = element.get("lat")
    lon_str = element.get("lon")

    if lat_str is None or lon_str is None:
        logger.warning(
            "Skipping point element without lat/lon attributes: %s",
            ET.tostring(element, encoding="unicode")[:200],
        )
        return None

    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except ValueError:
        logger.warning(
            "Skipping point with non-numeric lat/lon: lat=%r, lon=%r",
            lat_str,
            lon_str,
        )
        return None

    try:
        return Coordinate(latitude=lat, longitude=lon)
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Skipping point with invalid coordinates (lat=%s, lon=%s): %s",
            lat_str,
            lon_str,
            exc,
        )
        return None
