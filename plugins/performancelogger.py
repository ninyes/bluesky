""" BlueSky logger plugin to log aircraft performance.
    Initially log fuel consumption and intrusion severity """

import numpy as np
# Import the global bluesky objects. Uncomment the ones you need
from bluesky import traf  #, settings, navdb, traf, sim, scr, tools
from bluesky.tools import datalog
from bluesky.core import Entity, timed_function
from bluesky.traffic.asas import StateBased
from plugins.area import Area

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
    'Fuel Consumed [kg]'

# Log parameters for the los of separations log
losheader = \
    '#######################################################\n' + \
    'CONF LOG\n' + \
    'Conflict Statistics\n' + \
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
    'Intrusion severity [-]'

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
        
        with self.settrafarrays():
            self.startmass = np.array([])

        # The loggers
        self.fuellog = datalog.crelog('FUELLOG', None, fuelheader)
        self.loslog = datalog.crelog('LOSLOG', None, losheader)

        # Start the loggers
        self.fuellog.start()
        self.loslog.start()

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
        
        if self.sb.int_sev.any():
            newconf_unique = {frozenset(pair) for pair in traf.cd.lospairs}
            ac1, ac2 = zip(*newconf_unique)
            idx1 = traf.id2idx(ac1)
            idx2 = traf.id2idx(ac2)
            indcs = [traf.cd.lospairs.index(x) for x in list(zip(ac1, ac2))]
            intsev = self.sb.int_sev[indcs]

            self.loslog.log(list(zip(ac1, ac2)), 
                            list(zip(self.area.create_time[idx1], self.area.create_time[idx2])),
                            list(zip(traf.lat[idx1], traf.lon[idx1])),
                            list(zip(traf.lat[idx2], traf.lon[idx2])), intsev)