import datetime
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import click
import dateparser
import toml
from pydantic import BaseModel, ValidationError, validator


class Repo(BaseModel):
    name: str
    path: str

    @validator("path")
    def existing_git_repo(cls, value: str) -> str:
        if not os.path.exists(value):
            raise ValueError(f'"{value}" does not exist or is not readable.')
        try:
            return cgr(cwd=value)
        except subprocess.CalledProcessError:
            raise ValueError(f'"{value}" is not a valid git repository.')
        return value


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
        except ValidationError:
            click.secho(
                'Your config is invalid, consider "codelog config init"', err=True
            )
            sys.exit(1)
        return self._config

    @property
    def repos(self) -> List[Repo]:
        return self.config.projects.get(self.project, [])

    def write(self, config: Config):
        with open(self.config_path, "w") as config_file:
            return toml.dump(config.dict(), config_file)

    def report(self, start: datetime.datetime, end: datetime.datetime) -> Iterator[str]:
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


@main.command()
@click.argument("date", nargs=-1)
@click.pass_context
def report(ctx, date):
    """Generate your day's work report"""
    parsed = dateparser.parse(" ".join(date or ["today"]))
    start = datetime.datetime.fromordinal(parsed.date().toordinal())
    end = start + datetime.timedelta(hours=23, minutes=59, seconds=59)
    headers = "date,hours,text"
    messages = list(ctx.obj.report(start, end))
    text = " ".join(balance(messages, ctx.obj.config.limit))
    if not text.strip():
        text = ctx.obj.config.dummy
    content = ",".join(
        [start.strftime(ctx.obj.config.datefmt), str(ctx.obj.config.hours), f'"{text}"']
    )
    output = "\n".join([headers, content])
    click.echo(output)


if __name__ == "__main__":
    main(project=None, config=None)
