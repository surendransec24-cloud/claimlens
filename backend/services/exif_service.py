import os
from typing import Dict, Any, Optional, Tuple
from PIL import Image
from PIL.ExifTags import Base
import exifread

def _convert_to_degrees(value) -> Optional[float]:
    """Helper function to convert GPS coordinates stored in EXIF to decimal degrees."""
    try:
        d = float(value.values[0].num) / float(value.values[0].den)
        m = float(value.values[1].num) / float(value.values[1].den)
        s = float(value.values[2].num) / float(value.values[2].den)
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None

class ExifService:
    @staticmethod
    def extract_metadata(file_path: str) -> Dict[str, Any]:
        """Extracts EXIF date/time, GPS coordinates, and camera info from an image."""
        result: Dict[str, Any] = {
            "has_exif": False,
            "timestamp": None,
            "gps": None,
            "camera_make": None,
            "camera_model": None,
            "image_width": None,
            "image_height": None,
            "raw_tags": {}
        }
        
        if not os.path.exists(file_path):
            return result
            
        # 1. Pillow EXIF check
        try:
            with Image.open(file_path) as img:
                result["image_width"], result["image_height"] = img.size
                result["format"] = img.format
                p_exif = img.getexif()
                if p_exif:
                    result["has_exif"] = True
                    # Check DateTimeOriginal (tag 36867) or DateTime (tag 306)
                    raw_dt = p_exif.get(Base.DateTimeOriginal) or p_exif.get(Base.DateTime) or p_exif.get(36867) or p_exif.get(306)
                    if raw_dt:
                        result["timestamp"] = str(raw_dt).replace(":", "-", 2)
                    make = p_exif.get(Base.Make) or p_exif.get(271)
                    if make:
                        result["camera_make"] = str(make)
                    model = p_exif.get(Base.Model) or p_exif.get(272)
                    if model:
                        result["camera_model"] = str(model)
        except Exception:
            pass

        # 2. ExifRead check for supplementary / GPS data
        try:
            with open(file_path, "rb") as f:
                tags = exifread.process_file(f, details=False)
                if tags:
                    result["has_exif"] = True
                    # Timestamp fallback if Pillow didn't find it
                    if not result["timestamp"]:
                        for ts_key in ["EXIF DateTimeOriginal", "Image DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"]:
                            if ts_key in tags:
                                result["timestamp"] = str(tags[ts_key]).replace(":", "-", 2)
                                break
                    
                    if not result["camera_make"] and "Image Make" in tags:
                        result["camera_make"] = str(tags["Image Make"])
                    if not result["camera_model"] and "Image Model" in tags:
                        result["camera_model"] = str(tags["Image Model"])
                        
                    # GPS Extraction
                    lat = None
                    lon = None
                    if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
                        lat_deg = _convert_to_degrees(tags["GPS GPSLatitude"])
                        if lat_deg is not None:
                            lat_ref = str(tags["GPS GPSLatitudeRef"])
                            lat = lat_deg if lat_ref == "N" else -lat_deg
                            
                    if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
                        lon_deg = _convert_to_degrees(tags["GPS GPSLongitude"])
                        if lon_deg is not None:
                            lon_ref = str(tags["GPS GPSLongitudeRef"])
                            lon = lon_deg if lon_ref == "E" else -lon_deg
                            
                    if lat is not None and lon is not None:
                        result["gps"] = {
                            "latitude": round(lat, 6),
                            "longitude": round(lon, 6)
                        }
        except Exception as e:
            result["error"] = str(e)
            
        return result
