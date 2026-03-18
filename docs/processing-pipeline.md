# Memory Recall - 处理流程

> **文档说明**：本文档详细说明文本、图片等多模态输入的处理流程，以及结构化提取的 Prompt 设计和询问判断逻辑。

---

## 文本处理流程

### 1. 短文本处理（< 500 字符）

**适用场景**：日常记录、简短想法、灵感捕捉

```
用户输入："今天下午在咖啡店遇到老同学，聊了创业的事"
    ↓
文本预处理
    ├─ 清洗（去除多余空格、特殊字符）
    └─ 分词（用于后续处理）
    ↓
LLM 结构化提取
    ├─ 提取时间：今天下午 → 2026-03-19T14:00:00+08:00
    ├─ 提取位置：咖啡店 → {"name": "咖啡店", "need_confirm": true}
    ├─ 提取人物：老同学 → [{"name": "老同学", "need_confirm": true}]
    ├─ 推断情绪：开心
    └─ 生成标签：["社交", "创业", "聊天"]
    ↓
询问判断
    ├─ 时间：今天 → 需要确认具体日期？
    │   └─ 判断：内容中有"今天"，语境清晰，不需要询问
    ├─ 位置：咖啡店 → 需要确认具体位置？
    │   └─ 判断：位置模糊，标记 need_confirm = true
    └─ 人物：老同学 → 需要确认人物身份？
        └─ 判断：人物未知，标记 need_confirm = true
    ↓
[需要询问？]
    ├─ 否 → 直接存储
    └─ 是 → 生成询问问题
    ↓
存储记忆
```

### 2. 长文本处理（≥ 500 字符）

**适用场景**：会议记录、日记、文章摘要

```
用户输入：长文本（如会议记录）
    ↓
文本分段
    ├─ 按段落分段
    └─ 每段独立处理
    ↓
对每段进行：
    ├─ LLM 结构化提取
    ├─ 生成段摘要
    └─ 关联到主记忆
    ↓
生成整体摘要
    └─ 使用 LLM 总结全文
    ↓
存储主记忆 + 子记忆
```

**示例**：

```json
{
  "id": "mem_main001",
  "content": "今天参加了一个创业分享会...",
  "input_type": "text",
  "time": {"value": "2026-03-19T14:00:00+08:00"},
  "location": {"name": "创业孵化器"},
  "summary": "参加了创业分享会，讨论了产品定位和市场策略",
  "sub_memories": [
    {
      "id": "mem_sub001",
      "content": "第一位嘉宾分享了产品定位的经验...",
      "time": {"value": "2026-03-19T14:10:00+08:00"},
      "topic": {"main": "产品定位"}
    },
    {
      "id": "mem_sub002",
      "content": "第二位嘉宾讨论了市场策略...",
      "time": {"value": "2026-03-19T14:30:00+08:00"},
      "topic": {"main": "市场策略"}
    }
  ]
}
```

---

## 图片处理流程

### 1. 完整流程

```
图片输入（/path/to/image.jpg）
    ↓
┌─────────────────────────────────────────┐
│         基础信息提取                    │
├─────────────────────────────────────────┤
│ • 文件大小、格式                        │
│ • 图片尺寸                              │
│ • 哈希值（去重）                        │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         EXIF 提取                       │
├─────────────────────────────────────────┤
│ • 拍摄时间（DateTimeOriginal）         │
│ • GPS 坐标（GPSLatitude/Longitude）     │
│ • 设备信息（Make/Model）                │
│ • 曝光参数（ISO/Aperture/ShutterSpeed）│
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         OCR 文字识别                    │
├─────────────────────────────────────────┤
│ • 文字区域检测                          │
│ • 文字识别（PaddleOCR）                 │
│ • 文字位置信息                          │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         场景与物体识别                  │
├─────────────────────────────────────────┤
│ • 场景分类（室内/室外/自然/城市等）    │
│ • 物体检测（人物/动物/物品等）          │
│ • 颜色分析                             │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         人脸检测与识别                  │
├─────────────────────────────────────────┤
│ • 人脸检测                              │
│ • 人脸质量评估                          │
│ • 特征提取（512 维向量）                │
│ • 人脸匹配（关联人物档案）              │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         多模态理解                      │
├─────────────────────────────────────────┤
│ • 使用 Vision-Language Model            │
│ • 生成图片描述                          │
│ • 理解图片语义                          │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         LLM 结构化提取                  │
├─────────────────────────────────────────┤
│ • 时间：优先 EXIF，其次推断             │
│ • 位置：EXIF GPS + 场景推断             │
│ • 人物：人脸识别结果                    │
│ • 标签：场景 + 物体 + OCR               │
└─────────────┬───────────────────────────┘
              │
              ▼
存储记忆
```

