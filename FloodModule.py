import ee
import datetime
import json

# Initialize Earth Engine API
ee.Initialize(project = 'servir-ee')

# ----------------------------- #
#       USER DEFINED AOI        #
# ----------------------------- #

# OPTION 1: Define a BBox as AOI (min_lon, min_lat, max_lon, max_lat)
use_bbox = True  # Set to False to use a KML file
bbox = [-59.2, 3.2, -58.5, 4.0]  # Example bounding box

# OPTION 2: Load a KML file as AOI
use_kml = not use_bbox  # Switch to True if using KML
kml_file = "path/to/aoi.kml"  # Replace with the actual KML file path

# Function to extract geometry from KML
def load_kml_geometry(file_path):
    with open(file_path, "r") as f:
        kml_data = json.load(f)  # Convert KML to GeoJSON first!
    return ee.Geometry(kml_data["features"][0]["geometry"])  # Extract first geometry

# Set AOI based on selection
if use_bbox:
    roi = ee.Geometry.Rectangle(bbox)  # BBox AOI
elif use_kml:
    roi = load_kml_geometry(kml_file)  # KML AOI
else:
    raise ValueError("No AOI method selected. Set `use_bbox` or `use_kml`.")

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

# ----------------------------- #
#         LOAD DATASETS         #
# ----------------------------- #

# Satellite Data
jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory").filterBounds(roi).filterDate(start_date_ee, end_date_ee)
srtm = ee.Image("USGS/SRTMGL1_003")
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")

# Filter permanent water mask
permanent_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90)
jrc = jrc.map(lambda img: img.updateMask(permanent_water.Not()))

# ----------------------------- #
#    FLOOD FREQUENCY ANALYSIS   #
# ----------------------------- #

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

# ----------------------------- #
#   FLOOD-PRONE AREA DETECTION  #
# ----------------------------- #

slope = ee.Terrain.slope(srtm).rename("slope")
flat_area = slope.lt(5).rename("flat_area")
low_lying = srtm.lt(low_lying_threshold).rename("low_lying")
flood_prone_area = flood_frequency.updateMask(low_lying.And(flat_area))

# ----------------------------- #
#   FLOODED BUILDING ANALYSIS   #
# ----------------------------- #

flooded_buildings = buildings.filterBounds(flood_prone_area.geometry())
flooded_building_count = flooded_buildings.size().getInfo()

# ----------------------------- #
#  FLOODED AREA PER LULC CLASS  #
# ----------------------------- #

lulc_values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]  # ESA WorldCover classes
landcover_masked = worldcover.clip(roi).updateMask(flood_prone_area)
area_km2 = {}

for lulc_class in lulc_values:
    class_mask = landcover_masked.eq(lulc_class)
    area_m2 = class_mask.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=30,
        maxPixels=1e13
    ).getInfo()

    area_km2[lulc_class] = area_m2.get("Map", 0) / 1e6 if area_m2 else 0  # Convert to km²

# ----------------------------- #
#         PRINT RESULTS         #
# ----------------------------- #

print("=== FLOOD ANALYSIS RESULTS ===")
print(f"Flooded Buildings: {flooded_building_count}")
print("Flooded Area (km²) by LULC Class:")
for lulc_class, area in area_km2.items():
    print(f"  Class {lulc_class}: {area:.2f} km²")
