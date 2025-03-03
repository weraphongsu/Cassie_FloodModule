# cassie/src/algorithms/flood_analysis/flooded_building_analysis.py

import ee

def analyze_flooded_buildings(flood_prone_area, buildings, roi):
    """Analyzes flooded buildings based on flood-prone areas and building footprints."""
    flood_prone_clipped = flood_prone_area.clip(roi).toInt()

    flood_prone_vector = flood_prone_clipped.reduceToVectors(
        reducer=ee.Reducer.countEvery(),
        geometry=roi,
        geometryType='polygon',
        scale=30,
        maxPixels=1e8
    )

    flood_prone_geom = flood_prone_vector.geometry()

    buildings_in_aoi = buildings.filterBounds(roi)
    total_buildings = buildings_in_aoi.size().getInfo()

    flooded_buildings = buildings_in_aoi.filterBounds(flood_prone_geom)
    flooded_building_count = flooded_buildings.size().getInfo()

    return total_buildings, flooded_building_count, buildings_in_aoi, flooded_buildings