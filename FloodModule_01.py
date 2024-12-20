import geemap
import ee
# Initialize the Earth Engine API
ee.Initialize()

# gaul = ee.FeatureCollection('FAO/GAUL/2015/level1')
# guyana = gaul.filter(ee.Filter.eq("ADM0_NAME", "Guyana"))

gaul_level1 = ee.FeatureCollection('FAO/GAUL/2015/level1')
guyana = gaul_level1.filter(ee.Filter.eq('ADM0_NAME', 'Guyana'))
georgetown = guyana.filter(ee.Filter.eq('ADM1_NAME', 'Georgetown'))

roi = guyana.geometry()


# Define dynamic time period
start_date = "2005-01-01"
end_date = "2005-12-31"

# Load datasets
jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory")
srtm = ee.Image("USGS/SRTMGL1_003")

# Filter JRC dataset for the selected time period and region
jrc_filtered = jrc.filterBounds(roi).filterDate(start_date, end_date)

# Step 1: Exclude permanent water bodies
permanent_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90)
jrc_filtered = jrc_filtered.map(lambda img: img.updateMask(permanent_water.Not()))

# Step 2: Calculate Flood Frequency
def calculate_flood_frequency(collection):
    # Detect observations and water occurrences
    def add_bands(img):
        obs = img.gt(0).rename("obs")
        water = img.select("water").eq(2).rename("water")
        return img.addBands([obs, water])
    
    collection = collection.map(add_bands)
    total_obs = collection.select("obs").sum().rename("total_obs")
    total_water = collection.select("water").sum().rename("total_water")
    flood_frequency = total_water.divide(total_obs).multiply(100).rename("flood_frequency")
    return flood_frequency.updateMask(flood_frequency.neq(0))

flood_frequency = calculate_flood_frequency(jrc_filtered)

# Step 3: Analyze DEM
# Calculate slope and flat areas
slope = ee.Terrain.slope(srtm).rename("slope")
flat_area = slope.lt(5).rename("flat_area")  
low_lying = srtm.lt(10).rename("low_lying")  
# Step 4: Flood-Prone Areas
flood_prone_area = flood_frequency.updateMask(low_lying.And(flat_area))

# Step 5: Monthly Water Surface Maps
# def calculate_monthly_water_surface(img):
#     water_surface = img.select("water").eq(2).rename("water_surface")
#     return water_surface.set("system:time_start", img.get("system:time_start"))

# monthly_water_surface = jrc_filtered.map(calculate_monthly_water_surface)
def get_monthly_flood_layers(collection, roi):
    """
    Extracts monthly flood layers from the given collection.
    """
    monthly_layers = {}
    months = collection.aggregate_array("system:index").getInfo()
    for month in months:
        img = collection.filter(ee.Filter.eq("system:index", month)).first()
        monthly_layers[month] = img.clip(roi).select("water")
    return monthly_layers

monthly_layers = get_monthly_flood_layers(jrc_filtered, roi)

# Visualization parameters
dem_vis = {"min": 0, "max": 50, "palette": ["ffffff", "00ff00", "007f00"]}
slope_vis = {"min": 0, "max": 30, "palette": ["ffffff", "ffcc99", "ff3300"]}
flat_area_vis = {"min": 0, "max": 1, "palette": ["ffffff", "0000ff"]}
flood_frequency_vis = {"min": 0, "max": 50, "palette": ["ffffff", "fffcb8", "0905ff"]}
flood_prone_area_vis = {"min": 0, "max": 50, "palette": ["ffffff", "ff9999", "ff0000"]}
water_surface_vis = {"min": 0, "max": 1, "palette": ["0000ff"]}

# Add layers to the map
print("Adding layers to the map...")
Map = geemap.Map()
Map.centerObject(roi, 8)
Map.addLayer(srtm.clip(roi), dem_vis, "SRTM DEM")
Map.addLayer(slope.clip(roi), slope_vis, "Slope")
Map.addLayer(flat_area.clip(roi), flat_area_vis, "Flat Areas")
Map.addLayer(flood_frequency.clip(roi), flood_frequency_vis, f"Flood Frequency from {start_date} to {end_date}")
Map.addLayer(flood_prone_area.clip(roi), flood_prone_area_vis, f"Flood-Prone Areas from {start_date} to {end_date}")

for month, layer in monthly_layers.items():
    Map.addLayer(layer, water_surface_vis, f"Water Surface {month}")

Map.addLayerControl()
Map


