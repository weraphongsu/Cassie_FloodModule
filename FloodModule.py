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
kml_file = "D:/SIG/G_CAS/01_Bathymetry/00_SOURCE1/EPSG4326/_use/aoi.kml"  # Replace with actual KML file path

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

# Export Flood-Prone Area as GeoJSON
# import geopandas as gpd
# import json

# Convert the flood-prone area to a GeoJSON FeatureCollection
flood_prone_geojson = flood_prone_area.geometry().getInfo()

# Define output GeoJSON file path
geojson_filename = "/Users/weraphongsuaruang/Python/Cassie_FloodModule/flood_prone_area.geojson"

# Save the GeoJSON data
with open(geojson_filename, "w") as f:
    json.dump(flood_prone_geojson, f)

print(f"✅ Flood-prone area exported as GeoJSON: {geojson_filename}.")



# ----------------------------- #
#   FLOODED BUILDING ANALYSIS   #
# ----------------------------- #


print("⏳ Identifying flooded buildings...")

# Filter buildings only in the AOI before counting
buildings_in_aoi = buildings.filterBounds(roi)

# Count the buildings in the AOI (instead of the entire dataset)
total_buildings = buildings_in_aoi.size().getInfo()
print(f"🔍 Total buildings in AOI: {total_buildings}")

# Now filter the flooded buildings
test_buildings = buildings_in_aoi.limit(10).filterBounds(flood_prone_area.geometry())
test_count = test_buildings.size().getInfo()

print(f"✅ Test: Found {test_count} buildings in the flood-prone area.")

# If test works, filter all flooded buildings
if test_count > 0:
    flooded_buildings = buildings_in_aoi.filterBounds(flood_prone_area.geometry())
    flooded_building_count = flooded_buildings.size().getInfo()
    print(f"✅ Flooded buildings identified: {flooded_building_count}")
else:
    print("⚠ No buildings found in the flood-prone area.")


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
        "Flooded_Area_km2": flooded_area_km2
    })

print("✅ Flooded area per LULC class calculated.")


# # ----------------------------- #
# #         EXPORT RESULTS        #
# # ----------------------------- #

print("⏳ Exporting results...")

# 1. Export Flooded Buildings as Shapefile & GeoJSON
# export_shapefile = ee.batch.Export.table.toDrive(
#     collection=flooded_buildings,
#     description="Flooded_Buildings_SHP",
#     folder="FloodAnalysis",
#     fileFormat="SHP"
# )

# # Remove geometry from properties before exporting
# def remove_geometry(feature):
#     return feature.setGeometry(None)  # Removes geometry from properties

# # Apply function to FeatureCollection
# flooded_buildings_no_geom = flooded_buildings.map(remove_geometry)

# # Export without geometry in properties
# task = ee.batch.Export.table.toDrive(
#     collection=flooded_buildings_no_geom,
#     description="Flooded_Buildings_SHP",
#     folder="FloodAnalysis",
#     fileFormat="SHP"
# )
# task.start()


# export_geojson = ee.batch.Export.table.toDrive(
#     collection=flooded_buildings,
#     description="Flooded_Buildings_GeoJSON",
#     folder="FloodAnalysis",
#     fileFormat="GeoJSON"
# )

# # export_shapefile.start()
# export_geojson.start()

# print("✅ Flooded buildings export started.")

# 2. Export Flooded Area Per LULC as CSV
# Save to CSV

csv_filename = "/Users/weraphongsuaruang/Python/Cassie_FloodModule/flooded_area_per_lulc3.csv"
csv_data = pd.DataFrame(area_km2)
csv_data.to_csv(csv_filename, index=False)

print(f"✅ Flooded area per LULC saved as CSV: {csv_filename}.")

# ----------------------------- #
#         PRINT RESULTS         #
# ----------------------------- #

# print("\n=== FLOOD ANALYSIS RESULTS ===")
# print(f"Flooded Buildings: {flooded_building_count}")
# print("Flooded Area (km²) by LULC Class:")
# for lulc_class, area in area_km2.items():
#     print(f"  Class {lulc_class}: {area:.2f} km²")

# print("\n🚀 Exporting results...")
# print(f"- Flooded buildings saved as Shapefile & GeoJSON in Google Drive (folder: 'FloodAnalysis').")
# print(f"- Flooded area per LULC saved as CSV: {csv_filename}.")
# print("✅ Script execution completed successfully! 🎉")
