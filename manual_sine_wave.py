import numpy as np
import sounddevice as sd
import threading
import time

class DynamicMultiChannelSineGenerator:
    def __init__(self, initial_channels=16, sample_rate=44100):
        self.sample_rate = sample_rate
        self.is_playing = False
        self.thread = None
        self.lock = threading.Lock()
        self.set_channels(initial_channels)

    def set_channels(self, num_channels):
        with self.lock:
            self.num_channels = num_channels
            self.frequencies = [440] * num_channels
            self.amplitudes = [0.5] * num_channels
            self.available_channels = self.get_max_output_channels()

    def get_max_output_channels(self):
        try:
            device_info = sd.query_devices(kind='output')
            return min(device_info['max_output_channels'], self.num_channels)
        except:
            print("Error querying audio devices. Falling back to 2 channels.")
            return 2

    def generate_chunk(self, num_frames):
        with self.lock:
            t = np.arange(num_frames) / self.sample_rate
            chunk = np.zeros((num_frames, self.available_channels))
            for i in range(self.available_channels):
                chunk[:, i] = self.amplitudes[i] * np.sin(2 * np.pi * self.frequencies[i] * t)
        return chunk

    def audio_callback(self, outdata, frames, time, status):
        if status:
            print(status)
        outdata[:] = self.generate_chunk(frames)

    def start(self):
        if self.is_playing:
            print("Already playing")
            return
        self.is_playing = True
        def run():
            try:
                with sd.OutputStream(channels=self.available_channels, callback=self.audio_callback, samplerate=self.sample_rate):
                    print(f"Playing on {self.available_channels} channels")
                    while self.is_playing:
                        sd.sleep(1000)
            except Exception as e:
                print(f"Error in audio stream: {e}")
            finally:
                self.is_playing = False
        self.thread = threading.Thread(target=run)
        self.thread.start()

    def stop(self):
        self.is_playing = False
        if self.thread:
            self.thread.join()

    def set_frequency(self, channel, frequency):
        with self.lock:
            if 0 <= channel < self.num_channels:
                self.frequencies[channel] = frequency

    def set_amplitude(self, channel, amplitude):
        with self.lock:
            if 0 <= channel < self.num_channels:
                self.amplitudes[channel] = amplitude

    def get_channel_info(self):
        with self.lock:
            return {
                'num_channels': self.num_channels,
                'available_channels': self.available_channels,
                'frequencies': self.frequencies,
                'amplitudes': self.amplitudes
            }

    def update_channel(self, channel, frequency=None, amplitude=None):
        with self.lock:
            if 0 <= channel < self.num_channels:
                if frequency is not None:
                    self.frequencies[channel] = frequency
                if amplitude is not None:
                    self.amplitudes[channel] = amplitude

    def update_all_channels(self, frequencies=None, amplitudes=None):
        with self.lock:
            if frequencies is not None:
                self.frequencies = frequencies[:self.num_channels]
            if amplitudes is not None:
                self.amplitudes = amplitudes[:self.num_channels]

# Example usage
if __name__ == "__main__":
    generator = DynamicMultiChannelSineGenerator(initial_channels=4)
    generator.start()

    # Example of updating channels
    generator.update_channel(0, frequency=440, amplitude=0.8)
    generator.update_channel(1, frequency=880)
    generator.update_all_channels(frequencies=[200, 300, 400, 500])

    time.sleep(10)
    generator.stop()