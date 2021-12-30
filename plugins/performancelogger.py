""" BlueSky logger plugin to log aircraft performance.
    Initially log fuel consumption and intrusion severity """

import sys
import numpy as np
# Import the global bluesky objects. Uncomment the ones you need
from bluesky import traf, stack, settings, sim  # navdb, traf, scr, tools
from bluesky.tools import aero, datalog, geo
from bluesky.core import Entity, timed_function
from bluesky.traffic.asas import StateBased
from plugins.area import Area

if not 'C:/TUDelft/Thesis/AtlanticDirectRoutingGit/' in sys.path:
    sys.path.insert(0, 'C:/TUDelft/Thesis/AtlanticDirectRoutingGit/')
from pyproj import Proj
from matplotlib import path
from itertools import compress
from shapely.geometry import shape
from FIRarea import extract_fir, extract_Gander_Shanwick, fir_boundary

""" 
Try to add the fuel consumption per aircraft, for which the initial mass is necessary.
Couple of complications: - Want to keep original BS files intact.
                         - Not aware how to create input mass for perfbada create() function
                         - stack.commands not referencing commands for AT function
"""

# Log parameters for the flight statistics log
fuelheader = \
    '#######################################################\n' + \
    'MASS LOG\n' + \
    'Mass Logger\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation Time [s], ' + \
    'Call Sign [-], ' + \
    'Initial Mass [kg], ' + \
    'Current Mass [kg], ' + \
    'Fuel Consumed [kg] \n'

# Log parameters for the los of separations log
losheader = \
    '#######################################################\n' + \
    'LOS LOG\n' + \
    'Los of Separation Statistics\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'AC1 [-], ' + \
    'AC2 [-], ' + \
    'Spawn Time1 [s], ' + \
    'Spawn Time2 [s], ' + \
    'Lat1 [deg], ' + \
    'Lon1 [deg], ' + \
    'Lat2 [deg], ' + \
    'Lon2 [deg], ' + \
    'Alt1 [m], ' + \
    'Alt2 [m], ' + \
    'Hdg1 [deg], ' + \
    'Hdg2 [deg], ' + \
    'Intrusion severity [-] \n'

# Log parameters for the traffic density log
densheader = \
    '#######################################################\n' + \
    'DENS LOG\n' + \
    'Density Statistics\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Number of AC [-], ' + \
    'Average true airspeed [m/s], ' + \
    'Average nominal path distance [m], ' + \
    'Traffic density [AC/1000km^2], ' + \
    'Number of AC (G/S) [-], ' + \
    'Average true airspeed (G/S) [m/s], ' + \
    'Average nominal path distance (G/S) [m], ' + \
    'Traffic density (G/S) [AC/1000km^2] \n'

# Log parameters for periodic logger of aircraft states
stateheader = \
    '#######################################################\n' + \
    'STATE LOG\n' + \
    'Periodic State Logger\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'ACID [-], ' + \
    'Latitude [deg], ' + \
    'Longitude [deg], ' + \
    'Heading [deg], ' + \
    'Track [deg], ' + \
    'AP Track [deg], ' + \
    'Altitude [m], ' + \
    'Sel alt [m], ' + \
    'Vertical Speed [m/s], ' + \
    'Sel vs [m/s], ' + \
    'Mach [-], ' + \
    'Ground speed [m/s], ' + \
    'CAS [m/s], ' + \
    'Sel spd [m/s or -] \n'

# Global data
perflog = None

### Initialization function of your plugin. Do not change the name of this
### function, as it is the way BlueSky recognises this file as a plugin.
def init_plugin():

    # Addtional initilisation code
    global perflog
    perflog = PerformanceLogger()

    # Configuration parameters
    config = {
        # The name of your plugin
        'plugin_name':     'PERFLOG',

        # The type of this plugin. For now, only simulation plugins are possible.
        'plugin_type':     'sim'
        }

    stackfunctions = {
        'LOGMASS': [
            'LOGMASS acid',
            'acid',
            perflog.log_mass,
            'Log the mass of an aircraft'
        ],
        'SETMASS': [
            'SETMASS acid,mass',
            'acid,float',
            perflog.set_mass,
            'Set the mass of an aircraft'
        ],
    }

    return config, stackfunctions

