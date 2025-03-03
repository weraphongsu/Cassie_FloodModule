import ee
import datetime
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape

# Initialize Earth Engine API
ee.Initialize(project = 'servir-ee')

print("✅ Earth Engine initialized.")

# ----------------------------- #
#       USER DEFINED AOI        #
# ----------------------------- #

# OPTION 1: Define a BBox as AOI (min_lon, min_lat, max_lon, max_lat)
use_bbox = True  # Set to False to use a KML file
bbox = [-58.024429,6.729363,-57.935249,6.763412]  # Example bounding box

# OPTION 2: Load a KML file as AOI
use_kml = not use_bbox  # Switch to True if using KML
# use_kml = True
kml_file = "/_use/aoi.kml"  # Replace with actual KML file path

# Function to extract geometry from KML
import geopandas as gpd
from shapely.geometry import shape

def load_kml_geometry(kml_file):
    print(f"📂 Loading KML file: {kml_file}")

    try:
        # Read KML using GeoPandas
        gdf = gpd.read_file(kml_file, driver="KML")
        print(f"✅ KML file loaded successfully. Found {len(gdf)} features.")

        # Extract first feature geometry as GeoJSON
        geom = gdf.geometry.iloc[0]  # Get first feature
        geojson_geom = shape(geom).__geo_interface__  # Convert to GeoJSON format

        print("✅ Geometry extracted from KML.")
        return ee.Geometry(geojson_geom)  # Convert to Earth Engine Geometry

    except Exception as e:
        print(f"❌ Error loading KML: {e}")
        return None

# ----------------------------- #
#   TIME RANGE & PARAMETERS     #
# ----------------------------- #

# Time range for analysis
start_date = datetime.date(1984, 3, 16)
end_date = datetime.date(2024, 12, 31)
low_lying_threshold = 10  # Low-lying threshold (m)

# Convert to Earth Engine date objects
start_date_ee = ee.Date.fromYMD(start_date.year, start_date.month, start_date.day)
end_date_ee = ee.Date.fromYMD(end_date.year, end_date.month, end_date.day)

print("✅ Time range set:", start_date, "to", end_date)

# ----------------------------- #
#       DEFINE REGION (AOI)     #
# ----------------------------- #

roi = None  # Initialize ROI as None

if use_kml:  # If using KML, load AOI from KML file
    roi = load_kml_geometry(kml_file)
elif use_bbox:  # If using BBOX, define AOI as a bounding box
    roi = ee.Geometry.BBox(*bbox)  # Convert list to bbox geometry

# 🚨 Ensure ROI is valid before proceeding
if roi is None:
    raise ValueError("❌ ERROR: Region of Interest (ROI) is not defined! Check AOI selection.")

print("✅ AOI Loaded Successfully:", roi.getInfo())  # Debugging check

# ----------------------------- #
#         LOAD DATASETS         #
# ----------------------------- #

print("⏳ Loading datasets...")

# Satellite Data
jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory").filterBounds(roi).filterDate(start_date_ee, end_date_ee)
srtm = ee.Image("USGS/SRTMGL1_003")
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")

print("✅ Datasets loaded successfully.")

# Filter permanent water mask
permanent_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90)
jrc = jrc.map(lambda img: img.updateMask(permanent_water.Not()))

print("✅ Applied water mask.")

# ----------------------------- #
#    FLOOD FREQUENCY ANALYSIS   #
# ----------------------------- #

print("⏳ Calculating flood frequency...")

def calculate_flood_frequency(collection):
    def add_bands(img):
        obs = img.gt(0).rename("obs")
        water = img.select("water").eq(2).rename("water")
        return img.addBands([obs, water])

    collection = collection.map(add_bands)
    total_obs = collection.select("obs").sum().rename("total_obs")
    total_water = collection.select("water").sum().rename("total_water")
    flood_frequency = total_water.divide(total_obs).multiply(100).rename("flood_frequency")
    return flood_frequency.updateMask(flood_frequency.neq(0))

flood_frequency = calculate_flood_frequency(jrc)

print("✅ Flood frequency calculated.")

# ----------------------------- #
#   FLOOD-PRONE AREA DETECTION  #
# ----------------------------- #

print("⏳ Identifying flood-prone areas...")

slope = ee.Terrain.slope(srtm).rename("slope")
flat_area = slope.lt(5).rename("flat_area")
low_lying = srtm.lt(low_lying_threshold).rename("low_lying")
flood_prone_area = flood_frequency.updateMask(low_lying.And(flat_area))


print("✅ Flood-prone areas identified.")

# Ensure flood-prone area is integer
flood_prone_int = flood_prone_area.multiply(100).toInt()

