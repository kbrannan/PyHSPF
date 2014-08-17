# delineator.py
#                                                                             
# David J. Lampert (djlampert@gmail.com)
#                                                                             
# last updated: 07/27/2014
#                                                                              
# Purpose: Contains the NHDPlusdelineator class to analyze the NHDPlus data 
# for a watershed and subdivide it according to the criteria specified.

import os, shutil, time, pickle, numpy

from matplotlib import pyplot, path, patches, colors, ticker
from shapefile  import Reader, Writer
from mpl_toolkits.axes_grid1 import make_axes_locatable

from .merge_shapes import merge_shapes
from .raster       import get_raster, get_raster_on_poly, get_raster_in_poly

class NHDPlusDelineator:
    """A class to delineate a watershed using the NHDPlus data."""

    def __init__(self, 
                 attributefile, 
                 flowlinefile, 
                 catchmentfile, 
                 elevfile,
                 gagefile = None, 
                 damfile = None,
                 landuse = None,
                 ):

        self.attributefile = attributefile
        self.flowlinefile  = flowlinefile
        self.catchmentfile = catchmentfile
        self.elevfile      = elevfile
        self.gagefile      = gagefile
        self.damfile       = damfile
        self.landuse       = landuse
        
    def distance2(self, p1, p2):
        """Returns the square of the distance between two points."""

        return((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def closest_index(self, point, shapes, warning = False):
        """Determines the index of the shape in the shapefile that is 
        closest to the point.
        """

        x, y = point[0], point[1]

        # find all flowlines that have a bounding box around the point

        matches = []

        i = 0
        for shape in shapes:
            bbox = shape.bbox
            xmin, ymin, xmax, ymax = bbox[0], bbox[1], bbox[2], bbox[3]

            if xmin < x and x < xmax and ymin < y and y < ymax: 
                matches.append(i)
            i+=1

        if len(matches) == 0:

            if warning: print('unable to find a flowline with appropriate ' +
                              'bounding box, increasing tolerance\n')

            i = 0
            for shape in shapes:

                bbox = shape.bbox

                xmin = bbox[0] - (bbox[2] - bbox[0])
                xmax = bbox[2] + (bbox[2] - bbox[0])
                ymin = bbox[1] - (bbox[3] - bbox[1])
                ymax = bbox[3] + (bbox[3] - bbox[1])

                if xmin < x and x < xmax and ymin < y and y < ymax: 
                    matches.append(i)
                i+=1

        if len(matches) > 1:

            # if more than one bounding box contains the outlet, then find the
            # line with the point closest to the outlet

            if warning:
                print('multiple possible matches found, determining best\n')

            distances = []
            for i in matches:
                shape   = shapes[i]
                bbox   = shape.bbox
                points = shape.points

                distance = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
                for p in points:
                    distance = min(distance, get_distance(p, [x, y]))
                distances.append(distance)

            matches = [matches[distances.index(min(distances))]]

        if len(matches) != 1: 
            if warning: print('warning: unable to determine closest flowline')
            return None
        else: return matches[0]

    def find_flowlines(self, points):
        """Determines the comids of the flowlines in the flowline shapefile 
        that correspond to the points argument.
        """

        # open the flowline shapefile

        flowlines = Reader(self.flowlinefile, shapeType = 3)

        # find all the flowline feature attributes

        lines = flowlines.shapes()

        # find the indices of closest flowline for each point

        indices = [self.closest_index(point, lines) for point in points]

        # make a dictionary linking the outlet site index numbers to the 
        # corresponding flowline comids

        comid_index = flowlines.fields.index(['COMID', 'N', 9, 0])  - 1

        comids =[]
        for i in indices:
            if i is not None: comids.append(flowlines.record(i)[comid_index])
            else:             comids.append(None)

        return comids

    def find_comid(self, point):
        """Finds the comid of the flowline closest to the point."""

        # open the flowline shapefile

        flowlines = Reader(self.flowlinefile, shapeType = 3)

        # find the index of the comid in the flowline shapefile

        i = self.closest_index(point, flowlines.shapes())

        # find the comid feature attribute

        comid_index = flowlines.fields.index(['COMID', 'N', 9, 0])  - 1

        return flowlines.record(i)[comid_index]

    def find_gagecomid(self, gageid):
        """Finds the comid of the gage."""
        
        if self.gagefile is None:
            print('error: no gage file specified\n')
            raise

        # open the gage file

        gagereader = Reader(self.gagefile, shapeType = 1)

        # find the field index of the site number

        site_index = gagereader.fields.index(['SITE_NO', 'C', 15, 0]) - 1
        
        # make a list of all the sites

        sites = [r[site_index] for r in gagereader.records()] 

        # find the index of the gage id

        i = sites.index(gageid)

        # get the longitude and latitude

        p = gagereader.shape(i).points[0]

        # find the comid

        return self.find_comid(p)

    def find_subbasin_comids(self, outletcomid, verbose = True):
        """Finds the comids of all the flowlines upstream of the outletcomid."""

        # open up the attribute file

        with open(self.attributefile, 'rb') as f: flowlines = pickle.load(f)

        # make a dictionary linking the hydrologic sequences

        hydroseqs = {flowlines[f].comid: f for f in flowlines}

        # group flowlines into subbasins associated with each outlet

        comids = [outletcomid]

        # make a list of all the comids in the subbasin

        current = [hydroseqs[outletcomid]]
        while len(current) > 0:
            last    = current[:]
            current = []

            for comid in hydroseqs:
                if flowlines[hydroseqs[comid]].down in last:
                    comids.append(comid)
                    current.append(hydroseqs[comid])

        if verbose: print('found {} flowlines\n'.format(len(comids)))

        # convert the comid list to an updown dictionary

        updown = {}
        for comid in comids:

            if flowlines[hydroseqs[comid]].down in hydroseqs:

                updown[comid] = hydroseqs[flowlines[hydroseqs[comid]].down]

            else: updown[comid] = 0

        updown[outletcomid] = 0

        return updown

    def delineate_gage_watershed(self, 
                                 gageid, 
                                 output = None,
                                 flowlinefile = 'flowlines',
                                 catchmentfile = 'catchments',
                                 boundaryfile = 'boundary',
                                 plotfile = 'watershed',
                                 verbose = True,
                                 ):
        """Delineates the watershed for the provided NWIS gage id."""

        if output is None:              output = os.getcwd()
        elif not os.path.isdir(output): os.mkdir(output)

        # path to the delineated flowline file

        self.flowlines = '{}/{}'.format(output, flowlinefile)

        # path to the delineated subbasin file

        self.catchments = '{}/{}'.format(output, catchmentfile)

        # path to the watershed boundary file

        self.boundary = '{}/{}'.format(output, boundaryfile)

        if output is None: output = os.getcwd()
        if not os.path.isdir(output): os.mkdir(output)
        
        if (not os.path.isfile(self.flowlines + '.shp') or 
            not os.path.isfile(self.catchments + '.shp')):

            # find the comid of the flowline associated with the gage

            gagecomid = self.find_gagecomid(gageid)

            # find the upstream comids

            updown = self.find_subbasin_comids(gagecomid)

        # extract the flowline shapes from the watershed files

        if not os.path.isfile(self.flowlines + '.shp'):

            # copy the projection

            shutil.copy(self.flowlinefile + '.prj', self.flowlines + '.prj')

            if verbose: print('reading the flowline file\n')
    
            shapefile = Reader(self.flowlinefile, shapeType = 3)
            records   = shapefile.records()
    
            # figure out which field codes are the comid
    
            comid_index = shapefile.fields.index(['COMID', 'N',  9, 0]) - 1
    
            # go through the indices and find the comids
    
            if verbose: 
                print('searching for upstream flowlines in the watershed\n')
    
            indices = []
       
            i = 0
            for record in records:
                if record[comid_index] in updown: indices.append(i)
                i+=1

            if len(indices) == 0:
                if verbose: print('error: query returned no values')
                raise
    
            # write the data for the comids to a new shapefile
    
            w = Writer(shapeType = 3)
    
            for field in shapefile.fields: w.field(*field)
    
            for i in indices:
                shape = shapefile.shape(i)
                w.poly(shapeType = 3, parts = [shape.points])
    
                record = records[i]
    
                # little work around for blank GNIS_ID and GNIS_NAME values
    
                if isinstance(record[3], bytes):
                    record[3] = record[3].decode('utf-8')
                if isinstance(record[4], bytes):
                    record[4] = record[4].decode('utf-8')
    
                w.record(*record)
    
            w.save(self.flowlines)
    
            if verbose: 
                l = len(indices)
                print('queried {} flowlines\n'.format(l))

        # extract the catchment shapes from the watershed files

        if not os.path.isfile(self.catchments + '.shp'):

            # copy the projection

            shutil.copy(self.flowlinefile + '.prj', self.catchments + '.prj')

            if verbose: print('reading the catchment file\n')
    
            shapefile = Reader(self.catchmentfile, shapeType = 5)
            records   = shapefile.records()
    
            # get the index of the feature id, which links to the flowline comid
    
            feature_index = shapefile.fields.index(['FEATUREID', 'N', 9, 0]) - 1
    
            # go through the indices and find the comids
    
            if verbose: 
                print('searching for upstream catchments in the watershed\n')
    
            indices = []
       
            i = 0
            for record in records:
                if record[feature_index] in comids: indices.append(i)
                i+=1

            if len(indices) == 0:
                if verbose: print('error: query returned no values')
                raise
    
            # write the data for the comids to a new shapefile
    
            w = Writer(shapeType = 5)
    
            for field in shapefile.fields: w.field(*field)
    
            for i in indices:
                shape = shapefile.shape(i)
                w.poly(shapeType = 5, parts = [shape.points])    
                record = records[i]
                w.record(*record)
    
            w.save(self.catchments)

        # merge the catchments together to form the watershed boundary

        if not os.path.isfile(self.boundary + '.shp'):
        
            if verbose: print('merging the catchments to form a boundary\n')
    
            print('{}/{}'.format(output, catchmentfile))
            merge_shapes('{}/{}'.format(output, catchmentfile), 
                         outputfile = self.boundary)

        # make a plot of the watershed

        pfile = '{}/{}.png'.format(output, plotfile)
        if not os.path.isfile(pfile):
            self.plot_gage_watershed(gageid, output = pfile)

    def add_basin_landuse(self, landuse):
        """Adds basin-wide land use data to the extractor."""

        self.landuse = landuse
        
    def build_watershed(self,
#subbasinfile, flowfile, outletfile, damfile, gagefile,
#                    landfile, aggregatefile, VAAfile, years, HUC8, output, 
#                    plots = True, overwrite = False, format = 'png'
                        ):

        # create a dictionary to store subbasin data

        subbasins = {}

        # create a dictionary to keep track of subbasin inlets

        inlets = {}

        # read in the flow plane data into an instance of the FlowPlane class

        sf = Reader(self.catchmentfile, shapeType = 5)

        print(sf.fields)

        exit()
        comid_index = sf.fields.index(['ComID',      'N',  9, 0]) - 1
        len_index   = sf.fields.index(['PlaneLenM',  'N',  8, 2]) - 1
        slope_index = sf.fields.index(['PlaneSlope', 'N',  9, 6]) - 1
        area_index  = sf.fields.index(['AreaSqKm',   'N', 10, 2]) - 1
        cx_index    = sf.fields.index(['CenX',       'N', 12, 6]) - 1
        cy_index    = sf.fields.index(['CenY',       'N', 12, 6]) - 1
        elev_index  = sf.fields.index(['AvgElevM',   'N',  8, 2]) - 1

        for record in sf.records():
            comid     = '{}'.format(record[comid_index])
            length    = record[len_index]
            slope     = record[slope_index]
            tot_area  = record[area_index]
            centroid  = [record[cx_index], record[cy_index]]
            elevation = record[elev_index]

            subbasin  = Subbasin(comid)
            subbasin.add_flowplane(length, slope, centroid, elevation)

            subbasins[comid] = subbasin

        # read in the flowline data to an instance of the Reach class

        sf = Reader(self.flowfile)

        outcomid_index   = sf.fields.index(['OutComID',   'N',  9, 0]) - 1
        gnis_index       = sf.fields.index(['GNIS_NAME',  'C', 65, 0]) - 1
        reach_index      = sf.fields.index(['REACHCODE',  'C',  8, 0]) - 1
        incomid_index    = sf.fields.index(['InletComID', 'N',  9, 0]) - 1
        maxelev_index    = sf.fields.index(['MaxElev',    'N',  9, 2]) - 1
        minelev_index    = sf.fields.index(['MinElev',    'N',  9, 2]) - 1
        slopelen_index   = sf.fields.index(['SlopeLenKM', 'N',  6, 2]) - 1
        slope_index      = sf.fields.index(['Slope',      'N',  8, 5]) - 1
        inflow_index     = sf.fields.index(['InFlowCFS',  'N',  8, 3]) - 1
        outflow_index    = sf.fields.index(['OutFlowCFS', 'N',  8, 3]) - 1
        velocity_index   = sf.fields.index(['VelFPS',     'N',  7, 4]) - 1
        traveltime_index = sf.fields.index(['TravTimeHR', 'N',  8, 2]) - 1

        for record in sf.records():

            outcomid   = '{}'.format(record[outcomid_index])
            gnis       = record[gnis_index]
            reach      = record[reach_index]
            incomid    = '{}'.format(record[incomid_index])
            maxelev    = record[maxelev_index] / 100
            minelev    = record[minelev_index] / 100
            slopelen   = record[slopelen_index]
            slope      = record[slope_index]
            inflow     = record[inflow_index]
            outflow    = record[outflow_index]
            velocity   = record[velocity_index]
            traveltime = record[traveltime_index]

            if isinstance(gnis, bytes): gnis = ''

            subbasin = subbasins[outcomid]

            flow = (inflow + outflow) / 2
            subbasin.add_reach(gnis, maxelev, minelev, slopelen, flow = flow, 
                               velocity = velocity, traveltime = traveltime)
            inlets[outcomid] = incomid

        # open up the outlet file and see if the subbasin has a gage or dam

        sf = Reader(outletfile)

        records = sf.records()

        comid_index = sf.fields.index(['COMID',   'N',  9, 0]) - 1
        nid_index   = sf.fields.index(['NIDID',   'C',  7, 0]) - 1
        nwis_index  = sf.fields.index(['SITE_NO', 'C', 15, 0]) - 1

        nids = {'{}'.format(r[comid_index]):r[nid_index] for r in records 
                if isinstance(r[nid_index], str)}

        nwiss = {'{}'.format(r[comid_index]):r[nwis_index] for r in records 
                 if r[nwis_index] is not None}

        # open up the aggregate file to get the landuse group map

        m, landtypes, groups = get_aggregate_map(aggregatefile)

        # convert to a list of landuse names

        names = [landtypes[group] for group in groups]

        # read the land use data for each year into the subbasins

        with open(landfile, 'rb') as f: landyears, landuse = pickle.load(f)

        for comid in subbasins:

            subbasin      = subbasins[comid]
            subbasin_data = landuse[comid]

            for year, data in zip(landyears, zip(*subbasin_data)):

                subbasin.add_landuse(year, names, data)

        # create an instance of the watershed class

        watershed = Watershed(HUC8, subbasins)

        # open up the flowline VAA file to use to establish mass linkages

        with open(VAAfile, 'rb') as f: flowlines = pickle.load(f)
            
        # create a dictionary to connect the comids to hydroseqs

        hydroseqs = {'{}'.format(flowlines[f].comid): 
                     flowlines[f].hydroseq for f in flowlines}

        # establish the mass linkages using a dictionary "updown" and a list of 
        # head water subbasins

        updown = {}
    
        for comid, subbasin in watershed.subbasins.items():

            # get the flowline instance for the outlet comid

            flowline = flowlines[hydroseqs[comid]]

            # check if the subbasin is a watershed inlet or a headwater source

            inlet = hydroseqs[inlets[comid]]

            if flowlines[inlet].up in flowlines:
                i = '{}'.format(flowlines[flowlines[inlet].up].comid)
                subbasin.add_inlet(i)
            elif flowlines[inlet].up != 0:
                watershed.add_inlet(comid)
            else: 
                watershed.add_headwater(comid)

            # check if the subbasin is a watershed outlet, and if it is not, 
            # then find the downstream reach

            if flowline.down in flowlines:
                flowline = flowlines[flowline.down]
                while '{}'.format(flowline.comid) not in subbasins:
                    flowline = flowlines[flowline.down]
                updown[comid] = '{}'.format(flowline.comid)
            else: 
                updown[comid] = 0
                watershed.add_outlet('{}'.format(comid))

        # open 

        watershed.add_mass_linkage(updown)

        if output is None: 
            filename = os.getcwd() + '/watershed'
            plotname = os.getcwd() + '/masslink.%s' % format
        else:              
            filename = output + '/%s/watershed' % HUC8
            plotname = output + '/%s/images/%smasslink.%s'%(HUC8, HUC8, format)

        if not os.path.isfile(filename) or overwrite:
            with open(filename, 'wb') as f: pickle.dump(watershed, f)

        if not os.path.isfile(plotname) and plots or overwrite and plots: 
            plot_mass_flow(watershed, plotname)

    def get_distance(self, p1, p2):
        """Approximates the distance in kilometers between two points on the 
        Earth's surface designated in decimal degrees using an ellipsoidal 
        projection. per CFR 73.208 it is applicable for up to 475 kilometers.
        p1 and p2 are listed as (longitude, latitude).
        """

        deg_rad = numpy.pi / 180

        dphi = p1[1] - p2[1]
        phim = 0.5 * (p1[1] + p2[1])
        dlam = p1[0] - p2[0]

        k1 = (111.13209 - 0.56605 * numpy.cos(2 * phim * deg_rad) + 0.00120 * 
              numpy.cos(4 * phim * deg_rad))
        k2 = (111.41513 * numpy.cos(phim * deg_rad) - 0.09455 * 
              numpy.cos(3 * phim * deg_rad) + 0.0012 * 
              numpy.cos(5 * phim * deg_rad))

        return numpy.sqrt(k1**2 * dphi**2 + k2**2 * dlam**2)

    def get_boundaries(self, shapes, space = 0.1):
        """Gets the boundaries for the plot."""

        boundaries = shapes[0].bbox
        for shape in shapes[0:]:
            b = shape.bbox
            if b[0] < boundaries[0]: boundaries[0] = b[0]
            if b[1] < boundaries[1]: boundaries[1] = b[1]
            if b[2] > boundaries[2]: boundaries[2] = b[2]
            if b[3] > boundaries[3]: boundaries[3] = b[3]

        xmin = boundaries[0] - (boundaries[2] - boundaries[0]) * space
        ymin = boundaries[1] - (boundaries[3] - boundaries[1]) * space
        xmax = boundaries[2] + (boundaries[2] - boundaries[0]) * space
        ymax = boundaries[3] + (boundaries[3] - boundaries[1]) * space

        return xmin, ymin, xmax, ymax

    def add_raster(self, 
                   fig, 
                   filename, 
                   resolution, 
                   extent, 
                   colormap, 
                   scale,
                   ):
        """adds a rectangular raster image with corners located at the extents
        to a plot.
        """

        # flatten the arrays and set up an array for the raster

        xmin, ymin, xmax, ymax = extent

        xs = numpy.array([xmin + (xmax - xmin) / resolution * i 
                          for i in range(resolution + 1)])
        ys = numpy.array([ymax  - (ymax  - ymin)  / resolution * i 
                          for i in range(resolution + 1)])

        zs = numpy.zeros((resolution + 1, resolution + 1))

        # iterate through the grid and fill the array

        for i in range(len(ys)):
            zs[i, :] = get_raster(filename, zip(xs, [ys[i]] * (resolution + 1)),
                                  quiet = True)

        # scale the values

        zs = zs / scale
        space = 0.1
        mi, ma = zs.min(), zs.max()
        mi, ma = mi - space * (ma - mi), ma + space * (ma - mi)
        norm = colors.Normalize(vmin = mi, vmax = ma)

        # plot the grid

        return fig.imshow(zs, extent = [xmin, xmax, ymin, ymax], norm = norm, 
                          cmap = colormap)

    def make_patch(self,
                   points, 
                   facecolor, 
                   edgecolor = 'Black', 
                   width = 1, 
                   alpha = None,
                   hatch = None, 
                   label = None,
                   ):
        """Uses a list or array of points to generate a matplotlib patch."""

        vertices = [(point[0], point[1]) for point in points]
        vertices.append((points[0][0], points[0][1]))

        codes     = [path.Path.LINETO for i in range(len(points) + 1)]
        codes[0]  = path.Path.MOVETO

        patch = patches.PathPatch(path.Path(vertices, codes), 
                                  facecolor = facecolor,
                                  edgecolor = edgecolor, 
                                  lw = width, 
                                  hatch = hatch,
                                  alpha = alpha, 
                                  label = label)
        return patch

    def plot_gage_watershed(self, 
                            gage, 
                            title      = None,
                            resolution = 200,
                            output     = None,
                            show       = False,
                            verbose    = True,
                            ):
        """Makes a plot of the delineated watershed."""

        if verbose: 
            print('generating plot of watershed for gage {0}\n'.format(gage))

        fig = pyplot.figure()
        subplot = fig.add_subplot(111, aspect = 'equal')
        subplot.tick_params(axis = 'both', which = 'major', labelsize = 10)

        # open up and show the catchments

        facecolor = (1,0,0,0.)

        b = Reader(self.boundary, shapeType = 5)

        points = numpy.array(b.shape(0).points)
        subplot.add_patch(self.make_patch(points, facecolor = facecolor, 
                                          width = 1.))

        extent = self.get_boundaries(b.shapes(), space = 0.02)

        xmin, ymin, xmax, ymax = extent

        # figure out how far one foot is on the map

        points_per_width = 72 * 8
        ft_per_km = 3280.84
        scale_factor = (points_per_width / 
                        self.get_distance([xmin, ymin], [xmax, ymin]) / 
                        ft_per_km)

        s = Reader(self.catchments, shapeType = 5)

        # make patches of the subbasins

        for i in range(len(s.records())):
            shape = s.shape(i)
            points = numpy.array(shape.points)
            subplot.add_patch(self.make_patch(points, facecolor, width = 0.2))

        # get all the comids in the watershed

        f = Reader(self.flowlines, shapeType = 3)
        comid_index = f.fields.index(['COMID', 'N',  9, 0]) - 1

        all_comids = [r[comid_index] for r in f.records()]
    
        # get the flowline attributes, make an "updown" dictionary to follow 
        # flow, and change the keys to comids
    
        with open(self.attributefile, 'rb') as f: flowlineVAAs = pickle.load(f)
    
        updown = {item.comid: flowlineVAAs[flowlineVAAs[key].down].comid
                  for key, item in flowlineVAAs.items()
                  if item.comid in all_comids}
    
        flowlineVAAs = {flowlineVAAs[f].comid:flowlineVAAs[f] 
                        for f in flowlineVAAs
                        if flowlineVAAs[f].comid in all_comids}
        
        # find the flowlines in the main channel
    
        f = Reader(self.flowlines, shapeType = 3)
    
        comid_index = f.fields.index(['COMID', 'N',  9, 0]) - 1
        comids = [r[comid_index] for r in f.records()]

        # get the flows and velocities from the dictionary
    
        widths = []
        for comid in comids:
            flow     = flowlineVAAs[comid].flow
            velocity = flowlineVAAs[comid].velocity
    
            # estimate the flow width in feet assuming triangular 90 deg channel
    
            widths.append(numpy.sqrt(4 * flow / velocity))
    
        # convert widths in feet to points on the figure; exaggerated by 10
    
        widths = [w * scale_factor * 10 for w in widths]
        
        # show the flowlines
    
        for comid, w in zip(comids, widths):
    
            i = all_comids.index(comid)
            flowline = numpy.array(f.shape(i).points)
    
            # plot it
    
            subplot.plot(flowline[:, 0], flowline[:, 1], 'b', lw = w)
    
        # find the outlet and get the GNIS name and elevations
    
        i = 0
        while updown[comids[i]] in updown: i+=1
        gnis_name = f.record(all_comids.index(comids[i]))[4]
    
        # get the gage info
    
        f = Reader(self.gagefile, shapeType = 1)
    
        site_index = f.fields.index(['SITE_NO', 'C', 15, 0]) - 1
        gage_ids    = [r[site_index] for r in f.records()]
        gage_points = [g.points[0] for g in f.shapes()]
    
        x1, y1 = gage_points[gage_ids.index(gage)]
    
        subplot.scatter(x1, y1, marker = 'o', c = 'r', s = 60)
    
        subplot.set_xlabel('Longitude, Decimal Degrees', size = 13)
        subplot.set_ylabel('Latitude, Decimal Degrees',  size = 13)
    
        subplot.xaxis.set_major_formatter(ticker.ScalarFormatter('%.1f'))
        subplot.ticklabel_format(useOffset=False)

        # add the raster
    
        colormap = 'gist_earth'
    
        # use the min and max elev to set the countours
    
        im = self.add_raster(subplot, self.elevfile, resolution, extent, 
                             colormap, 100) 
    
        divider = make_axes_locatable(subplot)
        cax = divider.append_axes('right', size = 0.16, pad = 0.16)
        colorbar = fig.colorbar(im, cax = cax, orientation = 'vertical')
        colorbar.set_label('Elevation, m', size = 12)
        cbax = pyplot.axes(colorbar.ax)
        yaxis = cbax.get_yaxis()
        ticks = yaxis.get_majorticklabels()
        for t in ticks: t.set_fontsize(10)
    
        # add the title
    
        if not isinstance(gnis_name, bytes) > 0: descrip = ', ' + gnis_name
        else:                                    descrip = ''
    
        if title is None: 
            title = 'Watershed for Gage {0}{1}'.format(gage, descrip)
    
        subplot.set_title(title, fontsize = 14)
    
        # show it
    
        pyplot.tight_layout()
    
        if output is not None: pyplot.savefig(output)

        if show: pyplot.show()
    
        pyplot.close()

    def make_subbasin_outlets(self, 
                              extras   = None,
                              years    = None,
                              drainmax = None,
                              verbose  = True
                              ):
        """
        Creates a feature class of outlets containing all the data needed 
        for HSPF simulations.
        """

        if verbose: print('subdividing watershed\n')

        # use subbasin delineation criteria to make a list of inlets and outlets

        inlets = []

        if extras is None: outlets = []
        else:              outlets = extras

        # open up the flowline data in a dictionary using hydroseqs as keys 
        # and make a dictionary linking the comids to hydroseqs

        with open(self.attributefile, 'rb') as f: flowlines = pickle.load(f)

        hydroseqs  = {flowlines[f].comid: f for f in flowlines}

        # find the dam comids if a dam shapefile is provided

        if self.damfile is not None:

            dam_comids = find_flowlines(self.damfile, self.flowlinefile)

            for comid in dam_comids:
                
                if comid is not None and comid in hydroseqs: 
                    
                    outlets.append(comid)

            # read the dam file to find the outlet points

            damreader  = Reader(self.damfile, shapeType = 1)
            dampoints  = [s.points[0] for s in damreader.shapes()]
            damrecords = damreader.records()

            nid_index = damreader.fields.index(['NIDID', 'C', 7, 0]) - 1

        else: dam_comids = []

        # find the gages if a gage shapefile is provided

        if self.gagefile is not None:

            gage_comids = find_flowlines(self.gagefile, self.flowlinefile)

            # check the gages and see if they meet the criteria for outlets

            gagereader  = Reader(self.gagefile, shapeType = 1)
            gagerecords = gagereader.records()

            # figure out which field codes are the HUC8, the first day, the site
            # number, the drainage area, and the average 

            day1_index  = gagereader.fields.index(['DAY1',    'N', 19, 0]) - 1
            dayn_index  = gagereader.fields.index(['DAYN',    'N', 19, 0]) - 1
            HUC8_index  = gagereader.fields.index(['HUC',     'C',  8, 0]) - 1
            site_index  = gagereader.fields.index(['SITE_NO', 'C', 15, 0]) - 1
            nwis_index  = gagereader.fields.index(['NWISWEB', 'C', 75, 0]) - 1
            ave_index   = gagereader.fields.index(['AVE',     'N', 19, 3]) - 1

            gage_outlets = []
            last_HUC     = []
            next_HUC     = None
            for record, comid in zip(gagerecords, gage_comids):

                # make sure there are data

                data_criteria = (comid is not None)

                # check the gage has data during the years if provided

                if years is not None:

                    first_criteria, last_criteria = years
                    first_gage = int(str(record[day1_index])[:4])
                    last_gage  = int(str(record[dayn_index])[:4])

                    year_criteria = (first_gage <= last_criteria or
                                     last_gage >= first_criteria)

                else: year_criteria = True

                # make sure it is not an inlet and that it's in the watershed
            
                watershed_criteria = (flowlines[hydroseqs[comid]].up in 
                                      flowlines and record[HUC8_index] == HUC8)

                existing = comid not in outlets

                if all(data_criteria, year_criteria, watershed_criteria, 
                       existing):

                    gage_outlets.append(comid)

                    if verbose:
 
                        print('adding outlet %d for gage station %s' % 
                              (comid, record[site_index]))

        else: gage_outlets = []

        # add the gage stations meeting the criteria as outlets

        for comid in gage_outlets:
            outlets.append(comid)
            if verbose: print('adding outlet %d for gage station' % comid)

        # find all the inlets

        for f in flowlines:
            if flowlines[f].up not in flowlines and flowlines[f].up != 0:
                inlets.append(flowlines[f].comid)

        # find the watershed outlet using the drainage area

        max_area   = max([flowlines[f].drain for f in flowlines])
        last_comid = [flowlines[f].comid for f in flowlines 
                      if flowlines[f].drain == max_area][0]

        if last_comid not in outlets: outlets.append(last_comid)

        # check to see if there are two flowlines feeding the watershed outlet

        for k,v in flowlines.items():
            if (v.down == flowlines[hydroseqs[last_comid]].down and
                v.comid != last_comid):
                print('adding outlet for second watershed outlet at', 
                      v.comid, '\n')
                outlets.append(v.comid)

        # trace the main channels from the inlet hydroseqs

        main = []
        for inlet in inlets:
            flowline = flowlines[hydroseqs[inlet]]
            if flowline not in main: main.append(flowline)
            while flowline.down in flowlines:
                flowline = flowlines[flowline.down]
                if flowline not in main: main.append(flowline)

        # make the main channel if there is no inlet

        if len(inlets) == 0:
            flowline = flowlines[hydroseqs[last_comid]]
            main.append(flowline)
            while flowline.up != 0:
                flowline = flowlines[flowline.up]
                main.append(flowline)

        # add outlets to connect outlets to the main channel as needed

        for outlet in outlets:

            flowline = flowlines[hydroseqs[outlet]]

            # check that it isn't the watershed outlet

            if flowline.down in flowlines:

                # check if it's connected

                if flowline not in main:

                    if verbose: print(flowline.comid, 'is not connected')

                    # then need to add outlets to connect to the main line

                    while flowlines[flowline.down] not in main:
                        main.append(flowline)
                        flowline = flowlines[flowline.down]
                        if flowline.down not in flowlines: 
                            if verbose: print('reached the watershed outlet')
                            break

                    if flowline.comid not in outlets: 
                        outlets.append(flowline.comid)
                        main.append(flowline)
                        if verbose: print('adding outlet %d for connectivity' % 
                                          flowline.comid)

                    # add outlets for any others streams at the junction

                    others = [v for k,v in flowlines.items() 
                              if (v.down == flowline.down and v != flowline)]

                    for other in others:

                        if other.comid not in outlets:
                            outlets.append(other.comid)
                            if verbose: print('adding another outlet ' +
                                              '%d for connectivity' % 
                                              other.comid)
    
        # check the drainage areas to make sure subbasins are not too large
        # start at the main outlet and move upstream adding outlets as needed

        if drainmax is None: drainmax = max_area

        n = -1
        while len(outlets) != n:

            if verbose: print('checking outlet conditions\n')

            # move upstream and look at the changes in drainage area for 
            # each outlet

            n = len(outlets)

            for outlet in outlets:
                flowline = flowlines[hydroseqs[outlet]] # current flowline
                boundaries     = [0] + [hydroseqs[b] for b in inlets + outlets]
                drain_area     = flowline.divarea

                # check until reaching another outlet or the top of the 
                # watershed additional checks for max basin drainage area 
                # and major tributary

                while flowline.up not in boundaries:

                    # find all the tributaries

                    tributaries = [f for f in flowlines 
                                   if flowlines[f].down == flowline.hydroseq]

                    # find the major tributary

                    major = flowlines[flowline.up]

                    # if any tributary is an outlet or if the minor tributaries
                    # exceeds drainage max make them all outlets

                    if (any([flowlines[f].comid in outlets 
                             for f in tributaries]) or
                        flowline.divarea - major.divarea > drainmax):

                        for f in tributaries: 
                            if flowlines[f].comid not in outlets: 
                                outlets.append(flowlines[f].comid)

                                if verbose: 

                                    print('adding outlet %d for major tributary'
                                          % flowlines[f].comid)

                        break

                    elif drain_area - flowline.divarea > drainmax:

                        if flowlines[flowline.down].comid not in outlets: 
                            outlets.append(flowlines[flowline.down].comid)

                            if verbose: 
                                print('adding outlet %d for drainage area' % 
                                      flowlines[flowline.down].comid)

                        break

                    else: flowline = flowlines[flowline.up]

        # group flowlines into subbasins associated with each outlet

        subbasins = {outlet: [outlet] for outlet in outlets}

        # check to see if there are multiple outlets at the watershed outlet

        downhydroseq = flowlines[hydroseqs[last_comid]].down

        for comid in hydroseqs:
            if (flowlines[hydroseqs[comid]].down == downhydroseq and 
                comid not in outlets):
                subbasins[last_comid].append(comid)

        # go through each gage and make a list of all the comids in the subbasin

        for subbasin in subbasins:
            current = [hydroseqs[outlet] for outlet in subbasins[subbasin]]
            while len(current) > 0:
                last    = current[:]
                current = []

                for comid in hydroseqs:
                    if (flowlines[hydroseqs[comid]].down in last and 
                        comid not in outlets):

                        subbasins[subbasin].append(comid)
                        current.append(hydroseqs[comid])

        # make a shapefile containing the outlet points

        if verbose: print('copying the projections\n')

        # start by copying the projection files

        shutil.copy(self.flowlinefile + '.prj', outletfile + '.prj')
        shutil.copy(self.flowlinefile + '.prj', inletfile  + '.prj')

        # read the flowline and gage files

        flowreader  = Reader(self.flowlinefile, shapeType = 3)
        flowrecords = flowreader.records()

        # read the gage file

        gagereader  = Reader(self.gagefile, shapeType = 1)
        gagepoints  = [s.points[0] for s in gagereader.shapes()]

        # find the Reach code and comid fields in the flow file

        comid_index = flowreader.fields.index(['COMID',     'N',  9, 0]) - 1
        reach_index = flowreader.fields.index(['REACHCODE', 'C', 14, 0]) - 1
        gnis_index  = flowreader.fields.index(['GNIS_NAME', 'C', 65, 0]) - 1

        # make a list of the comids

        comids = [record[comid_index] for record in flowrecords]

        # make the inlet file

        if len(inlets) > 0:

            w = Writer(shapeType = 1)

            w.field(*['COMID',      'N',  9, 0])
            w.field(*['REACHCODE',  'C', 14, 0])
            w.field(*['SITE_NO',    'C', 15, 0])
            w.field(*['DRAIN_SQKM', 'N', 15, 3])
            w.field(*['AVG_FLOW',   'N', 15, 3])
            w.field(*['GNIS_NAME',  'C', 65, 0])
            w.field(*['NWISWEB',    'C', 75, 0])

            for inlet in inlets:
                index = comids.index(inlet)
                shape = flowreader.shape(index)
                point = shape.points[0]

                # get the parameters from the flow file

                reachcode = flowrecords[index][reach_index]
                comid     = flowrecords[index][comid_index]
                gnis      = flowrecords[index][gnis_index]

                # work around for blank records

                if isinstance(gnis, bytes): gnis = gnis.decode().strip()

                # get the area from the flowline database

                area = flowlines[hydroseqs[inlet]].drain

                if inlet in gage_outlets:

                    distances = [self.distance2(point, p) 
                                 for p in gagepoints]
                    closest   = distances.index(min(distances))

                    site_no = gagerecords[closest][site_index]
                    nwis    = gagerecords[closest][nwis_index]
                    flow    = round(gagerecords[closest][ave_index], 3)

                else:

                    site_no = ''
                    nwis    = ''

                    # estimate the flow from the nearest gage, start by going 
                    # upstream until reaching a gage comid

                    next_gage = flowlines[hydroseqs[comid]]
                    current_area = next_gage.drain

                    while (next_gage.comid not in gage_comids and 
                           next_gage.down in flowlines):
                        next_gage = flowlines[next_gage.down]
                    if next_gage.comid == last_comid:
                        flow = round(max([record[ave_index] 
                                          for record in gagerecords]), 3)
                    else:
                        # get the flow from the gage file (note units)

                        distances = [get_distance(point, p) for p in gagepoints]
                        closest   = distances.index(min(distances))
                        next_flow = gagerecords[closest][ave_index]
                        next_area = gagerecords[closest][drain_index] * 2.59

                        flow = round(next_flow * current_area / next_area, 3)

                w.point(point[0], point[1])
                w.record(comid, reachcode, site_no, area, flow, gnis, nwis)
    
            w.save(inletfile)

        # create the outlet point file that will store the comid and reachcode

        w = Writer(shapeType = 1)

        w.field(*['COMID',      'N',  9, 0])
        w.field(*['REACHCODE',  'C', 14, 0])
        w.field(*['NIDID',      'C',  7, 0])
        w.field(*['SITE_NO',    'C', 15, 0])
        w.field(*['DRAIN_SQKM', 'N', 15, 3])
        w.field(*['AVG_FLOW',   'N', 15, 3])
        w.field(*['GNIS_NAME',  'C', 65, 0])
        w.field(*['NWISWEB',    'C', 75, 0])

        for outlet in outlets:

            # find the flowline and use the last point as the outlet

            index = comids.index(outlet)
            shape = flowreader.shape(index)
            point = shape.points[-1]

            # get the parameters from the flow file

            reachcode = flowrecords[index][reach_index]
            comid     = flowrecords[index][comid_index]
            gnis      = flowrecords[index][gnis_index]

            if isinstance(gnis, bytes): gnis = gnis.decode().strip()

            # get the area from the flowline database

            area = flowlines[hydroseqs[outlet]].divarea

            # find the nearest dam if the outlet is co-located with a dam

            if outlet in dam_comids:

                distances = [get_distance(point, p) for p in dampoints]
                closest   = distances.index(min(distances))

                dam_no = damrecords[closest][nid_index]

            else:

                dam_no = ''

            # find the gage station if the outlet is co-located with a gage

            if outlet in gage_outlets:

                distances = [get_distance(point, p) for p in gagepoints]
                closest   = distances.index(min(distances))

                site_no = gagerecords[closest][site_index]
                nwis    = gagerecords[closest][nwis_index]
                flow    = round(gagerecords[closest][ave_index], 3)

            else:

                site_no = ''
                nwis    = ''

                # estimate the flow by interpolating from the nearest gage,
                # start by going downstream until reaching a gage comid and get
                # the drainage area and then repeat going upstream

                next_gage = flowlines[hydroseqs[comid]]
                while (next_gage.comid not in gage_comids and 
                       next_gage.down in flowlines):
                    next_gage = flowlines[next_gage.down]

                # see if the next_gage is outside the watershed, otherwise get 
                # the flows from the gage file (note units)

                if next_gage.comid == last_comid:
                    next_drains = [r[drain_index] for r in down_gages]
                    next_index  = next_drains.index(max(next_drains))
                    next_flow   = down_gages[next_index][ave_index]
                    next_area   = down_gages[next_index][drain_index]
                else: 
                    i = comids.index(next_gage.comid)
                    next_point = flowreader.shape(i).points[-1]
                    distances  = [get_distance(next_point, p) 
                                  for p in gagepoints]
                    closest    = distances.index(min(distances))
                    next_flow  = gagerecords[closest][ave_index]
                    next_area  = gagerecords[closest][drain_index] * 2.59

                last_gage = flowlines[hydroseqs[comid]]
                while (last_gage.comid not in gage_comids and
                       last_gage.up in flowlines):
                    last_gage = flowlines[last_gage.up]

                # see whether it's at the top of the watershed or an inlet
                # otherwise get the flows from the gage file (note units)

                if last_gage.up == 0 or len(up_gages) == 0:
                    last_flow = 0
                    last_area = 0
                elif last_gage.up not in flowlines: 
                    last_drains = [r[drain_index] for r in up_gages]
                    last_index  = last_drains.index(max(last_drains))
                    last_flow   = up_gages[last_index][ave_index]
                    last_area   = up_gages[last_index][drain_index]
                else: 
                    i = comids.index(last_gage.comid)
                    last_point = flowreader.shape(i).points[-1]
                    distances  = [get_distance(last_point, p) 
                                  for p in gagepoints]
                    closest    = distances.index(min(distances))
                    last_flow  = gagerecords[closest][ave_index]
                    last_area  = gagerecords[closest][drain_index] * 2.59

                if last_flow == next_flow: flow = last_flow
                else:
                    flow = round(last_flow + (next_flow - last_flow) * 
                                 (area - last_area) / (next_area - last_area),3)

            w.point(point[0], point[1])
            w.record(comid, reachcode, dam_no, site_no, area, flow, gnis, nwis)
    
        w.save(outletfile)

        with open(subbasinfile, 'wb') as f: pickle.dump(subbasins, f)

    def make_subbasin_flowlines(self, 
                                comids, 
                                output = None, 
                                verbose = True
                                ):
        """Makes a shapefile containing the major flowlines above a USGS gage
        within a HUC8.
        """

        if output is None: output = os.getcwd() + '/subbasin_flowlines'

        # start by copying the projection files

        shutil.copy(self.flowlinefile + '.prj', output + '.prj')

        # open the flowline shapefile
  
        shapefile = Reader(self.flowlinefile, shapeType = 3)
        records   = shapefile.records()

        # figure out which field code is the comid

        comid_index = shapefile.fields.index(['COMID', 'N', 9,  0]) - 1

        # go through the flowline comids and find the ones in the subbasin

        if verbose: print('extracting subbasin flowlines')

        indices = []
   
        i = 0
        for record in records:
            if record[comid_index] in comids: indices.append(i)
            i+=1

        # write the data to a new shapefile

        w = Writer(shapeType = 3)

        for field in shapefile.fields:  w.field(*field)

        for i in indices:
            shape  = shapefile.shape(i)

            w.poly(shapeType = 3, parts = [shape.points])

            record = records[i]

            # little work around for blank GNIS_ID and GNIS_NAME values

            if isinstance(record[3], bytes):
                record[3] = record[3].decode('utf-8')
            if isinstance(record[4], bytes):
                record[4] = record[4].decode('utf-8')

            w.record(*record)

        w.save(output)

        if verbose: print('successfully extracted subbasin flowlines')

    def combine_flowlines(self, 
                          output = None, 
                          overwrite = False,
                          verbose = True
                          ):
        """Makes a shapefile containing the major flowlines above each USGS gage
        within a subbasin based on the NHDPlus dataset.
        """

        if output is None: output = '{}/combined_flowline'.format(os.getcwd())

        if os.path.isfile(output) and not overwrite:
            if verbose: print('combined flowline shapefile %s exists' % output)
            return

        # start by copying the projection files

        shutil.copy(self.flowlinefile + '.prj', output + '.prj')

        # get the flowline attributes

        with open(self.attributefile, 'rb') as f: flowlines = pickle.load(f)

        # all the fields for the combined flowline feature class

        fields = [['OutComID', 'N', 9, 0], 
                  ['GNIS_NAME', 'C', 65, 0],
                  ['REACHCODE', 'C', 8, 0],
                  ['InletComID', 'N', 9, 0],
                  ['MaxElev', 'N', 9, 2],
                  ['MinElev', 'N', 9, 2],
                  ['SlopeLenKM', 'N', 6, 2],
                  ['Slope', 'N', 8, 5],
                  ['InFlowCFS', 'N', 8, 3],
                  ['OutFlowCFS', 'N', 8, 3],
                  ['VelFPS', 'N', 7, 4],
                  ['TravTimeHR', 'N', 8, 2]
                  ]

        # go through the reach indices, add add them to the list of flowlines if
        # they are in the watershed, and make a list of the corresponding comids
  
        shapefile = Reader(self.flowlinefile, shapeType = 3)
        records   = shapefile.records()

        # figure out which field code is the comid, reachcode, and gnis name

        comid_index = shapefile.fields.index(['COMID',     'N',  9, 0]) - 1
        reach_index = shapefile.fields.index(['REACHCODE', 'C', 14, 0]) - 1
        gnis_index  = shapefile.fields.index(['GNIS_NAME', 'C', 65, 0]) - 1

        all_comids = [r[comid_index] for r in records]
    
        # make a dictionary linking the hydrologic sequence

        updown = {f: flowlines[f].down for f in flowlines 
                  if flowlines[f].comid in all_comids}
        downup = {f: flowlines[f].up   for f in flowlines
                  if flowlines[f].comid in all_comids}

        # pick a flowline and follow it to the end of the watershed

        current = list(updown.keys())[0]

        while updown[current] in updown: current = updown[current]

        primary = [current]
        while downup[current] in downup:
            current = downup[current]
            primary.insert(0, current)

        inlet_comid = flowlines[primary[0]].comid
        last_comid  = flowlines[primary[-1]].comid

        inlet_flow  = round(flowlines[primary[0]].flow, 3)
        outlet_flow = round(flowlines[primary[-1]].flow, 3)
        velocity    = round(flowlines[primary[-1]].velocity, 4)
        traveltime  = round(sum([flowlines[f].traveltime for f in primary]), 3)

        # use the attributes for the last flowline for the combined flowline

        top    = flowlines[primary[0]].maxelev
        bottom = flowlines[primary[-1]].minelev
        length = round(sum([flowlines[f].length for f in primary]), 2)

        estimated_slope = round((top - bottom) / 100000 / length, 6)

        if estimated_slope < 0.00001: slope = 0.00001
        else:                         slope = estimated_slope

        # write the data from the HUC8 to a new shapefile

        w = Writer(shapeType = 3)

        # the fields will be effluent comid, GNIS name, the length (km), 
        # the 8-digit reach code, the slope, the flow at the inlet and outlet,
        # the velocity in ft/s, and the travel time in hours

        for field in fields: w.field(*field)

        last_index = all_comids.index(last_comid)
        if isinstance(records[last_index][gnis_index], bytes):
            gnis = records[last_index][gnis_index].decode('utf-8')
        else: gnis = records[last_index][gnis_index]

        r = [last_comid, gnis, records[last_index][reach_index][:8], 
             inlet_comid, top, bottom, length, slope, inlet_flow, 
             outlet_flow, velocity, traveltime]

        w.record(*r)

        points = []
        for f in primary:
            shape = shapefile.shape(all_comids.index(flowlines[f].comid))

            for p in shape.points:
                if p not in points: points.append(p)

        w.poly(shapeType = 3, parts = [points])

        w.save(output)

        if verbose: 
            print('successfully combined subbasin ' +
                  '{} flowlines'.format(last_comid))

    def combine_subbasin_flowlines(self,
                                   directory, 
                                   comids, 
                                   output, 
                                   overwrite = False, 
                                   verbose = True
                                   ):
        """
        Combines outlet subbasin flowlines for an 8-digit hydrologic unit 
        into a single shapefile.  Assumes directory structure of:

        path_to_HUC8\comids\combined_flowline.shp 
    
        where comids are all the elements in a list of the subbasin outlets 
        from  the NHDPlus dataset.
        """

        l = Writer(shapeType = 3)
        projection = None
        fields     = None

        for comid in comids:
            filename = directory + '/%d/combined_flowline' % comid
            if os.path.isfile(filename + '.shp'):
                if verbose: print('found combined file %s\n' % filename)

                # start by copying the projection files

                if projection is None:
                    projection = output + '.prj'
                    shutil.copy(filename + '.prj', projection)

                # read the new file
  
                r = Reader(filename, shapeType = 3)

                if fields is None:
                    fields = r.fields
                    for field in fields: l.field(*field)

                shape = r.shape(0)

                # write the shape and record to the new file

                l.poly(shapeType = 3, parts = [shape.points])
                record = r.record(0)
                if isinstance(record[1], bytes): record[1] = ''
                if record[1] == 65 * ' ': record[1] = ''
                l.record(*record)

            elif verbose: print('unable to locate %s\n' % filename)

        if fields is not None:  
            l.save(output)
            if verbose: print('successfully combined flowline shapefiles')
        elif verbose: print('warning: unable to combine flowline shapefiles')

    def subdivide_watershed(self, 
                            HUC8, 
                            extra_outlets = None,
                            drainmax = None, 
                            outputpath = None,
                            verbose = True, 
                            vverbose = False
                            ):
        """
        Analyzes the GIS data, subdivides the watershed into subbasins 
        that are co-located with the gages and have drainage areas no larger 
        than the max specified.

        extra_outlets -- list of longitudes and latitudes for additional outlets
        outputpath    -- path to write output
        """

        start = time.time()

        if outputpath is None: output = os.getcwd()
        else:                  output = outputpath

        # subdivide the watershed using the USGS NWIS stations and any 
        # additional subbasins

        attributefile = output + '/%s/flowlineVAAs'         %  HUC8
        subbasinfile  = output + '/%s/subbasincomids'       %  HUC8
        merged        = output + '/%s/%ssubbasin_flowlines' % (HUC8, HUC8)
        outletfile    = output + '/%s/%ssubbasin_outlets'   % (HUC8, HUC8)
        inletfile     = output + '/%s/%ssubbasin_inlets'    % (HUC8, HUC8)

        if (not os.path.isfile(subbasinfile) or 
            not os.path.isfile(outletfile + '.shp') or
            not os.path.isfile(merged + '.shp')):

            if verbose: 
                print('delineating HSPF watershed for USGS HUC %s\n' % HUC8)

            # add any additional outlets as a list of points (or None) and 
            # divide the flowfiles into subbasins above each of the subbasin 
            # outlets subbasins is a dictionary of linking the outlet flowline 
            # comid to the comids of all the tributaries up to the 
            # previous outlet

            subbasins = self.make_subbasin_outlets(HUC8, 
                                                   attributefile, 
                                                   gagefile, 
                                                   damfile, 
                                                   flowfile, 
                                                   outletfile, 
                                                   inletfile, 
                                                   subbasinfile, 
                                                   drainmin = drainmin, 
                                                   drainmax = drainmax, 
                                                   extras = extra_outlets, 
                                                   verbose = vverbose
                                                   )

        else: 
            if verbose: print('HSPF watershed {} exists\n'.format(HUC8))
            with open(subbasinfile, 'rb') as f: subbasins = pickle.load(f)

        # divide the flowline shapefile into subbasin flowline shapefiles 

        for subbasin in subbasins:
            path = output + '/%s/%d' % (HUC8, subbasin)
            flow = path + '/flowlines'
        
            # make a directory for the output if needed

            if not os.path.isdir(path): os.mkdir(path)

            # extract the flowlines if needed

            if not os.path.isfile(flow + '.shp'):
                make_subbasin_flowlines(flowfile, subbasins[subbasin], output = 
                                        flow, verbose = vverbose)

        # combine the flowlines in each subbasin into a combined shapefile

        for subbasin in subbasins:
            flow     = output + '/%s/%d/flowlines' % (HUC8, subbasin)
            combined = output + '/%s/%d/combined_flowline' % (HUC8, subbasin)
            if not os.path.isfile(combined + '.shp'):
                combine_flowlines(attributefile, flow, output = combined, 
                                  verbose = verbose)
        if verbose: print('')

        # merge the flowlines into a single file

        if not os.path.isfile(merged + '.shp'):
            combine_subbasin_flowlines(output + '/%s' % HUC8, 
                                       subbasins, 
                                       merged, 
                                       overwrite = True, 
                                       verbose = vverbose
                                       )
            if verbose: print('')

        if verbose: print('successfully divided watershed in %.1f seconds\n' %
                          (time.time() - start))

    def get_distance_vector(self, catchpoints, closest):
        """Vectorized version of get_distance method 
        (for computational efficiency).
        """

        deg_rad = math.pi / 180
          
        dphis = catchpoints[:, 1] - closest[:, 1]
        phims = 0.5 * (catchpoints[:, 1] + closest[:, 1])
        dlams = catchpoints[:,0] - closest[:,0]

        k1s = (111.13209 - 0.56605 * numpy.cos(2 * phims * deg_rad) + 
               0.00120 * numpy.cos(4 * phims * deg_rad))
        k2s = (111.41513 * numpy.cos(phims * deg_rad) - 0.09455 * 
               numpy.cos(3 * phims * deg_rad) + 0.0012 * 
               numpy.cos(5 * phims * deg_rad))
    
        return numpy.sqrt(k1s**2 * dphis**2 + k2s**2 * dlams**2)

    def get_overland(self, p1, p2, tolerance = 0.1, min_slope = 0.00001):
        """Returns the slope of the z-coordinate in the x-y plane between points
        p1 and p2.  Returns the min_slope if the points are too close together
        as specified by the tolerance (km).  Also return half the average length
        from the catchment boundary to the flowline (since the average length 
        across each line is half the total length)."""

        L = self.get_distance(p1, p2)

        if L > tolerance: return L / 2., (p1[2] - p2[2]) / L / 100000
        else:             return tolerance, min_slope

    def get_overland_vector(self, catchpoints, closest, tol = 0.1, 
                            min_slope = 0.00001):
        """Vectorized version of the get_overland function (for computational
        efficiency)."""

        length = get_distance_vector(catchpoints, closest)
        slope  = (catchpoints[:,2] - closest[:,2]) / length / 100000

        for l, s in zip(length, slope):
            if l < tol: l, s = tol, min_slope

        return length / 2., slope

    def get_centroid(self, points):
        """Calculates the centroid of a polygon with paired x-y values."""

        xs, ys = points[:, 0], points[:, 1]

        a = xs[:-1] * ys[1:]
        b = ys[:-1] * xs[1:]

        A = numpy.sum(a - b) / 2.

        cx = xs[:-1] + xs[1:]
        cy = ys[:-1] + ys[1:]

        Cx = numpy.sum(cx * (a - b)) / (6. * A)
        Cy = numpy.sum(cy * (a - b)) / (6. * A)

        return Cx, Cy

    def combine_catchments(self, catchmentfile, flowfile, elevationfile, comid, 
                           output = None, overwrite = False, verbose = True):
        """Combines together all the catchments in a basin catchment shapefile.
        Creates a new shapefile called "combined" in the same directory as the 
        original file.  Uses the elevation data from the raster file and the 
        flow data file to estimate the length and average slope of the 
        overland flow plane.
        """

        t0 = time.time()
        numpy.seterr(all = 'raise')

        if output is None: output = os.getcwd() + r'\combined'

        if os.path.isfile(output + '.shp') and not overwrite:
            if verbose: print('combined catchment shapefile %s exists' % output)
            return
   
        if verbose: print('combining catchments from %s\n' % catchmentfile)

        # start by copying the projection files

        shutil.copy(catchmentfile + '.prj', output + '.prj')

        # load the catchment and flowline shapefiles

        c = Reader(catchmentfile, shapeType = 5)
        f = Reader(flowfile,      shapeType = 3)

        # make lists of the comids and featureids

        featureid_index = c.fields.index(['FEATUREID', 'N', 9, 0]) - 1
        comid_index     = f.fields.index(['COMID', 'N', 9,  0])    - 1

        featureids = [r[featureid_index] for r in c.records()]
        comids     = [r[comid_index]     for r in f.records()]

        # check that shapes are traceable--don't have multiple points and start
        # and end at the same place--then make an appropriate list of shapes
        # and records--note it's more memory efficient to read one at a time

        n = len(c.records())
        shapes  = []
        records = [] 
        bboxes  = []

        try: 

            for i in range(n):
                catchment = c.shape(i)
                record = c.record(i)

                shape_list = format_shape(catchment.points)
                for s in shape_list:
                    shapes.append(s)
                    records.append(record)
                    bboxes.append(catchment.bbox)

            try:    combined = combine_shapes(shapes, bboxes, verbose = verbose)
            except: combined = combine_shapes(shapes, bboxes, skip = True, 
                                              verbose = verbose)

        except: 

            shapes  = []
            records = [] 
            bboxes  = []
            for i in range(n):
                catchment = c.shape(i)
                record = c.record(i)

                shape_list = format_shape(catchment.points, omit = True)
                for s in shape_list:
                    shapes.append(s)
                    records.append(record)
                    bboxes.append(catchment.bbox)

            try:    combined = combine_shapes(shapes, bboxes, verbose = verbose)
            except: combined = combine_shapes(shapes, bboxes, skip = True,
                                              verbose = verbose)

        # iterate through the catchments and get the elevation data from NED
        # then estimate the value of the overland flow plane length and slope

        lengths = numpy.empty((n), dtype = 'float')
        slopes  = numpy.empty((n), dtype = 'float')

        for i in range(n):
            catchment = c.shape(i)
            flowline  = f.shape(comids.index(featureids[i]))

            catchpoints = get_raster_on_poly(elevationfile, catchment.points,
                                             verbose = verbose)
            catchpoints = numpy.array([p for p in catchpoints])

            zs = get_raster(elevationfile, flowline.points)

            flowpoints = numpy.array([[p[0], p[1], z] 
                                      for p, z in zip(flowline.points, zs)])

            # iterate through the raster values and find the closest flow point

            closest = numpy.empty((len(catchpoints), 3), dtype = 'float')

            for point, j in zip(catchpoints, range(len(catchpoints))):
                closest[j] = flowpoints[numpy.dot(flowpoints[:, :2], 
                                                  point[:2]).argmin()]

            # estimate the slope and overland flow plane length

            length, slope = get_overland_vector(catchpoints, closest)

            if verbose: 
                print('avg slope and length =', slope.mean(), length.mean())

            lengths[i], slopes[i] = length.mean(), slope.mean()

        if verbose: print('\nfinished overland flow plane calculations\n')

        # get area of the subbasin from the catchment metadata

        areasq_index = c.fields.index(['AreaSqKM', 'N', 19, 6]) - 1
        areas        = numpy.array([r[areasq_index] for r in c.records()])

        # take the area weighted average of the slopes and flow lengths

        tot_area   = round(areas.sum(), 2)
        avg_length = round(1000 * numpy.sum(areas * lengths) / tot_area, 1)
        avg_slope  = round(numpy.sum(areas * slopes) / tot_area, 4)

        # get the centroid and the average elevation

        combined = [[float(x), float(y)] for x, y in combined]
        centroid = get_centroid(numpy.array(combined))

        Cx, Cy = round(centroid[0], 4), round(centroid[1], 4)

        elev_matrix, origin = get_raster_in_poly(elevationfile, combined, 
                                                 verbose = verbose)

        elev_matrix = elev_matrix.flatten()
        elev_matrix = elev_matrix[elev_matrix.nonzero()]
    
        avg_elev = round(elev_matrix.mean() / 100., 2)

        # write the data to the shapefile

        w = Writer(shapeType = 5)

        fields = [['ComID',      'N',  9, 0],
                  ['PlaneLenM',  'N',  8, 2],
                  ['PlaneSlope', 'N',  9, 6],
                  ['AreaSqKm',   'N', 10, 2],
                  ['CenX',       'N', 12, 6],
                  ['CenY',       'N', 12, 6],
                  ['AvgElevM',   'N',  8, 2]]

        record = [comid, avg_length, avg_slope, tot_area, Cx, Cy, avg_elev]

        for field in fields:  w.field(*field)
    
        w.record(*record)
    
        w.poly(shapeType = 5, parts = [combined])

        w.save(output)

        if verbose: print('\ncompleted catchment combination in ' +
                          '%.1f seconds\n' % (time.time() - t0))