### 2. EXIF 提取实现

```python
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import datetime

def extract_exif(image_path: str) -> dict:
    """提取图片 EXIF 信息"""
    exif_data = {
        'datetime': None,
        'gps': None,
        'device': None,
        'exposure': None
    }
    
    try:
        image = Image.open(image_path)
        exif = image._getexif()
        
        if exif:
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                
                # 拍摄时间
                if tag == 'DateTimeOriginal':
                    try:
                        exif_data['datetime'] = datetime.datetime.strptime(
                            value, '%Y:%m:%d %H:%M:%S'
                        )
                    except:
                        pass
                
                # GPS 信息
                elif tag == 'GPSInfo':
                    gps = {}
                    for gps_tag, gps_value in value.items():
                        gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                        gps[gps_tag_name] = gps_value
                    
                    # 解析 GPS 坐标
                    if 'GPSLatitude' in gps and 'GPSLongitude' in gps:
                        lat = _convert_to_degrees(gps['GPSLatitude'])
                        lon = _convert_to_degrees(gps['GPSLongitude'])
                        
                        if 'GPSLatitudeRef' in gps and gps['GPSLatitudeRef'] == 'S':
                            lat = -lat
                        if 'GPSLongitudeRef' in gps and gps['GPSLongitudeRef'] == 'W':
                            lon = -lon
                        
                        exif_data['gps'] = {'latitude': lat, 'longitude': lon}
                
                # 设备信息
                elif tag == 'Make':
                    exif_data['device'] = exif_data.get('device', {})
                    exif_data['device']['make'] = value
                elif tag == 'Model':
                    exif_data['device'] = exif_data.get('device', {})
                    exif_data['device']['model'] = value
    
    except Exception as e:
        print(f"EXIF 提取失败: {e}")
    
    return exif_data

def _convert_to_degrees(value):
    """将 GPS 坐标转换为度数"""
    degrees = float(value[0])
    minutes = float(value[1])
    seconds = float(value[2])
    return degrees + minutes / 60 + seconds / 3600
```

### 3. OCR 处理实现

```python
from paddleocr import PaddleOCR

class OCRProcessor:
    def __init__(self, use_gpu=False):
        self.ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=use_gpu)
    
    def process(self, image_path: str) -> dict:
        """处理图片 OCR"""
        result = self.ocr.ocr(image_path, cls=True)
        
        ocr_result = {
            'text': '',
            'regions': []
        }
        
        if result and result[0]:
            texts = []
            for line in result[0]:
                box = line[0]  # 文字区域坐标
                text_info = line[1]  # 文字内容和置信度
                text = text_info[0]
                confidence = text_info[1]
                
                texts.append(text)
                ocr_result['regions'].append({
                    'text': text,
                    'box': box,
                    'confidence': confidence
                })
            
            ocr_result['text'] = ' '.join(texts)
        
        return ocr_result
```

### 4. 人脸检测与识别