# Convert to vectors with a tolerance to reduce feature count
flood_prone_fc = ee.FeatureCollection(
    flood_prone_int.reduceToVectors(
        geometryType='polygon',
        reducer=ee.Reducer.countEvery(),
        geometry=roi,  # Ensure processing is within the AOI
        scale=30,
        maxPixels=1e13,
        bestEffort=True,  # Reduce output complexity
        tileScale=2  # Reduce memory usage
    )
).map(lambda f: f.simplify(30))  # Simplify geometry

# Buffer before union (simulate error margin)
flood_prone_fc = flood_prone_fc.map(lambda f: f.buffer(30)).union()

# ----------------------------- #
#   FLOODED BUILDING ANALYSIS   #
# ----------------------------- #

# Ensure flood-prone area is clipped to the AOI before vectorization
flood_prone_clipped = flood_prone_area.clip(roi).toInt()  # Convert to integer

# Convert flood image to vector (only flooded areas within AOI)
flood_prone_vector = flood_prone_clipped.reduceToVectors(
    reducer=ee.Reducer.countEvery(),
    geometry=roi,  # Specify AOI to limit vectorization
    geometryType='polygon',
    scale=30,  # Adjust resolution if needed
    maxPixels=1e8
)

# Ensure the flood-prone area is valid geometry
flood_prone_geom = flood_prone_vector.geometry()

# Filter buildings within AOI
buildings_in_aoi = buildings.filterBounds(roi)

# Count total buildings in AOI
total_buildings = buildings_in_aoi.size().getInfo()
print(f"🔍 Total buildings in AOI: {total_buildings}")

# Filter flooded buildings using the converted geometry
flooded_buildings = buildings_in_aoi.filterBounds(flood_prone_geom)

# Count flooded buildings
flooded_building_count = flooded_buildings.size().getInfo()
print(f"✅ Flooded buildings identified: {flooded_building_count}")


# ----------------------------- #
#  FLOODED AREA PER LULC CLASS  #
# ----------------------------- #

print("⏳ Calculating flooded area per LULC class...")

# Define LULC classes and their names
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

lulc_values = list(lulc_mapping.keys())  # ESA WorldCover classes
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

    flooded_area_km2 = area_m2.get("Map", 0) / 1e6 if area_m2 else 0  # Convert to km²

    # Store in list with LULC class name
    area_km2.append({
        "LULC_Class": lulc_class,
        "LULC_Name": lulc_mapping.get(lulc_class, "Unknown"),
        "Flooded_Area_km²": flooded_area_km2
    })

print("✅ Flooded area per LULC class calculated.")


# # ----------------------------- #
# #         EXPORT RESULTS        #
# # ----------------------------- #

## export to drive 

print('Start Export to drive')
print("⏳ Exporting Flood-Prone area...")
export_task = ee.batch.Export.table.toDrive(
    collection=flood_prone_fc,
    description="FloodProne_Area",
    folder="FloodAnalysis",
    fileFormat="GeoJSON"
)
export_task.start()

print("⏳ Exporting AOI Building...")
export_aoi_bld = ee.batch.Export.table.toDrive(
    collection=buildings_in_aoi,
    description="AOI_Buildings",
    folder="FloodAnalysis",
    fileFormat="GeoJSON"
)

export_aoi_bld.start()

print("⏳ Exporting AOI Building...")
export_fld_bld = ee.batch.Export.table.toDrive(
    collection=flooded_buildings,
    description="Flooded_Buildings",
    folder="FloodAnalysis",
    fileFormat="GeoJSON"
)

export_fld_bld.start()

print("⏳ Exporting Flooded area per LULC...")

# --- Export to Google Drive ---
# Convert DataFrame to a FeatureCollection for GEE export
features = []
for row in area_km2:
    feature = ee.Feature(None, row)  # Convert each row to an EE Feature
    features.append(feature)

# Create FeatureCollection
fc = ee.FeatureCollection(features)

# Define Google Drive Export Task
task = ee.batch.Export.table.toDrive(
    collection=fc,
    description="Flooded_Area_Per_LULC",
    fileFormat="CSV",
    folder="FloodAnalysis" 
)

# Start export task
task.start()



# ----------------------------- #
#         PRINT RESULTS         #
# ----------------------------- #

print("\n=== FLOOD ANALYSIS RESULTS ===")
print(f"Flooded Buildings: {flooded_building_count}")
# print("Flooded Area (km²) by LULC Class:")
# # for lulc_class, area in area_km2.items():
# #     print(f"  Class {lulc_class}: {area:.2f} km²")
for entry in area_km2:
    print(f"  Class {entry['LULC_Class']}: {entry['Flooded_Area_km²']:.2f} km²")


# print("\n🚀 Exporting results...")
print(f"- Flooded buildings saved as Shapefile & GeoJSON in Google Drive (folder: 'FloodAnalysis').")
# print(f"- Flooded area per LULC saved as CSV: {csv_filename}.")

