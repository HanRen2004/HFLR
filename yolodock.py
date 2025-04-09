from yolo_cls import predict
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from ultralytics import YOLO
import cv2
import numpy as np
from datetime import datetime
app = Flask(__name__)
CORS(app)  # 这将允许所有来源的请求

@app.route('/predict', methods=['POST'])
def predict_endpoint():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    file = request.files['image']
    img_array = np.frombuffer(file.read(), np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    # 使用当前时间作为文件名的一部分（仅用于日志或调试目的）
    current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Processing screenshot_{current_time_str}.jpg")

    # 调整大小以适应YOLO模型输入要求
    image_resized = cv2.resize(image, (640, 640))

    result = predict(image_resized)
    return jsonify({'result': result})


if __name__ == '__main__':
    app.run(host="0.0.0.0",port=5003)