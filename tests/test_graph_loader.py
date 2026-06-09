import os
import tempfile
from unittest.mock import MagicMock, call, patch

import networkx as nx
import pytest

from routeiq.graph import GraphLoader


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
    def test_downloads_and_saves_on_cache_miss(self, tmploader):
        fake_graph = _mock_graph()
        with (
            patch("osmnx.graph_from_bbox", return_value=fake_graph) as mock_dl,
            patch("osmnx.save_graphml") as mock_save,
        ):
            G = tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        mock_dl.assert_called_once()
        mock_save.assert_called_once()
        assert G is fake_graph

    def test_cache_key_format(self, tmploader):
        fake_graph = _mock_graph()
        with (
            patch("osmnx.graph_from_bbox", return_value=fake_graph),
            patch("osmnx.save_graphml") as mock_save,
        ):
            tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        saved_path = mock_save.call_args[0][1]
        assert "n30.350_s29.320_e-97.600_w-98.600" in saved_path

    def test_different_bboxes_trigger_two_downloads(self, tmploader):
        fake_graph = _mock_graph()
        with (
            patch("osmnx.graph_from_bbox", return_value=fake_graph) as mock_dl,
            patch("osmnx.save_graphml"),
        ):
            tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)
            tmploader.load(north=31.000, south=30.000, east=-97.000, west=-98.000)

        assert mock_dl.call_count == 2


class TestGraphLoaderDiskHit:
    def test_loads_from_disk_on_second_process(self, tmp_path):
        fake_graph = _mock_graph()
        key = "n30.350_s29.320_e-97.600_w-98.600"
        fake_path = str(tmp_path / f"{key}.graphml")

        # simulate file already on disk
        open(fake_path, "w").close()

        loader = GraphLoader(cache_dir=str(tmp_path))
        with (
            patch("osmnx.load_graphml", return_value=fake_graph) as mock_load,
            patch("osmnx.graph_from_bbox") as mock_dl,
        ):
            G = loader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        mock_load.assert_called_once()
        mock_dl.assert_not_called()
        assert G is fake_graph


class TestGraphLoaderInMemoryCache:
    def test_second_call_same_bbox_downloads_once(self, tmploader):
        fake_graph = _mock_graph()
        with (
            patch("osmnx.graph_from_bbox", return_value=fake_graph) as mock_dl,
            patch("osmnx.save_graphml"),
        ):
            G1 = tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)
            G2 = tmploader.load(north=30.350, south=29.320, east=-97.600, west=-98.600)

        assert mock_dl.call_count == 1
        assert G1 is G2
