import numpy as np

# from abc import ABC, abstractmethod
from ies_utils import get_intensity_vectorized
from .trigonometry import attitude, to_polar


class CalcZone(object):
    """
    Base class representing a calculation zone.

    This class provides a template for setting up zones within which various
    calculations related to lighting conditions are performed. Subclasses should
    provide specific implementations of the coordinate setting method.

    NOTE: I changed this from an abstract base class to an object superclass
    to make it more convenient to work with the website, but this class doesn't really
    work on its own

    Parameters:
    --------
    zone_id: str
        identification tag for internal tracking
    name: str, default=None
        externally visible name for zone
    dimensions: array of floats, default=None
        array of len 2 if CalcPlane, of len 3 if CalcVol
    offset: bool, default=True
    fov80: bool, default=False
        apply 80 degree field of view filtering - used for calculating eye limits
    vert: bool, default=False
        calculate vertical irradiance only
    horiz: bool, default=False
        calculate horizontal irradiance only
    dose: bool, default=False
        whether to calculate a dose over N hours or just fluence
    hours: float, default = 8.0
        number of hours to calculate dose over. Only relevant if dose is True.
    visible: bool, default = True
        whether or not the calc zone is visible in the room plot
    """

    def __init__(
        self,
        zone_id,
        name=None,
        offset=None,
        fov80=None,
        vert=None,
        horiz=None,
        dose=None,
        hours=None,
        visible=None,
    ):
        self.zone_id = zone_id
        self.name = zone_id if name is None else name
        self.visible = True if visible is None else visible
        self.offset = True if offset is None else offset
        self.fov80 = False if fov80 is None else fov80
        self.vert = False if vert is None else vert
        self.horiz = False if horiz is None else horiz
        self.dose = False if dose is None else dose
        if self.dose:
            self.units = "mJ/cm2"
        else:
            self.units = "uW/cm2"
        self.hours = 8.0 if hours is None else hours  # only used if dose is true
        # these will all be calculated after spacing is set, which is set in the subclass
        self.x1 = None
        self.x2 = None
        self.y1 = None
        self.y2 = None
        self.z1 = None
        self.z2 = None
        self.height = None
        self.spacing = None
        self.x_spacing = None
        self.y_spacing = None
        self.z_spacing = None
        self.num_points = None
        self.xp = None
        self.yp = None
        self.zp = None
        self.coords = None
        self.values = None

    def set_dimensions(self, dimensions):
        raise NotImplementedError

    def set_spacing(self, spacing):
        raise NotImplementedError

    def set_offset(self, offset):
        if type(offset) is not bool:
            raise TypeError("Offset must be either True or False")
        self.offset = offset
        self._update

    def set_value_type(self, dose):
        """
        if true values will be in dose over time
        if false
        """
        if type(dose) is not bool:
            raise TypeError("Dose must be either True or False")

        # convert values if they need converting
        if dose and not self.dose:
            self.values = self.values * 3.6 * self.hours
        elif self.dose and not dose:
            self.values = self.values / (3.6 * self.hours)

        self.dose = dose
        if self.dose:
            self.units = "mJ/cm2"
        else:
            self.units = "uW/cm2"

    def set_dose_time(self, hours):
        if type(hours) not in [float, int]:
            raise TypeError("Hours must be numeric")
        self.hours = hours

    def calculate_values(self, lamps: list):
        """
        Calculate and return irradiance values at all coordinate points within the zone.
        """
        total_values = np.zeros(self.coords.shape[0])
        for lamp_id, lamp in lamps.items():
            # determine lamp placement + calculate relative coordinates
            rel_coords = self.coords - lamp.position
            # store the theta and phi data based on this orientation
            Theta0, Phi0, R0 = to_polar(*rel_coords.T)
            # apply all transformations that have been applied to this lamp, but in reverse
            rel_coords = np.array(
                attitude(rel_coords.T, roll=0, pitch=0, yaw=-lamp.heading)
            ).T
            rel_coords = np.array(
                attitude(rel_coords.T, roll=0, pitch=-lamp.bank, yaw=0)
            ).T
            rel_coords = np.array(
                attitude(rel_coords.T, roll=0, pitch=0, yaw=-lamp.angle)
            ).T
            Theta, Phi, R = to_polar(*rel_coords.T)
            values = get_intensity_vectorized(Theta, Phi, lamp.interpdict) / R ** 2
            if self.fov80:
                values[Theta0 < 50] = 0
            if self.vert:
                values *= np.sin(np.radians(Theta0))
            if self.horiz:
                values *= np.cos(np.radians(Theta0))
            if lamp.intensity_units == "mW/Sr":
                total_values += values / 10  # convert from mW/Sr to uW/cm2
            else:
                raise KeyError("Units not recognized")
        total_values = total_values.reshape(
            self.num_points
        )  # reshape to correct dimensions
        total_values = np.ma.masked_invalid(
            total_values
        )  # mask any nans near light source
        self.values = total_values
        # convert to dose
        if self.dose:
            self.values = self.values * 3.6 * self.hours
        return self.values


