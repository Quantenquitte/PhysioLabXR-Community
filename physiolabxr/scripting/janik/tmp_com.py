import numpy as np
import time

from physiolabxr.scripting.RenaScript import RenaScript

# Wii Balance Board specifications
WII_BOARD_WIDTH = 43.3  # cm (distance between left and right sensors)
WII_BOARD_LENGTH = 23.8  # cm (distance between front and back sensors)

# Expected channel names for Wii Balance Board (you may need to adjust these based on your stream)
WII_CHANNELS = ["Weight_TopLeft", "Weight_TopRight", "Weight_BottomLeft", "Weight_BottomRight"]

# Configuration for real-time COP calculation
WII_EXPECTED_FRAMERATE = 60  # Hz (for PhysioLabXR Run Frequency setting)
WII_SMOOTHING_SAMPLES = 3   # Number of recent samples to use for smoothing (1-5)
WII_FORCE_THRESHOLD = 1.0   # kg, minimum force to calculate COP

class tmp_com(RenaScript):
    def __init__(self, *args, **kwargs):
        """
        Please do not edit this function
        """
        super().__init__(*args, **kwargs)

    # Start will be called once when the run button is hit.
    def init(self):
        # Access input parameters from PhysioLabXR GUI
        print("Available parameters:", list(self.params.keys()))
        
        # Get specific parameters with default values
        self.force_threshold = self.params.get('force_threshold', WII_FORCE_THRESHOLD)
        self.smoothing_samples = int(self.params.get('smoothing_samples', WII_SMOOTHING_SAMPLES))
        self.board_width = self.params.get('board_width', WII_BOARD_WIDTH)
        self.board_length = self.params.get('board_length', WII_BOARD_LENGTH)
        
        print("Wii Balance Board COP Calculator initialized")
        print(f"Available input streams: {list(self.inputs.keys())}")
        print(f"Board dimensions: {self.board_width}cm x {self.board_length}cm")
        print(f"Force threshold: {self.force_threshold}kg")
        print(f"Smoothing samples: {self.smoothing_samples}")
        print(f"Configured for ~{WII_EXPECTED_FRAMERATE}Hz")
        
        # Initialize variables for monitoring
        self.last_cop_time = time.time()
        self.cop_calculation_count = 0
        self.stream_name = None
        
        # Try to identify the Wii Balance Board stream
        # Look for stream names that might contain Wii or Balance Board data
        for stream_name in self.inputs.keys():
            print(f"Checking stream: {stream_name}")
            # You may need to adjust this based on your actual stream name
            if any(keyword in stream_name.lower() for keyword in ['wii', 'balance', 'board', 'force']):
                self.stream_name = stream_name
                print(f"Found potential Wii Balance Board stream: {stream_name}")
                break
        
        if self.stream_name is None and len(self.inputs.keys()) > 0:
            # Use the first available stream as fallback
            self.stream_name = list(self.inputs.keys())[0]
            print(f"Using first available stream: {self.stream_name}")
        
        if self.stream_name:
            try:
                # Get stream info
                channel_names = self.get_stream_info(self.stream_name, 'ChannelNames')
                sampling_rate = self.get_stream_info(self.stream_name, 'NominalSamplingRate')
                print(f"Stream '{self.stream_name}' channels: {channel_names}")
                print(f"Sampling rate: {sampling_rate} Hz")
            except Exception as e:
                print(f"Could not get stream info: {e}")

    # loop is called <Run Frequency> times per second
    def loop(self):
        if self.stream_name is None:
            return
            
        try:
            # Get the latest data from the Wii Balance Board stream
            if self.stream_name in self.inputs.keys():
                # Since PhysioLabXR calls this at Run Frequency (60-100Hz),
                # we just need to get the most recent data available
                force_data = self.inputs.get_data(self.stream_name)
                timestamps = self.inputs.get_timestamps(self.stream_name)
                
                if force_data.size > 0 and force_data.shape[1] > 0:
                    # For real-time processing: use only the most recent sample
                    # or a small batch of recent samples for smoothing
                    
                    # Get smoothing parameter (auto-updated by PhysioLabXR)
                    smoothing_samples = int(self.params.get('smoothing_samples', WII_SMOOTHING_SAMPLES))
                    
                    if force_data.shape[1] >= smoothing_samples:
                        # Use last N samples for slight smoothing (reduces noise)
                        recent_data = force_data[:, -smoothing_samples:]
                    else:
                        # Use all available data if less than N samples
                        recent_data = force_data
                    
                    # Calculate COP from the recent force data (parameters auto-update)
                    COPx, COPy, total_force = self.calculate_wii_cop_with_params(recent_data)
                    
                    # Use the most recent COP values (last calculated)
                    latest_copx = COPx[-1] if len(COPx) > 0 else 0.0
                    latest_copy = COPy[-1] if len(COPy) > 0 else 0.0
                    latest_force = total_force[-1] if len(total_force) > 0 else 0.0
                    
                    # Output the COP data
                    # Create output arrays - you can adjust the format as needed
                    cop_output = np.array([latest_copx, latest_copy, latest_force])
                    
                    # Set output to streams (you'll need to configure output streams in PhysioLabXR GUI)
                    self.outputs['COP_Output'] = cop_output
                    
                    self.cop_calculation_count += 1

                            
        except Exception as e:
            print(f"Error in COP calculation: {e}")

    # cleanup is called when the stop button is hit
    def cleanup(self):
        print('Wii Balance Board COP Calculator stopped')
        print(f"Total COP calculations performed: {self.cop_calculation_count}")

    def calculate_wii_cop_with_params(self, force_data: np.ndarray) -> tuple:
        """
        Calculate COP using parameters from PhysioLabXR GUI (auto-updated in real-time)
        """
        if force_data.shape[0] < 4:
            raise ValueError("Force data must contain at least 4 channels for Wii Balance Board.")
        
        # Extract force readings from each sensor
        TL, TR, BL, BR = force_data[0], force_data[1], force_data[2], force_data[3]
        
        # Calculate total force
        total_force = TL + TR + BL + BR
        
        # Board dimensions from parameters (auto-updated by PhysioLabXR)
        board_width = self.params.get('board_width', WII_BOARD_WIDTH)
        board_length = self.params.get('board_length', WII_BOARD_LENGTH)
        half_width = board_width / 2
        half_length = board_length / 2
        
        # Initialize COP arrays
        COPx = np.zeros_like(total_force)
        COPy = np.zeros_like(total_force)
        
        # Calculate COP only where there's sufficient force (auto-updated parameter)
        force_threshold = self.params.get('force_threshold', WII_FORCE_THRESHOLD)
        valid_force = total_force > force_threshold
        
        if np.any(valid_force):
            # Medial-lateral COP (X-direction)
            moment_y = half_width * ((TR[valid_force] + BR[valid_force]) - 
                                    (TL[valid_force] + BL[valid_force]))
            COPx[valid_force] = moment_y / total_force[valid_force]
            
            # Anterior-posterior COP (Y-direction)
            moment_x = half_length * ((TL[valid_force] + TR[valid_force]) - 
                                     (BL[valid_force] + BR[valid_force]))
            COPy[valid_force] = moment_x / total_force[valid_force]
        
        return COPx, COPy, total_force