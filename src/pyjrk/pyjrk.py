import logging
import os
import platform
from ctypes import *
from functools import partial
from typing import Callable

from pyjrk.pyjrk_base import JED, LoggerProtocol, PyJrkSettingsBase
from pyjrk.pyjrk_properties import PyJrkVariablesProperties
from pyjrk.pyjrk_protocol import jrk_constant as jc
from pyjrk.pyjrk_structures import *


class PyJrk:
    # Type annotations for dynamically created methods
    set_target: Callable[[int], int]
    stop_motor: Callable[[], int]
    force_duty_cycle_target: Callable[[], int]
    force_duty_cycle: Callable[[], int]
    reinitialize: Callable[[int], int]

    def __init__(self, logger: LoggerProtocol = None):
        self._logger = logger if logger else self._initialize_default_logger()
        self._load_drivers()

        self.device = None
        self.handle = None
        self.eeprom_settings: PyJrkEEPROMSettings = None
        self.ram_settings: PyJrkRAMSettings = None
        self.variables: PyJrkVariables = None
        self._commands = [
            ("set_target", c_uint16),
            ("stop_motor", None),
            ("force_duty_cycle_target", c_uint16),
            ("force_duty_cycle", c_uint16),
            ("reinitialize", c_uint8),
        ]
        self._create_jrk_command_attributes()

    def _initialize_default_logger(self):
        # - Logging -
        self._log_level = logging.DEBUG
        _logger = logging.getLogger("PyJrk")
        _logger.setLevel(self._log_level)
        _formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        # Console Logging
        _ch = logging.StreamHandler()
        _ch.setLevel(self._log_level)
        _ch.setFormatter(_formatter)
        _logger.addHandler(_ch)
        return _logger

    @property
    def log_level(self):
        return self._log_level

    @log_level.setter
    def log_level(self, level):
        self._log_level = level
        self._logger.setLevel(level)

    def _load_drivers(self):
        # Driver Locations (x64)
        file_path = os.path.dirname(os.path.abspath(__file__))
        if platform.system() == "Windows":
            # Windows DLL paths
            self.usblib = windll.LoadLibrary(
                file_path + "\\drivers\\x64\\libusbp-1.dll"
            )  # type: ignore
            self.jrklib = windll.LoadLibrary(
                file_path + "\\drivers\\x64\\libpololu-jrk2-1.dll"
            )  # type: ignore
        elif platform.system() == "Linux":
            # Linux shared library paths
            self.usblib = CDLL(file_path + "/drivers/linux/libusbp-1.so")
            self.jrklib = CDLL(file_path + "/drivers/linux/libpololu-jrk2-1.so")
        self._logger.debug("JRK Drivers loaded")

    def _create_jrk_command_attributes(self):
        for cmd_name, value_c_type in self._commands:
            if bool(value_c_type):
                setattr(
                    self.__class__,
                    cmd_name,
                    partial(self._jrk_command_with_value, cmd_name, value_c_type),
                )
            else:
                setattr(self.__class__, cmd_name, partial(self._jrk_command, cmd_name))

    @JED
    def _jrk_command(self, cmd_name):
        e_p = getattr(self.jrklib, "jrk_" + cmd_name)(byref(self.handle))
        return e_p

    @JED
    def _jrk_command_with_value(self, cmd_name, value_c_type, value):
        if "JRK" in str(value):
            value = jc[value]
        e_p = getattr(self.jrklib, "jrk_" + cmd_name)(
            byref(self.handle), value_c_type(value)
        )
        return e_p

    @JED
    def _list_connected_devices(self):
        self._devcnt = c_size_t(0)
        self._dev_pp = POINTER(POINTER(jrk_device))()
        e_p = self.jrklib.jrk_list_connected_devices(
            byref(self._dev_pp), byref(self._devcnt)
        )
        return e_p

    @JED
    def _jrk_handle_open(self):
        handle_p = POINTER(jrk_handle)()
        e_p = self.jrklib.jrk_handle_open(byref(self.device), byref(handle_p))
        self.handle = handle_p[0]
        return e_p

    def list_connected_device_serial_numbers(self):
        self._list_connected_devices()
        jrk_list = []
        if not self._devcnt.value:
            self._logger.warning("No Jrk devices connected.")
        for i in range(0, self._devcnt.value):
            jrkdev = self._dev_pp[0][i]
            jrk_list.append(jrkdev.serial_number.decode("utf-8"))
        return jrk_list

    def connect_to_serial_number(self, serial_number):
        self._list_connected_devices()
        for i in range(0, self._devcnt.value):
            if serial_number == self._dev_pp[0][i].serial_number.decode("utf-8"):
                self.device = self._dev_pp[0][i]
                self._jrk_handle_open()
                self.variables = PyJrkVariables(
                    self.handle, (self.usblib, self.jrklib), self._logger
                )
                self.eeprom_settings = PyJrkEEPROMSettings(
                    self.handle, (self.usblib, self.jrklib), self._logger
                )
                self.ram_settings = PyJrkRAMSettings(
                    self.handle, (self.usblib, self.jrklib), self._logger
                )
                return 0
        if not self.device:
            self._logger.error("Serial number device not found.")
            return 1


