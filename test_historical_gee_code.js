// Initialize the map and ROI (Guyana)
var gaulLevel1 = ee.FeatureCollection("FAO/GAUL/2015/level1");
var guyana = gaulLevel1.filter(ee.Filter.eq("ADM0_NAME", "Guyana"));
var roi = guyana.geometry();

// Extract list of available cities in Guyana
var rawCityList = guyana.aggregate_array("ADM1_NAME").getInfo();
var cityList = rawCityList.map(function(name) {
  return name.replace(/\s*\(region N°\d+\)/, ""); // Clean city names
});

// Define dynamic time period
var startDate = ee.Date("1984-03-16");
var endDate = ee.Date("2024-12-31");

// Load datasets
var jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory");
var srtm = ee.Image("USGS/SRTMGL1_003");
var worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map");
var buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons");

// Function to calculate flood frequency
function calculateFloodFrequency(collection) {
  collection = collection.map(function(img) {
    var obs = img.gt(0).rename("obs");
    var water = img.select("water").eq(2).rename("water");
    return img.addBands([obs, water]);
  });
  var totalObs = collection.select("obs").sum().rename("total_obs");
  var totalWater = collection.select("water").sum().rename("total_water");
  return totalWater.divide(totalObs).multiply(100).rename("flood_frequency");
}

// Function to update the map based on user selection
function updateMap(city, lowLyingThreshold, startDate, endDate, baseMap) {
  var rawCityName = rawCityList.find(function(name) {
    return name.includes(city);
  });
  var roiCity = guyana.filter(ee.Filter.eq("ADM1_NAME", rawCityName)).geometry();

  // Filter datasets
  var jrcFiltered = jrc.filterBounds(roiCity).filterDate(startDate, endDate);
  var permanentWater = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(90);
  jrcFiltered = jrcFiltered.map(function(img) {
    return img.updateMask(permanentWater.not());
  });

  var floodFrequency = calculateFloodFrequency(jrcFiltered);
  var slope = ee.Terrain.slope(srtm).rename("slope");
  var flatArea = slope.lt(5).rename("flat_area");
  var lowLying = srtm.lt(lowLyingThreshold).rename("low_lying");
  var floodProneArea = floodFrequency.updateMask(lowLying.and(flatArea));

  // Convert building polygons to centroids
  var buildingCentroids = buildings.filterBounds(roiCity).map(function(f) {
    return f.centroid();
  });
  var floodedBuildings = buildingCentroids.filterBounds(floodProneArea.geometry());
  var floodedBuildingCount = floodedBuildings.size().getInfo();

  // Visualization parameters
  var demVis = { min: 0, max: 50, palette: ["ffffff", "00ff00", "007f00"] };
  var slopeVis = { min: 0, max: 30, palette: ["ffffff", "ffcc99", "ff3300"] };
  var floodFrequencyVis = { min: 0, max: 50, palette: ["ffffff", "fffcb8", "0905ff"] };
  var landcoverVis = {
    bands: ["Map"],
    min: 10,
    max: 100,
    palette: [
      "#006400", "#ffbb22", "#ffff4c", "#f096ff", "#fa0000",
      "#b4b4b4", "#f0f0f0", "#0064c8", "#0096a0", "#00cf75", "#fae6a0"
    ]
  };

  // Add layers to the map
  Map.centerObject(roiCity, 8);
  Map.addLayer(srtm.clip(roiCity), demVis, "SRTM DEM");
  Map.addLayer(slope.clip(roiCity), slopeVis, "Slope");
  Map.addLayer(floodFrequency.clip(roiCity), floodFrequencyVis, "Flood Frequency");
  Map.addLayer(floodProneArea.clip(roiCity), floodFrequencyVis, "Flood-Prone Areas");
  Map.addLayer(worldcover.clip(roiCity), landcoverVis, "Land Use (ESA WorldCover)");
  Map.addLayer(buildingCentroids, { color: "blue" }, "Buildings");
  Map.addLayer(floodedBuildings, { color: "red" }, "Flooded Buildings");

  print("Flooded Buildings:", floodedBuildingCount);
}

// Example usage
updateMap("Region Name", 10, startDate, endDate, "SATELLITE");