```python
import cv2
import numpy as np
from insightface.app import FaceAnalysis

class FaceDetector:
    def __init__(self):
        self.app = FaceAnalysis(name='buffalo_l')
        self.app.prepare(ctx_id=0, det_size=(640, 640))
    
    def detect(self, image_path: str) -> list:
        """检测人脸"""
        img = cv2.imread(image_path)
        faces = self.app.get(img)
        
        results = []
        for face in faces:
            # 人脸质量评估
            quality_score = self._assess_quality(img, face)
            
            results.append({
                'bbox': face.bbox.tolist(),
                'landmark': face.kps.tolist(),
                'embedding': face.embedding.tolist(),
                'quality_score': quality_score,
                'blur_score': self._calculate_blur(img, face)
            })
        
        return results
    
    def _assess_quality(self, img, face) -> float:
        """评估人脸质量"""
        # 基于人脸大小、清晰度、亮度等评估
        bbox = face.bbox.astype(int)
        face_region = img[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        
        # 计算亮度
        brightness = np.mean(face_region) / 255.0
        
        # 计算清晰度（拉普拉斯方差）
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness = min(blur_score / 1000, 1.0)
        
        # 综合评分
        quality = 0.5 * brightness + 0.5 * sharpness
        return quality
    
    def _calculate_blur(self, img, face) -> float:
        """计算模糊度"""
        bbox = face.bbox.astype(int)
        face_region = img[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        return blur_score / 1000  # 归一化到 0-1
```

---

## 结构化提取 Prompt

### 1. 文本提取 Prompt

```markdown
# 记忆结构化提取

你是一个记忆提取助手。请从用户输入中提取结构化记忆信息。

## 输入内容
{content}

## 提取规则

### 1. 时间（time）
- 提取文本中的时间信息
- 转换为 ISO 8601 格式（包含时区）
- source 类型：
  - extracted：明确提取的时间
  - inferred：推断的时间（如"今天"、"昨天"）
- confidence：时间信息的置信度（0-1）
- original_text：原始时间表述

### 2. 位置（location）
- 提取文本中的位置信息
- 字段：
  - name：位置名称
  - address：详细地址（如有）
  - latitude/longitude：坐标（如有）
  - need_confirm：位置是否模糊需要确认
- 判断 need_confirm：
  - 位置明确（如"星巴克（国贸店）"）→ false
  - 位置模糊（如"某咖啡店"）→ true
  - 无法确定 → true

### 3. 人物（people）
- 提取文本中的人物信息
- 字段：
  - name：人物名称或称呼
  - person_id：人物档案 ID（已知人物）
  - need_confirm：是否需要确认人物身份
  - role：人物角色
- 判断 need_confirm：
  - 已知人物 → false
  - 未知人物 → true

### 4. 情绪（emotion）
- 推断情绪状态
- 字段：
  - value：情绪值
  - confidence：置信度

### 5. 标签（tags）
- 生成 3-5 个标签
- 标签应简洁、有意义

### 6. 持续时间（duration）
- 推断事件持续时间
- 字段：
  - value：持续时间
  - source：推断来源

### 7. 主题（topic）
- 提取主要主题
- 字段：
  - main：主要主题
  - keywords：关键词列表

## 输出格式

```json
{
  "time": {
    "value": "2026-03-19T14:30:00+08:00",
    "source": "inferred",
    "confidence": 0.8,
    "original_text": "今天下午"
  },
  "location": {
    "name": "咖啡店",
    "address": null,
    "latitude": null,
    "longitude": null,
    "need_confirm": true,
    "original_text": "咖啡店"
  },
  "people": [
    {
      "name": "老同学",
      "person_id": null,
      "need_confirm": true,
      "role": "朋友",
      "original_text": "老同学"
    }
  ],
  "emotion": {
    "value": "开心",
    "confidence": 0.7
  },
  "tags": ["社交", "友谊", "聊天"],
  "duration": {
    "value": "2小时",
    "source": "inferred"
  },
  "topic": {
    "main": "聊天",
    "keywords": ["老同学", "聊天", "咖啡店"]
  }
}
```

## 注意事项
1. 时间必须转换为 ISO 8601 格式
2. 位置和人物字段需要判断是否模糊
3. 情绪和标签由模型推断，不询问用户
4. 缺失的可选字段可以不填或填 null
```

### 2. 图片提取 Prompt

