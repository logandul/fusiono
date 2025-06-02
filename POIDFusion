#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from car_ros_msgs.msg import POI2D
from std_msgs.msg import Header
from cv_bridge import CvBridge, CvBridgeError
import cv2
import numpy as np
from collections import defaultdict
import threading
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

class POIDrivableStatus:
    def __init__(self, poi_msg, is_in_drivable_area, confidence=1.0):
        self.poi = poi_msg
        self.is_in_drivable_area = is_in_drivable_area
        self.confidence = confidence
        self.timestamp = poi_msg.header.stamp

class POIDrivableAreaFusion(Node):
    
    def __init__(self):
        super().__init__('poi_drivable_area_fusion')
        
        self.declare_parameter('camera_name', 'center_short_camera')
        self.declare_parameter('sync_timeout', 0.1)  # 100ms timeout for message synchronization
        self.declare_parameter('drivable_threshold', 0.5)  # Threshold for considering object in drivable area
        
        self.camera_name = self.get_parameter('camera_name').get_parameter_value().string_value
        self.sync_timeout = self.get_parameter('sync_timeout').get_parameter_value().double_value
        self.drivable_threshold = self.get_parameter('drivable_threshold').get_parameter_value().double_value
        
        self.bridge = CvBridge()
        self.lock = threading.Lock()
        
        self.latest_da_mask = None
        self.latest_da_timestamp = None
        self.poi_buffer = defaultdict(list)  # Buffer POIs by timestamp
        
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        self.da_mask_sub = self.create_subscription(
            Image,
            '/yolopv2/da_mask_resized',
            self.da_mask_callback,
            qos_profile
        )
        
        self.poi_sub = self.create_subscription(
            POI2D,
            f'/{self.camera_name}_yolo_msg',
            self.poi_callback,
            qos_profile
        )
        
        self.filtered_poi_pub = self.create_publisher(
            POI2D,
            f'/{self.camera_name}_drivable_pois',
            qos_profile
        )
        
        self.visualization_pub = self.create_publisher(
            Image,
            f'/{self.camera_name}_poi_drivable_visualization',
            qos_profile
        )
        
        self.timer = self.create_timer(0.05, self.process_synchronized_data)  # 20Hz processing
        
        self.get_logger().info(f'POI Drivable Area Fusion Node initialized for camera: {self.camera_name}')
    
    def da_mask_callback(self, msg):
        """Callback for drivable area mask"""
        with self.lock:
            try:
                self.latest_da_mask = self.bridge.imgmsg_to_cv2(msg, desired_encoding='mono8')
                self.latest_da_timestamp = msg.header.stamp
                
                self.get_logger().debug(f'Received DA mask: {self.latest_da_mask.shape}')
                
            except CvBridgeError as e:
                self.get_logger().error(f'Error converting DA mask: {e}')
    
    def poi_callback(self, msg):
        """Callback for POI messages"""
        with self.lock:
            timestamp_ns = msg.header.stamp.sec * 1e9 + msg.header.stamp.nanosec
            self.poi_buffer[timestamp_ns].append(msg)
            
            current_time_ns = self.get_clock().now().nanoseconds
            old_timestamps = [ts for ts in self.poi_buffer.keys() 
                            if (current_time_ns - ts) / 1e9 > self.sync_timeout * 2]
            for ts in old_timestamps:
                del self.poi_buffer[ts]
            
            self.get_logger().debug(f'Received POI: x={msg.x}, y={msg.y}, category={msg.category}')
    
    def process_synchronized_data(self):
        with self.lock:
            if self.latest_da_mask is None or not self.poi_buffer:
                return
            
            da_timestamp_ns = self.latest_da_timestamp.sec * 1e9 + self.latest_da_timestamp.nanosec
            
            synchronized_pois = []
            for poi_timestamp_ns, poi_list in self.poi_buffer.items():
                time_diff = abs(da_timestamp_ns - poi_timestamp_ns) / 1e9  # Convert to seconds
                if time_diff <= self.sync_timeout:
                    synchronized_pois.extend(poi_list)
            
            if not synchronized_pois:
                return
            
            processed_pois = []
            visualization_img = None
            
            if self.visualization_pub.get_subscription_count() > 0:
                visualization_img = cv2.cvtColor(self.latest_da_mask * 255, cv2.COLOR_GRAY2BGR)
            
            for poi in synchronized_pois:
                is_in_drivable, confidence = self.check_poi_in_drivable_area(
                    poi, self.latest_da_mask
                )
                
                processed_poi = POIDrivableStatus(poi, is_in_drivable, confidence)
                processed_pois.append(processed_poi)
                
                if is_in_drivable:
                    self.filtered_poi_pub.publish(poi)
                if visualization_img is not None:
                    self.add_poi_to_visualization(visualization_img, poi, is_in_drivable, confidence)
            
            if visualization_img is not None:
                try:
                    viz_msg = self.bridge.cv2_to_imgmsg(visualization_img, encoding='bgr8')
                    viz_msg.header.stamp = self.latest_da_timestamp
                    viz_msg.header.frame_id = f'{self.camera_name}_link'
                    self.visualization_pub.publish(viz_msg)
                except CvBridgeError as e:
                    self.get_logger().error(f'Error publishing visualization: {e}')
                    drivable_count = sum(1 for p in processed_pois if p.is_in_drivable_area)
            total_count = len(processed_pois)
            self.get_logger().debug(
                f'Processed {total_count} POIs, {drivable_count} in drivable area'
            )
    
    def check_poi_in_drivable_area(self, poi, da_mask):
        """
        Check if a POI is within the drivable area
        Returns: (is_in_drivable_area: bool, confidence: float)
        """
        try:
            x, y = int(poi.x), int(poi.y)
            mask_height, mask_width = da_mask.shape
            
            if x < 0 or x >= mask_width or y < 0 or y >= mask_height:
                return False, 0.0
            
            sample_radius = 5 
            x_min = max(0, x - sample_radius)
            x_max = min(mask_width, x + sample_radius + 1)
            y_min = max(0, y - sample_radius)
            y_max = min(mask_height, y + sample_radius + 1)
            
            roi = da_mask[y_min:y_max, x_min:x_max]
            
            if roi.size > 0:
                confidence = np.mean(roi > 0)  # Assuming drivable area is > 0
                is_in_drivable = confidence >= self.drivable_threshold
            else:
                confidence = 0.0
                is_in_drivable = False
            
            return is_in_drivable, confidence
            
        except Exception as e:
            self.get_logger().error(f'Error checking POI in drivable area: {e}')
            return False, 0.0
    
    def add_poi_to_visualization(self, img, poi, is_in_drivable, confidence):
        """Add POI visualization to the image"""
        try:
            x, y = int(poi.x), int(poi.y)
            
            color = (0, 255, 0) if is_in_drivable else (0, 0, 255)  
            
            # Draw circle for POI
            cv2.circle(img, (x, y), 8, color, 2)
            
            text = f'Cat:{poi.category} C:{confidence:.2f}'
            font_scale = 0.5
            thickness = 1
            
            (text_width, text_height), baseline = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )
            
            cv2.rectangle(
                img,
                (x - 2, y - text_height - baseline - 2),
                (x + text_width + 2, y - 2),
                (0, 0, 0), 
                -1
            )
            
            cv2.putText(
                img, text, (x, y - baseline - 2),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness
            )
            
        except Exception as e:
            self.get_logger().error(f'Error adding POI to visualization: {e}')


def main(args=None):
    rclpy.init(args=args)
    
    node = None
    try:
        node = POIDrivableAreaFusion()
        rclpy.spin(node)
        
    except KeyboardInterrupt:
        if node:
            node.get_logger().info("Keyboard interrupt received, shutting down.")
    except Exception as e:
        if node:
            node.get_logger().fatal(f"Unhandled exception: {e}")
        else:
            print(f"Unhandled exception during initialization: {e}")
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
