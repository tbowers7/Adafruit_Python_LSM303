# The MIT License (MIT)
#
# Copyright (c) 2016 Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import struct


# Minimal constants carried over from Arduino library:
LSM303_ADDRESS_ACCEL = (0x32 >> 1)  # 0011001x
LSM303_ADDRESS_MAG   = (0x3C >> 1)  # 0011110x
                                         # Default    Type
LSM303_REGISTER_ACCEL_CTRL_REG1_A = 0x20 # 00000111   rw
LSM303_REGISTER_ACCEL_CTRL_REG4_A = 0x23 # 00000000   rw
LSM303_REGISTER_ACCEL_OUT_X_L_A   = 0x28
LSM303_REGISTER_MAG_CRB_REG_M     = 0x01
LSM303_REGISTER_MAG_MR_REG_M      = 0x02
LSM303_REGISTER_MAG_OUT_X_H_M     = 0x03

# Gain settings for set_mag_gain()
LSM303_MAGGAIN_1_3 = 0x20 # +/- 1.3
LSM303_MAGGAIN_1_9 = 0x40 # +/- 1.9
LSM303_MAGGAIN_2_5 = 0x60 # +/- 2.5
LSM303_MAGGAIN_4_0 = 0x80 # +/- 4.0
LSM303_MAGGAIN_4_7 = 0xA0 # +/- 4.7
LSM303_MAGGAIN_5_6 = 0xC0 # +/- 5.6
LSM303_MAGGAIN_8_1 = 0xE0 # +/- 8.1