```markdown
# 图片记忆结构化提取

你是一个记忆提取助手。请从图片中提取结构化记忆信息。

## 图片信息

### EXIF 信息
- 拍摄时间：{datetime}
- GPS 坐标：{gps}
- 设备：{device}

### OCR 结果
{text}

### 场景识别
- 场景类型：{scene}
- 检测到的物体：{objects}

### 人脸信息
- 检测到 {face_count} 张人脸
- 人脸信息：{faces}

## 提取规则

### 1. 时间（time）
- 优先使用 EXIF 拍摄时间
- EXIF 缺失时，从图片内容推断
- source 为 "metadata"（EXIF）或 "inferred"（推断）

### 2. 位置（location）
- 优先使用 EXIF GPS 坐标
- 根据 GPS 坐标反向地理编码获取地址
- 根据 OCR 和场景推断位置名称
- need_confirm：位置是否需要确认

### 3. 人物（people）
- 从人脸识别结果获取
- 关联已知人物档案
- 未知人物标记 need_confirm = true

### 4. 标签（tags）
- 结合场景、物体、OCR 文字生成
- 生成 5-8 个标签

### 5. 内容描述
- 使用 Vision-Language Model 生成图片描述
- 描述应包含场景、人物、活动等信息

## 输出格式

```json
{
  "content": "图片描述：在咖啡店里，两个人坐在桌前聊天...",
  "time": {
    "value": "2026-03-19T14:30:00+08:00",
    "source": "metadata"
  },
  "location": {
    "name": "星巴克（国贸店）",
    "address": "北京市朝阳区建国门外大街1号",
    "latitude": 39.9086,
    "longitude": 116.4595,
    "need_confirm": false
  },
  "people": [
    {
      "name": "张三",
      "person_id": "person_xyz789",
      "need_confirm": false,
      "role": "朋友"
    },
    {
      "name": "未知人物",
      "person_id": null,
      "need_confirm": true,
      "role": null
    }
  ],
  "tags": ["咖啡", "社交", "室内", "聊天", "朋友"],
  "topic": {
    "main": "社交",
    "keywords": ["咖啡", "聊天", "朋友"]
  }
}
```

## 注意事项
1. 优先使用 EXIF 元数据
2. 人脸识别结果需要关联人物档案
3. 生成详细的图片描述
4. 标签应反映图片的主要特征
```

---

## 询问判断逻辑

### 1. 判断规则

| 字段 | 判断条件 | 是否询问 | 示例 |
|------|---------|---------|------|
| **time** | 时间表述明确（具体日期时间） | ❌ 否 | "2026-03-19 14:30" |
| | 时间表述模糊（相对时间） | ⚠️ 标记确认 | "今天下午" |
| | 完全缺失 | ✅ 是 | 无时间信息 |
| **location** | 位置明确（具体地址/店名） | ❌ 否 | "星巴克（国贸店）" |
| | 位置模糊（泛指） | ⚠️ 标记确认 | "某咖啡店" |
| | 完全缺失 | ❌ 否 | 无位置信息（可选字段） |
| **people** | 已知人物（在档案中） | ❌ 否 | "张三"（已建档） |
| | 未知人物（不在档案中） | ⚠️ 标记确认 | "老同学" |
| | 完全缺失 | ❌ 否 | 无人物信息（可选字段） |

### 2. 询问时机

**两种策略**：

1. **即时询问**（同步）
   - 记忆创建时立即询问
   - 用户体验好，一气呵成
   - 适合关键字段（time）

2. **延迟询问**（异步）
   - 标记 `need_confirm = true`
   - 后续统一询问
   - 适合非关键字段

**推荐策略**：
- **time**：即时询问（关键信息）
- **location**：延迟询问（非必需）
- **people**：延迟询问（可后续补充）

### 3. 询问 Prompt

