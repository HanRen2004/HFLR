from ultralytics import YOLO
from datetime import datetime

def predict(img):
    model = YOLO('best.pt')  # 假设模型文件位于项目根目录下

    # 读取图片并预测
    results = model(img)

    # 解析预测结果
    probs = results[0].probs.data.tolist()  # 获取每个类别的概率值列表

    # 根据编号获取类别名称（需与训练时dataset.yaml的names顺序一致）
    class_names = ['anger', 'disgust', 'fear', 'happy', 'neutral', 'sad', 'surprise']

    # 将所有类别的预测概率和类别名称配对，并按置信度降序排列
    prob_list = list(zip(class_names, probs))
    sorted_probs = sorted(prob_list, key=lambda x: x[1], reverse=True)

    # 构建输出字符串，包含所有表情及其对应的置信度，并加上分析的时间戳
    emotion_details = [f"{emotion}: {conf:.2f}" for emotion, conf in sorted_probs]
    emotion_output = ", ".join(emotion_details)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 获取当前时间并格式化
    emotion = f"预测的表情及置信度（从高到低）: {emotion_output}。分析时间: {timestamp}。请你根据该表情对用户进行安慰"
    return emotion