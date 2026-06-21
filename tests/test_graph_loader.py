import pickle
from unittest.mock import patch

import networkx as nx
import pytest

from routeiq.graph import GraphLoader


@pytest.fixture(autouse=True)
def _no_enrich(monkeypatch):
    """Patch out OSMnx edge enrichment — these tests verify caching, not speed attributes."""
    monkeypatch.setattr("routeiq.graph.graph_loader.GraphLoader._enrich", lambda self, G: None)


@pytest.fixture
def tmploader(tmp_path):
    return GraphLoader(cache_dir=str(tmp_path))


def _mock_graph():
    G = nx.MultiDiGraph()
    G.add_node(0, x=-98.0, y=29.5)
    G.add_node(1, x=-97.6, y=29.56)
    G.add_edge(0, 1, length=100)
    return G


class TestGraphLoaderCacheMiss:
    def test_downloads_and_saves_on_cache_miss(self, tmploader, tmp_path):
        fake_graph = _mock_graph()
        with patch("osmnx.graph_from_bbox", return_value=fake_graph):
            G = tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        pkl_files = list(tmp_path.glob("*.pkl"))
        assert len(pkl_files) == 1
        assert G is fake_graph

    def test_cache_key_format(self, tmploader, tmp_path):
        fake_graph = _mock_graph()
        with patch("osmnx.graph_from_bbox", return_value=fake_graph):
            tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        pkl_files = list(tmp_path.glob("*.pkl"))
        assert len(pkl_files) == 1
        assert "n30.350_s29.320_e-97.600_w-98.600" in pkl_files[0].name

    def test_different_bboxes_trigger_two_downloads(self, tmploader):
        fake_graph = _mock_graph()
        with patch("osmnx.graph_from_bbox", return_value=fake_graph) as mock_dl:
            tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)
            tmploader.load(north=31.000, south=30.000, east=-97.000, west=-98.000)

        assert mock_dl.call_count == 2


class TestGraphLoaderDiskHit:
    def test_loads_from_pkl_on_second_process(self, tmp_path):
        fake_graph = _mock_graph()
        key = "n30.350_s29.320_e-97.600_w-98.600"
        pkl_path = tmp_path / f"{key}.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(fake_graph, f)

        loader = GraphLoader(cache_dir=str(tmp_path))
        with patch("osmnx.graph_from_bbox") as mock_dl:
            G = loader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        mock_dl.assert_not_called()
        assert set(G.nodes) == set(fake_graph.nodes)

    def test_migrates_graphml_to_pkl(self, tmp_path):
        fake_graph = _mock_graph()
        key = "n30.350_s29.320_e-97.600_w-98.600"
        graphml_path = tmp_path / f"{key}.graphml"
        graphml_path.touch()

        loader = GraphLoader(cache_dir=str(tmp_path))
        with (
            patch("osmnx.load_graphml", return_value=fake_graph) as mock_load,
            patch("osmnx.graph_from_bbox") as mock_dl,
        ):
            G = loader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        mock_load.assert_called_once()
        mock_dl.assert_not_called()
        # Pickle file written as migration artifact
        assert (tmp_path / f"{key}.pkl").exists()
        assert G is fake_graph


class TestGraphLoaderInMemoryCache:
    def test_second_call_same_bbox_downloads_once(self, tmploader):
        fake_graph = _mock_graph()
        with patch("osmnx.graph_from_bbox", return_value=fake_graph) as mock_dl:
            G1 = tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)
            G2 = tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        assert mock_dl.call_count == 1
        assert G1 is G2
