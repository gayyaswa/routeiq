import os
import pytest
from unittest.mock import patch

from routeiq.ratings.factory import RatingsFactory, _NullRatingProvider
from routeiq.ratings.foursquare import FoursquareRatingProvider
from routeiq.ratings.google_places import GooglePlacesRatingProvider
from routeiq.graph.poi import POI


_POI = POI(name="Test Place", category="tourism", lat=37.8, lon=-122.4, osm_id="way/1")


class TestRatingsFactory:
    def test_foursquare_with_key_returns_foursquare_provider(self):
        with patch.dict(os.environ, {"RATING_PROVIDER": "foursquare", "FOURSQUARE_API_KEY": "test-key"}):
            provider = RatingsFactory.create()
        assert isinstance(provider, FoursquareRatingProvider)

    def test_foursquare_without_key_returns_null_provider(self):
        env = {"RATING_PROVIDER": "foursquare", "FOURSQUARE_API_KEY": ""}
        with patch.dict(os.environ, env):
            # Unset FOURSQUARE_API_KEY entirely
            env_clean = {k: v for k, v in os.environ.items() if k != "FOURSQUARE_API_KEY"}
            with patch.dict(os.environ, env_clean, clear=True):
                provider = RatingsFactory.create()
        assert isinstance(provider, _NullRatingProvider)

    def test_missing_api_key_env_var_returns_null_provider(self):
        env = {k: v for k, v in os.environ.items() if k not in ("FOURSQUARE_API_KEY", "RATING_PROVIDER")}
        with patch.dict(os.environ, env, clear=True):
            provider = RatingsFactory.create()
        assert isinstance(provider, _NullRatingProvider)

    def test_google_places_returns_google_provider(self):
        with patch.dict(os.environ, {"RATING_PROVIDER": "google_places"}):
            provider = RatingsFactory.create()
        assert isinstance(provider, GooglePlacesRatingProvider)

    def test_unknown_provider_returns_null(self):
        with patch.dict(os.environ, {"RATING_PROVIDER": "unknown_xyz"}):
            provider = RatingsFactory.create()
        assert isinstance(provider, _NullRatingProvider)

    def test_null_provider_passes_pois_through(self):
        pois = [_POI]
        rated = _NullRatingProvider().enrich_batch("San Francisco, CA", pois)
        assert len(rated) == 1
        assert rated[0].poi is _POI
        assert rated[0].rating is None
        assert rated[0].review_count is None
