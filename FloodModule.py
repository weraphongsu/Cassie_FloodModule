import ee
import geemap
import datetime
import ipywidgets as widgets
from IPython.display import display
import re  # Import regex module

# Initialize Earth Engine API
ee.Initialize()

# Create map
Map = geemap.Map()

# Load GAUL dataset and filter for Guyana
gaul_level1 = ee.FeatureCollection('FAO/GAUL/2015/level1')
guyana = gaul_level1.filter(ee.Filter.eq('ADM0_NAME', 'Guyana'))

# Get list of available cities in Guyana
raw_city_list = guyana.aggregate_array('ADM1_NAME').getInfo()

# Clean region names by removing "(region N°X)"
city_list = [re.sub(r"\s*\(region N°\d+\)", "", name) for name in raw_city_list]

# Define dynamic time period
start_date = datetime.date(1984, 3, 16)
end_date = datetime.date(2024, 12, 31)

# Convert to ee.Date objects
start_date_ee = ee.Date.fromYMD(start_date.year, start_date.month, start_date.day)
end_date_ee = ee.Date.fromYMD(end_date.year, end_date.month, end_date.day)

# Load datasets
jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory")
srtm = ee.Image("USGS/SRTMGL1_003")
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")  # Fixed selection issue
buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")  # Open Buildings dataset

# Interactive widgets
city_selector = widgets.Dropdown(
    options=city_list,
    value=city_list[0],
    description="City:",
)
start_date_picker = widgets.DatePicker(description="Start Date", value=start_date)
end_date_picker = widgets.DatePicker(description="End Date", value=end_date)
low_lying_input = widgets.BoundedFloatText(description="Low-Lying Level (m)", value=10, min=0, max=100, step=1)
base_map_selector = widgets.Dropdown(
    options=["SATELLITE", "OSM"],
    value="SATELLITE",
    description="Base Map:",
)
run_button = widgets.Button(description="Run Analysis", button_style="success")


def update_map(change):
    selected_city = city_selector.value

    # Match the cleaned city name with the original dataset
    raw_city_name = next(name for name in raw_city_list if selected_city in name)
    roi = guyana.filter(ee.Filter.eq('ADM1_NAME', raw_city_name)).geometry()

    start_date = start_date_picker.value
    end_date = end_date_picker.value
    low_lying_threshold = low_lying_input.value  # Get updated low-lying level
    selected_basemap = base_map_selector.value  # Get selected base map

    # Convert to ee.Date objects
    start_date_ee = ee.Date.fromYMD(start_date.year, start_date.month, start_date.day)
    end_date_ee = ee.Date.fromYMD(end_date.year, end_date.month, end_date.day)

    # Filter datasets to ROI
    jrc_filtered = jrc.filterBounds(roi).filterDate(start_date_ee, end_date_ee)
    permanent_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90)
    jrc_filtered = jrc_filtered.map(lambda img: img.updateMask(permanent_water.Not()))

    # Calculate flood frequency
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

    flood_frequency = calculate_flood_frequency(jrc_filtered)
    slope = ee.Terrain.slope(srtm).rename("slope")
    flat_area = slope.lt(5).rename("flat_area")
    low_lying = srtm.lt(low_lying_threshold).rename("low_lying")
    flood_prone_area = flood_frequency.updateMask(low_lying.And(flat_area))

    ### ---------------------- Building Analysis ---------------------- ###
    # **Use original building polygons instead of centroids**
    building_polygons = buildings.filterBounds(roi)
    # Count flooded buildings (filter original polygons)
    flooded_buildings = building_polygons.filterBounds(flood_prone_area.geometry())

    # Count flooded buildings
    building_centroids = buildings.filterBounds(roi).map(lambda f: f.centroid())
    flooded_bld = building_centroids.filterBounds(flood_prone_area.geometry())
    flooded_building_count = flooded_bld.size().getInfo()

    # Landcover visualization
    landcover_roi = worldcover.clip(roi)
    landcover_vis = {
        "bands": ["Map"],
        "min": 10,
        "max": 100,
        "palette": [
            "#006400", "#ffbb22", "#ffff4c", "#f096ff", "#fa0000",
            "#b4b4b4", "#f0f0f0", "#0064c8", "#0096a0", "#00cf75", "#fae6a0"
        ]
    }

    # Remove previous layers safely
    layer_names = [
        "Flood Frequency",
        "Flood-Prone Areas",
        "SRTM DEM",
        "Slope",
        "Land Use (ESA WorldCover)",
        "Buildings",
        "Flooded Buildings"
    ]
    for layer_name in layer_names:
        try:
            Map.remove_layer(layer_name)
        except Exception:
            pass  # Ignore errors if the layer is not found

    # Set the selected base map
    Map.add_basemap(selected_basemap)
    Map.centerObject(roi, 8)

    # Visualization parameters
    dem_vis = {"min": 0, "max": 50, "palette": ["ffffff", "00ff00", "007f00"]}
    slope_vis = {"min": 0, "max": 30, "palette": ["ffffff", "ffcc99", "ff3300"]}
    flood_prone_area_vis = {"min": 0, "max": 50, "palette": ["ffffff", "ff9999", "ff0000"]}
    flood_frequency_vis = {"min": 0, "max": 50, "palette": ["ffffff", "fffcb8", "0905ff"]}
    building_vis = {"color": "blue", "fillColor": "blue", "width": 1}
    flooded_building_vis = {"color": "red", "fillColor": "red", "width": 1}
    # count_label_vis = {"color": "black", "pointSize": 8}

    
    # Add layers
    Map.addLayer(srtm.clip(roi), dem_vis, "SRTM DEM")
    Map.addLayer(slope.clip(roi), slope_vis, "Slope")
    Map.addLayer(flood_frequency.clip(roi), flood_frequency_vis, "Flood Frequency")
    Map.addLayer(flood_prone_area.clip(roi), flood_prone_area_vis, "Flood-Prone Areas")
    Map.addLayer(landcover_roi, landcover_vis, "Land Use (ESA WorldCover)")
    Map.addLayer(building_polygons, building_vis, "Buildings")
    Map.addLayer(flooded_buildings, flooded_building_vis, "Flooded Buildings")
    
    # Add flooded building count as text overlay (legend)
    Map.add_text(
        text=f"Flooded Buildings: {flooded_building_count}",
        position="topright",
        font_size=14,
        text_color="white",
        background_color="black",
        name="Flooded Buildings Count"
    )

    add_legend()


def add_legend():
    legend_dict = {
        "Trees": "#006400",
        "Shrubland": "#ffbb22",
        "Grassland": "#ffff4c",
        "Cropland": "#f096ff",
        "Built-up": "#fa0000",
        "Bare / Sparse Veg": "#b4b4b4",
        "Snow & Ice": "#f0f0f0",
        "Permanent Water": "#0064c8",
        "Herbaceous Wetland": "#0096a0",
        "Mangroves": "#00cf75",
        "Moss / Lichen": "#fae6a0",
    }
    Map.add_legend(title="ESA WorldCover 2020", legend_dict=legend_dict)


# Set the button action
run_button.on_click(update_map)

# Display the widgets
display(city_selector, start_date_picker, end_date_picker, low_lying_input, base_map_selector, run_button)

# Ensure the base map is added initially
Map.addLayerControl()
Map
