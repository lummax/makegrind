# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os
import sys
import from pathlib import Path
import multiprocessing as mp
import logging

import yaml
import click

import makegrind


def print_report(report, output):
    output.write(yaml.dump(report, default_flow_style=False, sort_keys=False))


def setup_logging(ctx, param, verbose):
    level = [logging.WARNING, logging.INFO, logging.DEBUG]

    fmt = logging.Formatter("%(levelname)s: %(message)s")
    hdl = logging.StreamHandler()
    hdl.setFormatter(fmt)

    log = logging.getLogger()
    log.handlers.clear()
    log.addHandler(hdl)
    log.setLevel(level[min(verbose, len(level) - 1)])


def target_specifier(ctx, param, value):
    targets = []
    for target in value:
        target = target.split(":")
        targets.append(
            {
                "target": arg[0] if arg and arg[0] else None,
                "makefile": os.path.expanduser(arg[1])
                if len(arg) > 1 and arg[1]
                else None,
                "pid": int(arg[2]) if len(arg) > 2 and arg[2] else None,
            }
        )

    return targets


def find_json_files(ctx, param, value):
    logging.debug("Checking %s", str(value))
    if not value:
        value = [os.getcwd()]

    paths = list()
    for path in value:
        if os.path.isfile(path):
            paths.append(path)
        else:
            paths.extend(
                paths.extend([str(file) for file in Path(path).rglob("build.*.json")])
            )

    if not paths:
        raise click.BadParameter(
            "unable to find build.json files in {}".format(", ".join(value))
        )

    logging.debug("Found %d files", len(paths))
    return set(paths)


@click.group(chain=True)
@click.option(
    "-v",
    "--verbose",
    count=True,
    default=0,
    expose_value=False,
    is_eager=True,
    callback=setup_logging,
)
@click.option(
    "-i",
    "--input",
    "infiles",
    help="Path to build.json file or directory to search within",
    multiple=True,
    type=click.Path(exists=True),
    callback=find_json_files,
)
@click.pass_context
def main(ctx, infiles):
    """Analyze build.json files generated by remake"""
    logging.info("Loading files")

    logging.debug("Found files: %s", ", ".join(infiles))
    with mp.Pool() as pool:
        builds = pool.map(makegrind.BuildDiGraph.from_remake, infiles)

    logging.info("Combining graphs")
    graph = makegrind.BuildDiGraph()
    for build in builds:
        graph.update(build)

    ctx.obj = graph


@main.command()
@click.option("-o", "--output", "outfile", type=click.File("w"), default="-")
@click.pass_obj
def summary(graph, outfile):
    """Generate a summary report"""
    logging.info("Generating summary report")
    print_report(makegrind.SummaryReport(graph), outfile)


@main.command()
@click.option(
    "-o", "--output", "outfile", type=click.File("w"), default="callgrind.out.targets"
)
@click.pass_obj
def callgrind(graph, outfile):
    """Generate a single callgrind-formatted file from combined build.json files"""
    logging.info("Generating callgrind file")
    makegrind.dump_callgrind(graph, outfile)


@main.command()
@click.option(
    "-t",
    "--target",
    help="Ensure target is within the path found. Formatted as TARGET:MAKEFILE:PID",
    multiple=True,
    callback=target_specifier,
)
@click.option(
    "-c",
    "--children",
    help="Limit number of children displayed in each node of path",
    default=10,
)
@click.option("-o", "--output", "outfile", type=click.File("w"), default="-")
@click.pass_obj
def paths(graph, target, children, outfile):
    """Show dependency path taking the most time"""
    if target:
        path = makegrind.find_path(
            graph, list(makegrind.find_target(graph, **x) for x in target)
        )
        logging.info("Generating path report")
        print_report(makegrind.PathReport(graph, path, children=children), outfile)
    else:
        logging.info("Generating top path report")
        print_report(makegrind.TopPathReport(graph, children=children), outfile)


@main.command()
@click.option(
    "-n", "--limit", "count", help="Limit output to specified number", default=10
)
@click.option("-p", "--prefix", help="Only include entries from specified subdirectory")
@click.option("-o", "--output", "outfile", type=click.File("w"), default="-")
@click.pass_obj
def dirs(graph, count, prefix, outfile):
    """Show stats on directories taking the most time"""
    logging.info("Generating directory report")
    print_report(makegrind.TopMakefileReport(graph, count, prefix), outfile)


@main.command()
@click.option(
    "-n", "--limit", "count", help="Limit output to specified number", default=10
)
@click.option("-o", "--output", "outfile", type=click.File("w"), default="-")
@click.pass_obj
def recipes(graph, count, outfile):
    """Show stats on recipes taking the most time"""
    logging.info("Generating recipe report")
    print_report(makegrind.TopRecipesReport(graph, count), outfile)


if __name__ == "__main__":
    sys.exit(main())
