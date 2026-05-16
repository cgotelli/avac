import geopandas as gpd
from shapely.geometry import Polygon

from gui.shape_services import (
    add_polygon_from_wkt,
    add_rectangle_feature,
    delete_features,
    update_feature_wkt,
)


def _empty_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(data={"feature_name": []}, geometry=[], crs="EPSG:4326")


def test_add_polygon_from_wkt() -> None:
    frame = _empty_frame()
    out = add_polygon_from_wkt(frame, "POLYGON ((0 0, 1 0, 1 1, 0 0))", {"feature_name": "a"})
    assert len(out) == 1
    assert out.iloc[0]["feature_name"] == "a"
    assert isinstance(out.geometry.iloc[0], Polygon)


def test_update_feature_wkt() -> None:
    frame = add_polygon_from_wkt(_empty_frame(), "POLYGON ((0 0, 2 0, 2 2, 0 0))", {"feature_name": "a"})
    out = update_feature_wkt(frame, 0, "POLYGON ((0 0, 3 0, 3 3, 0 0))")
    assert out.geometry.iloc[0].area > frame.geometry.iloc[0].area


def test_add_rectangle_and_delete() -> None:
    frame = _empty_frame()
    frame = add_rectangle_feature(frame, 10.0, 10.0, 20.0, 30.0, "rect")
    frame = add_rectangle_feature(frame, 0.0, 0.0, 1.0, 1.0, "small")
    assert len(frame) == 2

    out = delete_features(frame, [0])
    assert len(out) == 1
    assert out.iloc[0]["feature_name"] == "small"
