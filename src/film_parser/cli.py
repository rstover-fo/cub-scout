"""CLI for parsing All-22 film into structured play catalogs."""

import json
import logging
import time
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
except ImportError:
    raise SystemExit(
        "Film parser CLI requires extra dependencies.\n"
        "Install them with: pip install 'cfb-scout[film]'\n"
        "Required packages: typer, rich, opencv-python, scenedetect, paddleocr, paddlepaddle"
    )

from src.film_parser.models import PlayCatalog, SegmentType

app = typer.Typer(help="Parse All-22 film into structured play catalogs.")
console = Console()
logger = logging.getLogger("src.film_parser")


def _build_output_filename(catalog: PlayCatalog) -> str:
    """Build output JSON filename from game metadata."""
    meta = catalog.game_metadata
    parts = [
        meta.team.lower().replace(" ", "_"),
        meta.side.value.lower(),
        "vs",
        meta.opponent.lower().replace(" ", "_"),
        meta.opponent_side.value.lower(),
        str(meta.season_year),
    ]
    return "_".join(parts) + ".json"


@app.command()
def parse(
    video_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the All-22 film video file.",
    ),
    season: int = typer.Option(..., help="Season year for this film."),
    output_dir: Path = typer.Option(
        Path("./output/"),
        help="Directory for output JSON and clips.",
    ),
    extract_clips: bool = typer.Option(False, help="Extract MP4 clips for each play."),
    extract_frames: bool = typer.Option(False, help="Extract situation frame PNGs."),
    dry_run: bool = typer.Option(False, help="Run pipeline without writing output files."),
    verbose: bool = typer.Option(False, help="Enable debug logging."),
    scene_threshold: float = typer.Option(27.0, help="ContentDetector threshold for scenes."),
) -> None:
    """Parse an All-22 film video into a structured play catalog JSON."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    try:
        from src.film_parser.clip_extractor import extract_play_clips, extract_situation_frames
        from src.film_parser.filename_parser import parse_filename
        from src.film_parser.frame_classifier import classify_segments
        from src.film_parser.ocr_extract import extract_all_situation_data
        from src.film_parser.play_assembler import assemble_plays
        from src.film_parser.scene_detect import detect_scenes
        from src.film_parser.utils import get_video_info
    except ImportError as exc:
        console.print(
            f"[red]Missing film dependency:[/red] {exc}\n"
            "Install with: pip install 'cfb-scout[film]'"
        )
        raise typer.Exit(code=1) from exc

    start_time = time.monotonic()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        pipeline_task = progress.add_task("Parsing film...", total=7)

        # Step 1: Parse filename
        progress.update(pipeline_task, description="Parsing filename...")
        try:
            game_metadata = parse_filename(str(video_path), season)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from e
        console.print(
            f"  Game: [bold]{game_metadata.team} {game_metadata.side.value}[/bold]"
            f" vs [bold]{game_metadata.opponent} {game_metadata.opponent_side.value}[/bold]"
        )
        progress.advance(pipeline_task)

        # Step 2: Get video info
        progress.update(pipeline_task, description="Reading video info...")
        video_info = get_video_info(video_path)
        console.print(
            f"  Video: {video_info['width']}x{video_info['height']}"
            f" @ {video_info['fps']:.1f}fps, {video_info['duration']:.1f}s"
        )
        progress.advance(pipeline_task)

        # Step 3: Detect scenes
        progress.update(pipeline_task, description="Detecting scenes...")
        segments = detect_scenes(video_path, threshold=scene_threshold)
        console.print(f"  Scenes detected: [cyan]{len(segments)}[/cyan]")
        progress.advance(pipeline_task)

        # Step 4: Classify segments
        progress.update(pipeline_task, description="Classifying segments...")
        classified = classify_segments(video_path, segments)
        situation_count = sum(1 for s in classified if s.segment_type == SegmentType.SITUATION)
        action_count = sum(1 for s in classified if s.segment_type == SegmentType.GAME_ACTION)
        console.print(
            f"  Classified: [green]{situation_count}[/green] situations,"
            f" [blue]{action_count}[/blue] game actions"
        )
        progress.advance(pipeline_task)

        # Step 5: OCR extraction
        progress.update(pipeline_task, description="Extracting OCR data...")
        ocr_results = extract_all_situation_data(video_path, classified)
        console.print(f"  OCR extracted: [cyan]{len(ocr_results)}[/cyan] segments")
        progress.advance(pipeline_task)

        # Step 6: Assemble plays
        progress.update(pipeline_task, description="Assembling plays...")
        catalog = assemble_plays(classified, game_metadata)

        # Attach OCR situation_data to plays by matching situation segment indices
        segment_index_map: dict[tuple[float, float], int] = {}
        for idx, seg in enumerate(classified):
            segment_index_map[(seg.start_time, seg.end_time)] = idx

        for play in catalog.plays:
            key = (play.situation.start_time, play.situation.end_time)
            sit_idx = segment_index_map.get(key)
            if sit_idx is not None and sit_idx in ocr_results:
                play.situation_data = ocr_results[sit_idx]

        # Compute OCR quality metrics
        ocr_field_counts: dict[str, int] = {}
        total_ocr_fields = 0
        parsed_ocr_fields = 0
        for data in ocr_results.values():
            for field_name, val in [
                ("quarter", data.quarter),
                ("down", data.down),
                ("distance", data.distance),
                ("clock", data.clock),
                ("play_number", data.play_number),
            ]:
                total_ocr_fields += 1
                if val is not None:
                    parsed_ocr_fields += 1
                    ocr_field_counts[field_name] = ocr_field_counts.get(field_name, 0) + 1

        ocr_success_rate = parsed_ocr_fields / total_ocr_fields if total_ocr_fields > 0 else 0.0
        catalog.quality_metrics.ocr_success_rate = ocr_success_rate
        catalog.quality_metrics.fields_extracted = ocr_field_counts

        console.print(f"  Plays assembled: [bold green]{len(catalog.plays)}[/bold green]")
        progress.advance(pipeline_task)

        # Step 7: Fill processing_info
        progress.update(pipeline_task, description="Finalizing...")
        elapsed = time.monotonic() - start_time
        catalog.processing_info.processing_time_seconds = round(elapsed, 2)
        catalog.processing_info.video_duration_seconds = video_info["duration"]
        catalog.processing_info.video_resolution = f"{video_info['width']}x{video_info['height']}"
        catalog.processing_info.video_fps = video_info["fps"]
        catalog.processing_info.scene_threshold = scene_threshold
        progress.advance(pipeline_task)

    # Optional clip extraction
    if extract_clips and not dry_run:
        clips_dir = output_dir / "clips"
        console.print(f"Extracting play clips to [cyan]{clips_dir}[/cyan]...")
        clip_paths = extract_play_clips(video_path, catalog, clips_dir)
        console.print(f"  Extracted [green]{len(clip_paths)}[/green] clips")

    if extract_frames and not dry_run:
        frames_dir = output_dir / "frames"
        console.print(f"Extracting situation frames to [cyan]{frames_dir}[/cyan]...")
        frame_paths = extract_situation_frames(video_path, catalog, frames_dir)
        console.print(f"  Extracted [green]{len(frame_paths)}[/green] frames")

    # Write JSON output
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = _build_output_filename(catalog)
        output_path = output_dir / output_filename
        output_path.write_text(json.dumps(catalog.model_dump(mode="json"), indent=2, default=str))
        console.print(f"\nCatalog written to [bold]{output_path}[/bold]")
    else:
        console.print("\n[yellow]Dry run -- no files written.[/yellow]")

    # Summary table
    table = Table(title="Processing Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    qm = catalog.quality_metrics
    pi = catalog.processing_info

    table.add_row("Total segments", str(qm.total_segments))
    table.add_row("Situations", str(qm.classified_situations))
    table.add_row("Game actions", str(qm.classified_game_actions))
    table.add_row("Complete plays", str(qm.complete_triplets))
    table.add_row("Orphaned segments", str(qm.orphaned_segments))
    table.add_row("OCR success rate", f"{qm.ocr_success_rate:.1%}")
    table.add_row("Processing time", f"{pi.processing_time_seconds:.2f}s")
    table.add_row("Video duration", f"{pi.video_duration_seconds:.1f}s")
    table.add_row("Scene threshold", str(pi.scene_threshold))

    console.print()
    console.print(table)


if __name__ == "__main__":
    app()