```markdown
# 询问判断

你是一个询问判断助手。请判断字段是否需要询问用户。

## 字段信息
- 字段名：{field_name}
- 字段值：{field_value}
- 上下文：{context}

## 判断规则

### 时间字段（time）
- 时间明确（具体日期时间）→ need_inquiry: false
- 时间模糊（相对时间，如"今天"、"昨天"）→ need_inquiry: true
  - 询问问题："具体是哪一天？"
- 完全缺失 → need_inquiry: true
  - 询问问题："这件事发生在什么时候？"

### 位置字段（location）
- 位置明确 → need_inquiry: false
- 位置模糊 → need_inquiry: false, need_confirm: true
  - 不立即询问，标记需要确认
- 完全缺失 → need_inquiry: false
  - 位置为可选字段，不询问

### 人物字段（people）
- 已知人物 → need_inquiry: false
- 未知人物 → need_inquiry: false, need_confirm: true
  - 不立即询问，标记需要确认
- 完全缺失 → need_inquiry: false
  - 人物为可选字段，不询问

## 输出格式

```json
{
  "need_inquiry": false,
  "need_confirm": true,
  "inquiry_question": null,
  "reason": "时间信息明确，不需要询问"
}
```

## 示例

### 示例 1
输入：
- 字段名：time
- 字段值：{"value": "2026-03-19T14:30:00+08:00", "source": "extracted"}
- 上下文："今天下午在咖啡店..."

输出：
```json
{
  "need_inquiry": false,
  "need_confirm": false,
  "inquiry_question": null,
  "reason": "时间信息明确，不需要询问"
}
```

### 示例 2
输入：
- 字段名：time
- 字段值：{"value": null, "source": "inferred", "original_text": "昨天"}
- 上下文："昨天遇到一个老朋友..."

输出：
```json
{
  "need_inquiry": true,
  "need_confirm": false,
  "inquiry_question": "具体是哪一天？",
  "reason": "时间为相对表述，需要确认具体日期"
}
```

### 示例 3
输入：
- 字段名：location
- 字段值：{"name": "咖啡店", "need_confirm": null}
- 上下文："在咖啡店聊天..."

输出：
```json
{
  "need_inquiry": false,
  "need_confirm": true,
  "inquiry_question": null,
  "reason": "位置模糊，标记需要确认，但不立即询问"
}
```
```

### 4. 实现代码

```python
class InquiryJudge:
    def __init__(self, llm_service):
        self.llm = llm_service
    
    def judge_time_inquiry(self, time_data: dict, context: str) -> dict:
        """判断时间字段是否需要询问"""
        # 规则优先
        if not time_data.get('value'):
            return {
                'need_inquiry': True,
                'inquiry_question': '这件事发生在什么时候？',
                'reason': '时间信息缺失'
            }
        
        if time_data.get('source') == 'inferred' and '今天' in time_data.get('original_text', ''):
            # "今天" 语境清晰，不询问
            return {
                'need_inquiry': False,
                'reason': '时间表述清晰'
            }
        
        # 其他情况使用 LLM 判断
        prompt = self._build_time_judge_prompt(time_data, context)
        result = self.llm.extract(prompt)
        return result
    
    def judge_location_inquiry(self, location_data: dict, context: str) -> dict:
        """判断位置字段是否需要询问"""
        if not location_data.get('name'):
            # 位置缺失，不询问（可选字段）
            return {
                'need_inquiry': False,
                'need_confirm': False,
                'reason': '位置信息缺失，但为可选字段'
            }
        
        # 位置存在，判断是否模糊
        location_name = location_data.get('name', '')
        
        # 检查是否包含具体店名
        if any(keyword in location_name for keyword in ['店', '公司', '大厦', '中心']):
            # 可能是具体位置
            return {
                'need_inquiry': False,
                'need_confirm': False,
                'reason': '位置可能明确'
            }
        else:
            # 位置模糊
            return {
                'need_inquiry': False,
                'need_confirm': True,
                'reason': '位置模糊，标记需要确认'
            }
    
    def judge_people_inquiry(self, people_data: list, context: str) -> list:
        """判断人物字段是否需要询问"""
        results = []
        
        for person in people_data:
            if person.get('person_id'):
                # 已知人物
                results.append({
                    'name': person['name'],
                    'need_inquiry': False,
                    'need_confirm': False,
                    'reason': '已知人物'
                })
            else:
                # 未知人物
                results.append({
                    'name': person['name'],
                    'need_inquiry': False,
                    'need_confirm': True,
                    'reason': '未知人物，标记需要确认'
                })
        
        return results
```

---

*文档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
