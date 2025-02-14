## PyHSPF Examples

This folder contains a number of example scripts designed to illustrate different concepts needed to use HSPF and how PyHSPF can help accomplish these tasks. The examples are designed such that the assumptions in a particular script can be modified. For example, start and end dates, watershed HUC, or latitudes/longitudes are intended to be relatively arbitrary choices that are modifiable. Please adapt the assumptions in the scripts and report changes that result in errors. 

The examples in each subdirectory are subdivided into the following groups:

**Introduction:** These examples are designed to illustrate how HSPF organizes information about the world into a computer program and how PyHSPF can be supply this information to HSPF. The data supplied directly in these scripts can be provided using the extraction and processing tools illustrated in the other sections.

**Tests:** These scripts were developed to run the test simulations distributed with the HSPF source code. The scripts may be of interest to watershed modelers who are already familiar with HSPF and want a deeper understanding of how PyHSPF interacts with the HSPF library. Information from the real world must be translated into the User Control Input (UCI) and Watershed Data Management (WDM) files to perform HSPF simulations. Existing UCI files could be adapted and run in Python using the approaches outlines in these examples. 

**GIS:** Python has many modules that are useful for working with Geographic Information Systems (GIS) data. Hydrography and land use data associated with GIS are an essential part of HSPF models. PyHSPF integrates built-in Python modules with extension modules (PyShp, GDAL, and Pillow) to extract data from a few particularly useful publically-available data sets including the National Hydrography Dataset Plus Version 2 (NHDPlus), the Cropland Data Layer (CDL), and the National Inventory of Dams (NID). These tools can expedite extraction and integration of data in new watersheds into HSPF models in the United States. Similar tools could be developed for other publically-available datasets.

**Timeseries:** Many external time series are required to supply climate forcing for HSPF models. PyHSPF has a number of utilities to gather time series data from publically-available databases including the National Water Information System (NWIS), the Global Historical Climate Network Daily (GHCND) database, the Global Summary of the Day (GSOD) database, the National Solar Radiation Database (NSRDB), and the National Climate Data Center's cooperative hourly precipitation database (DSI-3240). 

**ClimateProcessor:** The raw climate time series data gathered from the various databases are typically not suitable for hydrologic modeling for a variety of reasons. For example, some of the data may be missing or errors may have been made in reporting. Since HSPF models require estimates of the conditions throughout the watershed, "point" observations from individual stations must be interpolated/extrapolated throughout the watershed. PyHSPF has a ClimateProcessor class to assist with the aggregation and disaggregation of time series data.

**Evapotranspiration:** One of the essential time series for HSPF models is the potential evapotranspiration (PET) for each land segment. There are a number of methods for estimating PET including the Penman-Moneith Equation. PyHSPF has an ETCalculator class that utilizes a daily and sub-daily form of this equation to estimate the PET time series for land segments in a watershed.

**Special Actions:** This section needs work, but there is one example. Special Actions are designed to represent how the activities of humans modify hydrological processes in HSPF. Some examples of this include tilling, harvesting, pesticide and fertilizer applications.

**Advanced:** The scripts in this directory illustrate how to integrate data into HSPF models using the preprocessing tools (thus enabling the construction of complicated models).

Questions and suggestions are always welcome. The examples may not be compatible with older versions of the software. Please report any problems running the scripts in these directories (check that any required data files in the right location first).
