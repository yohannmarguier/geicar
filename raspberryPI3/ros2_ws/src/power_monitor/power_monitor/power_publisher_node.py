#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import serial


#####TODO instal pyserial on the raspberry : pip install pyserial

class PowerPublisher(Node):
    def __init__(self):
        super().__init__('power_publisher')
        
        # Parameter to transmit data from ESP to raspberry (Change when the information will be known)
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        
        port = self.get_parameter('port').get_parameter_value().string_value
        baudrate = self.get_parameter('baudrate').get_parameter_value().integer_value
        
        # creating the publisher
        self.publisher_ = self.create_publisher(Float32, 'power_value', 10)
        
        # init of serial connection
        try:
            self.serial_conn = serial.Serial(port, baudrate, timeout=1.0)
            self.get_logger().info(f"Connecté avec succès à l'ESP sur {port} à {baudrate} bauds.")
        except Exception as e:
            self.get_logger().error(f"Impossible d'ouvrir le port série {port}: {e}")
            self.serial_conn = None

        # timer to continusly publish the data (20hz for now)
        self.timer = self.create_timer(0.05, self.read_and_publish)

    def read_and_publish(self):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    # read one line of the data sent by esp
                    line = self.serial_conn.readline().decode('utf-8').strip()
                    if line:
                        # TODO : we do not know for now the format, we assume there is just the value
                        power_val = float(line)
                        
                        # publish the data through ros message
                        msg = Float32()
                        msg.data = power_val
                        self.publisher_.publish(msg)
            except ValueError:
                # If its a line for log or error
                pass
            except Exception as e:
                self.get_logger().warn(f"Erreur de lecture série : {e}")

def main(args=None):
    rclpy.init(args=args)
    node = PowerPublisher()
    try:
        rclpy.spin(node) 
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, 'serial_conn') and node.serial_conn and node.serial_conn.is_open:
            node.serial_conn.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()