import os
import subprocess
import re

def list_video_devices():
    video_devices = []
    for dev in os.listdir('/dev'):
        if dev.startswith('video'):
            video_devices.append('/dev/' + dev)
    return sorted(video_devices)

def get_usb_cam_info(dev):
    print(f"\n=== Kamera gefunden: {dev} ===")
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--device', dev, '--list-formats-ext'],
            capture_output=True, text=True, check=True
        )
        output = result.stdout
        if not output.strip():
            print("Keine Informationen gefunden (evtl. gesperrt oder kein Gerät).")
            return
        print(output)
    except Exception as e:
        print(f"Fehler bei {dev}: {e}")

def check_libcamera():
    # Prüft ob libcamera installiert ist
    return subprocess.call(['which', 'libcamera-hello'], stdout=subprocess.DEVNULL) == 0

def get_rpi_camera_info():
    print("\n=== Prüfe auf Raspberry Pi Kamera (CSI, libcamera) ===")
    if check_libcamera():
        try:
            result = subprocess.run(
                ['libcamera-hello', '--list-cameras'],
                capture_output=True, text=True, check=True
            )
            output = result.stdout
            print(output)
        except Exception as e:
            print(f"Fehler bei libcamera-hello: {e}")
    else:
        print("libcamera-hello nicht installiert oder keine Kamera erkannt.")

def main():
    print("Starte Kamera-Erkennung...")

    # Liste alle /dev/video* Geräte auf (meist USB, UVC)
    devices = list_video_devices()
    if devices:
        for dev in devices:
            get_usb_cam_info(dev)
    else:
        print("Keine USB-Kameras unter /dev/video* gefunden.")

    # Prüfe auf PiCam (CSI) via libcamera
    get_rpi_camera_info()

if __name__ == "__main__":
    main()
