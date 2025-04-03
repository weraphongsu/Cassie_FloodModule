# cassie/src/index.js

import ee
import datetime
from flood_frequency_analysis import calculate_flood_frequency
from flood_prone_area_detection import detect_flood_prone_areas
from flooded_building_analysis import analyze_flooded_buildings
from lulc_flooded_area_analysis import analyze_lulc_flooded_area
from aoi_utils import load_kml_geometry

ee.Initialize(project='servir-ee')
print("✅ Earth Engine initialized.")

use_bbox = True
bbox = [-58.024429, 6.729363, -57.935249, 6.763412]

use_kml = not use_bbox
kml_file = "/_use/aoi.kml"

start_date = datetime.date(1984, 3, 16)
end_date = datetime.date(2024, 12, 31)
low_lying_threshold = 10

start_date_ee = ee.Date.fromYMD(start_date.year, start_date.month, start_date.day)
end_date_ee = ee.Date.fromYMD(end_date.year, end_date.month, end_date.day)

print("✅ Time range set:", start_date, "to", end_date)

roi = None
if use_kml:
    roi = load_kml_geometry(kml_file)
elif use_bbox:
    roi = ee.Geometry.BBox(*bbox)

if roi is None:
    raise ValueError("❌ ERROR: Region of Interest (ROI) is not defined! Check AOI selection.")

print("✅ AOI Loaded Successfully:", roi.getInfo())

print("⏳ Loading datasets...")
jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory").filterBounds(roi).filterDate(start_date_ee, end_date_ee)
srtm = ee.Image("USGS/SRTMGL1_003")
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
print("✅ Datasets loaded successfully.")

permanent_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90)
jrc = jrc.map(lambda img: img.updateMask(permanent_water.Not()))
print("✅ Applied water mask.")

print("⏳ Calculating flood frequency...")
print("⏳ Calculating flood frequency...")
flood_frequency = calculate_flood_frequency(jrc)  #Call the function
print("✅ Flood frequency calculated.")

print("⏳ Identifying flood-prone areas...")
flood_prone_area, flood_prone_fc = detect_flood_prone_areas(flood_frequency, srtm, low_lying_threshold, roi)  #Call the function
print("✅ Flood-prone areas identified.")

total_buildings, flooded_building_count, buildings_in_aoi, flooded_buildings = analyze_flooded_buildings(flood_prone_area, buildings, roi)
print(f"🔍 Total buildings in AOI: {total_buildings}")
print(f"✅ Flooded buildings identified: {flooded_building_count}")

print("⏳ Calculating flooded area per LULC class...")
area_km2 = analyze_lulc_flooded_area(flood_prone_area, worldcover, roi)  #Call the function
print("✅ Flooded area per LULC class calculated.")

# ----------------------------- #
#         EXPORT RESULTS        #
# ----------------------------- #

print("\n🚀 Exporting results...")

# --- Export Flood-Prone Area ---
print("⏳ Exporting Flood-Prone area...")
task_flood_prone = ee.batch.Export.table.toDrive(
    collection=flood_prone_fc,
    description="FloodProne_Area",
    folder="FloodAnalysis",
    fileFormat="GeoJSON"
)
task_flood_prone.start()

# --- Export Buildings ---
print("⏳ Exporting AOI Buildings...")
task_aoi_buildings = ee.batch.Export.table.toDrive(
    collection=buildings_in_aoi,
    description="AOI_Buildings",
    folder="FloodAnalysis",
    fileFormat="GeoJSON"
)
task_aoi_buildings.start()

print("⏳ Exporting Flooded Buildings...")
task_flooded_buildings = ee.batch.Export.table.toDrive(
    collection=flooded_buildings,
    description="Flooded_Buildings",
    folder="FloodAnalysis",
    fileFormat="GeoJSON"
)
task_flooded_buildings.start()

# --- Export Flooded Area per LULC ---
print("⏳ Exporting Flooded area per LULC...")

# Convert area_km2 to a FeatureCollection
features = []
for row in area_km2:
    feature = ee.Feature(None, row)
    features.append(feature)
lulc_fc = ee.FeatureCollection(features)

task_lulc_flooded = ee.batch.Export.table.toDrive(
    collection=lulc_fc,
    description="Flooded_Area_Per_LULC",
    fileFormat="CSV",
    folder="FloodAnalysis"
)
task_lulc_flooded.start()

print("\n=== FLOOD ANALYSIS RESULTS ===")
