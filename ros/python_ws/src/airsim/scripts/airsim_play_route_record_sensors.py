#!/usr/bin/env python

import setup_path
import airsimpy
import rospy
import time
import math
from std_msgs.msg import String, Header
from geometry_msgs.msg import PoseStamped, TransformStamped, Point, Quaternion
import sensor_msgs.point_cloud2 as pc2
import tf2_ros
from airsim.msg import StringArray
from sensor_msgs.msg import PointCloud2, PointField,  CameraInfo
from uwb_msgs.msg import Diagnostics, Range, RangeArray
from wifi_msgs.msg import DiagnosticsRSSI, RangeRSSI, RangeArrayRSSI
import rosbag
import numpy as np
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
import msgpackrpc
import sys
import tf2_msgs
from tf.transformations import *

def get_camera_type(cameraType):
    if (cameraType == "Scene"):
        cameraTypeClass = airsimpy.ImageType.Scene
    elif (cameraType == "Segmentation"):
        cameraTypeClass = airsimpy.ImageType.Segmentation
    elif (cameraType == "DepthPerspective"):
        cameraTypeClass = airsimpy.ImageType.DepthPerspective
    elif (cameraType == "DepthPlanner"):
        cameraTypeClass = airsimpy.ImageType.DepthPlanner
    elif (cameraType == "DepthVis"):
        cameraTypeClass = airsimpy.ImageType.DepthVis
    elif (cameraType == "Infrared"):
        cameraTypeClass = airsimpy.ImageType.Infrared
    elif (cameraType == "SurfaceNormals"):
        cameraTypeClass = airsimpy.ImageType.SurfaceNormals
    elif (cameraType == "DisparityNormalized"):
        cameraTypeClass = airsimpy.ImageType.DisparityNormalized
    else:
        cameraTypeClass = airsimpy.ImageType.Scene
        rospy.logwarn("Camera type %s not found, setting to Scene as default", cameraType)
    return cameraTypeClass


def is_pixels_as_float(cameraType):
    if (cameraType == "Scene"):
        return False
    elif (cameraType == "Segmentation"):
        return False
    elif (cameraType == "DepthPerspective"):
        return True
    elif (cameraType == "DepthPlanner"):
        return True
    elif (cameraType == "DepthVis"):
        return True
    elif (cameraType == "Infrared"):
        return False
    elif (cameraType == "SurfaceNormals"):
        return False
    elif (cameraType == "DisparityNormalized"):
        return True
    else:
        return False


def get_image_bytes(data, cameraType):
    if (cameraType == "Scene"):
        img_rgb_string = data.image_data_uint8
    elif (cameraType == "Segmentation"):
        img_rgb_string = data.image_data_uint8
    elif (cameraType == "DepthPerspective"):
        img_depth_float = data.image_data_float
        img_depth_float32 = np.asarray(img_depth_float, dtype=np.float32)
        img_rgb_string = img_depth_float32.tobytes()
    elif (cameraType == "DepthPlanner"):
        img_depth_float = data.image_data_float
        img_depth_float32 = np.asarray(img_depth_float, dtype=np.float32)
        img_rgb_string = img_depth_float32.tobytes()
    elif (cameraType == "DepthVis"):
        img_depth_float = data.image_data_float
        img_depth_float32 = np.asarray(img_depth_float, dtype=np.float32)
        img_rgb_string = img_depth_float32.tobytes()
    elif (cameraType == "Infrared"):
        img_rgb_string = data.image_data_uint8
    elif (cameraType == "SurfaceNormals"):
        img_rgb_string = data.image_data_uint8
    elif (cameraType == "DisparityNormalized"):
        img_depth_float = data.image_data_float
        img_depth_float32 = np.asarray(img_depth_float, dtype=np.float32)
        img_rgb_string = img_depth_float32.tobytes()
    else:
        img_rgb_string = data.image_data_uint8
    return img_rgb_string


