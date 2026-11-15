from so_arm101.bus import FeetechBus


class FakeHandler:
    def __init__(self):
        self.events = []
        self.registers = {(5, 33): 0, (5, 40): 0, (5, 62): 50, (5, 65): 0}

    def read1ByteTxRx(self, motor_id, address):
        self.events.append(("read", motor_id, address))
        return self.registers[motor_id, address], 0, 0

    def write1ByteTxRx(self, motor_id, address, value):
        self.events.append(("write", motor_id, address, value))
        self.registers[motor_id, address] = value
        return 0, 0

    def WritePosEx(self, motor_id, position, speed, acceleration):
        self.events.append(("goal", motor_id, position))
        return 0, 0


def test_enable_motion_sets_present_goal_before_torque():
    bus = FeetechBus.__new__(FeetechBus)
    bus.handler = FakeHandler()
    bus.comm_success = 0
    bus.enable_motion([5], [2125], 30, 10)
    events = bus.handler.events
    assert ("goal", 5, 2125) in events
    assert ("write", 5, 40, 1) in events
    assert events.index(("goal", 5, 2125)) < events.index(("write", 5, 40, 1))
    assert bus.handler.registers[5, 40] == 1
