#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TIMESTAMP_RE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3})\s+-->\s+(?P<end>(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3})"
)
HOME = Path.home()
COMMON_ENV_ROOTS = (
    HOME / ".venvs",
    HOME / ".virtualenvs",
    HOME / "venvs",
    HOME / "miniconda3" / "envs",
    HOME / "anaconda3" / "envs",
    HOME / "mambaforge" / "envs",
    HOME / "micromamba" / "envs",
)


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str
    words: list[dict] | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Local subtitle workflow helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local runtime dependencies.")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable diagnostics.")
    doctor.add_argument("--probe", action="store_true", help="Probe nearby Python interpreters for faster-whisper.")

    models = sub.add_parser("models", help="List locally cached faster-whisper model variants.")
    models.add_argument("--json", action="store_true", help="Print machine-readable model list.")

    transcribe = sub.add_parser("transcribe", help="Transcribe media with faster-whisper.")
    transcribe.add_argument("input", type=Path)
    transcribe.add_argument("--output-dir", type=Path, default=None)
    transcribe.add_argument("--model", default="base")
    transcribe.add_argument("--device", default="cpu")
    transcribe.add_argument("--language", default="auto")
    transcribe.add_argument("--format", choices=["srt", "vtt", "both"], default="both")

    validate = sub.add_parser("validate", help="Validate .srt, .vtt, or segments.json.")
    validate.add_argument("input", type=Path)

    audit = sub.add_parser("audit", help="Report subtitle readability risks.")
    audit.add_argument("input", type=Path)
    audit.add_argument("--max-width", type=int, default=42)
    audit.add_argument("--severe-width", type=int, default=60)
    audit.add_argument("--max-han-chars", type=int, default=20)
    audit.add_argument("--severe-han-chars", type=int, default=24)
    audit.add_argument("--max-cps", type=float, default=20.0)
    audit.add_argument("--min-duration", type=float, default=1.0)
    audit.add_argument("--max-duration", type=float, default=6.0)
    audit.add_argument("--json", action="store_true", help="Print machine-readable audit output.")

    convert = sub.add_parser("convert", help="Convert .srt, .vtt, or segments.json to normalized segments.json.")
    convert.add_argument("input", type=Path)
    convert.add_argument("--output", type=Path, required=True)

    export = sub.add_parser("export", help="Export segments.json to SRT or VTT.")
    export.add_argument("input", type=Path)
    export.add_argument("--format", choices=["srt", "vtt"], required=True)
    export.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "models":
        return cmd_models(args)
    if args.command == "transcribe":
        return cmd_transcribe(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "convert":
        return cmd_convert(args)
    if args.command == "export":
        return cmd_export(args)
    return 2


def cmd_doctor(args: argparse.Namespace) -> int:
    interpreters = probe_interpreters() if args.probe else []
    usable_interpreters = [item for item in interpreters if item["faster_whisper"]]
    status = {
        "executable": sys.executable,
        "python": sys.version.split()[0],
        "ffmpeg": shutil.which("ffmpeg"),
        "faster_whisper": module_available("faster_whisper"),
    }
    if args.probe:
        status["interpreters"] = interpreters
        status["usable_interpreters"] = usable_interpreters
    status["ok_for_validate_convert_export"] = True
    status["ok_for_transcribe"] = bool(status["ffmpeg"] and (status["faster_whisper"] or usable_interpreters))
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"python: {status['python']} ({status['executable']})")
        print(f"ffmpeg: {status['ffmpeg'] or 'not found'}")
        print(f"faster-whisper: {'available' if status['faster_whisper'] else 'not installed'}")
        if args.probe:
            if usable_interpreters:
                print("usable interpreters with faster-whisper:")
                for item in usable_interpreters:
                    print(f"  {item['path']} ({item.get('python', 'unknown python')})")
            else:
                print("usable interpreters with faster-whisper: none found")
        if not status["ok_for_transcribe"]:
            print("transcribe: unavailable until ffmpeg and a Python environment with faster-whisper are available")
        print("validate/convert/export: available")
    return 0 if status["ok_for_validate_convert_export"] else 1


