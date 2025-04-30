from ctypes import *

from pyjrk.pyjrk_protocol import jrk_constant as j_const


class libusbp_generic_interface(Structure):
    _fields_ = [
        ("interface_number", c_uint8),
        ("device_instance_id", c_char_p),
        ("filename", c_char_p),
    ]


class libusbp_generic_handle(Structure):
    # untested type, no HANDLE or WIN_INTERFACE_HANDLE type
    _fields_ = [("file_handle", c_ulong), ("winusb_handle", c_ulong)]


class libusbp_device(Structure):
    _fields_ = [
        ("device_instance_id", c_char_p),
        ("product_id", c_uint16),
        ("vendor_id", c_uint16),
        ("revision", c_uint16),
    ]


class jrk_device(Structure):
    _fields_ = [
        ("usb_device", POINTER(libusbp_device)),
        ("usb_interface", POINTER(libusbp_generic_interface)),
        ("serial_number", c_char_p),
        ("os_id", c_char_p),
        ("firmware_version", c_uint16),
        ("product", c_uint32),
    ]


class jrk_handle(Structure):
    _fields_ = [
        ("usb_handle", POINTER(libusbp_generic_handle)),
        ("device", POINTER(jrk_device)),
        ("cached_firmware_version_string", c_char_p),
    ]


class jrk_settings(Structure):
    _fields_ = [
        ("product", c_uint32),
        ("firmware_version", c_uint16),
        ("input_mode", c_uint8),
        ("input_error_minimum", c_uint16),
        ("input_error_maximum", c_uint16),
        ("input_minimum", c_uint16),
        ("input_maximum", c_uint16),
        ("input_neutral_minimum", c_uint16),
        ("input_neutral_maximum", c_uint16),
        ("output_minimum", c_uint16),
        ("output_neutral", c_uint16),
        ("output_maximum", c_uint16),
        ("input_invert", c_bool),
        ("input_scaling_degree", c_uint8),
        ("input_detect_disconnect", c_bool),
        ("input_analog_samples_exponent", c_uint8),
        ("feedback_mode", c_uint8),
        ("feedback_error_minimum", c_uint16),
        ("feedback_error_maximum", c_uint16),
        ("feedback_minimum", c_uint16),
        ("feedback_maximum", c_uint16),
        ("feedback_invert", c_bool),
        ("feedback_detect_disconnect", c_bool),
        ("feedback_dead_zone", c_uint8),
        ("feedback_analog_samples_exponent", c_uint8),
        ("feedback_wraparound", c_bool),
        ("serial_mode", c_uint8),
        ("serial_baud_rate", c_uint32),
        ("serial_timeout", c_uint32),
        ("serial_device_number", c_uint16),
        ("never_sleep", c_bool),
        ("serial_enable_crc", c_bool),
        ("serial_enable_14bit_device_number", c_bool),
        ("serial_disable_compact_protocol", c_bool),
        ("proportional_multiplier", c_uint16),
        ("proportional_exponent", c_uint8),
        ("integral_multiplier", c_uint16),
        ("integral_exponent", c_uint8),
        ("derivative_multiplier", c_uint16),
        ("derivative_exponent", c_uint8),
        ("pid_period", c_uint16),
        ("integral_divider_exponent", c_uint8),
        ("integral_limit", c_uint16),
        ("reset_integral", c_bool),
        ("pwm_frequency", c_uint8),
        ("current_samples_exponent", c_uint8),
        ("hard_overcurrent_threshold", c_uint8),
        ("current_offset_calibration", c_int16),
        ("current_scale_calibration", c_int16),
        ("motor_invert", c_bool),
        ("max_duty_cycle_while_feedback_out_of_range", c_uint16),
        ("max_acceleration_forward", c_uint16),
        ("max_acceleration_reverse", c_uint16),
        ("max_deceleration_forward", c_uint16),
        ("max_deceleration_reverse", c_uint16),
        ("max_duty_cycle_forward", c_uint16),
        ("max_duty_cycle_reverse", c_uint16),
        ("encoded_hard_current_limit_forward", c_uint16),
        ("encoded_hard_current_limit_reverse", c_uint16),
        ("brake_duration_forward", c_uint32),
        ("brake_duration_reverse", c_uint32),
        ("soft_current_limit_forward", c_uint16),
        ("soft_current_limit_reverse", c_uint16),
        ("soft_current_regulation_level_forward", c_uint16),
        ("soft_current_regulation_level_reverse", c_uint16),
        ("coast_when_off", c_bool),
        ("error_enable", c_uint16),
        ("error_latch", c_uint16),
        ("error_hard", c_uint16),
        ("vin_calibration", c_int16),
        ("disable_i2c_pullups", c_bool),
        ("analog_sda_pullup", c_bool),
        ("always_analog_sda", c_bool),
        ("always_analog_fba", c_bool),
        ("fbt_method", c_uint8),
        ("fbt_timing_clock", c_uint8),
        ("fbt_timing_polarity", c_bool),
        ("fbt_timing_timeout", c_uint16),
        ("fbt_samples", c_uint8),
        ("fbt_divider_exponent", c_uint8),
    ]


class pin_info(Structure):
    _fields_ = [
        ("analog_reading", c_uint16),
        ("digital_reading", c_bool),
        ("pin_state", c_uint8),
    ]


class jrk_variables(Structure):
    _fields_ = [
        ("input", c_uint16),
        ("target", c_uint16),
        ("feedback", c_uint16),
        ("scaled_feedback", c_uint16),
        ("integral", c_int16),
        ("duty_cycle_target", c_int16),
        ("duty_cycle", c_int16),
        ("current_low_res", c_uint8),
        ("pid_period_exceeded", c_bool),
        ("pid_period_count", c_uint16),
        ("error_flags_halting", c_uint16),
        ("error_flags_occurred", c_uint16),
        ("vin_voltage", c_uint16),
        ("current", c_uint16),
        ("device_reset", c_uint8),
        ("up_time", c_uint32),
        ("rc_pulse_width", c_uint16),
        ("fbt_reading", c_uint16),
        ("raw_current", c_uint16),
        ("encoded_hard_current_limit", c_uint16),
        ("last_duty_cycle", c_int16),
        ("current_chopping_consecutive_count", c_uint8),
        ("current_chopping_occurrence_count", c_uint8),
        ("force_mode", c_uint8),
        ("pin_info", pin_info * j_const["JRK_CONTROL_PIN_COUNT"]),
    ]


class jrk_error(Structure):
    _fields_ = [
        ("do_not_free", c_bool),
        ("message", c_char_p),
        ("code_count", c_size_t),
        ("code_array", POINTER(c_uint32)),
    ]
