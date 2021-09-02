import datetime
import csv
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Protocol

from arrow import Arrow

import click
import dateparser
import toml
from pydantic import BaseModel, ValidationError, validator


class Repo(BaseModel):
    name: str
    path: str

    @validator("path")
    def existing_git_repo(cls, value: str) -> str:
        assert cls is not None
        if not os.path.exists(value):
            raise ValueError(f'"{value}" does not exist or is not readable.')
        try:
            return cgr(cwd=value)
        except subprocess.CalledProcessError:
            raise ValueError(f'"{value}" is not a valid git repository.')


class Config(BaseModel):
    author: str
    ignore: List[str] = [
        "index on",
        "WIP on",
    ]
    limit: int = 400
    dummy: str = "PR Reviews, non coding work"
    datefmt: str = "%d/%m/%Y"
    hours: int = 8
    projects: Dict[str, List[Repo]] = {"default": []}


def fix(line: str) -> str:
    line = line.replace('"', "")
    line = re.sub(r"\(.*\)", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def valid(line: str, ignore: List[str]) -> bool:
    return bool(line) and not any(line.startswith(prefix) for prefix in ignore)


def cgr(cwd: str = None) -> str:
    return (
        subprocess.check_output(
            [
                "git",
                "rev-parse",
                "--show-toplevel",
            ],
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
        .decode()
        .strip()
    )


def balance(sources: List[str], cap: int) -> List[str]:
    if sum(len(source) for source in sources) < cap:
        return sources
    even = (cap // len(sources)) - len(sources)
    if all(len(source) >= even for source in sources):
        return [source[: even - 3] + "..." for source in sources]
    extra = sum(len(source) - even for source in sources if len(source) < even) // sum(
        len(source) > even for source in sources
    )
    return [
        source[: even + extra - 3] + "..." if len(source) > even else source
        for source in sources
    ]


class Context:
    def __init__(self, config, project) -> None:
        self.config_path: Path = config
        self.project: str = project
        self._config: Optional[Config] = None

    @property
    def config(self) -> Config:
        if self._config:
            return self._config
        try:
            with open(self.config_path) as config_file:
                self._config = Config(**toml.load(config_file))
        except ValidationError as e:
            click.secho(
                f'Your config is invalid, consider "codelog config init"\n{e}', err=True
            )
            sys.exit(1)
        return self._config

    @property
    def repos(self) -> List[Repo]:
        return self.config.projects.get(self.project, [])

    def write(self, config: Config):
        with open(self.config_path, "w") as config_file:
            return toml.dump(config.dict(), config_file)

    def fetch(self):
        for repo in self.repos:
            try:
                subprocess.call(["git", "pull"], cwd=repo.path)
            except subprocess.CalledProcessError:
                click.secho('"{path}" is not a git repository', err=True)
                sys.exit(1)

    def messages(
        self, start: datetime.datetime, end: datetime.datetime
    ) -> Iterator[str]:
        for repo in self.repos:
            try:
                output = subprocess.check_output(
                    [
                        "git",
                        "--no-pager",
                        "log",
                        r"--pretty=format:%s",
                        "--all",
                        "--author",
                        f"{self.config.author}",
                        f"--before={end.isoformat()}",
                        f"--after={start.isoformat()}",
                    ],
                    cwd=repo.path,
                ).decode()
                lines = [fix(line) for line in output.split("\n") if line]
                lines = [line for line in lines if valid(line, self.config.ignore)]
                if not lines:
                    continue
                non_merges = [line for line in lines if not line.startswith("Merge")]
                if len(lines) > len(non_merges):
                    yield f"[{repo.name}]: " + ", ".join(["PR Reviews", *non_merges])
                else:
                    yield f"[{repo.name}]: " + ", ".join(lines)
            except subprocess.CalledProcessError:
                click.secho('"{path}" is not a git repository', err=True)
                sys.exit(1)

    def report(
        self,
        start: datetime.datetime,
        end: datetime.datetime,
        limit: Optional[int] = None,
        default: Optional[str] = None,
    ) -> str:
        """
        Balanced string report of all the projects.
        """
        messages = list(self.messages(start, end))
        if not messages and default:
            return default
        if limit:
            return " ".join(balance(list(messages), limit))
        return " ".join(messages)


class CtxType(Protocol):
    obj: Context


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


@main.group()
def config():
    """
    Codelog config management.
    """


@config.command()
@click.pass_context
def init(ctx):
    try:
        author = (
            subprocess.check_output(
                [
                    "git",
                    "config",
                    "--global",
                    "user.name",
                ],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        ctx.obj.write(Config(author=author))
    except subprocess.CalledProcessError:
        click.secho("Make sure git is installed on your system.", err=True)
        sys.exit(1)


@config.command()
@click.option("-n", "--name", default=None, help="name of the repo to add")
@click.pass_context
def track(ctx, name):
    try:
        original = ctx.obj.config.dict()
        path = cgr()
        if name is None:
            name = os.path.basename(path)
        repos = original.get("projects", {}).get(ctx.obj.project, [])
        ctx.obj.write(
            Config(
                **{
                    **original,
                    "projects": {
                        **original.get("projects", {}),
                        ctx.obj.project: [
                            *repos,
                            Repo(name=name, path=path),
                        ],
                    },
                }
            )
        )
    except subprocess.CalledProcessError:
        click.secho("Not a git repository", err=True)
        sys.exit(1)


@config.command()
@click.pass_context
def show(ctx):
    click.echo(open(ctx.obj.config_path).read())


@config.command()
@click.pass_context
def edit(ctx):
    new_conf = click.edit(open(ctx.obj.config_path).read(), require_save=False)
    try:
        ctx.obj.write(Config(**toml.loads(new_conf)))
    except ValidationError:
        click.secho("Your new config is not valid.", err=True)
        sys.exit(1)
    except toml.TomlDecodeError:
        click.secho("Your new config is not a valid toml file.", err=True)
        sys.exit(1)


def date(val: str) -> Arrow:
    parsed = dateparser.parse(val)
    if parsed is None:
        raise ValueError(f'"{val}" is not a valid date')
    return Arrow.fromdatetime(parsed)


@main.command()
@click.option("--from", "start", default="today", help="Start date", type=date)
@click.option("--to", "end", default="today", help="End date", type=date)
@click.option("--output", "-o", default="-", help="End date", type=click.File("w"))
@click.pass_context
def report(ctx: CtxType, start: Arrow, end: Arrow, output: click.File):
    """Generate your day's work report"""
    headers = ["date", "text", "hours"]
    rows = [
        {
            "date": _from.date(),
            "text": ctx.obj.report(
                _from.datetime,
                _until.datetime,
                limit=ctx.obj.config.limit,
                default=ctx.obj.config.dummy,
            ),
            "hours": ctx.obj.config.hours,
        }
        for _from, _until in Arrow.span_range(
            "day", start.floor("day").datetime, end.ceil("day").datetime
        )
        if _from.weekday() not in (5, 6)
    ]
    if rows:
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


@main.command()
@click.pass_context
def fetch(ctx):
    """Generate your day's work report"""
    ctx.obj.fetch()
    click.secho("All repos fetched", fg="green")


if __name__ == "__main__":
    main(project=None, config=None)
