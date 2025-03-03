# cassie/src/algorithms/utils/aoi_utils.py

import ee
import geopandas as gpd
from shapely.geometry import shape

def load_kml_geometry(kml_file):
    """Loads geometry from a KML file."""
    print(f"📂 Loading KML file: {kml_file}")

    try:
        gdf = gpd.read_file(kml_file, driver="KML")
        print(f"✅ KML file loaded successfully. Found {len(gdf)} features.")

        geom = gdf.geometry.iloc[0]
        geojson_geom = shape(geom).__geo_interface__

        print("✅ Geometry extracted from KML.")
        return ee.Geometry(geojson_geom)

    except Exception as e:
        print(f"❌ Error loading KML: {e}")
        return None