class PerformanceLogger(Entity):
    ''' Traffic area: delete traffic when it leaves this area (so not when outside)'''
    def __init__(self):
        super().__init__()
        self.sb = StateBased()
        self.area = Area()
        self.prevlospairs = set()
        
        with self.settrafarrays():
            self.startmass = np.array([])
        
        # Get the North Atlantic navigation region area
        firdf     = extract_fir(['nat'])
        coords    = fir_boundary(firdf, 'fir')
        pa        = Proj("+proj=aea +lat_1=17.0 +lat_2=89.0 +lat_0=53.0 +lon_0=-23.0")
        lon, lat  = tuple(np.array(coords)[0][:,1]), tuple(np.array(coords)[0][:,0])
        x, y      = pa(lon, lat)
        cop       = {"type": "Polygon", "coordinates": [zip(x, y)]}
        self.simarea = shape(cop).area / 1e9 # thousand (1,000) km^2
        self.p       = path.Path(np.array(coords[0]))
        
        # Get the Gander and Shanwick FIRs area
        firdf     = extract_Gander_Shanwick()
        coords    = fir_boundary(firdf, 'fir')
        pa        = Proj("+proj=aea +lat_1=45.0 +lat_2=65.0 +lat_0=55.0 +lon_0=-35.5")
        lon, lat  = tuple(np.array(coords)[0][:,1]), tuple(np.array(coords)[0][:,0])
        x, y      = pa(lon, lat)
        cop       = {"type": "Polygon", "coordinates": [zip(x, y)]}
        self.GSarea = shape(cop).area / 1e9 # thousand (1,000) km^2
        self.p_GS   = path.Path(np.array(coords[0]))

        # The loggers
        self.fuellog  = datalog.crelog('FUELLOG', None, fuelheader)
        self.loslog   = datalog.crelog('LOSLOG', None, losheader)
        self.denslog  = datalog.crelog('DENSLOG', None, densheader)
        self.statelog = datalog.crelog('STATELOG', None, stateheader)

        # Start the loggers
        self.fuellog.start()
        self.loslog.start()
        self.denslog.start()
        self.statelog.start()

    def reset(self):
        ''' Reset area state when simulation is reset. '''
        super().reset()
        self.startmass = np.array([])

    def create(self, n=1):
        ''' Create is called when new aircraft are created. '''
        super().create(n)

    def log_mass(self, idx):
        """ Log the mass/fuel of the aircraft when calling this function via AT """
        self.fuellog.log(
            traf.id[idx],
            self.startmass[idx],
            traf.perf.mass[idx],
            (self.startmass[idx] - traf.perf.mass[idx]))
    
    def set_mass(self, idx, mass):
        """ Set the mass of the aircraft for performance purposes """
        traf.perf.mass[idx] = mass
        self.startmass[idx] = traf.perf.mass[idx]

    @timed_function(name='PERFLOG', dt=1.0)
    def update(self, dt):
        ''' Update Los of Separation metrics, intrusion severity '''
        
        # # Hold simulation if new lospairs are detected to research cause
        # lospairs_new = list(set(traf.cd.lospairs) - self.prevlospairs)
        # if lospairs_new:
        #     stack.stack("HOLD")
        
        # self.prevlospairs = set(traf.cd.lospairs)

        # Log lospairs
        if len(traf.cd.lospairs) > 0:
            newconf_unique = {frozenset(pair) for pair in traf.cd.lospairs}
            ac1, ac2 = zip(*newconf_unique)
            idx1 = traf.id2idx(ac1)
            idx2 = traf.id2idx(ac2)
            indcs = [traf.cd.lospairs.index(x) for x in list(zip(ac1, ac2))]
            intsev = self.sb.int_sev[indcs]

            self.loslog.log(list(zip(ac1, ac2)), 
                            list(zip(self.area.create_time[idx1], self.area.create_time[idx2])),
                            list(zip(traf.lat[idx1], traf.lon[idx1])),
                            list(zip(traf.lat[idx2], traf.lon[idx2])),
                            list(zip(traf.alt[idx1], traf.alt[idx2])),
                            list(zip(traf.hdg[idx1], traf.hdg[idx2])), intsev)
        
        # Density calculation every 15 minutes
        if sim.simt % 900 == 0:
            # Get the aircraft in the whole North Atlantic region
            inreg  = self.p.contains_points(np.concatenate((traf.lat.reshape(-1,1), traf.lon.reshape(-1,1)), axis=1))
            routes = list(compress(traf.ap.route, inreg)) 
            
            # Create empty arrays and loop over routes in region
            avgspd  = np.array([])
            avgdist = np.array([])
    
            for route in routes:
                spd = np.array(route.wpspd)
                alt = np.array(route.wpalt)
                lat = np.array(route.wplat)
                lon = np.array(route.wplon)
                avgspd  = np.append(avgspd, np.average(aero.vcas2tas(spd, alt)))
                avgdist = np.append(avgdist, np.sum(geo.latlondist_matrix(lat[0:-1], lon[0:-1],
                                                                          lat[1::], lon[1::])*geo.nm))
            
            # Calculate the density
            avg_tot_spd  = np.average(avgspd)
            avg_tot_dist = np.average(avgdist) 
            ac_dens      = np.sum(inreg)/(self.simarea*settings.asas_dt*(avg_tot_spd/avg_tot_dist))
            
            # Get the aircraft in the Gander and Shanwick FIRS
            inreg_GS  = self.p_GS.contains_points(np.concatenate((traf.lat.reshape(-1,1), 
                                                                  traf.lon.reshape(-1,1)), axis=1))
            routes_GS = list(compress(traf.ap.route, inreg_GS)) 
            
            # Create empty arrays and loop over routes in region
            avgspd_GS  = np.array([])
            avgdist_GS = np.array([])
    
            for route_GS in routes_GS:
                spd_GS = np.array(route_GS.wpspd)
                alt_GS = np.array(route_GS.wpalt)
                lat_GS = np.array(route_GS.wplat)
                lon_GS = np.array(route_GS.wplon)
                avgspd_GS  = np.append(avgspd_GS, np.average(aero.vcas2tas(spd_GS, alt_GS)))
                avgdist_GS = np.append(avgdist_GS, 
                                       np.sum(geo.latlondist_matrix(lat_GS[0:-1], lon_GS[0:-1],
                                                                    lat_GS[1::], lon_GS[1::])*geo.nm))
            
            # Calculate the density
            avg_tot_spd_GS  = np.average(avgspd_GS)
            avg_tot_dist_GS = np.average(avgdist_GS) 
            ac_dens_GS      = np.sum(inreg_GS)/(self.GSarea*settings.asas_dt*(avg_tot_spd_GS/avg_tot_dist_GS))
            
            self.denslog.log(np.sum(inreg), avg_tot_spd, avg_tot_dist, ac_dens,
                             np.sum(inreg_GS), avg_tot_spd_GS, avg_tot_dist_GS, ac_dens_GS)
            
        # Log aircraft states every 10 seconds
        if sim.simt % 10 == 0:
            self.statelog.log(traf.id, traf.lat, traf.lon, traf.hdg, traf.trk, 
                              (traf.ap.trk + 360)%360, traf.alt, traf.selalt, 
                              traf.vs, traf.selvs, traf.M, traf.gs, traf.cas,
                              traf.selspd)
