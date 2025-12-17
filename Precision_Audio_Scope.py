import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pyaudio
import sys
import statistics
import struct
import collections
import time

# --- Audio Configuration ---
FORMAT = pyaudio.paInt16
CHANNELS = 2         # Hardware typically requires stereo
RATE = 48000         # 48kHz
CHUNK = 2048         # Buffer size for visual refresh
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

# --- Buffer to hold data (10 seconds capacity) ---
math_buffer = collections.deque(maxlen=RATE * 10)

# --- PyAudio Setup ---
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
                    frames_per_buffer=CHUNK)
    print(f"Successfully opened stream on device index: {device_id}")
except Exception as e:
    print(f"Error opening PyAudio stream: {e}")
    sys.exit(1)

# --- Frequency Estimation Logic (High Precision State-Machine) ---
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
        # Read all available samples to prevent buffer lag
        available_samples = stream.get_read_available()
        if available_samples > 0:
            raw_bytes = stream.read(available_samples, exception_on_overflow=False)
            # Unpack interleaved stereo S16_LE data
            s = struct.unpack("<" + "h" * (len(raw_bytes) // 2), raw_bytes)
            # Pick Left channel for calculation/display
            left_channel = s[0::CHANNELS]
            math_buffer.extend(left_channel)

        # 1. Frequency Calculation (Every HOP_SEC)
        now = time.time()
        if now - state['last_calc_time'] >= HOP_SEC:
            state['last_calc_time'] = now
            full_data = list(math_buffer)
            needed_samples = int(RATE * WINDOW_SEC)
            calc_input = full_data[-needed_samples:] if len(full_data) >= needed_samples else full_data
            state['current_freq'] = estimate_freq(calc_input, RATE)

        # 2. Visualization Processing
        num_vis = int(RATE * state['time_window'])
        all_data = list(math_buffer)

        if len(all_data) < num_vis:
            vis_data = np.array(all_data)
        else:
            vis_data = np.array(all_data[-num_vis:])

        # Visual Triggering for waveform stabilization (No signal modification)
        offset = 0
        if state['trigger_on'] and len(vis_data) > 2048:
            search_area = vis_data[:2048]
            signs = np.sign(search_area - state['trigger_level'])
            diffs = np.diff(signs)
            triggers = np.where(diffs > 0)[0]
            if len(triggers) > 0:
                offset = triggers[0]

        plot_data = vis_data[offset:]

        # 3. Update Graphics
        line.set_data(np.arange(len(plot_data)), plot_data)
        ax.set_xlim(0, len(plot_data))
        ax.set_ylim(-state['y_limit'], state['y_limit'])

        # Update UI Labels
        f = state['current_freq']
        f_str = f"Frequency: {f:.3f} Hz" if f is not None else "Frequency: Syncing..."
        txt_freq.set_text(f_str)

        trig_status = "ON" if state['trigger_on'] else "OFF"
        txt_ctrl.set_text(f"Window: {state['time_window']*1000:.0f}ms | Scale: {state['y_limit']} | Trigger: {trig_status} [T]")

        return line, txt_freq, txt_ctrl
    except Exception:
        return line,

# Animation loop using Matplotlib
ani = animation.FuncAnimation(fig, update, interval=30, blit=False)

print("\n--- PRECISION AUDIO SCOPE ---")
print("Interactive Controls:")
print("  Arrows [Left/Right]: Zoom Time (X-axis)")
print("  Arrows [Up/Down]:    Zoom Voltage (Y-axis)")
print("  Key [T]:             Toggle Visual Trigger")
print("------------------------------")

plt.show()

# Final Resource Cleanup
stream.stop_stream()
stream.close()
p.terminate()
