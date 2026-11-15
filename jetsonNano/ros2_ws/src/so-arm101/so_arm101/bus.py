"""Narrow Feetech STS3215 bus adapter for the SO-101 follower."""


class FeetechBus:
    def __init__(self, port_name, baudrate):
        from scservo_sdk import COMM_SUCCESS, PortHandler
        from scservo_sdk.sms_sts import sms_sts

        self.comm_success = COMM_SUCCESS
        self.port = PortHandler(port_name)
        self.handler = sms_sts(self.port)
        if not self.port.openPort():
            raise RuntimeError(f"Cannot open serial port {port_name}")
        if not self.port.setBaudRate(baudrate):
            self.port.closePort()
            raise RuntimeError(f"Cannot set serial baud rate to {baudrate}")

    def read_positions(self, motor_ids):
        positions = []
        for motor_id in motor_ids:
            position, result, error = self.handler.ReadPos(motor_id)
            self._check(motor_id, result, error)
            if not 0 <= position <= 4095:
                raise RuntimeError(f"Motor {motor_id} returned invalid position {position}")
            positions.append(position)
        return positions

    def read_register(self, motor_id, address, size=1):
        if size == 1:
            value, result, error = self.handler.read1ByteTxRx(motor_id, address)
        elif size == 2:
            value, result, error = self.handler.read2ByteTxRx(motor_id, address)
        else:
            raise ValueError("Only one- and two-byte registers are supported")
        self._check(motor_id, result, error)
        return value

    def write_positions(self, motor_ids, targets, speed, acceleration):
        for motor_id, target in zip(motor_ids, targets):
            result, error = self.handler.WritePosEx(motor_id, target, speed, acceleration)
            self._check(motor_id, result, error)

    def enable_motion(self, motor_ids, positions, speed, acceleration):
        for motor_id in motor_ids:
            if self.read_register(motor_id, 33) != 0:
                raise RuntimeError(f"Motor {motor_id} is not in position mode")
            if self.read_register(motor_id, 65) != 0:
                raise RuntimeError(f"Motor {motor_id} reports a protection fault")
            if self.read_register(motor_id, 62) < 40:
                raise RuntimeError(f"Motor {motor_id} supply is below 4.0 V")
        # A stale goal may be zero after power-up. Replace it before applying torque.
        self.write_positions(motor_ids, positions, speed, acceleration)
        enabled = []
        try:
            for motor_id in motor_ids:
                self.write_register(motor_id, 40, 1)
                enabled.append(motor_id)
                if self.read_register(motor_id, 40) != 1:
                    raise RuntimeError(f"Motor {motor_id} did not enable torque")
        except Exception:
            self.disable_torque(enabled)
            raise

    def write_register(self, motor_id, address, value):
        result, error = self.handler.write1ByteTxRx(motor_id, address, value)
        self._check(motor_id, result, error)

    def disable_torque(self, motor_ids):
        for motor_id in motor_ids:
            self.write_register(motor_id, 40, 0)

    def close(self):
        self.port.closePort()

    def _check(self, motor_id, result, error):
        if result != self.comm_success:
            raise RuntimeError(
                f"Motor {motor_id}: {self.handler.getTxRxResult(result)}"
            )
        if error:
            raise RuntimeError(
                f"Motor {motor_id}: {self.handler.getRxPacketError(error)}"
            )


class SimulatedBus:
    """Software-only bus for trying the ROS interface without an arm."""

    def __init__(self, motor_ids):
        self.positions = dict.fromkeys(motor_ids, 2048)

    def read_positions(self, motor_ids):
        return [self.positions[motor_id] for motor_id in motor_ids]

    def write_positions(self, motor_ids, targets, speed, acceleration):
        self.positions.update(zip(motor_ids, targets))

    def enable_motion(self, motor_ids, positions, speed, acceleration):
        self.write_positions(motor_ids, positions, speed, acceleration)

    def disable_torque(self, motor_ids):
        pass

    def close(self):
        pass
