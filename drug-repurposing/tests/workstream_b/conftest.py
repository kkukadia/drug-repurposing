import pytest

from models.graph_data import GraphData
from tests.workstream_b.synthetic import make_synthetic


@pytest.fixture(scope="session")
def synth():
    return make_synthetic(seed=0)


@pytest.fixture(scope="session")
def graph(synth) -> GraphData:
    return synth[0]


@pytest.fixture(scope="session")
def ind(synth):
    return synth[1]