def airsim_play_route_record_sensors(client, vehicle_name, pose_topic, pose_frame, tf_static,
                                     sensor_echo_names, sensor_echo_topics, sensor_echo_frames, sensor_lidar_names,
                                     sensor_lidar_toggle_segmentation,
                                     sensor_lidar_topics, sensor_lidar_segmentation_topics, sensor_lidar_frames,
                                     sensor_gpulidar_names, sensor_gpulidar_topics,
                                     sensor_gpulidar_frames, sensor_camera_names, sensor_camera_toggle_scene_mono,
                                     sensor_camera_scene_quality, sensor_camera_toggle_segmentation,
                                     sensor_camera_toggle_depth, sensor_camera_scene_topics,
                                     sensor_camera_segmentation_topics, sensor_camera_depth_topics,
                                     sensor_camera_frames,sensor_camera_optical_frames, sensor_camera_toggle_camera_info, sensor_camera_info_topics, sensor_stereo_enable, baseline,
                                     object_names, objects_coordinates_local, object_topics,
                                     route_rosbag, merged_rosbag):

    rospy.loginfo("Reading route...")
    route = rosbag.Bag(route_rosbag)
    output = rosbag.Bag(merged_rosbag, 'w')
    rospy.loginfo("Route retrieved!")

    last_timestamps = {}
    warning_issued = {}

    for sensor_index, sensor_name in enumerate(sensor_echo_names):
        last_timestamps[sensor_name] = None
    for sensor_index, sensor_name in enumerate(sensor_lidar_names):
        last_timestamps[sensor_name] = None
    for sensor_index, sensor_name in enumerate(sensor_gpulidar_names):
        last_timestamps[sensor_name] = None
    for object_index, object_name in enumerate(object_names):
        warning_issued[object_name] = False

    cv_bridge = CvBridge()

    fields_echo = [
        PointField('x', 0, PointField.FLOAT32, 1),
        PointField('y', 4, PointField.FLOAT32, 1),
        PointField('z', 8, PointField.FLOAT32, 1),
        PointField('a', 12, PointField.FLOAT32, 1),
        PointField('d', 16, PointField.FLOAT32, 1)
    ]

    fields_lidar = [
        PointField('x', 0, PointField.FLOAT32, 1),
        PointField('y', 4, PointField.FLOAT32, 1),
        PointField('z', 8, PointField.FLOAT32, 1),
        PointField('rgb', 12, PointField.UINT32, 1),
        PointField('intensity', 16, PointField.FLOAT32, 1)
    ]

    requests = []
    response_locations = {}
    cameraInfo_objects = {}
    response_index = 0
    for sensor_index, sensor_name in enumerate(sensor_camera_names):
        response_locations[sensor_name + '_scene'] = response_index
        response_index += 1
        requests.append(airsimpy.ImageRequest(sensor_name, get_camera_type("Scene"),
                                              is_pixels_as_float("Scene"), False))
        if sensor_camera_toggle_segmentation[sensor_index] == 1:
            requests.append(airsimpy.ImageRequest(sensor_name, get_camera_type("Segmentation"),
                                                  is_pixels_as_float("Segmentation"), False))
            response_locations[sensor_name + '_segmentation'] = response_index
            response_index += 1
        if sensor_camera_toggle_depth[sensor_index] == 1:
            requests.append(airsimpy.ImageRequest(sensor_name, get_camera_type("DepthPlanner"),
                                                  is_pixels_as_float("DepthPlanner"), False))
            response_locations[sensor_name + '_depth'] = response_index
            response_index += 1
        if sensor_camera_toggle_camera_info[sensor_index] == 1:
            cameraInfo_objects[sensor_name] = client.simGetCameraInfo(sensor_name)

    print("Starting...")
    rospy.logwarn("Ensure focus is on the screen of AirSim simulator to allow auto configuration!")
    rospy.logdebug(str(route.get_type_and_topic_info()))

    pose_count = route.get_message_count('/' + pose_topic)
    pose_index = 1
    period = 1/ros_rate
    tolerance = 0.05*period
    lastTime = 0
    first_timestamp= None

    for topic, msg, t in route.read_messages(topics=['/' + pose_topic,'tf_static']):

        if rospy.is_shutdown():
            break

        ros_timestamp = t
        if first_timestamp is None:
            first_timestamp = ros_timestamp
        timestamp = msg.header.stamp

        if topic == "tf_static":
            tf_static.transforms = tf_static.transforms + msg.transforms

        elif topic == '/' + pose_topic:
            rospy.logdebug("Setting vehicle pose at {}".format(str(t)))
            elapsedTime = t.to_sec() - lastTime
            if elapsedTime + tolerance >= period:
                client.simContinueForTime(period)
                lastTime = t.to_sec()
                position = airsimpy.Vector3r(msg.pose.position.x, -msg.pose.position.y, -msg.pose.position.z)
                orientation = airsimpy.Quaternionr(msg.pose.orientation.x, msg.pose.orientation.y, msg.pose.orientation.z,
                                                   msg.pose.orientation.w).inverse()
                orientation = airsimpy.Quaternionr(float(orientation.x_val), float(orientation.y_val),
                                                   float(orientation.z_val), float(orientation.w_val))
                client.simSetVehiclePose(airsimpy.Pose(position, orientation), True, vehicle_name)

                rospy.loginfo("Setting vehicle pose " + str(pose_index) + ' of ' + str(pose_count) + '.')
                pose_index += 1

                camera_responses = client.simGetImages(requests)

                for sensor_index, sensor_name in enumerate(sensor_camera_names):
                    response = camera_responses[response_locations[sensor_name + '_scene']]
                    if response.width == 0 and response.height == 0:
                        rospy.logwarn("Camera '" + sensor_name + "' could not retrieve scene image.")
                    else:
                        rgb_matrix = np.frombuffer(get_image_bytes(response, "Scene"), dtype=np.uint8).reshape(response.height,
                                                                                                        response.width, 3)
                        if sensor_camera_scene_quality[sensor_index] > 0:
                            rgb_matrix = cv2.cvtColor(rgb_matrix, cv2.COLOR_RGB2BGR)
                            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), sensor_camera_scene_quality[sensor_index]]
                            result, img = cv2.imencode('.jpg', rgb_matrix, encode_params)
                            rgb_matrix = cv2.imdecode(img, 1)
                            rgb_matrix = cv2.cvtColor(rgb_matrix, cv2.COLOR_BGR2RGB)

                        if sensor_camera_toggle_scene_mono == 1:
                            camera_msg = cv_bridge.cv2_to_imgmsg(cv2.cvtColor(rgb_matrix, cv2.COLOR_RGB2GRAY), encoding="mono8")
                        else:
                            camera_msg = cv_bridge.cv2_to_imgmsg(rgb_matrix, encoding="rgb8")
                        camera_msg.header.stamp = timestamp
                        camera_msg.header.frame_id = sensor_camera_optical_frames[sensor_index]
                        output.write(sensor_camera_scene_topics[sensor_index], camera_msg, t=ros_timestamp)

                    if sensor_camera_toggle_segmentation[sensor_index] == 1:
                        response = camera_responses[response_locations[sensor_name + '_segmentation']]
                        if response.width == 0 and response.height == 0:
                            rospy.logwarn("Camera '" + sensor_name + "' could not retrieve segmentation image.")
                        else:
                            rgb_string = get_image_bytes(response, "Segmentation")
                            camera_msg.step = response.width * 3
                            camera_msg.data = rgb_string
                            output.write(sensor_camera_segmentation_topics[sensor_index], camera_msg, t=ros_timestamp)
                    if sensor_camera_toggle_depth[sensor_index] == 1:
                        response = camera_responses[response_locations[sensor_name + '_depth']]
                        if response.width == 0 and response.height == 0:
                            rospy.logwarn("Camera '" + sensor_name + "' could not retrieve depth image.")
                        else:
                            rgb_string = get_image_bytes(response, "DepthPlanner")
                            camera_msg.encoding = "32FC1"
                            camera_msg.step = response.width * 4
                            camera_msg.data = rgb_string
                            output.write(sensor_camera_depth_topics[sensor_index], camera_msg, t=ros_timestamp)
                    if sensor_camera_toggle_camera_info[sensor_index] == 1:
                        FOV = cameraInfo_objects[sensor_name].fov
                        cam_info_msg = CameraInfo()
                        cam_info_msg.header.frame_id = sensor_camera_optical_frames[sensor_index]
                        cam_info_msg.header.stamp = timestamp
                        cam_info_msg.height = response.height
                        cam_info_msg.width = response.width
                        f = (cam_info_msg.width / 2.0) / math.tan(FOV * math.pi / 360)
                        if sensor_stereo_enable and sensor_index == 1:
                            Tx = -f * baseline
                        else:
                            Tx = 0
                        cam_info_msg.K = [f, 0.0, cam_info_msg.width / 2.0,
                                          0.0, f, cam_info_msg.height / 2.0,
                                          0.0, 0.0, 1.0]
                        cam_info_msg.P = [f, 0.0, cam_info_msg.width / 2.0, Tx,
                                          0.0, f, cam_info_msg.height / 2.0, 0.0,
                                          0.0, 0.0, 1.0, 0.0]
                        cam_info_msg.D = [0, 0, 0, 0, 0]  # in future get from client.simGetDistortionParams(camera1Name)
                        cam_info_msg.distortion_model = 'plumb_bob'
                        cam_info_msg.R = [1, 0, 0, 0, 1, 0, 0, 0, 1]
                        output.write(sensor_camera_info_topics[sensor_index],cam_info_msg,t=ros_timestamp)

                for sensor_index, sensor_name in enumerate(sensor_echo_names):
                    echo_data = client.getEchoData(sensor_name, vehicle_name)

                    if echo_data.time_stamp != last_timestamps[sensor_name]:
                        if len(echo_data.point_cloud) < 4:
                            last_timestamps[sensor_name] = timestamp
                        else:
                            last_timestamps[sensor_name] = timestamp

                            points = np.array(echo_data.point_cloud, dtype=np.dtype('f4'))
                            points = np.reshape(points, (int(points.shape[0] / 5), 5))
                            points = points * np.array([1, -1, -1, 1, 1])
                            points_list = points.tolist()
                            header = Header()
                            header.frame_id = sensor_echo_frames[sensor_index]
                            pcloud = pc2.create_cloud(header, fields_echo, points_list)
                            pcloud.header.stamp = timestamp
                            output.write(sensor_echo_topics[sensor_index], pcloud, t=ros_timestamp)

                for sensor_index, sensor_name in enumerate(sensor_lidar_names):
                    lidar_data = client.getLidarData(sensor_name, vehicle_name)

                    if lidar_data.time_stamp != last_timestamps[sensor_name]:
                        if len(lidar_data.point_cloud) < 4:
                            last_timestamps[sensor_name] = lidar_data.time_stamp
                        else:
                            last_timestamps[sensor_name] = lidar_data.time_stamp

                            pcloud = PointCloud2()
                            points = np.array(lidar_data.point_cloud, dtype=np.dtype('f4'))
                            points = np.reshape(points, (int(points.shape[0] / 3), 3))
                            points = points * np.array([1, -1, -1])
                            cloud = points.tolist()
                            pcloud.header.frame_id = sensor_lidar_frames[sensor_index]
                            pcloud.header.stamp = timestamp
                            pcloud = pc2.create_cloud_xyz32(pcloud.header, cloud)

                            output.write(sensor_lidar_topics[sensor_index], pcloud, t=ros_timestamp)

                            if sensor_lidar_toggle_segmentation[sensor_index] == 1:
                                labels = np.array(lidar_data.groundtruth, dtype=np.dtype('U'))
                                groundtruth = StringArray()
                                groundtruth.data = labels.tolist()
                                groundtruth.header.frame_id = sensor_lidar_frames[sensor_index]
                                groundtruth.header.stamp = timestamp
                                output.write(sensor_lidar_segmentation_topics[sensor_index], groundtruth, t=ros_timestamp)

                for sensor_index, sensor_name in enumerate(sensor_gpulidar_names):
                    lidar_data = client.getGPULidarData(sensor_name, vehicle_name)

                    if lidar_data.time_stamp != last_timestamps[sensor_name]:
                        if len(lidar_data.point_cloud) < 5:
                            last_timestamps[sensor_name] = lidar_data.time_stamp
                        else:
                            last_timestamps[sensor_name] = lidar_data.time_stamp

                            pcloud = PointCloud2()
                            points = np.array(lidar_data.point_cloud, dtype=np.dtype('f4'))
                            points = np.reshape(points, (int(points.shape[0] / 5), 5))
                            pcloud.header.frame_id = sensor_gpulidar_frames[sensor_index]
                            pcloud.header.stamp = timestamp
                            pcloud = pc2.create_cloud(pcloud.header, fields_lidar, points.tolist())

                            output.write(sensor_gpulidar_topics[sensor_index], pcloud, t=ros_timestamp)

                for sensor_index, sensor_name in enumerate(sensor_uwb_names):
                    if (sensor_index == 0):  # only once
                        uwb_data = client.getUWBData()

                        # Sanity check
                        if len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_anchorPosY) or \
                                len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_anchorPosZ) or \
                                len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_distance) or \
                                len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_rssi) or \
                                len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_time_stamp) or \
                                len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_anchorId) or \
                                len(uwb_data.mur_anchorPosX) != len(uwb_data.mur_valid_range):
                            rospy.logerr("UWB sensor mur lengths do not match")
                            rospy.signal_shutdown('Packet error.')
                            sys.exit()
                        if len(uwb_data.mura_ranges) != len(uwb_data.mura_tagId) or \
                                len(uwb_data.mura_ranges) != len(uwb_data.mura_tagPosX) or \
                                len(uwb_data.mura_ranges) != len(uwb_data.mura_tagPosY) or \
                                len(uwb_data.mura_ranges) != len(uwb_data.mura_tagPosZ):
                            rospy.logerr("UWB sensor mura lengths do not match")
                            rospy.signal_shutdown('Packet error.')
                            sys.exit()

                        uwb_data.mur_anchorId = np.array(uwb_data.mur_anchorId)

                        mur_time_stamp = []
                        mur_anchorId = []
                        mur_anchorPosX = []
                        mur_anchorPosY = []
                        mur_anchorPosZ = []
                        mur_valid_range = []
                        mur_distance = []
                        mur_rssi = []
                        mura_ranges = []

                        idx_offset = 0

                        for rangeIdx, ranges in enumerate(uwb_data.mura_ranges):
                            u, uniqueRangeIds = np.unique(uwb_data.mur_anchorId[ranges], return_index=True)
                            uniqueRangeIds += idx_offset

                            mura_ranges_idx_start = len(mur_anchorPosX)
                            mur_anchorPosX += list(np.array(uwb_data.mur_anchorPosX)[uniqueRangeIds])
                            mur_anchorPosY += list(np.array(uwb_data.mur_anchorPosY)[uniqueRangeIds])
                            mur_anchorPosZ += list(np.array(uwb_data.mur_anchorPosZ)[uniqueRangeIds])
                            mur_time_stamp += list(np.array(uwb_data.mur_time_stamp)[uniqueRangeIds])
                            mur_anchorId += list(np.array(uwb_data.mur_anchorId)[uniqueRangeIds])
                            mur_valid_range += list(np.array(uwb_data.mur_valid_range)[uniqueRangeIds])

                            mura_ranges.append([])
                            mura_ranges[rangeIdx] = list(range(mura_ranges_idx_start, len(mur_anchorPosX)))
                            for arange in uniqueRangeIds:
                                currentRanges = np.array(uwb_data.mur_anchorId)[ranges]
                                currentRssi = np.array(uwb_data.mur_rssi)[ranges]
                                currentDistance = np.array(uwb_data.mur_distance)[ranges]
                                currentRssiFiltered = currentRssi * list(map(int, currentRanges == uwb_data.mur_anchorId[arange]))
                                maxRssi = max(currentRssiFiltered)
                                maxRssiIdx = currentRssiFiltered.argmax()

                                mur_distance.append(currentDistance[maxRssiIdx])
                                mur_rssi.append(maxRssi)

                            # for arange in uniqueRangeIds:

                            idx_offset += len(ranges)

                        for mura_idx in range(0, len(uwb_data.mura_tagId)):
                            rangeArray = RangeArray()
                            rangeArray.tagid = str(uwb_data.mura_tagId[mura_idx])
                            rangeArray.tag_position = Point(uwb_data.mura_tagPosX[mura_idx], uwb_data.mura_tagPosY[mura_idx], uwb_data.mura_tagPosZ[mura_idx])
                            rangeArray.header.stamp = timestamp

                            # for mur_id in range(0, len(mur_time_stamp)):
                            for mur_id in mura_ranges[mura_idx]:
                                diag = Diagnostics()
                                diag.rssi = mur_rssi[mur_id]

                                rang = Range()
                                # rang.stamp = mur_time_stamp[mur_id]
                                rang.stamp = timestamp
                                rang.anchorid = str(mur_anchorId[mur_id]).split(":")[-1]
                                rang.anchor_position = Point(mur_anchorPosX[mur_id], mur_anchorPosY[mur_id], mur_anchorPosZ[mur_id])
                                rang.valid_range = mur_valid_range[mur_id]
                                rang.distance = mur_distance[mur_id]
                                rang.diagnostics = diag

                                rangeArray.ranges.append(rang)
                            output.write(sensor_uwb_topic, rangeArray, t=ros_timestamp)

                        # rospy.logerr("run once")
                        # rospy.signal_shutdown('Packet error.')
                        # sys.exit()
                for sensor_index, sensor_name in enumerate(sensor_wifi_names):
                    if (sensor_index == 0):  # only once
                        wifi_data = client.getWifiData()

                        # Sanity check
                        if len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_anchorPosY) or \
                                len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_anchorPosZ) or \
                                len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_distance) or \
                                len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_rssi) or \
                                len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_time_stamp) or \
                                len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_anchorId) or \
                                len(wifi_data.wr_anchorPosX) != len(wifi_data.wr_valid_range):
                            rospy.logerr("Wifi sensor wr lengths do not match")
                            rospy.signal_shutdown('Packet error.')
                            sys.exit()
                        if len(wifi_data.wra_ranges) != len(wifi_data.wra_tagId) or \
                                len(wifi_data.wra_ranges) != len(wifi_data.wra_tagPosX) or \
                                len(wifi_data.wra_ranges) != len(wifi_data.wra_tagPosY) or \
                                len(wifi_data.wra_ranges) != len(wifi_data.wra_tagPosZ):
                            rospy.logerr("Wifi sensor wra lengths do not match")
                            rospy.signal_shutdown('Packet error.')
                            sys.exit()

                        wifi_data.wr_anchorId = np.array(wifi_data.wr_anchorId)

                        wr_time_stamp = []
                        wr_anchorId = []
                        wr_anchorPosX = []
                        wr_anchorPosY = []
                        wr_anchorPosZ = []
                        wr_valid_range = []
                        wr_distance = []
                        wr_rssi = []
                        wra_ranges = []

                        idx_offset = 0

                        for rangeIdx, ranges in enumerate(wifi_data.wra_ranges):
                            u, uniqueRangeIds = np.unique(wifi_data.wr_anchorId[ranges], return_index=True)
                            uniqueRangeIds += idx_offset

                            wra_ranges_idx_start = len(wr_anchorPosX)
                            wr_anchorPosX += list(np.array(wifi_data.wr_anchorPosX)[uniqueRangeIds])
                            wr_anchorPosY += list(np.array(wifi_data.wr_anchorPosY)[uniqueRangeIds])
                            wr_anchorPosZ += list(np.array(wifi_data.wr_anchorPosZ)[uniqueRangeIds])
                            wr_time_stamp += list(np.array(wifi_data.wr_time_stamp)[uniqueRangeIds])
                            wr_anchorId += list(np.array(wifi_data.wr_anchorId)[uniqueRangeIds])
                            wr_valid_range += list(np.array(wifi_data.wr_valid_range)[uniqueRangeIds])

                            wra_ranges.append([])
                            wra_ranges[rangeIdx] = list(range(wra_ranges_idx_start, len(wr_anchorPosX)))
                            for arange in uniqueRangeIds:
                                currentRanges = np.array(wifi_data.wr_anchorId)[ranges]
                                currentRssi = np.array(wifi_data.wr_rssi)[ranges]
                                currentDistance = np.array(wifi_data.wr_distance)[ranges]
                                currentRssiFiltered = currentRssi * list(map(int, currentRanges == wifi_data.wr_anchorId[arange]))
                                maxRssi = max(currentRssiFiltered)
                                maxRssiIdx = currentRssiFiltered.argmax()

                                wr_distance.append(currentDistance[maxRssiIdx])
                                wr_rssi.append(maxRssi)

                            # for arange in uniqueRangeIds:

                            idx_offset += len(ranges)

                        for wra_idx in range(0, len(wifi_data.wra_tagId)):
                            rangeArray = RangeArray()
                            rangeArray.tagid = str(wifi_data.wra_tagId[wra_idx])
                            rangeArray.tag_position = Point(wifi_data.wra_tagPosX[wra_idx], wifi_data.wra_tagPosY[wra_idx], wifi_data.wra_tagPosZ[wra_idx])
                            rangeArray.header.stamp = timestamp

                            # for wr_id in range(0, len(wr_time_stamp)):
                            for wr_id in wra_ranges[wra_idx]:
                                diag = Diagnostics()
                                diag.rssi = wr_rssi[wr_id]

                                rang = Range()
                                # rang.stamp = wr_time_stamp[wr_id]
                                rang.stamp = timestamp
                                rang.anchorid = str(wr_anchorId[wr_id])
                                rang.anchor_position = Point(wr_anchorPosX[wr_id], wr_anchorPosY[wr_id], wr_anchorPosZ[wr_id])
                                rang.valid_range = wr_valid_range[wr_id]
                                rang.distance = wr_distance[wr_id]
                                rang.diagnostics = diag

                                rangeArray.ranges.append(rang)

                            output.write(sensor_wifi_topic, rangeArray, t=ros_timestamp)

                        # rospy.logerr("run once")
                        # rospy.signal_shutdown('Packet error.')
                        # sys.exit()

                for object_index, object_name in enumerate(object_names):
                    if objects_coordinates_local[object_index] == 1:
                        pose = client.simGetObjectPose(object_name, True)
                    else:
                        pose = client.simGetObjectPose(object_name, False)
                    if np.isnan(pose.position.x_val):
                        if warning_issued[object_name] is False:
                            rospy.logwarn("Object '" + object_name + "' could not be found.")
                            warning_issued[object_name] = True
                    else:
                        warning_issued[object_name] = False
                        pos = pose.position
                        orientation = pose.orientation.inverse()
                        object_pose = PoseStamped()
                        object_pose.pose.position.x = pos.x_val
                        object_pose.pose.position.y = -pos.y_val
                        object_pose.pose.position.z = pos.z_val
                        object_pose.pose.orientation.w = orientation.w_val
                        object_pose.pose.orientation.x = orientation.x_val
                        object_pose.pose.orientation.y = orientation.y_val
                        object_pose.pose.orientation.z = orientation.z_val
                        object_pose.header.stamp = timestamp
                        object_pose.header.seq = 1
                        object_pose.header.frame_id = pose_frame

                        output.write(object_topics[sensor_index], object_pose, t=ros_timestamp)
    output.write('/tf_static',tf_static,first_timestamp)
    print("Process completed. Writing all messages to merged rosbag...")
    for topic, msg, t in route.read_messages():
        if topic != 'tf/static':
            output.write(topic, msg, t)
    output.close()
    print("Merged rosbag with route and sensor data created!")


