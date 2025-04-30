import logging
from abc import ABC, abstractmethod
from ctypes import *
from functools import partial, wraps
from typing import Protocol, runtime_checkable

import yaml

from pyjrk.pyjrk_properties import PyJrkSettingsProperties
from pyjrk.pyjrk_protocol import jrk_constant as jc
from pyjrk.pyjrk_structures import *


# [J]rk [E]rror [D]ecoder
def JED(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        _e_p = func(*args, **kwargs)
        if bool(_e_p):
            _e = cast(_e_p, POINTER(jrk_error))
            # TODO pass logger to here
            _logger = logging.getLogger("PyJrk")
            _logger.error(_e.contents.message)
            return 1
        else:
            return 0

    return func_wrapper


@runtime_checkable
class LoggerProtocol(Protocol):
    def info(self, message: str, *args, **kwargs) -> None: ...
    def debug(self, message: str, *args, **kwargs) -> None: ...
    def warning(self, message: str, *args, **kwargs) -> None: ...
    def error(self, message: str, *args, **kwargs) -> None: ...


class PyJrkSettingsBase(ABC, PyJrkSettingsProperties):
    """Base class for PyJrk_Settings with static property definitions for IDE support."""

    def __init__(self, device_handle, driver_handles, logger: LoggerProtocol):
        self._device_handle = device_handle
        self.usblib, self.jrklib = driver_handles
        self._logger = logger

        # local vs device - local settings on pc, device settings on jrk
        self._local_settings = jrk_settings()
        self._device_settings = jrk_settings()
        self._device_settings_p = POINTER(jrk_settings)()

        self._convert_structure_to_properties()
        self.auto_apply = False

        self._initialize_settings()

    @abstractmethod
    def _initialize_settings(self): ...

    @abstractmethod
    def _get_jrk_setting_from_device(self, field_name: str, _): ...

    def _set_jrk_setting_with_option(self, field_name, _, value):
        setattr(self._local_settings, field_name, value)
        if self.auto_apply:
            self.apply()

    def _convert_structure_to_properties(self):
        for field_name, field_type in jrk_settings._fields_:
            prop = property(
                fget=partial(self._get_jrk_setting_from_device, field_name),
                fset=partial(self._set_jrk_setting_with_option, field_name),
            )
            setattr(self.__class__, field_name, prop)

    @abstractmethod
    def apply(self): ...

    @abstractmethod
    def print(self): ...

    def load_config(self, config_file):
        with open(config_file, "r") as ymlfile:
            cfg = yaml.safe_load(ymlfile)

        cfg_settings = cfg["jrk_settings"]

        jrk_settings_list = [
            setting_name for setting_name, setting_type in jrk_settings._fields_
        ]

        for setting in cfg_settings:
            if setting in jrk_settings_list:
                if "JRK" in str(cfg_settings[setting]):
                    value = jc[cfg_settings[setting]]
                else:
                    value = cfg_settings[setting]
                setattr(self._local_settings, setting, value)

        if self.auto_apply:
            self.apply()

    ## Wrapped methods from C API
    @JED
    def _get_eeprom_settings(self):
        """Gets the current settings stored in the device's EEPROM memory and write them
        to _device_settings_p.

        This method reads the current settings from the device's EEPROM and stores
        them in _device_settings. This function is always called before calling a
        getting a setting from the device via properties in order to refresh the settings.
        """
        e_p = self.jrklib.jrk_get_eeprom_settings(
            byref(self._device_handle), byref(self._device_settings_p)
        )
        self._device_settings = self._device_settings_p[0]
        return e_p

    @JED
    def _set_eeprom_settings(self):
        """Sets the controller settings based on _local_settings.

        This method writes the previously configured settings stored in _local_settings
        to the device's EEPROM memory. The _local_settings variable must be properly
        set before calling this method.
        """
        e_p = self.jrklib.jrk_set_eeprom_settings(
            byref(self._device_handle), byref(self._local_settings)
        )
        return e_p

    @JED
    def _get_ram_settings(self):
        """Gets the current settings stored in the device's RAM memory and write them
        to _device_settings_p.

        This method reads the current settings from the device's RAM and stores
        them in _device_settings.
        """
        e_p = self.jrklib.jrk_get_ram_settings(
            byref(self._device_handle), byref(self._device_settings_p)
        )
        self._device_settings = self._device_settings_p[0]
        return e_p

    @JED
    def _set_ram_settings(self):
        """Sets the controller settings based on _local_settings.

        This method writes the previously configured settings stored in _local_settings
        to the device's RAM memory. The _local_settings variable must be properly
        set before calling this method.
        """
        e_p = self.jrklib.jrk_set_ram_settings(
            byref(self._device_handle), byref(self._local_settings)
        )
        return e_p

    @JED
    def _jrk_restore_defaults(self):
        """ "Restore factory default settings to EEPROM"""
        e_p = self.jrklib.jrk_restore_defaults(byref(self._device_handle))
        return e_p

    @JED
    def _settings_fix(self):
        warnings_p = POINTER(c_char_p)()
        e_p = self.jrklib.jrk_settings_fix(byref(self._local_settings), warnings_p)
        if bool(warnings_p):
            for w in warnings_p:
                self._logger.warning(w)
        return e_p

    @JED
    def _reinitialize(self):
        e_p = self.jrklib.jrk_reinitialize(byref(self._device_handle))
        return e_p

    @JED
    def _settings_to_string(self, settings_str):
        e_p = self.jrklib.jrk_settings_to_string(
            byref(self._device_settings), byref(settings_str)
        )
        return e_p
