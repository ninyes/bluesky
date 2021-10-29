""" BlueSky logger plugin to log aircraft performance.
    Initially log fuel consumption and intrusion severity """

import numpy as np
# Import the global bluesky objects. Uncomment the ones you need
from bluesky import traf, sim, stack  #, settings, navdb, traf, sim, scr, tools
from bluesky.tools import datalog, areafilter
from bluesky.core import Entity, timed_function
from bluesky.tools.aero import ft, kts, nm, fpm, vcasormach, vatmos
# from bluesky.traffic.performance.perfbase import PerfBase

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

losheader = \
    '#######################################################\n' + \
    'CONF LOG\n' + \
    'Conflict Statistics\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'LoS pair [-], ' + \
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
        # # Parameters of area
        # self.active = False
        # self.delarea = ''
        # self.exparea = ''
        # self.swtaxi = True  # Default ON: Doesn't do anything. See comments of set_taxi function below.
        # self.swtaxialt = 1500.0  # Default alt for TAXI OFF
        # self.prevconfpairs = set()
        # self.confinside_all = 0
        
        # with self.settrafarrays():
        #     self.insdel = np.array([], dtype=np.bool) # In deletion area or not
        #     self.insexp = np.array([], dtype=np.bool) # In experiment area or not
        #     self.oldalt = np.array([])
        #     self.distance2D = np.array([])
        #     self.distance3D = np.array([])
        #     self.dstart2D = np.array([])
        #     self.dstart3D = np.array([])
        #     self.workstart = np.array([])
        #     self.entrymass = np.array([])
        #     self.entrytime = np.array([])
        #     self.create_time = np.array([])
        
        with self.settrafarrays():
            self.startmass = np.array([])

        # The loggers
        self.fuellog = datalog.crelog('FUELLOG', None, fuelheader)
        self.loslog = datalog.crelog('LOSLOG', None, losheader)

        # Start the loggers
        self.fuellog.start()
        # self.loslog.start()

    def reset(self):
        ''' Reset area state when simulation is reset. '''
        super().reset()
    #     self.active = False
    #     self.delarea = ''
    #     self.exparea = ''
    #     self.swtaxi = True
    #     self.swtaxialt = 1500.0
    #     self.confinside_all = 0

    def create(self, n=1):
        ''' Create is called when new aircraft are created. '''
        super().create(n)
    #     self.oldalt[-n:] = traf.alt[-n:]
    #     self.insdel[-n:] = False
    #     self.insexp[-n:] = False
    #     self.create_time[-n:] = sim.simt

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


    # @timed_function(name='LOSLOG', dt=1.0)
    # def update(self, dt):
    #     ''' Update flight efficiency metrics
    #         2D and 3D distance [m], and work done (force*distance) [J] '''
    #     if self.active:
    #         resultantspd = np.sqrt(traf.gs * traf.gs + traf.vs * traf.vs)
    #         self.distance2D += dt * traf.gs
    #         self.distance3D += dt * resultantspd

    #         # Find out which aircraft are currently inside the experiment area, and
    #         # determine which aircraft need to be deleted.
    #         insdel = areafilter.checkInside(self.delarea, traf.lat, traf.lon, traf.alt)
    #         insexp = insdel if not self.exparea else \
    #             areafilter.checkInside(self.exparea, traf.lat, traf.lon, traf.alt)
    #         # Find all aircraft that were inside in the previous timestep, but no
    #         # longer are in the current timestep
    #         delidx = np.where(np.array(self.insdel) * (np.array(insdel) == False))[0]
    #         self.insdel = insdel

    #         # Count new conflicts where at least one of the aircraft is inside
    #         # the experiment area
    #         # Store statistics for all new conflict pairs
    #         # Conflict pairs detected in the current timestep that were not yet
    #         # present in the previous timestep
    #         confpairs_new = list(set(traf.cd.confpairs) - self.prevconfpairs)
    #         if confpairs_new:
    #             # If necessary: select conflict geometry parameters for new conflicts
    #             # idxdict = dict((v, i) for i, v in enumerate(traf.cd.confpairs))
    #             # idxnew = [idxdict.get(i) for i in confpairs_new]
    #             # dcpa_new = np.asarray(traf.cd.dcpa)[idxnew]
    #             # tcpa_new = np.asarray(traf.cd.tcpa)[idxnew]
    #             # tLOS_new = np.asarray(traf.cd.tLOS)[idxnew]
    #             # qdr_new = np.asarray(traf.cd.qdr)[idxnew]
    #             # dist_new = np.asarray(traf.cd.dist)[idxnew]

    #             newconf_unique = {frozenset(pair) for pair in confpairs_new}
    #             ac1, ac2 = zip(*newconf_unique)
    #             idx1 = traf.id2idx(ac1)
    #             idx2 = traf.id2idx(ac2)
    #             newconf_inside = np.logical_or(insexp[idx1], insexp[idx2])

    #             nnewconf_exp = np.count_nonzero(newconf_inside)
    #             if nnewconf_exp:
    #                 self.confinside_all += nnewconf_exp
    #                 self.conflog.log(self.confinside_all)
    #         self.prevconfpairs = set(traf.cd.confpairs)

            
    #         # Register distance values upon entry of experiment area
    #         newentries = np.logical_not(self.insexp) * insexp
    #         self.dstart2D[newentries] = self.distance2D[newentries]
    #         self.dstart3D[newentries] = self.distance3D[newentries]
    #         self.workstart[newentries] = traf.work[newentries]
    #         self.entrymass[newentries] = traf.perf.mass[newentries]
    #         self.entrytime[newentries] = sim.simt

    #         # Log flight statistics when exiting experiment area
    #         exits = np.logical_and(self.insexp,np.logical_not(insexp))
    #         # Update insexp
    #         self.insexp = insexp

    #         if np.any(exits):
    #             self.flst.log(
    #                 np.array(traf.id)[exits],
    #                 np.array(traf.type)[exits],
    #                 self.create_time[exits],
    #                 sim.simt - self.entrytime[exits],
    #                 (self.distance2D[exits] - self.dstart2D[exits])/nm,
    #                 (self.distance3D[exits] - self.dstart3D[exits])/nm,
    #                 (traf.work[exits] - self.workstart[exits])*1e-6,
    #                 (self.entrymass[exits] - traf.perf.mass[exits]),
    #                 traf.lat[exits],
    #                 traf.lon[exits],
    #                 traf.alt[exits]/ft,
    #                 traf.tas[exits]/kts,
    #                 traf.vs[exits]/fpm,
    #                 traf.hdg[exits],
    #                 traf.cr.active[exits],
    #                 traf.aporasas.alt[exits]/ft,
    #                 traf.aporasas.tas[exits]/kts,
    #                 traf.aporasas.vs[exits]/fpm,
    #                 traf.aporasas.hdg[exits])

    #         # delete all aicraft in self.delidx
    #         if len(delidx) > 0:
    #             traf.delete(delidx)


