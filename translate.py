# -*- coding: utf-8 -*-
"""翻译模块：可配置引擎，适配国内网络。翻译结果由调用方缓存进数据库。"""
from deep_translator import (
    GoogleTranslator, DeeplTranslator, BaiduTranslator, LibreTranslator, MyMemoryTranslator
)
from config import TRANSLATE

_cache = {}

def is_chinese(text):
    if not text:
        return False
    cnt = sum(1 for c in text if '一' <= c <= '鿿')
    return cnt / max(len(text), 1) > 0.15

def translate(text, src="auto", dest="zh-CN"):
    """把英文(或其他)翻译成中文。已是中文则原样返回。"""
    if not text or is_chinese(text):
        return text
    key = (text[:200], dest)
    if key in _cache:
        return _cache[key]
    try:
        eng = TRANSLATE["engine"].lower()
        if eng == "deepl":
            t = DeeplTranslator(source="en", target="zh", api_key=TRANSLATE["deepl_key"])
        elif eng == "baidu":
            t = BaiduTranslator(source="en", target="zh",
                                appid=TRANSLATE["baidu_appid"], key=TRANSLATE["baidu_key"])
        elif eng == "libretranslate":
            t = LibreTranslator(source="en", target="zh",
                                base_url=TRANSLATE["libretranslate_url"])
        elif eng == "mymemory":
            t = MyMemoryTranslator(source="en", target="zh")
        else:
            t = GoogleTranslator(source="auto", target="zh-CN")
        out = t.translate(text[:4500])
        _cache[key] = out or text
    except Exception as e:
        # 主引擎失败：自动回退到 MyMemory（免费、无需 key、国内通常可达）
        try:
            out = MyMemoryTranslator(source="en", target="zh").translate(text[:4500])
            _cache[key] = out or text
        except Exception:
            _cache[key] = text
            print(f"  [translate-skip] {str(e)[:60]}")
    return _cache[key]
