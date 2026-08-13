"""Defensive VAST 4.x and VMAP 1.0 XML parser with XXE protection."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

from app.modules.monetization.schemas import VASTAdData, VASTMediaFile, VASTTrackingUrl, VMAPAdBreakData


class VASTVMAPParserError(ValueError):
    """Exception raised when VAST or VMAP XML is malformed or contains unsafe entities."""


def safe_parse_xml(xml_content: str) -> ET.Element:
    """Parse XML string defensively, raising VASTVMAPParserError on entity expansion or syntax errors."""
    if not xml_content or not xml_content.strip():
        raise VASTVMAPParserError("Empty XML content")

    # Reject explicit DTD entity expansion declarations
    if "<!ENTITY" in xml_content or "<!DOCTYPE" in xml_content:
        raise VASTVMAPParserError("Unsafe XML entity declaration detected (XXE protection)")

    try:
        root = ET.fromstring(xml_content)
        return root
    except (ET.ParseError, ExpatError, Exception) as exc:
        raise VASTVMAPParserError(f"XML parse failure: {exc}") from exc


def parse_vast_xml(xml_content: str) -> list[VASTAdData]:
    """Parse VAST 2.0-4.x XML string and return list of extracted VASTAdData items."""
    root = safe_parse_xml(xml_content)
    ads: list[VASTAdData] = []

    # Strip XML namespace if present
    def clean_tag(elem: ET.Element) -> str:
        return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    ad_elements = [elem for elem in root.iter() if clean_tag(elem) == "Ad"]
    if not ad_elements and clean_tag(root) == "Ad":
        ad_elements = [root]

    for ad_elem in ad_elements:
        ad_id = ad_elem.attrib.get("id", "ad_1")
        title = ""
        duration_seconds = 15.0
        media_files: list[VASTMediaFile] = []
        impression_urls: list[str] = []
        tracking_urls: list[VASTTrackingUrl] = []

        for elem in ad_elem.iter():
            tag = clean_tag(elem)

            if tag == "AdTitle" and elem.text:
                title = elem.text.strip()
            elif tag == "Duration" and elem.text:
                parts = elem.text.strip().split(":")
                try:
                    if len(parts) == 3:
                        duration_seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    elif len(parts) == 2:
                        duration_seconds = float(parts[0]) * 60 + float(parts[1])
                except ValueError:
                    duration_seconds = 15.0
            elif tag == "Impression" and elem.text and elem.text.strip():
                impression_urls.append(elem.text.strip())
            elif tag == "Tracking" and elem.text and elem.text.strip():
                event = elem.attrib.get("event", "custom")
                tracking_urls.append(VASTTrackingUrl(event=event, url=elem.text.strip()))
            elif tag == "MediaFile" and elem.text and elem.text.strip():
                media_files.append(
                    VASTMediaFile(
                        url=elem.text.strip(),
                        delivery=elem.attrib.get("delivery", "progressive"),
                        type=elem.attrib.get("type", "video/mp4"),
                        width=int(elem.attrib.get("width", 1920)),
                        height=int(elem.attrib.get("height", 1080)),
                        bitrate=int(elem.attrib.get("bitrate", 2500)),
                    )
                )

        if media_files or impression_urls:
            ads.append(
                VASTAdData(
                    ad_id=ad_id,
                    title=title or f"Ad {ad_id}",
                    duration_seconds=duration_seconds,
                    media_files=media_files,
                    impression_urls=impression_urls,
                    tracking_urls=tracking_urls,
                )
            )

    if not ads:
        raise VASTVMAPParserError("No valid video Ad entries found in VAST document")

    return ads


def parse_vmap_xml(xml_content: str) -> list[VMAPAdBreakData]:
    """Parse VMAP 1.0 XML string and return list of VMAPAdBreakData items."""
    root = safe_parse_xml(xml_content)
    breaks: list[VMAPAdBreakData] = []

    def clean_tag(elem: ET.Element) -> str:
        return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    break_elements = [elem for elem in root.iter() if clean_tag(elem) == "AdBreak"]
    for break_elem in break_elements:
        break_id = break_elem.attrib.get("breakId", f"break_{len(breaks) + 1}")
        time_offset = break_elem.attrib.get("timeOffset", "00:00:00")
        break_type = break_elem.attrib.get("breakType", "linear")

        # Parse inline VAST if embedded
        vast_ad = None
        vast_elem = None
        for child in break_elem.iter():
            if clean_tag(child) == "VAST":
                vast_elem = child
                break

        if vast_elem is not None:
            vast_str = ET.tostring(vast_elem, encoding="utf-8").decode("utf-8")
            try:
                vast_ads = parse_vast_xml(vast_str)
                if vast_ads:
                    vast_ad = vast_ads[0]
            except VASTVMAPParserError:
                pass

        breaks.append(
            VMAPAdBreakData(
                break_id=break_id,
                time_offset=time_offset,
                break_type=break_type,
                vast_ad=vast_ad,
            )
        )

    if not breaks:
        raise VASTVMAPParserError("No valid AdBreak entries found in VMAP document")

    return breaks
