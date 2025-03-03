# cassie/src/algorithms/flood_analysis/flood_prone_area_detection.py

import ee

def detect_flood_prone_areas(flood_frequency, srtm, low_lying_threshold, roi):
    """Detects flood-prone areas based on flood frequency, slope, and elevation."""
    slope = ee.Terrain.slope(srtm).rename("slope")
    flat_area = slope.lt(5).rename("flat_area")
    low_lying = srtm.lt(low_lying_threshold).rename("low_lying")
    flood_prone_area = flood_frequency.updateMask(low_lying.And(flat_area))

    flood_prone_int = flood_prone_area.multiply(100).toInt()

    flood_prone_fc = ee.FeatureCollection(
        flood_prone_int.reduceToVectors(
            geometryType='polygon',
            reducer=ee.Reducer.countEvery(),
            geometry=roi,
            scale=30,
            maxPixels=1e13,
            bestEffort=True,
            tileScale=2
        )
    ).map(lambda f: f.simplify(30))

    flood_prone_fc = flood_prone_fc.map(lambda f: f.buffer(30)).union()

    return flood_prone_area, flood_prone_fc