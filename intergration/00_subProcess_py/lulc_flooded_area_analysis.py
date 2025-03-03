# cassie/src/algorithms/flood_analysis/lulc_flooded_area_analysis.py

import ee

def analyze_lulc_flooded_area(flood_prone_area, worldcover, roi):
    """Analyzes flooded area per LULC class."""
    lulc_mapping = {
        10: "Tree cover",
        20: "Shrubland",
        30: "Grassland",
        40: "Cropland",
        50: "Built-up",
        60: "Bare / sparse vegetation",
        70: "Snow and ice",
        80: "Permanent water bodies",
        90: "Herbaceous wetland",
        95: "Mangroves",
    }

    lulc_values = list(lulc_mapping.keys())
    landcover_masked = worldcover.clip(roi).updateMask(flood_prone_area)
    area_km2 = []

    for lulc_class in lulc_values:
        class_mask = landcover_masked.eq(lulc_class)
        area_m2 = class_mask.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=30,
            maxPixels=1e13
        ).getInfo()

        flooded_area_km2 = area_m2.get("Map", 0) / 1e6 if area_m2 else 0

        area_km2.append({
            "LULC_Class": lulc_class,
            "LULC_Name": lulc_mapping.get(lulc_class, "Unknown"),
            "Flooded_Area_km²": flooded_area_km2
        })

    return area_km2