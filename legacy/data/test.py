from roboflow import Roboflow

rf = Roboflow(api_key="49uN4FgymUPGMxrSlTx0")
project = rf.workspace("vehicle-xxgod").project("vietnam-vehicle-detection")
version = project.version(2)
dataset = version.download("yolov8")