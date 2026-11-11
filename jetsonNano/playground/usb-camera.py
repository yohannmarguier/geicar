"""Detect objects in a USB camera stream: python usb-camera.py --camera 0.

Requires ultralytics and OpenCV with GUI support.
Try --camera 1 if camera 0 selects the computer's built-in camera.
Press Q or Escape, or close the window, to quit.
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    args = parser.parse_args()

    try:
        import cv2
        from ultralytics import YOLO
    except ImportError:
        print("Install dependencies with: python -m pip install ultralytics opencv-python", file=sys.stderr)
        return 1

    model_path = Path(__file__).resolve().with_name("yolov8n.pt")
    if not model_path.is_file():
        print("YOLO model not found: {}".format(model_path), file=sys.stderr)
        return 1
    model = YOLO(str(model_path))

    camera = cv2.VideoCapture(args.camera)
    window = "YOLO USB camera - Q or Escape to quit"
    try:
        if not camera.isOpened():
            print(
                "Cannot open camera {}. Check the USB connection and camera permissions, "
                "close other camera apps, or try another --camera index.".format(args.camera),
                file=sys.stderr,
            )
            return 1

        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        while True:
            success, frame = camera.read()
            if not success or frame is None:
                print("Could not read a frame from the camera.", file=sys.stderr)
                return 1
            results = model.predict(
                source=frame,
                imgsz=640,
                conf=0.25,
                iou=0.45,
                verbose=False,
                save=False,
            )
            cv2.imshow(window, results[0].plot())
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    except cv2.error as error:
        print("OpenCV error: {}".format(error), file=sys.stderr)
        return 1
    finally:
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
