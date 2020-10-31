import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterator, List

import click
import dateparser
import toml
import re


def fix(line: str) -> str:
    line = line.replace('"', "")
    line = re.sub(r"\(.*\)", "", line)
    line = re.sub(r"\s+", " ", line)
    return line


def valid(line: str) -> bool:
    return (
        line
        and not line.startswith("Merge")
        and not line.startswith("index on")
        and not line.startswith("WIP on")
    )


def ellipsis(source: str, cap: int) -> str:
    if len(source) > cap:
        return source[: cap - 3] + "..."
    return source


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
            try:
                output = subprocess.check_output(
                    [
                        "git",
                        "--no-pager",
                        "log",
                        r"--pretty=format:%s",
                        "--all",
                        "--author=Oscar",
                        f"--before={end.isoformat()}",
                        f"--after={start.isoformat()}",
                    ],
                    cwd=path,
                )
                lines = [fix(line) for line in output.decode().split("\n") if line]
                if any(line.startswith("Merge") for line in lines):
                    yield "PR Reviews"
                lines = [line for line in lines if valid(line)]
                yield from lines
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
    start = datetime.datetime.fromordinal(parsed.date().toordinal())
    end = start + datetime.timedelta(hours=23, minutes=59, seconds=59)
    headers = "date,hours,text"
    messages = ctx.obj.report(start, end)
    text = ellipsis(", ".join(messages), 400)
    if not text.strip():
        text = "PR Reviews, non coding work"
    content = ",".join([start.date().isoformat().replace("-", "/"), "8", f'"{text}"'])
    output = "\n".join([headers, content])
    click.echo(output)


if __name__ == "__main__":
    main(project=None, config=None)
