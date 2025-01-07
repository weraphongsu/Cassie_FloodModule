
		Map.setCenter(97.75360107421875, 13.553886614976648, 7);
		var geoJsonBoundaryGeometry = ee.Geometry.Polygon([97.75360107421875,13.553886614976648,97.75360107421875,15.304054942239205,99.50454711914062,15.304054942239205,99.50454711914062,13.553886614976648,97.75360107421875,13.553886614976648]);
		var areaBoundary = ee.FeatureCollection([ee.Feature(geoJsonBoundaryGeometry)]);

		var	jrcSurfaceWater = ee.ImageCollection('JRC/GSW1_3/YearlyHistory').filter(ee.Filter.calendarRange(2010, 2010, 'year')).map(function(image) {return image.select('waterClass').eq(3);}).sum().clip(areaBoundary)
    	jrcSurfaceWater = jrcSurfaceWater.updateMask(jrcSurfaceWater.gt(0)) 
    	jrcSurfaceWater = jrcSurfaceWater.visualize(min=0, max=1, palette=['#00008B'])
                   
    	var jrcSurfaceFlood = ee.ImageCollection('JRC/GSW1_3/YearlyHistory').filter(ee.Filter.calendarRange(2010, 2010, 'year')).map(function(image) {return image.select('waterClass').eq(2);}).sum().clip(areaBoundary)
    	jrcSurfaceFlood = jrcSurfaceFlood.updateMask(jrcSurfaceFlood.gt(0)) 
    	jrcSurfaceFlood = jrcSurfaceFlood.visualize(min=0, max=1, palette=['#FD0303'])

		var LCLU = ee.ImageCollection("ESA/WorldCover/v200").first().clip(areaBoundary);

		var PopulationDensity = ee.Image('CIESIN/GPWv411/GPW_UNWPP-Adjusted_Population_Density/gpw_v4_population_density_adjusted_to_2015_unwpp_country_totals_rev11_2020_30_sec').clip(areaBoundary);
		PopulationDensity = PopulationDensity.visualize({min : 0.0, max : 1000,  palette : ['ffffe7','FFc869', 'ffac1d','e17735','f2552c', '9f0c21']});
				
		var SoilTexture = ee.Image('OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02').clip(areaBoundary).select('b10');
		SoilTexture = SoilTexture.visualize({min: 1.0, max: 12.0, palette: ['d5c36b','b96947','9d3706','ae868f','f86714','46d143','368f20','3e5a14','ffd557','fff72e','ff5a9d','ff005b']});
		
		var HealthCareAccess = ee.Image('Oxford/MAP/accessibility_to_healthcare_2019').select('accessibility').clip(areaBoundary);
		HealthCareAccess = HealthCareAccess.visualize({  min: 1,  max: 60,  palette: ['FFF8DC', 'FFEBCD', 'FFDEAD', 'F5DEB3', 'DEB887', 'D2B48C', 'CD853F', '8B4513', 'A0522D', '8B4513']});

		Map.addLayer(jrcSurfaceWater, {}, 'Permanent Water Data');
		Map.addLayer(jrcSurfaceFlood, {}, 'Inundated Area Data');
		Map.addLayer(LCLU, {}, "LCLU");
		Map.addLayer(PopulationDensity, {}, 'PopulationDensity');
		Map.addLayer(SoilTexture, {}, 'Soil texture class (USDA system)');
		Map.addLayer(HealthCareAccess, {}, 'HealthCareAccessibility');
		Map.addLayer(areaBoundary, {}, 'Boundary');
		