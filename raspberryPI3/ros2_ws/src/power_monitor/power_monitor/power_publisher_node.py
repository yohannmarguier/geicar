import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import serial

class ArduinoSerialNode(Node):
    def __init__(self):
        super().__init__('arduino_serial_node')
        
        # Paramètres de liaison série 
        self.port = '/dev/ttyACM0'
        self.baudrate = 115200
        
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            self.get_logger().info(f"Connecté au port série {self.port} à {self.baudrate} bauds.")
        except Exception as e:
            self.get_logger().error(f"Impossible de se connecter au port série : {e}")
            self.serial_conn = None

        # declaration des 4 publisher pour chaque puissance mesurer
        self.pub_i1 = self.create_publisher(Float32, 'arduino/p1', 10)
        self.pub_i2 = self.create_publisher(Float32, 'arduino/p2', 10)
        self.pub_i3 = self.create_publisher(Float32, 'arduino/p3', 10)
        self.pub_i4 = self.create_publisher(Float32, 'arduino/p4', 10)

        # timer pour publier tout les 0.01 seconde (100hz)
        self.timer = self.create_timer(0.01, self.read_and_publish)

    def read_and_publish(self):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    # on lit 1 ligne du arduino
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    self.get_logger().warn(line)
                    if line:
                        # stocker temporairement les infos
                        data_dict = {}
                        
                        # decoupage du format : P1:float,P2:float,P3:float,P4:float
                        pairs = line.split(',')
                        for pair in pairs:
                            if ':' in pair:
                                key, val_str = pair.split(':')
                                data_dict[key.strip()] = float(val_str.strip())
                        
                        # on publie les puissance sur chaque topics 
                        if 'P1' in data_dict:
                            msg1 = Float32()
                            msg1.data = data_dict['P1']
                            self.pub_i1.publish(msg1)
                            
                        if 'P2' in data_dict:
                            msg2 = Float32()
                            msg2.data = data_dict['P2']
                            self.pub_i2.publish(msg2)

                        if 'P3' in data_dict:
                            msg3 = Float32()
                            msg3.data = data_dict['P3']
                            self.pub_i3.publish(msg3)

                        if 'P4' in data_dict:
                            msg4 = Float32()
                            msg4.data = data_dict['P4']
                            self.pub_i4.publish(msg4)
                            
            except ValueError:
                # Si c'est une ligne de log texte ou un message mal formaté qui provoque une erreur de conversion float
                pass
            except Exception as e:
                self.get_logger().warn(f"Erreur de lecture série ou de parsing : {e}")

    def destroy_node(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = ArduinoSerialNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()