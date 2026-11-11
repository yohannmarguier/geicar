from pathlib import Path

from ultralytics import YOLO

image_dir = Path(__file__).resolve().parents[2] / "ressources"
images = sorted(
    path for path in image_dir.iterdir()
    if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
)

if not images:
    print(f"No JPG or PNG images found in {image_dir}")
else:
    model = YOLO("yolov8n.pt")
    for image in images:
        model.predict(
            source=str(image),
            imgsz=640,
            conf=0.25,
            iou=0.45,
            save=True,
        )