if __name__ == '__main__':
    try:
        rospy.init_node('airsim_play_route_record_sensors', anonymous=True)

        ip = rospy.get_param('~ip', "")
        ros_rate = rospy.get_param('~rate', 10)
        toggle_drone = rospy.get_param('~toggle_drone', 0)

        vehicle_name = rospy.get_param('~vehicle_name', 'airsimvehicle')
        vehicle_base_frame = rospy.get_param('~vehicle_base_frame', 'base_link')

        pose_topic = rospy.get_param('~pose_topic', "airsim/gtpose")
        pose_frame = rospy.get_param('~pose_frame', "world")

        route_rosbag = rospy.get_param('~route_rosbag', "airsim_route_only.bag")
        merged_rosbag = rospy.get_param('~merged_rosbag', "airsim_route_sensors.bag")
        
        sensor_echo_names = rospy.get_param('~sensor_echo_names', "True")
        sensor_echo_topics = rospy.get_param('~sensor_echo_topics', "True")
        sensor_echo_frames = rospy.get_param('~sensor_echo_frames', "True")

        sensor_lidar_names = rospy.get_param('~sensor_lidar_names', "True")
        sensor_lidar_toggle_groundtruth = rospy.get_param('~sensor_lidar_toggle_groundtruth', "True")
        sensor_lidar_topics = rospy.get_param('~sensor_lidar_topics', "True")
        sensor_lidar_segmentation_topics = rospy.get_param('~sensor_lidar_segmentation_topics', "True")
        sensor_lidar_frames = rospy.get_param('~sensor_lidar_frames', "True")

        sensor_gpulidar_names = rospy.get_param('~sensor_gpulidar_names', "True")
        sensor_gpulidar_topics = rospy.get_param('~sensor_gpulidar_topics', "True")
        sensor_gpulidar_frames = rospy.get_param('~sensor_gpulidar_frames', "True")

        sensor_uwb_names = rospy.get_param('~sensor_uwb_names', "True")
        sensor_uwb_topic = rospy.get_param('~sensor_uwb_topic', "True")
        sensor_uwb_frames = rospy.get_param('~sensor_uwb_frames', "True")

        sensor_wifi_names = rospy.get_param('~sensor_wifi_names', "True")
        sensor_wifi_topic = rospy.get_param('~sensor_wifi_topic', "True")
        sensor_wifi_frames = rospy.get_param('~sensor_wifi_frames', "True")

        sensor_camera_names = rospy.get_param('~sensor_camera_names', "True")
        sensor_camera_toggle_scene_mono = rospy.get_param('~sensor_camera_toggle_scene_mono', "True")
        sensor_camera_scene_quality = rospy.get_param('~sensor_camera_scene_quality', "True")
        sensor_camera_toggle_segmentation = rospy.get_param('~sensor_camera_toggle_segmentation', "True")
        sensor_camera_toggle_depth = rospy.get_param('~sensor_camera_toggle_depth', "True")
        sensor_camera_scene_topics = rospy.get_param('~sensor_camera_scene_topics', "True")
        sensor_camera_segmentation_topics = rospy.get_param('~sensor_camera_segmentation_topics', "True")
        sensor_camera_depth_topics = rospy.get_param('~sensor_camera_depth_topics', "True")
        sensor_camera_frames = rospy.get_param('~sensor_camera_frames', "True")
        sensor_camera_optical_frames = rospy.get_param('~sensor_camera_optical_frames', "True")
        sensor_camera_toggle_camera_info = rospy.get_param('~sensor_camera_toggle_camera_info', "True")
        sensor_camera_info_topics = rospy.get_param('~sensor_camera_info_topics', "True")
        sensor_stereo_enable = rospy.get_param('~sensor_stereo_enable', "True")

        object_names = rospy.get_param('~object_names', "True")
        objects_coordinates_local = rospy.get_param('~objects_coordinates_local', "True")
        object_topics = rospy.get_param('~object_topics', "True")

        print("Connecting to AirSim...")
        if toggle_drone:
            client = airsimpy.MultirotorClient(ip, timeout_value=15)
        else:
            client = airsimpy.CarClient(ip, timeout_value=15)
        try:
            client.confirmConnection(rospy.get_name())
        except msgpackrpc.error.TimeoutError:
            rospy.logerr("Could not connect to AirSim.")
            rospy.signal_shutdown('no connection to airsim.')
            sys.exit()
        # print("Connected to AirSim!")

        client.simPause(True)

        # rospy.loginfo("Starting static transforms...")
        tf_static = tf2_msgs.msg.TFMessage()

        for sensor_index, sensor_name in enumerate(sensor_echo_names):
            try:
                echo_data = client.getEchoData(sensor_name, vehicle_name)
            except msgpackrpc.error.RPCError:
                rospy.logerr("Echo sensor '" + sensor_name + "' could not be found.")
                rospy.signal_shutdown('Sensor not found.')
                sys.exit()
            pose = echo_data.pose
            orientation = pose.orientation.inverse()
            static_transform = TransformStamped()
            static_transform.header.stamp = rospy.Time.now()
            static_transform.header.frame_id = vehicle_base_frame
            static_transform.child_frame_id = sensor_echo_frames[sensor_index]
            static_transform.transform.translation.x = pose.position.x_val
            static_transform.transform.translation.y = -pose.position.y_val
            static_transform.transform.translation.z = -pose.position.z_val
            static_transform.transform.rotation.x = orientation.x_val
            static_transform.transform.rotation.y = orientation.y_val
            static_transform.transform.rotation.z = orientation.z_val
            static_transform.transform.rotation.w = orientation.w_val
            tf_static.transforms.append(static_transform)
            time.sleep(0.1)
            rospy.loginfo("Started static transform for echo sensor with ID " + sensor_name + ".")

        for sensor_index, sensor_name in enumerate(sensor_lidar_names):
            try:
                lidar_data = client.getLidarData(sensor_name, vehicle_name)
            except msgpackrpc.error.RPCError:
                rospy.logerr("LiDAR sensor '" + sensor_name + "' could not be found.")
                rospy.signal_shutdown('Sensor not found.')
                sys.exit()
            pose = lidar_data.pose
            orientation = pose.orientation.inverse()
            static_transform = TransformStamped()
            static_transform.header.stamp = rospy.Time.now()
            static_transform.header.frame_id = vehicle_base_frame
            static_transform.child_frame_id = sensor_lidar_frames[sensor_index]
            static_transform.transform.translation.x = pose.position.x_val
            static_transform.transform.translation.y = -pose.position.y_val
            static_transform.transform.translation.z = -pose.position.z_val
            static_transform.transform.rotation.x = orientation.x_val
            static_transform.transform.rotation.y = orientation.y_val
            static_transform.transform.rotation.z = orientation.z_val
            static_transform.transform.rotation.w = orientation.w_val
            tf_static.transforms.append(static_transform)
            time.sleep(0.1)
            rospy.loginfo("Started static transform for LiDAR sensor with ID " + sensor_name + ".")

        for sensor_index, sensor_name in enumerate(sensor_gpulidar_names):
            try:
                lidar_data = client.getGPULidarData(sensor_name, vehicle_name)
            except msgpackrpc.error.RPCError:
                rospy.logerr("GPU-LiDAR sensor '" + sensor_name + "' could not be found.")
                rospy.signal_shutdown('Sensor not found.')
                sys.exit()
            pose = lidar_data.pose
            orientation = pose.orientation.inverse()
            static_transform = TransformStamped()
            static_transform.header.stamp = rospy.Time.now()
            static_transform.header.frame_id = vehicle_base_frame
            static_transform.child_frame_id = sensor_gpulidar_frames[sensor_index]
            static_transform.transform.translation.x = pose.position.x_val
            static_transform.transform.translation.y = -pose.position.y_val
            static_transform.transform.translation.z = -pose.position.z_val
            static_transform.transform.rotation.x = orientation.x_val
            static_transform.transform.rotation.y = orientation.y_val
            static_transform.transform.rotation.z = orientation.z_val
            static_transform.transform.rotation.w = orientation.w_val
            tf_static.transforms.append(static_transform)
            time.sleep(0.1)
            rospy.loginfo("Started static transform for GPU-LiDAR sensor with ID " + sensor_name + ".")

        for sensor_index, sensor_name in enumerate(sensor_uwb_names):

            # Get uwb sensor data
            try:
                uwb_data = client.getUWBSensorData(sensor_name, vehicle_name)
                # timeStamp = uwb_data[0]

            except msgpackrpc.error.RPCError:
                rospy.logerr("UWB sensor '" + sensor_name + "' could not be found.")
                rospy.signal_shutdown('Sensor not found.')
                sys.exit()

            if (len(uwb_data) == 2):
                pose = uwb_data[1]
                static_transform = TransformStamped()
                static_transform.header.stamp = rospy.Time.now()
                static_transform.header.frame_id = vehicle_base_frame
                static_transform.child_frame_id = sensor_uwb_frames[sensor_index]
                static_transform.transform.translation.x = pose['position']['x_val']
                static_transform.transform.translation.y = -pose['position']['y_val']
                static_transform.transform.translation.z = -pose['position']['z_val']
                static_transform.transform.rotation.x = pose['orientation']['x_val']
                static_transform.transform.rotation.y = pose['orientation']['y_val']
                static_transform.transform.rotation.z = pose['orientation']['z_val']
                static_transform.transform.rotation.w = pose['orientation']['w_val']
                transform_list.append(static_transform)
                time.sleep(0.1)
                rospy.loginfo("Started static transform for UWB sensor with ID " + sensor_name + ".")
        left_position = None
        right_position = None
        for sensor_index, sensor_name in enumerate(sensor_camera_names):
            try:
                camera_data = client.simGetCameraInfo(sensor_name)
            except msgpackrpc.error.RPCError:
                rospy.logerr("camera sensor '" + sensor_name + "' could not be found.")
                rospy.signal_shutdown('Sensor not found.')
                sys.exit()
            pose = camera_data.pose
            orientation = pose.orientation.inverse()

            # camera frame
            static_transform = TransformStamped()
            static_transform.header.stamp = rospy.Time.now()
            static_transform.header.frame_id = vehicle_base_frame
            static_transform.child_frame_id = sensor_camera_frames[sensor_index]
            static_transform.transform.translation.x = pose.position.x_val
            static_transform.transform.translation.y = -pose.position.y_val
            static_transform.transform.translation.z = -pose.position.z_val
            static_transform.transform.rotation.x = orientation.x_val
            static_transform.transform.rotation.y = orientation.y_val
            static_transform.transform.rotation.z = orientation.z_val
            static_transform.transform.rotation.w = orientation.w_val
            tf_static.transforms.append(static_transform)

            # optical frame
            static_transform = TransformStamped()
            static_transform.header.stamp = rospy.Time.now()
            static_transform.header.frame_id = sensor_camera_frames[sensor_index]
            static_transform.child_frame_id = sensor_camera_optical_frames[sensor_index]
            static_transform.transform.translation.x = 0
            static_transform.transform.translation.y = 0
            static_transform.transform.translation.z = 0
            q_rot = quaternion_from_euler(-math.pi/2, 0,-math.pi/2)
            static_transform.transform.rotation.x = q_rot[0]
            static_transform.transform.rotation.y = q_rot[1]
            static_transform.transform.rotation.z = q_rot[2]
            static_transform.transform.rotation.w = q_rot[3]
            tf_static.transforms.append(static_transform)

            time.sleep(0.1)
            rospy.loginfo("Started static transform for camera sensor with ID " + sensor_name + ".")

            if sensor_stereo_enable == 1 and sensor_index == 0:
                left_position = [pose.position.x_val, -pose.position.y_val, -pose.position.z_val]
            elif sensor_stereo_enable == 1 and sensor_index == 1:
                right_position = [pose.position.x_val, -pose.position.y_val, -pose.position.z_val]
        if left_position != None and right_position != None:
            baseline = math.sqrt((left_position[0] - right_position[0]) ** 2 + (left_position[1] - right_position[1]) ** 2 + (left_position[2] - right_position[2]) ** 2)
        else:
            baseline = 0

        airsim_play_route_record_sensors(client, vehicle_name, pose_topic, pose_frame, tf_static,
                                         sensor_echo_names,
                                         sensor_echo_topics, sensor_echo_frames, sensor_lidar_names,
                                         sensor_lidar_toggle_groundtruth,
                                         sensor_lidar_topics, sensor_lidar_segmentation_topics, sensor_lidar_frames,
                                         sensor_gpulidar_names, sensor_gpulidar_topics,
                                         sensor_gpulidar_frames, sensor_camera_names, sensor_camera_toggle_scene_mono,
                                         sensor_camera_scene_quality, sensor_camera_toggle_segmentation,
                                         sensor_camera_toggle_depth, sensor_camera_scene_topics,
                                         sensor_camera_segmentation_topics, sensor_camera_depth_topics,
                                         sensor_camera_frames, sensor_camera_optical_frames, sensor_camera_toggle_camera_info, sensor_camera_info_topics, sensor_stereo_enable, baseline,
                                         object_names, objects_coordinates_local,object_topics, route_rosbag, merged_rosbag)

    except rospy.ROSInterruptException:
        pass
