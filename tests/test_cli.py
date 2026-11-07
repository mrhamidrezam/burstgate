import argparse
import pytest
from burstgate.cli import cmd_info, cmd_benchmark, cmd_simulate


def test_cli_info():
    args = argparse.Namespace()
    assert cmd_info(args) == 0


def test_cli_benchmark():
    args = argparse.Namespace(iterations=500)
    assert cmd_benchmark(args) == 0


def test_cli_simulate():
    args = argparse.Namespace(rpm=60, tpm=5000, requests=5)
    assert cmd_simulate(args) == 0