def cmd_models(args: argparse.Namespace) -> int:
    models = discover_models()
    if args.json:
        print(json.dumps({"models": models}, ensure_ascii=False, indent=2))
    else:
        if not models:
            print("No cached faster-whisper models found in common cache locations.")
            print("Ask before downloading a model; do not assume the default is acceptable.")
            return 0
        print("Cached faster-whisper models:")
        for item in models:
            size = f", size={item['size']}" if item.get("size") else ""
            print(f"- {item['model']} ({item['source']}{size})")
            if item.get("path"):
                print(f"  path: {item['path']}")
        if len(models) > 1:
            print("Multiple cached variants found. Ask the user which one to use before transcribing.")
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"input not found: {input_path}")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH")

    output_dir = (args.output_dir or input_path.with_suffix("")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="transub-skill-") as tmp:
        audio_path = Path(tmp) / "audio.wav"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(input_path),
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(audio_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip().splitlines()[-5:]
            raise SystemExit("ffmpeg failed to extract audio:\n" + "\n".join(detail)) from exc
        segments = transcribe_audio(audio_path, args.model, args.device, args.language)

    stem = input_path.stem
    json_path = output_dir / f"{stem}.segments.json"
    json_path.write_text(json.dumps([segment_to_dict(s) for s in segments], ensure_ascii=False, indent=2), encoding="utf-8")

    written = [json_path]
    if args.format in {"srt", "both"}:
        srt_path = output_dir / f"{stem}.srt"
        srt_path.write_text(to_srt(segments), encoding="utf-8")
        written.append(srt_path)
    if args.format in {"vtt", "both"}:
        vtt_path = output_dir / f"{stem}.vtt"
        vtt_path.write_text(to_vtt(segments), encoding="utf-8")
        written.append(vtt_path)

    report = validate_segments(segments)
    print(json.dumps({"ok": report["ok"], "segments": len(segments), "written": [str(p) for p in written], "issues": report["issues"]}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def cmd_validate(args: argparse.Namespace) -> int:
    path = args.input.expanduser().resolve()
    segments = read_segments(path)
    report = validate_segments(segments)
    print(json.dumps(report | {"segments": len(segments)}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def cmd_audit(args: argparse.Namespace) -> int:
    segments = read_segments(args.input.expanduser().resolve())
    report = audit_segments(
        segments,
        max_width=args.max_width,
        severe_width=args.severe_width,
        max_han_chars=args.max_han_chars,
        severe_han_chars=args.severe_han_chars,
        max_cps=args.max_cps,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"segments: {report['segments']}")
        print(f"avg_width: {report['avg_width']:.1f}")
        print(f"max_width: {report['max_width']}")
        print(f"avg_han_chars: {report['avg_han_chars']:.1f}")
        print(f"max_han_chars: {report['max_han_chars']}")
        print(f"avg_cps: {report['avg_cps']:.1f}")
        print(f"max_cps: {report['max_cps']:.1f}")
        print(f"warnings: {len(report['warnings'])}")
        for warning in report["warnings"][:20]:
            print(
                f"  #{warning['index']} {warning['kind']} "
                f"width={warning['width']} han={warning['han_chars']} duration={warning['duration']:.2f}s cps={warning['cps']:.1f} "
                f"text={warning['text']}"
            )
        if len(report["warnings"]) > 20:
            print(f"  ... {len(report['warnings']) - 20} more")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    segments = read_segments(args.input.expanduser().resolve())
    report = validate_segments(segments)
    if not report["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([segment_to_dict(s) for s in segments], ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    segments = read_segments(args.input.expanduser().resolve())
    report = validate_segments(segments)
    if not report["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_srt(segments) if args.format == "srt" else to_vtt(segments), encoding="utf-8")
    print(str(output))
    return 0


def transcribe_audio(audio_path: Path, model: str, device: str, language: str) -> list[Segment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not available in this Python environment. "
            "Run `python subtitle_workflow.py doctor --probe` to look for an existing interpreter before installing anything."
        ) from exc

    compute_type = "int8" if device == "cpu" else "float16"
    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    kwargs = {
        "word_timestamps": True,
        "temperature": 0.0,
        "compression_ratio_threshold": 2.6,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.3,
        "condition_on_previous_text": True,
    }
    if language and language != "auto":
        kwargs["language"] = language

    raw_segments, _info = whisper.transcribe(str(audio_path), **kwargs)
    result: list[Segment] = []
    for idx, seg in enumerate(raw_segments, start=1):
        text = (seg.text or "").strip()
        if not text:
            continue
        words = getattr(seg, "words", None)
        word_payload = None
        if words:
            word_payload = [{"word": w.word, "start": w.start, "end": w.end} for w in words]
        result.append(Segment(index=idx, start=float(seg.start), end=float(seg.end), text=text, words=word_payload))
    if not result:
        raise SystemExit("faster-whisper returned no subtitle segments")
    return result


def module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def probe_interpreters() -> list[dict]:
    candidates: list[Path] = []
    for env_name in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        env_value = os.environ.get(env_name)
        if env_value:
            candidates.extend(candidate_pythons(Path(env_value)))

    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        for dirname in (".venv", "venv", "env"):
            candidates.extend(candidate_pythons(parent / dirname))
        if parent == parent.parent:
            break

    for root in COMMON_ENV_ROOTS:
        if root.is_dir():
            for env_dir in sorted(root.iterdir()):
                if env_dir.is_dir():
                    candidates.extend(candidate_pythons(env_dir))

    for executable in ("python", "python3"):
        found = shutil.which(executable)
        if found:
            candidates.append(Path(found))

    seen: set[str] = set()
    results: list[dict] = []
    for candidate in candidates:
        try:
            resolved = str(candidate.expanduser().resolve())
        except OSError:
            resolved = str(candidate)
        if resolved in seen or not Path(resolved).exists():
            continue
        seen.add(resolved)
        results.append(check_interpreter(Path(resolved)))
    return results


def candidate_pythons(env_dir: Path) -> list[Path]:
    return [
        env_dir / "bin" / "python",
        env_dir / "bin" / "python3",
        env_dir / "Scripts" / "python.exe",
    ]


def check_interpreter(path: Path) -> dict:
    code = (
        "import importlib.util, json, sys; "
        "print(json.dumps({'python': sys.version.split()[0], "
        "'faster_whisper': importlib.util.find_spec('faster_whisper') is not None}))"
    )
    result = {"path": str(path), "python": None, "faster_whisper": False, "error": None}
    try:
        completed = subprocess.run(
            [str(path), "-c", code],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
        return result
    if completed.returncode != 0:
        result["error"] = (completed.stderr or "").strip()
        return result
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        result["error"] = f"invalid probe output: {exc}"
        return result
    result["python"] = payload.get("python")
    result["faster_whisper"] = bool(payload.get("faster_whisper"))
    return result


def discover_models() -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()

    for cache_dir in huggingface_cache_dirs():
        hub_dir = cache_dir / "hub"
        if not hub_dir.is_dir():
            continue
        for model_dir in sorted(hub_dir.glob("models--*")):
            if ".locks" in model_dir.parts or "faster-whisper" not in model_dir.name.lower():
                continue
            model_id = model_dir.name.removeprefix("models--").replace("--", "/")
            snapshot = preferred_snapshot(model_dir)
            key = str(snapshot or model_dir)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "model": model_id,
                    "path": str(snapshot or model_dir),
                    "source": "huggingface-cache",
                    "size": human_size(dir_size(model_dir)),
                }
            )

    for root in local_model_roots():
        if not root.is_dir():
            continue
        for model_bin in sorted(root.glob("**/model.bin")):
            model_dir = model_bin.parent
            key = str(model_dir)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "model": str(model_dir),
                    "path": str(model_dir),
                    "source": "local-dir",
                    "size": human_size(dir_size(model_dir)),
                }
            )
    return results


def huggingface_cache_dirs() -> list[Path]:
    dirs = []
    for env_name in ("HF_HOME", "HUGGINGFACE_HUB_CACHE"):
        value = os.environ.get(env_name)
        if value:
            path = Path(value).expanduser()
            dirs.append(path.parent if env_name == "HUGGINGFACE_HUB_CACHE" and path.name == "hub" else path)
    dirs.append(HOME / ".cache" / "huggingface")
    return unique_paths(dirs)


def local_model_roots() -> list[Path]:
    return unique_paths(
        [
            Path.cwd(),
            HOME / "models",
            HOME / ".cache" / "whisper",
            HOME / ".cache" / "faster-whisper",
        ]
    )


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    unique = []
    seen = set()
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser())
        if key not in seen:
            seen.add(key)
            unique.append(Path(key))
    return unique


def preferred_snapshot(model_dir: Path) -> Path | None:
    ref = model_dir / "refs" / "main"
    if ref.is_file():
        revision = ref.read_text(encoding="utf-8").strip()
        candidate = model_dir / "snapshots" / revision
        if candidate.is_dir():
            return candidate
    snapshots = sorted((model_dir / "snapshots").glob("*")) if (model_dir / "snapshots").is_dir() else []
    for candidate in snapshots:
        if candidate.is_dir():
            return candidate
    return None


def dir_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_symlink():
                continue
            if item.is_file():
                total += item.stat().st_size
    except OSError:
        return 0
    return total


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"


def read_segments(path: Path) -> list[Segment]:
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise SystemExit("segments json must contain a list")
        return [Segment(index=int(item.get("index", i)), start=float(item["start"]), end=float(item["end"]), text=str(item["text"]).strip(), words=item.get("words")) for i, item in enumerate(data, start=1)]
    if suffix == ".srt":
        return parse_srt(text)
    if suffix == ".vtt":
        return parse_vtt(text)
    raise SystemExit("input must be .json, .srt, or .vtt")


def parse_srt(content: str) -> list[Segment]:
    blocks = re.split(r"\n\s*\n", content.strip())
    segments: list[Segment] = []
    for fallback_index, block in enumerate(blocks, start=1):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        index = int(lines[0]) if lines[0].isdigit() else fallback_index
        timing_line = lines[1] if lines[0].isdigit() else lines[0]
        text_lines = lines[2:] if lines[0].isdigit() else lines[1:]
        match = TIMESTAMP_RE.search(timing_line)
        if not match:
            continue
        segments.append(Segment(index=index, start=parse_timestamp(match.group("start")), end=parse_timestamp(match.group("end")), text="\n".join(text_lines).strip()))
    return segments


def parse_vtt(content: str) -> list[Segment]:
    content = re.sub(r"^\ufeff?WEBVTT[^\n]*\n+", "", content.strip())
    blocks = re.split(r"\n\s*\n", content)
    segments: list[Segment] = []
    for index, block in enumerate(blocks, start=1):
        lines = [line for line in block.splitlines() if line.strip() and not line.strip().startswith(("NOTE", "STYLE", "REGION"))]
        if not lines:
            continue
        timing_i = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_i is None:
            continue
        match = TIMESTAMP_RE.search(lines[timing_i])
        if not match:
            continue
        segments.append(Segment(index=index, start=parse_timestamp(match.group("start")), end=parse_timestamp(match.group("end")), text="\n".join(lines[timing_i + 1 :]).strip()))
    return segments


def validate_segments(segments: Iterable[Segment]) -> dict:
    issues: list[str] = []
    prev_end = -1.0
    seen: set[int] = set()
    count = 0
    for expected, segment in enumerate(segments, start=1):
        count += 1
        if segment.index in seen:
            issues.append(f"duplicate index {segment.index}")
        seen.add(segment.index)
        if segment.index != expected:
            issues.append(f"non-sequential index at position {expected}: got {segment.index}")
        if segment.end <= segment.start:
            issues.append(f"index {segment.index} has non-positive duration")
        if segment.start < prev_end:
            issues.append(f"index {segment.index} overlaps previous cue")
        if not segment.text.strip():
            issues.append(f"index {segment.index} has empty text")
        prev_end = max(prev_end, segment.end)
    if count == 0:
        issues.append("no subtitle segments found")
    return {"ok": not issues, "issues": issues}


def audit_segments(
    segments: Iterable[Segment],
    max_width: int,
    severe_width: int,
    max_han_chars: int,
    severe_han_chars: int,
    max_cps: float,
    min_duration: float,
    max_duration: float,
) -> dict:
    rows = []
    warnings = []
    for segment in segments:
        text = " ".join(segment.text.split())
        width = display_width(text)
        han_chars = count_han_chars(text)
        duration = max(0.0, segment.end - segment.start)
        cps = width / duration if duration else float("inf")
        rows.append({"width": width, "han_chars": han_chars, "duration": duration, "cps": cps})
        kinds = []
        if width > severe_width:
            kinds.append("severe_width")
        elif width > max_width:
            kinds.append("width")
        if han_chars > severe_han_chars:
            kinds.append("severe_han_chars")
        elif han_chars > max_han_chars:
            kinds.append("han_chars")
        if cps > max_cps:
            kinds.append("cps")
        if duration < min_duration:
            kinds.append("short_duration")
        if duration > max_duration:
            kinds.append("long_duration")
        for kind in kinds:
            warnings.append(
                {
                    "index": segment.index,
                    "kind": kind,
                    "width": width,
                    "han_chars": han_chars,
                    "duration": duration,
                    "cps": cps,
                    "text": text,
                }
            )
    if not rows:
        return {
            "segments": 0,
            "avg_width": 0.0,
            "max_width": 0,
            "avg_han_chars": 0.0,
            "max_han_chars": 0,
            "avg_cps": 0.0,
            "max_cps": 0.0,
            "warnings": [],
        }
    return {
        "segments": len(rows),
        "avg_width": sum(row["width"] for row in rows) / len(rows),
        "max_width": max(row["width"] for row in rows),
        "avg_han_chars": sum(row["han_chars"] for row in rows) / len(rows),
        "max_han_chars": max(row["han_chars"] for row in rows),
        "avg_cps": sum(row["cps"] for row in rows) / len(rows),
        "max_cps": max(row["cps"] for row in rows),
        "warnings": warnings,
    }


def display_width(text: str) -> int:
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def count_han_chars(text: str) -> int:
    return sum(
        1
        for char in text
        if "\u4e00" <= char <= "\u9fff"
        or "\u3400" <= char <= "\u4dbf"
        or "\uf900" <= char <= "\ufaff"
    )


def segment_to_dict(segment: Segment) -> dict:
    data = {"index": segment.index, "start": segment.start, "end": segment.end, "text": segment.text}
    if segment.words:
        data["words"] = segment.words
    return data


def to_srt(segments: Iterable[Segment]) -> str:
    blocks = []
    for segment in segments:
        blocks.append(f"{segment.index}\n{format_timestamp(segment.start, comma=True)} --> {format_timestamp(segment.end, comma=True)}\n{segment.text}")
    return "\n\n".join(blocks) + "\n"


def to_vtt(segments: Iterable[Segment]) -> str:
    blocks = ["WEBVTT\n"]
    for segment in segments:
        blocks.append(f"{format_timestamp(segment.start, comma=False)} --> {format_timestamp(segment.end, comma=False)}\n{segment.text}")
    return "\n\n".join(blocks) + "\n"


def parse_timestamp(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, rest = parts
    elif len(parts) == 2:
        hours = "0"
        minutes, rest = parts
    else:
        raise ValueError(f"invalid timestamp: {value}")
    seconds, millis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def format_timestamp(seconds: float, comma: bool) -> str:
    millis_total = max(0, round(seconds * 1000))
    hours, rem = divmod(millis_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


if __name__ == "__main__":
    raise SystemExit(main())
