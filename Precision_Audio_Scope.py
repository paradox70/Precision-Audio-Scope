import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pyaudio
import sys
import statistics
import struct
import collections
import time
import threading

# --- Audio Configuration ---
FORMAT = pyaudio.paInt16
CHANNELS = 2         # Hardware typically requires stereo
RATE = 48000         # 48kHz
CHUNK = 1024         # Small chunk for low latency
WINDOW_SEC = 2.0     # Math window for frequency calculation (2s for precision)
HOP_SEC = 0.25       # Frequency update interval
HYST_FRAC = 0.05     # 5% Hysteresis to ignore noise

# --- Instrument State ---
state = {
    'time_window': 1.0,    # Visual window in seconds (Adjustable via Arrows)
    'y_limit': 32768,      # Vertical zoom (Adjustable via Arrows)
    'trigger_on': True,
    'trigger_level': 0,
    'last_calc_time': 0,
    'current_freq': None
}

# --- Thread-safe Buffer (10 seconds capacity) ---
# Callback feeds this buffer in a separate thread to prevent lag and vertical lines
math_buffer = collections.deque(maxlen=RATE * 10)
buffer_lock = threading.Lock()

# --- Frequency Estimation Logic (EXACTLY from your original script) ---
def estimate_freq(samples, rate):
    if not samples or len(samples) < 2:
        return None
    
    # Remove DC component using list-based calculation
    mean = sum(samples) / len(samples)
    x = [s - mean for s in samples]

    peak = max(abs(v) for v in x) or 1.0
    th = peak * HYST_FRAC

    crossings_t = []
    armed = False

    # Precision zero-crossing logic with hysteresis
    for i in range(1, len(x)):
        a, b = x[i-1], x[i]

        if not armed:
            if b <= -th:
                armed = True
            continue

        # Upward zero crossing detection
        if a < 0 <= b:
            # Linear interpolation for sub-sample accuracy
            denom = (b - a)
            frac = (-a / denom) if denom != 0 else 0.0
            t = (i - 1 + frac) / rate
            crossings_t.append(t)
            armed = False 

    if len(crossings_t) < 2:
        return None

    # Calculate periods and use median for filtering outliers/noise
    periods = [crossings_t[i+1] - crossings_t[i] for i in range(len(crossings_t)-1)]
    if not periods:
        return None
        
    T = statistics.median(periods)
    if T <= 0:
        return None
    return 1.0 / T

# --- PyAudio Callback ---
# This function is called by the system in a separate high-priority thread
def audio_callback(in_data, frame_count, time_info, status):
    if in_data:
        # Unpack interleaved stereo S16_LE data
        s = struct.unpack("<" + "h" * (len(in_data) // 2), in_data)
        # Pick Left channel for calculation/display
        left_channel = s[0::CHANNELS]
        with buffer_lock:
            math_buffer.extend(left_channel)
    return (None, pyaudio.paContinue)

# --- Initialize PyAudio ---
p = pyaudio.PyAudio()

def get_input_device_index():
    """Auto-detect the best input device (Microphone)."""
    info = p.get_host_api_info_by_index(0)
    num_devices = info.get('deviceCount')
    found_idx = None
    
    for i in range(num_devices):
        dev = p.get_device_info_by_host_api_device_index(0, i)
        if dev.get('maxInputChannels') > 0:
            # On Linux, try to find direct hardware access first (hw:0,0)
            if "hw:0,0" in dev.get('name').lower():
                return i
            # On Windows/Other, keep track of the first available input
            if found_idx is None:
                found_idx = i
                
    return found_idx 

device_id = get_input_device_index()

try:
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    input_device_index=device_id,
                    frames_per_buffer=CHUNK,
                    stream_callback=audio_callback)
    stream.start_stream()
    print(f"Stream started on device index: {device_id} (Callback Mode)")
except Exception as e:
    print(f"Error starting audio stream: {e}")
    sys.exit(1)

# --- UI Setup ---
fig, ax = plt.subplots(figsize=(12, 6))
line, = ax.plot([], [], lw=1.5, color='#00FF00')

ax.set_facecolor('black')
ax.grid(True, color='#004400', linestyle='--')
txt_freq = ax.text(0.02, 0.94, '', transform=ax.transAxes, color='yellow', fontsize=16, fontweight='bold')
txt_ctrl = ax.text(0.02, 0.02, '', transform=ax.transAxes, color='white', fontsize=10)

# --- Keyboard Interactivity ---
def on_key(event):
    if event.key == 'right':
        state['time_window'] *= 1.5
    elif event.key == 'left':
        state['time_window'] = max(0.002, state['time_window'] / 1.5)
    elif event.key == 'up':
        state['y_limit'] = max(200, state['y_limit'] / 1.5)
    elif event.key == 'down':
        state['y_limit'] = min(32768, state['y_limit'] * 1.5)
    elif event.key == 't':
        state['trigger_on'] = not state['trigger_on']

fig.canvas.mpl_connect('key_press_event', on_key)

# --- Main Animation Loop ---
def update(frame):
    try:
        with buffer_lock:
            all_data = list(math_buffer)
        
        if not all_data:
            return line,

        # 1. Frequency Calculation (Every HOP_SEC)
        now = time.time()
        if now - state['last_calc_time'] >= HOP_SEC:
            state['last_calc_time'] = now
            needed_samples = int(RATE * WINDOW_SEC)
            calc_input = all_data[-needed_samples:] if len(all_data) >= needed_samples else all_data
            state['current_freq'] = estimate_freq(calc_input, RATE)
        
        # 2. Visualization Processing
        num_vis = int(RATE * state['time_window'])
        vis_data = np.array(all_data[-num_vis:]) if len(all_data) >= num_vis else np.array(all_data)

        # Visual Triggering for waveform stabilization
        offset = 0
        if state['trigger_on'] and len(vis_data) > CHUNK:
            search_area = vis_data[:CHUNK]
            signs = np.sign(search_area - state['trigger_level'])
            diffs = np.diff(signs)
            triggers = np.where(diffs > 0)[0]
            if len(triggers) > 0:
                offset = triggers[0]
        
        plot_data = vis_data[offset:]
        
        # 3. Update Plot Graphics
        line.set_data(np.arange(len(plot_data)), plot_data)
        ax.set_xlim(0, len(plot_data))
        ax.set_ylim(-state['y_limit'], state['y_limit'])
        
        # Update Text Overlays
        f = state['current_freq']
        f_str = f"Frequency: {f:.3f} Hz" if f is not None else "Frequency: Syncing..."
        txt_freq.set_text(f_str)
        
        trig_status = "ON" if state['trigger_on'] else "OFF"
        txt_ctrl.set_text(f"Window: {state['time_window']*1000:.0f}ms | Scale: {state['y_limit']} | Trigger: {trig_status} [T]")
        
        return line, txt_freq, txt_ctrl
    except Exception:
        return line,

# Start Animation
ani = animation.FuncAnimation(fig, update, interval=30, blit=False)

print("\n--- PRECISION AUDIO SCOPE ---")
print("Controls:")
print("  Arrows [Left/Right]: Zoom Time (X-axis)")
print("  Arrows [Up/Down]:    Zoom Voltage (Y-axis)")
print("  Key [T]:             Toggle Visual Trigger")
print("------------------------------")

plt.show()

# Cleanup
stream.stop_stream()
stream.close()
p.terminate()
