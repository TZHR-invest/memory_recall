"""
EXIF 信息提取器
从图片中提取拍摄时间、GPS 位置等信息
"""
from typing import Optional, Dict, Any
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import logging

logger = logging.getLogger(__name__)


class EXIFExtractor:
    """EXIF 信息提取器"""
    
    @staticmethod
    def extract(image_path: str) -> Dict[str, Any]:
        """
        从图片中提取 EXIF 信息
        
        Args:
            image_path: 图片文件路径
        
        Returns:
            EXIF 信息字典，包含：
            - datetime: 拍摄时间
            - gps: GPS 坐标（latitude, longitude）
            - camera: 相机信息（make, model）
            - orientation: 拍摄方向
            - flash: 是否使用闪光灯
        """
        exif_data = {
            "datetime": None,
            "gps": None,
            "camera": None,
            "orientation": None,
            "flash": None
        }
        
        try:
            # 打开图片
            image = Image.open(image_path)
            
            # 获取 EXIF 数据
            exif_info = image._getexif()
            if not exif_info:
                logger.info(f"图片 {image_path} 没有 EXIF 信息")
                return exif_data
            
            # 解析 EXIF 标签
            exif = {}
            for tag, value in exif_info.items():
                decoded = TAGS.get(tag, tag)
                exif[decoded] = value
            
            # 提取拍摄时间
            # 尝试多个可能的标签
            datetime_tags = ["DateTimeOriginal", "DateTime", "DateTimeDigitized"]
            for tag in datetime_tags:
                if tag in exif:
                    try:
                        dt_str = exif[tag]
                        # EXIF 时间格式: "2024:01:15 10:30:00"
                        dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                        exif_data["datetime"] = dt.isoformat()
                        logger.info(f"成功提取拍摄时间: {exif_data['datetime']}")
                        break
                    except Exception as e:
                        logger.warning(f"解析拍摄时间失败: {e}")
            
            # 提取 GPS 信息
            if "GPSInfo" in exif:
                gps_info = exif["GPSInfo"]
                gps_data = {}
                
                # 解析 GPS 标签
                for key in gps_info.keys():
                    name = GPSTAGS.get(key, key)
                    gps_data[name] = gps_info[key]
                
                # 提取经纬度
                latitude = EXIFExtractor._get_gps_coordinate(
                    gps_data.get("GPSLatitude"),
                    gps_data.get("GPSLatitudeRef")
                )
                longitude = EXIFExtractor._get_gps_coordinate(
                    gps_data.get("GPSLongitude"),
                    gps_data.get("GPSLongitudeRef")
                )
                
                if latitude and longitude:
                    exif_data["gps"] = {
                        "latitude": latitude,
                        "longitude": longitude
                    }
            
            # 提取相机信息
            if "Make" in exif or "Model" in exif:
                exif_data["camera"] = {
                    "make": exif.get("Make", "").strip(),
                    "model": exif.get("Model", "").strip()
                }
            
            # 提取拍摄方向
            if "Orientation" in exif:
                exif_data["orientation"] = exif["Orientation"]
            
            # 提取闪光灯信息
            if "Flash" in exif:
                # Flash 值是一个整数，第 0 位表示是否闪光
                exif_data["flash"] = bool(exif["Flash"] & 1)
            
            logger.info(f"成功提取 EXIF 信息: {exif_data}")
            return exif_data
            
        except Exception as e:
            logger.error(f"提取 EXIF 信息失败: {e}")
            return exif_data
    
    @staticmethod
    def _get_gps_coordinate(coordinate: Optional[tuple], ref: Optional[str]) -> Optional[float]:
        """
        将 GPS 坐标转换为十进制
        
        Args:
            coordinate: GPS 坐标元组 (度, 分, 秒)
            ref: 方向参考 (N/S/E/W)
        
        Returns:
            十进制坐标
        """
        if not coordinate or not ref:
            return None
        
        try:
            # 度分秒转换为十进制
            degrees = coordinate[0]
            minutes = coordinate[1]
            seconds = coordinate[2]
            
            decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
            
            # 根据方向调整符号
            if ref in ["S", "W"]:
                decimal = -decimal
            
            return round(decimal, 6)
        except Exception as e:
            logger.warning(f"GPS 坐标转换失败: {e}")
            return None
    
    @staticmethod
    def get_datetime(image_path: str) -> Optional[datetime]:
        """
        从图片中提取拍摄时间
        
        Args:
            image_path: 图片文件路径
        
        Returns:
            拍摄时间，失败返回 None
        """
        exif_data = EXIFExtractor.extract(image_path)
        if exif_data["datetime"]:
            try:
                return datetime.fromisoformat(exif_data["datetime"])
            except:
                return None
        return None
    
    @staticmethod
    def get_gps(image_path: str) -> Optional[Dict[str, float]]:
        """
        从图片中提取 GPS 坐标
        
        Args:
            image_path: 图片文件路径
        
        Returns:
            GPS 坐标字典 {latitude, longitude}，失败返回 None
        """
        exif_data = EXIFExtractor.extract(image_path)
        return exif_data.get("gps")