class PyJrkVariables(PyJrkVariablesProperties):
    def __init__(self, device_handle, driver_handles, logger: LoggerProtocol):
        self._device_handle = device_handle
        self.usblib, self.jrklib = driver_handles
        self._logger = logger

        self._jrk_variables_p = POINTER(jrk_variables)()
        self._jrk_variables = jrk_variables()

        self.pin_info = []
        for i in range(0, jc["JRK_CONTROL_PIN_COUNT"]):
            self.pin_info.append(type("pinfo_" + str(i), (object,), {})())

        self._convert_structure_to_readonly_properties()

    def _convert_structure_to_readonly_properties(self):
        for field_name, field_type in jrk_variables._fields_:
            if not field_name == "pin_info":
                prop = property(
                    fget=partial(self._get_jrk_readonly_property, field_name)
                )
                setattr(self.__class__, field_name, prop)

        for i in range(0, jc["JRK_CONTROL_PIN_COUNT"]):
            for field_name, field_type in pin_info._fields_:
                prop = property(
                    fget=partial(self._get_pin_readonly_property, field_name, i)
                )
                setattr(self.pin_info[i].__class__, field_name, prop)

    @JED
    def _update_jrk_variables(self):
        e_p = self.jrklib.jrk_get_variables(
            byref(self._device_handle), byref(self._jrk_variables_p), c_bool(True)
        )
        self._jrk_variables = self._jrk_variables_p[0]
        return e_p

    def _get_jrk_readonly_property(self, field_name, _):
        self._update_jrk_variables()
        value = getattr(self._jrk_variables, field_name)
        if field_name == "error_flags_halting" or field_name == "error_flags_occurred":
            error_list = self._convert_error_bitmask(value)
            self._logger.debug(error_list)
        return value

    def _get_pin_readonly_property(self, field_name, pin_num, _):
        self._update_jrk_variables()
        return getattr(self._jrk_variables.pin_info[pin_num], field_name)

    def _convert_error_bitmask(self, e_bit_mask):
        ecodes = [
            "JRK_ERROR_AWAITING_COMMAND",
            "JRK_ERROR_NO_POWER",
            "JRK_ERROR_MOTOR_DRIVER",
            "JRK_ERROR_INPUT_INVALID",
            "JRK_ERROR_INPUT_DISCONNECT",
            "JRK_ERROR_FEEDBACK_DISCONNECT",
            "JRK_ERROR_SOFT_OVERCURRENT",
            "JRK_ERROR_SERIAL_SIGNAL",
            "JRK_ERROR_SERIAL_OVERRUN",
            "JRK_ERROR_SERIAL_BUFFER_FULL",
            "JRK_ERROR_SERIAL_CRC",
            "JRK_ERROR_SERIAL_PROTOCOL",
            "JRK_ERROR_SERIAL_TIMEOUT",
            "JRK_ERROR_HARD_OVERCURRENT",
        ]
        error_list = []
        for code in ecodes:
            if (e_bit_mask >> jc[code]) & 1:
                error_list.append(code)
        return error_list


class PyJrkEEPROMSettings(PyJrkSettingsBase):
    def __init__(self, device_handle, driver_handles, logger: LoggerProtocol):
        super().__init__(device_handle, driver_handles, logger)

    def _initialize_settings(self):
        """Get current settings from eeprom and fill the _local_settings"""
        self._get_eeprom_settings()
        self._local_settings = self._device_settings_p[0]

    def _convert_structure_to_properties(self):
        for field_name, field_type in jrk_settings._fields_:
            prop = property(
                fget=partial(self._get_jrk_setting_from_device, field_name),
                fset=partial(self._set_jrk_setting_with_option, field_name),
            )
            setattr(self.__class__, field_name, prop)

    def _get_jrk_setting_from_device(self, field_name: str, _):
        self._get_eeprom_settings()
        return getattr(self._device_settings, field_name)

    def apply(self):
        self._settings_fix()
        self._set_eeprom_settings()
        self._reinitialize()

    def print(self):
        settings_str = c_char_p()
        self._get_eeprom_settings()
        self._settings_to_string(settings_str)
        self._logger.debug(f"Device EEPROM settings:\n{settings_str.value.decode()}")


class PyJrkRAMSettings(PyJrkSettingsBase):
    def __init__(self, device_handle, driver_handles, logger: LoggerProtocol):
        super().__init__(device_handle, driver_handles, logger)
        self.auto_apply = True

    def _initialize_settings(self):
        """Get current settings from eeprom, fill the _local_settings with them
        and set the ram settings to the current eeprom settings"""
        self._get_eeprom_settings()
        self._local_settings = self._device_settings_p[0]
        self._set_ram_settings()

    def _get_jrk_setting_from_device(self, field_name: str, _):
        self._get_ram_settings()
        return getattr(self._device_settings, field_name)

    def apply(self):
        self._settings_fix()
        self._set_ram_settings()

    def print(self):
        settings_str = c_char_p()
        self._get_ram_settings()
        self._settings_to_string(settings_str)
        self._logger.debug(f"Device RAM settings:\n{settings_str.value.decode()}")


if __name__ == "__main__":
    jrk = PyJrk()
    print(jrk.list_connected_device_serial_numbers())
