# cassie/src/algorithms/flood_analysis/flood_frequency_analysis.py

import ee

def calculate_flood_frequency(collection):
    """Calculates the flood frequency from a JRC water history collection."""
    def add_bands(img):
        obs = img.gt(0).rename("obs")
        water = img.select("water").eq(2).rename("water")
        return img.addBands([obs, water])

    collection = collection.map(add_bands)
    total_obs = collection.select("obs").sum().rename("total_obs")
    total_water = collection.select("water").sum().rename("total_water")
    flood_frequency = total_water.divide(total_obs).multiply(100).rename("flood_frequency")
    return flood_frequency.updateMask(flood_frequency.neq(0))