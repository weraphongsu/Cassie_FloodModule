
'''



'''
import ee
import datetime
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape

ee.Initialize(project='servir-ee')

print("✅ Earth Engine initialized.")

# ----------------------------- #
#       USER DEFINED AOI        #
# ----------------------------- #

# OPTION 1: Define a BBox as AOI (min_lon, min_lat, max_lon, max_lat)
use_bbox = True  # Set to False to use a KML file
bbox = [-58.024429, 6.729363, -57.935249, 6.763412]  # Example bounding box

# OPTION 2: Load a KML file as AOI
use_kml = not use_bbox  # Switch to True if using KML
kml_file = "/_use/aoi.kml"  # Replace with actual KML file path

# Define ROI
if use_kml:
    try:
        gdf = gpd.read_file(kml_file, driver="KML")
        geom = gdf.geometry.iloc[0]
        geojson_geom = shape(geom).__geo_interface__
        roi = ee.Geometry(geojson_geom)
    except Exception as e:
        print(f"❌ Error loading KML: {e}")
        roi = ee.Geometry.BBox(*bbox)
else:
    roi = ee.Geometry.BBox(*bbox)

print("✅ AOI Loaded Successfully")

# ----------------------------- #
#   TIME RANGE & PARAMETERS     #
# ----------------------------- #

start_date = datetime.date(1984, 3, 16)
end_date = datetime.date(2024, 12, 31)
low_lying_threshold = 10  # Low-lying threshold (m)

start_date_ee = ee.Date.fromYMD(start_date.year, start_date.month, start_date.day)
end_date_ee = ee.Date.fromYMD(end_date.year, end_date.month, end_date.day)

print("✅ Time range set:", start_date, "to", end_date)

# ----------------------------- #
#         LOAD DATASETS         #
# ----------------------------- #

print("⏳ Loading datasets...")

# Water data
jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory") \
      .filterBounds(roi) \
      .filterDate(start_date_ee, end_date_ee) \
      .select('water')

# Elevation data
srtm = ee.Image("USGS/SRTMGL1_003").clip(roi)

# Land cover data
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").clip(roi)

# Permanent water mask
permanent_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90)

print("✅ Datasets loaded successfully.")

# ----------------------------- #
#    FLOOD FREQUENCY ANALYSIS   #
# ----------------------------- #

print("⏳ Calculating flood frequency...")

def calculate_flood_frequency(collection):
    # Count valid observations (non-permanent water)
    obs_count = collection.map(lambda img: img.gt(0).And(permanent_water.Not())) \
                         .sum().rename('total_obs')
    
    # Count flood observations (water=2 and not permanent water)
    water_count = collection.map(lambda img: img.eq(2).And(permanent_water.Not())) \
                           .sum().rename('total_water')
    
    # Calculate flood frequency percentage
    flood_freq = water_count.divide(obs_count).multiply(100).rename('flood_frequency')
    
    return flood_freq.updateMask(flood_freq.gt(0))

flood_frequency = calculate_flood_frequency(jrc)

print("✅ Flood frequency calculated.")

# ----------------------------- #
#   FLOOD-PRONE AREA DETECTION  #
# ----------------------------- #

print("⏳ Identifying flood-prone areas...")

# Calculate terrain characteristics
slope = ee.Terrain.slope(srtm).rename("slope")
flat_area = slope.lt(5).rename("flat_area")
low_lying = srtm.lt(low_lying_threshold).rename("low_lying")

# Combine criteria for flood-prone areas
flood_prone_mask = low_lying.And(flat_area).And(flood_frequency.gt(0))
flood_prone_area = flood_frequency.updateMask(flood_prone_mask)

print("✅ Flood-prone areas identified.")

# ----------------------------- #
#   FLOODED BUILDING ANALYSIS   #
# ----------------------------- #

print("⏳ Analyzing flooded buildings (raster-based)...")

# 1. Load building polygons and convert to centroids
buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons") \
              .filterBounds(roi)
building_points = buildings.map(lambda f: f.centroid())

# 2. Create building raster (10m resolution)
building_raster = ee.Image().byte().paint(
    featureCollection=building_points,
    color=1
).rename('buildings').clip(roi)

# 3. Count total buildings
total_buildings = building_raster.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=roi,
    scale=10,
    maxPixels=1e13
).get('buildings').getInfo() or 0

print(f"🔍 Total buildings in AOI: {total_buildings}")

# 4. Identify flooded buildings
flooded_buildings = building_raster.updateMask(flood_prone_mask)
flooded_building_count = flooded_buildings.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=roi,
    scale=10,
    maxPixels=1e13
).get('buildings').getInfo() or 0

print(f"✅ Flooded buildings identified: {flooded_building_count}")

# ----------------------------- #
#  FLOODED AREA PER LULC CLASS  #
# ----------------------------- #

print("⏳ Calculating flooded area per LULC class...")

# Define LULC classes
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

# Calculate flooded area per class
flooded_lulc = worldcover.updateMask(flood_prone_mask)
area_km2 = []

for lulc_class, lulc_name in lulc_mapping.items():
    area_m2 = flooded_lulc.eq(lulc_class) \
               .multiply(ee.Image.pixelArea()) \
               .reduceRegion(
                   reducer=ee.Reducer.sum(),
                   geometry=roi,
                   scale=30,
                   maxPixels=1e13
               ).get('Map')
    
    flooded_area_km2 = (area_m2.getInfo() or 0) / 1e6
    area_km2.append({
        "LULC_Class": lulc_class,
        "LULC_Name": lulc_name,
        "Flooded_Area_km²": flooded_area_km2
    })

print("✅ Flooded area per LULC class calculated.")

# ----------------------------- #
#         EXPORT RESULTS        #
# ----------------------------- #

print('⏳ Exporting results...')

# # Export flood-prone area
# export_flood = ee.batch.Export.image.toDrive(
#     image=flood_prone_area,
#     description="FloodProne_Area_Raster",
#     folder="FloodAnalysis",
#     region=roi,
#     scale=30,
#     maxPixels=1e13,
#     fileFormat="GeoTIFF"
# )
# export_flood.start()

# Export flooded buildings
export_buildings = ee.batch.Export.image.toDrive(
    image=flooded_buildings,
    description="Flooded_Buildings_Raster",
    folder="FloodAnalysis",
    region=roi,
    scale=5,
    maxPixels=1e13,
    fileFormat="GeoTIFF"
)
export_buildings.start()

# # Export LULC results
# df = pd.DataFrame(area_km2)
# df.to_csv('_result/flooded_lulc_areas.csv', index=False)

print("✅ Export tasks started.")

# ----------------------------- #
#         PRINT RESULTS         #
# ----------------------------- #

print("\n=== FLOOD ANALYSIS RESULTS ===")
print(f"Total buildings in AOI: {total_buildings}")
print(f"Flooded buildings: {flooded_building_count}")
print("\nFlooded Area (km²) by LULC Class:")
for entry in area_km2:
    print(f"  {entry['LULC_Name']}: {entry['Flooded_Area_km²']:.2f} km²")

print("\n🚀 Exports saved to Google Drive folder 'FloodAnalysis':")
print("- Flood-prone areas (GeoTIFF)")
print("- Flooded buildings (GeoTIFF)")
print("- Flooded area by LULC class (CSV)")