class LSM303(object):
    """LSM303 accelerometer & magnetometer."""

    def __init__(self, hires=True, accel_address=LSM303_ADDRESS_ACCEL,
                 mag_address=LSM303_ADDRESS_MAG, i2c=None, **kwargs):
        """Initialize the LSM303 accelerometer & magnetometer.  The hires
        boolean indicates if high resolution (12-bit) mode vs. low resolution
        (10-bit, faster and lower power) mode should be used.
        """
        # Setup I2C interface for accelerometer and magnetometer.
        if i2c is None:
            import Adafruit_GPIO.I2C as I2C
            i2c = I2C
        self._accel = i2c.get_i2c_device(accel_address, **kwargs)
        self._mag = i2c.get_i2c_device(mag_address, **kwargs)
        # Enable the accelerometer
        self._accel.write8(LSM303_REGISTER_ACCEL_CTRL_REG1_A, 0x27)
        # Select hi-res (12-bit) or low-res (10-bit) output mode.
        # Low-res mode uses less power and sustains a higher update rate,
        # output is padded to compatible 12-bit units.
        if hires:
            self._accel.write8(LSM303_REGISTER_ACCEL_CTRL_REG4_A, 0b00001000)
        else:
            self._accel.write8(LSM303_REGISTER_ACCEL_CTRL_REG4_A, 0)
        # Enable the magnetometer
        self._mag.write8(LSM303_REGISTER_MAG_MR_REG_M, 0x00)

    def read(self):
        """Read the accelerometer and magnetometer value.  A tuple of tuples will
        be returned with:
          ((accel X, accel Y, accel Z), (mag X, mag Y, mag Z))
        """
        # Read the accelerometer as signed 16-bit little endian values.
        accel_raw = self._accel.readList(LSM303_REGISTER_ACCEL_OUT_X_L_A | 0x80, 6)
        accel = struct.unpack('<hhh', accel_raw)
        # Convert to 12-bit values by shifting unused bits.
        accel = (accel[0] >> 4, accel[1] >> 4, accel[2] >> 4)
        # Read the magnetometer.
        mag_raw = self._mag.readList(LSM303_REGISTER_MAG_OUT_X_H_M, 6)
        mag = struct.unpack('>hhh', mag_raw)
        return (accel, mag)

    def set_mag_gain(self,gain=LSM303_MAGGAIN_1_3):
        """Set the magnetometer gain.  Gain should be one of the following
        constants:
         - LSM303_MAGGAIN_1_3 = +/- 1.3 (default)
         - LSM303_MAGGAIN_1_9 = +/- 1.9
         - LSM303_MAGGAIN_2_5 = +/- 2.5
         - LSM303_MAGGAIN_4_0 = +/- 4.0
         - LSM303_MAGGAIN_4_7 = +/- 4.7
         - LSM303_MAGGAIN_5_6 = +/- 5.6
         - LSM303_MAGGAIN_8_1 = +/- 8.1
        """
        self._mag.write8(LSM303_REGISTER_MAG_CRB_REG_M, gain)


    # ===================================================================
    # Compute the roll / pitch / heading from the acceleration and mag
    # data.
    #
    # Code translated from the Adafruit 9DOF Arduino library found at:
    # https://github.com/adafruit/Adafruit_9DOF/blob/master/Adafruit_9DOF.cpp
    #
    #************************************************************************
    #  This is a library for the Adafruit 9DOF Breakout
    #  Designed specifically to work with the Adafruit 9DOF Breakout:
    #  http://www.adafruit.com/products/1714
    #  This class does not communicate directly with the hardware, but
    #  converts raw readings (X-Y-Z magnitudes) into more useful values in
    #  degrees (roll, pitch, heading).
    #  Adafruit invests time and resources providing this open source code,
    #  please support Adafruit and open-source hardware by purchasing products
    #  from Adafruit!
    #  Written by Kevin Townsend for Adafruit Industries.
    #  BSD license, all text above must be included in any redistribution
    #************************************************************************
    #
    # The starting position is set by placing the object flat and
    # pointing northwards (Z-axis pointing upward and X-axis pointing
    # northwards).
    #
    # The orientation of the object can be modeled as resulting from
    # 3 consecutive rotations in turn: heading (Z-axis), pitch (Y-axis),
    # and roll (X-axis) applied to the starting position.
    
    def get_orientation(self, accel, mag):
        import numpy as np
        
        # Unpack the accel and mag tuples
        accel_x, accel_y, accel_z = accel
        mag_x, mag_y, mag_z = mag
        
        # roll: Rotation around the X-axis. -180 <= roll <= 180
        # a positive roll angle is defined to be a clockwise rotation about the
        # positive X-axis
        #
        #                y
        #  roll = atan2(---)
        #                z
        #
        # where:  y, z are returned value from accelerometer sensor
        roll = np.arctan2(accel_y, accel_z)
        
        # pitch: Rotation around the Y-axis. -180 <= roll <= 180
        # a positive pitch angle is defined to be a clockwise rotation about
        # the positive Y-axis
        #
        #                                 -x
        #      pitch = atan(-------------------------------)
        #                    y * sin(roll) + z * cos(roll)
        #
        # where:  x, y, z are returned value from accelerometer sensor
        if (accel_y * np.sin(roll) + accel_z * np.cos(roll) == 0):
            pitch = (np.pi / 2.) if accel_x > 0 else (-np.pi / 2.)
        else:
            pitch = np.arctan(accel_x / (accel_y * np.sin(roll) +
                                       accel_z * np.cos(roll) ) )

        # heading: Rotation around the Z-axis. -180 <= roll <= 180
        # a positive heading angle is defined to be a clockwise rotation about
        # the positive Z-axis
        #
        #                                       z * sin(roll) - y * cos(roll)
        #   heading = atan2(--------------------------------------------------------------------------)
        #                    x * cos(pitch) + y * sin(pitch) * sin(roll) + z * sin(pitch) * cos(roll))
        #
        # where:  x, y, z are returned value from magnetometer sensor
        heading = np.arctan2( mag_z * np.sin(roll) - mag_y * np.cos(roll),
                              mag_x * np.cos(pitch) +
                              mag_y * np.sin(pitch) * np.sin(roll) +
                              mag_z * np.sin(pitch) * np.cos(roll) )

        # Convert angular data to degrees
        roll    = roll    * 180. / np.pi
        pitch   = pitch   * 180. / np.pi
        heading = heading * 180. / np.pi

        # Return
        return (roll, pitch, heading)
    

    #==========================================================#
    # Python port of GSL's hypot3 function ([gsl]/sys/hypot.c) #
    # This function computes the value of √( x ² + y ² + z ²)  #
    # in a way that avoids overflow.                           #
    #==========================================================#
    def hypot3(self, x, y, z):
        import numpy as np

        # Take the absolute values of each input, find maximum
        xabs = np.fabs(x)
        yabs = np.fabs(y)
        zabs = np.fabs(z)
        w = np.amax([xabs,yabs,zabs])

        if (w == 0.0):
            return 0.0
        else:
            r = w * np.sqrt((xabs / w) * (xabs / w) +
                            (yabs / w) * (yabs / w) +
                            (zabs / w) * (zabs / w))
            return r


