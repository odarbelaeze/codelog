import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterator, List

import click
import dateparser
import toml


class Context:
    def __init__(self, config, project) -> None:
        self.config_path: Path = config
        self.project: str = project

    @property
    def config(self) -> Dict[str, List[str]]:
        with open(self.config_path) as config_file:
            return toml.load(config_file)

    @property
    def repos(self) -> List[str]:
        return self.config.get(self.project, [])

    def write(self, config: Dict[str, List[str]]):
        with open(self.config_path, "w") as config_file:
            return toml.dump(config, config_file)

    def report(self, start: datetime.datetime, end: datetime.datetime) -> Iterator[str]:
        for path in self.repos:
            yield path
            try:
                # subprocess.run(
                #     [
                #         "git",
                #         "pull",
                #     ],
                #     cwd=path,
                #     stderr=subprocess.DEVNULL,
                #     stdout=subprocess.DEVNULL,
                # )
                output = subprocess.check_output(
                    [
                        "git",
                        "--no-pager",
                        "log",
                        r'--pretty=format:"%ad %an %d %s"',
                        "--all",
                        "--author=Oscar",
                        f"--before={end.isoformat()}",
                        f"--after={start.isoformat()}",
                    ],
                    cwd=path,
                )
                yield from (line for line in output.decode().split("\n") if line)
            except subprocess.CalledProcessError:
                click.secho("Not a git repository", err=True)
                sys.exit(1)


@click.group()
@click.option("-p", "--project", default="default", help="project to work with")
@click.option(
    "-c",
    "--config",
    type=click.Path(dir_okay=False, exists=True),
    default=None,
    help="config file name",
)
@click.pass_context
def main(ctx, project, config):
    if config is None:
        app_dir = click.get_app_dir("codelog")
        os.makedirs(app_dir, exist_ok=True)
        config = Path(os.path.join(click.get_app_dir("codelog"), "codelog.toml"))
        config.touch(exist_ok=True)
    ctx.obj = Context(config, project)


@main.command()
@click.pass_context
def add(ctx):
    try:
        subprocess.check_output(["git", "status"], stderr=subprocess.DEVNULL)
        ctx.obj.write(
            {
                **ctx.obj.config,
                ctx.obj.project: list(set([*ctx.obj.repos, os.getcwd()])),
            }
        )
    except subprocess.CalledProcessError:
        click.secho("Not a git repository", err=True)
        sys.exit(1)


@main.command("list")
@click.pass_context
def list_repos(ctx):
    click.echo("\n".join(ctx.obj.repos))


@main.command()
@click.pass_context
def clear(ctx):
    ctx.obj.write({**ctx.obj.config, ctx.obj.project: []})


@main.command()
@click.argument("date", nargs=-1)
@click.pass_context
def report(ctx, date):
    parsed = dateparser.parse(" ".join(date or ["today"]))
    print(parsed.isoformat())
    start = datetime.datetime.fromordinal(parsed.date().toordinal())
    end = start + datetime.timedelta(hours=23, minutes=59, seconds=59)
    click.echo("\n".join(ctx.obj.report(start, end)))


if __name__ == "__main__":
    main(project=None, config=None)
