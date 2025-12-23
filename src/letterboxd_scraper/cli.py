from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings, load_settings
from .db import models
from .db.session import get_session, init_engine
from .services import cohorts as cohort_service
from .services import export as export_service
from .services import ratings as rating_service
from .services import rankings as ranking_service
from .services import rss_updates as rss_service
from .services import stats as stats_service
from .services import telemetry as telemetry_service
from .scrapers.follow_graph import FollowGraphScraper, expand_follow_graph
from .scrapers.ratings import ProfileRatingsScraper
from .scrapers.rss import RSSScraper

console = Console()

app = typer.Typer(
    help="Personalized Letterboxd scraper CLI.",
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
cohort_app = typer.Typer(help="Manage cohorts (follow lists).", no_args_is_help=True)
scrape_app = typer.Typer(help="Scraping commands.", no_args_is_help=True)
stats_app = typer.Typer(help="Statistics/materialized view maintenance.", no_args_is_help=True)
rank_app = typer.Typer(help="Ranking computations.", no_args_is_help=True)
export_app = typer.Typer(help="Export data into consumable formats.")

app.add_typer(cohort_app, name="cohort")
app.add_typer(scrape_app, name="scrape")
app.add_typer(stats_app, name="stats")
app.add_typer(rank_app, name="rank")
app.add_typer(export_app, name="export")


def get_state(ctx: typer.Context) -> Dict[str, Settings]:
    return ctx.ensure_object(dict)  # type: ignore[return-value]


@app.callback()
def main(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to TOML config file."),
) -> None:
    """Application entry point: load configuration."""
    settings = load_settings(config_path=config)
    state = get_state(ctx)
    state["settings"] = settings
    init_engine(settings)
    console.log(f"Loaded configuration from {config or 'config/default.toml'}")


@cohort_app.command("build")
def cohort_build(
    ctx: typer.Context,
    seed: str = typer.Option(..., "--seed", "-s", help="Seed Letterboxd username."),
    label: str = typer.Option(..., "--label", "-l", help="Human readable cohort label."),
    depth: int = typer.Option(None, "--depth", "-d", help="Follow depth; overrides config default."),
    include_seed: Optional[bool] = typer.Option(None, help="Include the seed user themselves?"),
) -> None:
    """Create cohort definition and queue follow graph scrape."""
    settings = get_state(ctx)["settings"]
    depth = depth or settings.cohort_defaults.follow_depth
    include_seed = (
        include_seed if include_seed is not None else settings.cohort_defaults.include_seed
    )
    definition = {"depth": depth, "include_seed": include_seed}
    cohort_id = None
    with get_session(settings) as session:
        seed_user = cohort_service.get_or_create_user(session, seed)
        cohort = cohort_service.create_cohort(session, seed_user, label, definition)
        cohort_id = cohort.id
        if include_seed:
            cohort_service.add_member(session, cohort, seed_user, depth=0)
    console.print(f"[green]Created cohort[/green] '{label}' (id={cohort_id}) with seed '{seed}'.")


@cohort_app.command("refresh")
def cohort_refresh(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
) -> None:
    """Refresh follow graph membership for an existing cohort."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        definition = cohort.definition or {}
        depth = definition.get("depth", settings.cohort_defaults.follow_depth)
        include_seed = definition.get("include_seed", settings.cohort_defaults.include_seed)
        seed_user = session.get(models.User, cohort.seed_user_id) if cohort.seed_user_id else None
        seed_username = seed_user.letterboxd_username if seed_user else ""
        if not seed_username:
            typer.echo("Cohort seed user missing; rebuild cohort.")
            raise typer.Exit(code=1)
    with telemetry_service.timed_operation(f"cohort_refresh[{cohort_id}]"):
        scraper = FollowGraphScraper(settings)
        try:
            edges = list(expand_follow_graph(scraper, seed_username, depth))
            with get_session(settings) as session:
                cohort = cohort_service.get_cohort(session, cohort_id)
                if cohort:
                    cohort_service.refresh_cohort_members(
                        session,
                        cohort,
                        edges,
                        include_seed=include_seed,
                        seed_username=seed_username,
                    )
            console.print(f"[green]Refreshed[/green] cohort {cohort_id} members (depth={depth}).")
        finally:
            scraper.close()


@scrape_app.command("full")
def scrape_full(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    resume: bool = typer.Option(False, "--resume/--no-resume", help="Resume from last checkpoint."),
) -> None:
    """Run a full historical scrape for every user in the cohort."""
    settings = get_state(ctx)["settings"]
    usernames: list[str]
    with get_session(settings) as session:
        if not cohort_service.get_cohort(session, cohort_id):
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        usernames = cohort_service.list_member_usernames(session, cohort_id)
    run_id = None
    with get_session(settings) as session:
        run_id = telemetry_service.record_scrape_run(
            session,
            cohort_id=cohort_id,
            run_type="full",
            status="running",
        )
    status = "success"
    note = None
    scraper = ProfileRatingsScraper(settings)
    try:
        with telemetry_service.timed_operation(f"scrape_full[{cohort_id}]"):
            for username in usernames:
                with telemetry_service.timed_operation(f"user[{username}]"):
                    console.print(f"[cyan]Scraping[/cyan] ratings for {username}...")
                    ratings_iter = scraper.fetch_user_ratings(username)
                    with get_session(settings) as session:
                        rating_service.upsert_ratings(session, username, ratings_iter)
    except Exception as exc:
        status = "failed"
        note = str(exc)
        raise
    finally:
        scraper.close()
        if run_id:
            with get_session(settings) as session:
                telemetry_service.finalize_scrape_run(
                    session, run_id, status=status, notes=note
                )
    console.print(f"[green]Completed[/green] full scrape for cohort {cohort_id}.")


@scrape_app.command("incremental")
def scrape_incremental(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
) -> None:
    """Apply incremental updates via RSS feeds + lightweight scraping."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            typer.echo(f"Cohort {cohort_id} not found.")
            raise typer.Exit(code=1)
        usernames = cohort_service.list_member_usernames(session, cohort_id)
    run_id = None
    with get_session(settings) as session:
        run_id = telemetry_service.record_scrape_run(
            session,
            cohort_id=cohort_id,
            run_type="incremental",
            status="running",
        )
    status = "success"
    note = None
    rss_scraper = RSSScraper(settings)
    total_updates = 0
    try:
        with telemetry_service.timed_operation(f"scrape_incremental[{cohort_id}]"):
            for username in usernames:
                with telemetry_service.timed_operation(f"rss[{username}]"):
                    entries = list(rss_scraper.fetch_feed(username))
                if not entries:
                    continue
                with get_session(settings) as session:
                    updated = rss_service.apply_rss_entries(session, username, entries)
                    total_updates += updated
                console.print(f"[cyan]{username}[/cyan]: applied {len(entries)} RSS entries.")
    except Exception as exc:
        status = "failed"
        note = str(exc)
        raise
    finally:
        if run_id:
            with get_session(settings) as session:
                telemetry_service.finalize_scrape_run(
                    session, run_id, status=status, notes=note
                )
    console.print(f"[green]Incremental update complete[/green]; {total_updates} ratings touched.")


@rank_app.command("compute")
def rank_compute(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    strategy: str = typer.Option("bayesian", "--strategy", "-s", help="Ranking strategy id."),
) -> None:
    """Compute ranking values for a cohort."""
    settings = get_state(ctx)["settings"]
    with telemetry_service.timed_operation(f"rank[{cohort_id}:{strategy}]"):
        with get_session(settings) as session:
            if strategy == "bayesian":
                m_value = settings.cohort_defaults.m_value
                results = ranking_service.compute_bayesian(session, cohort_id, m_value)
                ranking_service.persist_rankings(
                    session,
                    cohort_id,
                    strategy,
                    results,
                    params={"m_value": float(m_value)},
                )
                console.print(f"[green]Computed[/green] {len(results)} rankings (showing top 5):")
                for result in results[:5]:
                    console.print(
                        f"#{result.rank}: film_id={result.film_id} "
                        f"score={result.score:.3f} watchers={result.metadata['watchers']}"
                    )
            else:
                console.print(f"[yellow]TODO[/yellow]: strategy '{strategy}' not implemented yet.")


@export_app.command("csv")
def export_csv(
    ctx: typer.Context,
    cohort_id: int = typer.Argument(..., help="Cohort identifier."),
    strategy: str = typer.Option("bayesian", "--strategy", "-s", help="Ranking strategy id."),
    min_score: float = typer.Option(0.0, "--min-score", help="Score threshold."),
    output: Path = typer.Option(Path("exported/cohort.csv"), "--output", "-o", help="Output CSV."),
) -> None:
    """Export ranking results to CSV."""
    settings = get_state(ctx)["settings"]
    with telemetry_service.timed_operation(f"export[{cohort_id}:{strategy}]"):
        with get_session(settings) as session:
            count = export_service.export_rankings_to_csv(
                session,
                cohort_id=cohort_id,
                strategy=strategy,
                min_score=min_score,
                output_path=output,
            )
    console.print(
        f"[green]Exported[/green] {count} rows for cohort {cohort_id} strategy {strategy} to {output}"
    )


@stats_app.command("refresh")
def stats_refresh(ctx: typer.Context, concurrent: bool = typer.Option(False, "--concurrent/--no-concurrent")) -> None:
    """Refresh the cohort_film_stats materialized view."""
    settings = get_state(ctx)["settings"]
    with telemetry_service.timed_operation("stats_refresh"):
        with get_session(settings) as session:
            stats_service.refresh_cohort_stats(session, concurrently=concurrent)
    console.print("[green]Refreshed[/green] cohort_film_stats view.")

@cohort_app.command("list")
def cohort_list(ctx: typer.Context) -> None:
    """List existing cohorts."""
    settings = get_state(ctx)["settings"]
    with get_session(settings) as session:
        cohorts = cohort_service.list_cohorts(session)
    table = Table(title="Cohorts")
    table.add_column("ID", style="cyan")
    table.add_column("Label")
    table.add_column("Seed")
    table.add_column("Members")
    for cohort_id, label, seed_id, member_count in cohorts:
        table.add_row(str(cohort_id), label, str(seed_id or ""), str(member_count))
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