class CalcVol(CalcZone):
    """
    Represents a volumetric calculation zone.
    A subclass of CalcZone designed for three-dimensional volumetric calculations.
    """

    def __init__(
        self,
        zone_id,
        name=None,
        x1=None,
        x2=None,
        y1=None,
        y2=None,
        z1=None,
        z2=None,
        x_spacing=None,
        y_spacing=None,
        z_spacing=None,
        offset=None,
        fov80=None,
        vert=None,
        horiz=None,
        dose=None,
        hours=None,
        visible=None,
    ):

        super().__init__(
            zone_id, name, offset, fov80, vert, horiz, dose, hours, visible
        )
        self.x1 = 0 if x1 is None else x1
        self.x2 = 6 if x2 is None else x2
        self.y1 = 0 if y1 is None else y1
        self.y2 = 4 if y2 is None else y2
        self.z1 = 0 if z1 is None else z1
        self.z2 = 2.7 if z2 is None else z2
        self.x_spacing = 0.1 if x_spacing is None else x_spacing
        self.y_spacing = 0.1 if y_spacing is None else y_spacing
        self.z_spacing = 0.1 if z_spacing is None else z_spacing
        self._update()

    def set_dimensions(self, x1=None, x2=None, y1=None, y2=None, z1=None, z2=None):
        self.x1 = self.x1 if x1 is None else x1
        self.x2 = self.x2 if x2 is None else x2
        self.y1 = self.y1 if y1 is None else y1
        self.y2 = self.y2 if y2 is None else y2
        self.z1 = self.z1 if z1 is None else z1
        self.z2 = self.z2 if z2 is None else z2
        self._update()

    def set_spacing(self, x_spacing=None, y_spacing=None, z_spacing=None):
        self.x_spacing = self.x_spacing if x_spacing is None else x_spacing
        self.y_spacing = self.y_spacing if y_spacing is None else y_spacing
        self.z_spacing = self.z_spacing if z_spacing is None else z_spacing
        self._update()

    def _update(self):
        """
        Update the number of points based on the spacing, and then the points
        """
        numx = int((self.x2 - self.x1) / self.x_spacing)
        numy = int((self.y2 - self.y1) / self.y_spacing)
        numz = int((self.z2 - self.z1) / self.z_spacing)
        self.num_points = np.array([numx, numy, numz])
        if self.offset:
            xpoints = np.linspace(
                self.x1 + (self.x_spacing / 2), self.x2 - (self.x_spacing / 2), numx
            )
            ypoints = np.linspace(
                self.y1 + (self.y_spacing / 2), self.y2 - (self.y_spacing / 2), numy
            )
            zpoints = np.linspace(
                self.z1 + (self.z_spacing / 2), self.z2 - (self.z_spacing / 2), numz
            )
        else:
            xpoints = np.linspace(self.x1, self.x2, numx)
            ypoints = np.linspace(self.y1, self.y2, numy)
            zpoints = np.linspace(self.z1, self.z2, numz)
        self.points = [xpoints, ypoints, zpoints]
        self.xp, self.yp, self.zp = self.points
        X, Y, Z = [grid.reshape(-1) for grid in np.meshgrid(*self.points)]
        self.coords = np.array((X, Y, Z)).T


class CalcPlane(CalcZone):
    """
    Represents a planar calculation zone.
    A subclass of CalcZone designed for two-dimensional planar calculations at a specific height.
    """

    def __init__(
        self,
        zone_id,
        name=None,
        x1=None,
        x2=None,
        y1=None,
        y2=None,
        height=None,
        x_spacing=None,
        y_spacing=None,
        offset=None,
        fov80=None,
        vert=None,
        horiz=None,
        dose=None,
        hours=None,
        visible=None,
    ):

        super().__init__(
            zone_id, name, offset, fov80, vert, horiz, dose, hours, visible
        )

        self.height = 1.9 if height is None else height
        self.x1 = 0 if x1 is None else x1
        self.x2 = 6 if x2 is None else x2
        self.y1 = 0 if y1 is None else y1
        self.y2 = 4 if y2 is None else y2
        self.x_spacing = 0.1 if x_spacing is None else x_spacing
        self.y_spacing = 0.1 if y_spacing is None else y_spacing
        self._update()

    def set_height(self, height):
        if type(height) not in [float, int]:
            raise TypeError("Height must be numeric")
        self.height = height
        self._update()

    def set_dimensions(self, x1=None, x2=None, y1=None, y2=None):
        self.x1 = self.x1 if x1 is None else x1
        self.x2 = self.x2 if x2 is None else x2
        self.y1 = self.y1 if y1 is None else y1
        self.y2 = self.y2 if y2 is None else y2
        self._update()

    def set_spacing(self, x_spacing=None, y_spacing=None):
        self.x_spacing = self.x_spacing if x_spacing is None else x_spacing
        self.y_spacing = self.y_spacing if y_spacing is None else y_spacing
        self._update()

    def _update(self):
        """
        Update the number of points based on the spacing, and then the points
        """
        numx = int((self.x2 - self.x1) / self.x_spacing)
        numy = int((self.y2 - self.y1) / self.y_spacing)
        self.num_points = np.array([numx, numy])
        if self.offset:
            xpoints = np.linspace(
                self.x1 + (self.x_spacing / 2), self.x2 - (self.x_spacing / 2), numx
            )
            ypoints = np.linspace(
                self.y1 + (self.y_spacing / 2), self.y2 - (self.y_spacing / 2), numy
            )
        else:
            xpoints = np.linspace(self.x1, self.x2, numx)
            ypoints = np.linspace(self.y1, self.y2, numy)
        self.points = [xpoints, ypoints]
        self.xp, self.yp = self.points
        X, Y = [grid.reshape(-1) for grid in np.meshgrid(*self.points)]
        xy_coords = np.array([np.array((x0, y0)) for x0, y0 in zip(X, Y)])
        zs = np.ones(xy_coords.shape[0]) * self.height
        self.coords = np.stack([xy_coords.T[0], xy_coords.T[1], zs]).T
