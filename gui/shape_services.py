from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely import wkt
from shapely.geometry import Polygon, box


def load_vector(path: Path) -> gpd.GeoDataFrame:
    frame = gpd.read_file(Path(path))
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    if "feature_name" not in frame.columns:
        frame["feature_name"] = [f"feature_{i + 1}" for i in range(len(frame))]
    return frame


def save_vector(frame: gpd.GeoDataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)


def export_vector(frame: gpd.GeoDataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".json", ".geojson"}:
        frame.to_file(path, driver="GeoJSON")
        return
    if suffix == ".gpkg":
        frame.to_file(path, driver="GPKG")
        return
    frame.to_file(path)


def add_polygon_from_wkt(frame: gpd.GeoDataFrame, wkt_value: str, attrs: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    geom = wkt.loads(wkt_value)
    if not isinstance(geom, Polygon):
        raise ValueError("Only Polygon geometry is supported for AVAC starting areas")
    data = attrs or {}
    record = {**data, "geometry": geom}
    return gpd.GeoDataFrame([record], crs=frame.crs).pipe(lambda new_frame: gpd.GeoDataFrame(
        data=list(frame.to_dict("records")) + list(new_frame.to_dict("records")),
        geometry="geometry",
        crs=frame.crs,
    ))


def add_rectangle_feature(frame: gpd.GeoDataFrame, xmin: float, ymin: float, xmax: float, ymax: float, name: str) -> gpd.GeoDataFrame:
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("Invalid bounds for rectangle")
    rect = box(xmin, ymin, xmax, ymax)
    next_name = name.strip() or f"feature_{len(frame) + 1}"
    new = gpd.GeoDataFrame([{"feature_name": next_name, "geometry": rect}], geometry="geometry", crs=frame.crs)
    return gpd.GeoDataFrame(
        data=list(frame.to_dict("records")) + list(new.to_dict("records")),
        geometry="geometry",
        crs=frame.crs,
    )


def update_feature_wkt(frame: gpd.GeoDataFrame, row_index: int, wkt_value: str) -> gpd.GeoDataFrame:
    if row_index < 0 or row_index >= len(frame):
        raise IndexError("row_index out of range")
    geom = wkt.loads(wkt_value)
    if not isinstance(geom, Polygon):
        raise ValueError("Only Polygon geometry is supported for AVAC starting areas")
    updated = frame.copy()
    updated.at[row_index, "geometry"] = geom
    return updated


def delete_features(frame: gpd.GeoDataFrame, indices: list[int]) -> gpd.GeoDataFrame:
    if not indices:
        return frame
    valid = [idx for idx in indices if 0 <= idx < len(frame)]
    if not valid:
        return frame
    kept = frame.drop(index=valid).reset_index(drop=True)
    return gpd.GeoDataFrame(kept, geometry="geometry", crs=frame.crs)
