"""Defensive VAST and VMAP XML parsing."""

from __future__ import annotations

from xml.etree import ElementTree

from fastapi import HTTPException, status

from app.modules.monetization.schemas import VastCreative, VastMediaFile, VmapAdBreak

MAX_XML_BYTES = 256_000
TRACKING_EVENTS = {"start", "firstQuartile", "midpoint", "thirdQuartile", "complete"}


def _reject_unsafe_xml(xml_text: str) -> None:
    if len(xml_text.encode("utf-8")) > MAX_XML_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"code": "xml_too_large"})
    lowered = xml_text[:4096].lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "unsafe_xml_rejected"})


def _parse_xml(xml_text: str) -> ElementTree.Element:
    _reject_unsafe_xml(xml_text)
    try:
        return ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "malformed_ad_xml"}) from exc


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in element.iter() if _local_name(child.tag) == name]


def _text(element: ElementTree.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def parse_duration(value: str | None) -> float:
    if not value:
        return 0
    parts = value.strip().split(":")
    if len(parts) != 3:
        return 0
    hours, minutes, seconds = parts
    try:
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return 0


def parse_vast(xml_text: str) -> list[VastCreative]:
    root = _parse_xml(xml_text)
    if _local_name(root.tag) != "VAST":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_vast_document"})

    impressions = [_text(element) for element in _children(root, "Impression")]
    error_urls = [_text(element) for element in _children(root, "Error")]
    parsed_impressions = [value for value in impressions if value]
    parsed_errors = [value for value in error_urls if value]

    creatives: list[VastCreative] = []
    for creative in _children(root, "Creative"):
        duration = parse_duration(_text(next(iter(_children(creative, "Duration")), None)))
        media_files = [
            VastMediaFile(
                url=value,
                mime_type=media.attrib.get("type"),
                width=int(media.attrib["width"]) if media.attrib.get("width", "").isdigit() else None,
                height=int(media.attrib["height"]) if media.attrib.get("height", "").isdigit() else None,
            )
            for media in _children(creative, "MediaFile")
            if (value := _text(media))
        ]
        tracking: dict[str, list[str]] = {event: [] for event in TRACKING_EVENTS}
        for tracking_node in _children(creative, "Tracking"):
            event = tracking_node.attrib.get("event", "")
            url = _text(tracking_node)
            if event in TRACKING_EVENTS and url:
                tracking[event].append(url)
        if media_files and duration > 0:
            creatives.append(
                VastCreative(
                    duration_seconds=duration,
                    media_files=media_files,
                    impressions=parsed_impressions,
                    tracking={event: urls for event, urls in tracking.items() if urls},
                    errors=parsed_errors,
                )
            )
    if not creatives:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "vast_creative_not_found"})
    return creatives


def parse_vmap(xml_text: str) -> list[VmapAdBreak]:
    root = _parse_xml(xml_text)
    if _local_name(root.tag) != "VMAP":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_vmap_document"})

    breaks: list[VmapAdBreak] = []
    for ad_break in _children(root, "AdBreak"):
        vast_data = next(iter(_children(ad_break, "VASTData")), None)
        ad_tag = next(iter(_children(ad_break, "AdTagURI")), None)
        breaks.append(
            VmapAdBreak(
                time_offset=ad_break.attrib.get("timeOffset", "start"),
                break_id=ad_break.attrib.get("breakId") or f"break-{len(breaks) + 1}",
                break_type=ad_break.attrib.get("breakType") or "linear",
                vast_ad_data=ElementTree.tostring(vast_data, encoding="unicode") if vast_data is not None else None,
                ad_tag_uri=_text(ad_tag),
            )
        )
    if not breaks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "vmap_ad_break_not_found"})
    return breaks
