import time
import zmq
import subprocess
from multiprocessing import Process, Event
from physiolabxr.interfaces.DeviceInterface.DeviceInterface import DeviceInterface
from physiolabxr.utils.time_utils import get_clock_time
import numpy as np
import os
import platform
from physiolabxr.ui.dialogs import dialog_popup

def get_executable_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))  # Get script directory
    return os.path.join(base_dir, "x64", "Debug", "BAlertX24.exe")


class BAlertX24_Interface(DeviceInterface):
    def __init__(self,
                 _device_name='BAlertX24',
                 _device_type='eeg',
                 _device_nominal_sampling_rate=256,
                 _ch_names=None,
                 license_path=None):
        super(BAlertX24_Interface, self).__init__(_device_name=_device_name,
                                                       _device_type=_device_type,
                                                       device_nominal_sampling_rate=_device_nominal_sampling_rate,
                                                       is_supports_device_availability=False,
                                                       )
        # Check for platform compatibility
        if platform.system() != "Windows":
            # Raise an exception to prevent further setup if not Windows
            raise EnvironmentError("Platform Not Supported: BAlertX24 is only supported on Windows")

        self.stream_name = _device_name
        self.stream_type = _device_type
        self.stream_path = _license_path
        self.ch_names = ["Fp1", "F7", "F8", "T4", "T6", "T5", "T3", "Fp2", "O1", "P3", "Pz", "F3", "Fz", "F4", "C4", "P4", "POz", "C3", "Cz", "O2", "EKG", "AUX1", "AUX2", "AUX3"]

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind("tcp://*:0")  # Bind to port 0 for an available random port
        self.port = self.socket.getsockopt(zmq.LAST_ENDPOINT).decode("utf-8").split(":")[-1]  # Get the randomly binded port number from the socket

        # self.terminate_event = Event()
        self.device_process = None
        self.terminate_event = None
        self.device_available = False

    def start_stream(self):
        self.terminate_event = Event()
        args = [get_executable_path(), str(self.port)]
        if self.license_path:
            args += ["--license", self.license_path]


    def stop_stream(self):
        if self.term_event:
            self.terminate_event.set()
        self.device_available = False
        # empty the socket buffer, so that the next time we start the stream, we don't get old data
        while True:  # do this after the process has been terminated
            try:
                self.socket.recv_json(flags=zmq.NOBLOCK)
            except zmq.error.Again:
                break

    def get_sampling_rate(self):
        return self.device_nominal_sampling_rate

    def process_frames(self):
        # Code to receive and process data from the eye tracker
        frames, timestamps, messages = [], [], []
        while True:  # Collect all available data
            try:
                data = self.socket.recv_json(flags=zmq.NOBLOCK)  # Non-blocking receive
                if data['t'] == 'e':
                    messages.append(data['message'])
                    self.stop_stream();
                elif data['t'] == 'd':
                    frames.append(data['frame'])
                    timestamps.append(data['timestamp'])
            except zmq.Again:
                # No more data available, break the loop
                break

        if len(frames) > 0:
            frames_array = np.array(frames).astype(np.float64)
            # print(f"Shape of frames before transpose: {frames_array.shape}")

            if frames_array.ndim == 3:
                # If it's 3D, transpose as originally intended
                return frames_array.transpose(2, 1, 0)[0], np.array(timestamps)[:, 0], messages
            elif frames_array.ndim == 2:
                # If it's 2D, just transpose the two axes
                return frames_array.transpose(1, 0), np.array(timestamps)[:, 0], messages
            else:
                # If it's 1D or unexpected, return it directly or handle differently
                return frames_array, np.array(timestamps)[:, 0], messages
        return frames, timestamps, messages


    def is_device_available(self):
        return self.device_available


    def __del__(self):
        """Clean up ZMQ context and sockets.

        Note that you don't need to terminate the device process here, because this is handled in
        the stop_stream method. And stop_stream is called by the DeviceWorker before the interface is destroyed.
        """
        self.socket.close()
        self.context.term()

 # time.perf_counter_ns()

if __name__ == "__main__":
    # Instantiate the device interface
    BAlertX24_interface = BAlertX24_Interface()
    print(BAlertX24_interface.port)

    # Start the device stream
    BAlertX24_interface.start_stream()

    try:
        # Continuously process frames from the device in a test loop
        for _ in range(10000):  # Run for 100 iterations (or replace with a time-based loop)
            frames, timestamps, messages = BAlertX24_interface.process_frames()
            # if timestamps:
            #     for timestamp in timestamps:
            #         system_time = get_clock_time()
            #         time_diff = abs(system_time - float(timestamp) * 1e-6)
            #         print(f"Timestamp: {timestamp}, System Time: {system_time}, Difference: {time_diff}ms")
            if frames is not None and len(frames) > 0:
                print(f"Frames: {frames}")
                print(f"Timestamps: {timestamps}")
            if messages:
                print(f"Messages: {messages}")

            time.sleep(0.004)  # Adjust sleep time to match expected data rate

    except KeyboardInterrupt:
        print("Test interrupted by user.")

    finally:
        # Stop the device stream and clean up resources
        BAlertX24_interface.stop_stream()
        print("Device stream stopped and resources cleaned up.")