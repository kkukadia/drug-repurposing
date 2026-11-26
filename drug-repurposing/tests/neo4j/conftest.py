import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterator

import pytest
from neo4j import Driver, GraphDatabase

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="session")
def neo4j_server() -> Iterator[dict[str, str]]:
    if not docker_ready():
        pytest.skip("docker is not available")
    password = secrets.token_urlsafe(16)
    cid = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            "127.0.0.1::7687",
            "-e",
            f"NEO4J_AUTH=neo4j/{password}",
            "neo4j:5-community",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    try:
        port = (
            subprocess.run(
                ["docker", "port", cid, "7687/tcp"], capture_output=True, text=True, check=True
            )
            .stdout.split(":")[-1]
            .strip()
        )
        uri = f"bolt://127.0.0.1:{port}"
        deadline = time.time() + 120
        while True:
            try:
                with GraphDatabase.driver(uri, auth=("neo4j", password)) as d:
                    d.verify_connectivity()
                break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(2)
        yield {"uri": uri, "user": "neo4j", "password": password}
    finally:
        subprocess.run(["docker", "stop", cid], capture_output=True)


@pytest.fixture
def driver(neo4j_server: dict[str, str]) -> Iterator[Driver]:
    d = GraphDatabase.driver(
        neo4j_server["uri"], auth=(neo4j_server["user"], neo4j_server["password"])
    )
    with d.session() as s:
        s.run("MATCH (n) DETACH DELETE n").consume()
    yield d
    d.close()


@pytest.fixture
def loaded(driver: Driver) -> Driver:
    import pandas as pd

    from graph.neo4j_load import load_graph

    load_graph(
        driver,
        pd.read_parquet(FIX / "graph" / "nodes.parquet"),
        pd.read_parquet(FIX / "graph" / "edges.parquet"),
        pd.read_parquet(FIX / "results" / "candidates.parquet"),
    )
    return driver
