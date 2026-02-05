#!/usr/bin/env python3
"""Smart short-video template renderer inspired by OpusClip-style presets.

This script builds a fixed, reusable editing template so each new video only
needs source media + text content. It uses FFmpeg under the hood.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaptionLine:
    start: float
    end: float
    text: str


def run(cmd: list[str]) -> None:
    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
        )


def probe_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Unable to probe duration: {result.stderr}")
    return float(result.stdout.strip())


def parse_captions_file(path: Path, fallback_duration: float) -> list[CaptionLine]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        lines = []
        for item in raw:
            lines.append(
                CaptionLine(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    text=str(item["text"]).strip(),
                )
            )
        return lines

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # TXT mode: each non-empty line becomes a caption chunk distributed
    # uniformly across video duration.
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    if not rows:
        return []

    chunk = fallback_duration / len(rows)
    lines = []
    for idx, row in enumerate(rows):
        start = idx * chunk
        end = min(fallback_duration, (idx + 1) * chunk)
        lines.append(CaptionLine(start=start, end=end, text=row))
    return lines


def ass_escape(text: str) -> str:
    escaped = text.replace("\\", r"\\")
    escaped = escaped.replace("{", r"\{").replace("}", r"\}")
    return escaped


def seconds_to_ass_time(value: float) -> str:
    value = max(0.0, value)
    h = int(value // 3600)
    m = int((value % 3600) // 60)
    s = int(value % 60)
    cs = int(round((value - math.floor(value)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def hex_to_ass_bgr(color_hex: str) -> str:
    c = color_hex.strip().lstrip("#")
    if len(c) != 6:
        raise ValueError(f"Invalid color: {color_hex}")
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b}{g}{r}"


def build_ass(template: dict[str, Any], captions: list[CaptionLine], ass_path: Path) -> None:
    style = template["text_style"]
    effects = template["text_effects"]

    alignment_map = {
        "bottom_center": 2,
        "middle_center": 5,
        "top_center": 8,
    }
    alignment = alignment_map.get(style.get("position", "bottom_center"), 2)

    margin_v = int(style.get("margin_v", 120))
    font_size = int(style.get("font_size", 64))
    outline = float(style.get("outline", 4))
    shadow = float(style.get("shadow", 2))

    primary = hex_to_ass_bgr(style.get("primary_color", "#FFFFFF"))
    secondary = hex_to_ass_bgr(style.get("secondary_color", "#FFD447"))
    outline_color = hex_to_ass_bgr(style.get("outline_color", "#000000"))

    fade_in = int(effects.get("fade_in_ms", 160))
    fade_out = int(effects.get("fade_out_ms", 180))
    pop = bool(effects.get("pop_in", True))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{style.get("font_family", "Montserrat ExtraBold")},{font_size},{primary},{secondary},{outline_color},&H64000000,{-1 if style.get("bold", True) else 0},{-1 if style.get("italic", False) else 0},0,0,100,100,0,0,1,{outline},{shadow},{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    rows: list[str] = [header]
    for line in captions:
        tags = [f"\\fad({fade_in},{fade_out})"]
        if pop:
            tags.append(r"\fscx92\fscy92\t(0,180,\fscx100\fscy100)")
        tag_blob = "{" + "".join(tags) + "}"
        text = ass_escape(line.text.upper())
        rows.append(
            "Dialogue: 0,"
            f"{seconds_to_ass_time(line.start)},"
            f"{seconds_to_ass_time(line.end)},"
            f"Main,,0,0,0,,{tag_blob}{text}\n"
        )

    ass_path.write_text("".join(rows), encoding="utf-8")


def build_filter(template: dict[str, Any], ass_path: Path) -> str:
    canvas = template["canvas"]
    vfx = template["video_effects"]
    target_w = int(canvas.get("width", 1080))
    target_h = int(canvas.get("height", 1920))

    saturation = float(vfx.get("saturation", 1.15))
    contrast = float(vfx.get("contrast", 1.05))
    brightness = float(vfx.get("brightness", 0.01))
    blur_strength = float(vfx.get("background_blur", 22))
    zoom_strength = float(vfx.get("foreground_zoom_strength", 0.03))

    escaped_ass = str(ass_path).replace("\\", r"\\").replace(":", r"\:")

    # Two-layer portrait layout:
    # 1) blurred full-frame background
    # 2) sharp foreground center crop + subtle animated zoom
    return (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},gblur=sigma={blur_strength}[bg];"
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
        f"scale='iw*(1+{zoom_strength}*sin(t*1.4))':'ih*(1+{zoom_strength}*sin(t*1.4))':eval=frame,"
        f"crop={target_w}:{target_h}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"eq=saturation={saturation}:contrast={contrast}:brightness={brightness},"
        f"subtitles='{escaped_ass}'[v]"
    )


def render_video(
    input_video: Path,
    output_video: Path,
    template: dict[str, Any],
    captions: list[CaptionLine],
) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed or not in PATH")

    with tempfile.TemporaryDirectory(prefix="video-template-") as tmp_dir:
        ass_path = Path(tmp_dir) / "captions.ass"
        build_ass(template, captions, ass_path)
        vf = build_filter(template, ass_path)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-filter_complex",
            vf,
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(template.get("encoding", {}).get("crf", 19)),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
        run(cmd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a reusable smart editing template to short-form videos."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input video file")
    parser.add_argument("--output", required=True, type=Path, help="Output video file")
    parser.add_argument(
        "--template",
        required=True,
        type=Path,
        help="Template JSON describing text style + video effects",
    )
    parser.add_argument(
        "--captions",
        required=True,
        type=Path,
        help="Caption source (.json with timing, or .txt for auto timing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    template = json.loads(args.template.read_text(encoding="utf-8"))
    duration = probe_duration(args.input)
    captions = parse_captions_file(args.captions, duration)
    if not captions:
        raise RuntimeError("No captions found. Please provide non-empty caption input.")

    render_video(args.input, args.output, template, captions)
    print(f"✅ Rendered template video: {args.output}")


if __name__ == "__main__":
    main()
