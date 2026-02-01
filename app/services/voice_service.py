"""
Voice Analysis Service
基于 voice_feature_extract.py 严格同步
"""
import numpy as np
import librosa
from pathlib import Path
from typing import Dict, Any


def convert_to_native_types(obj):
    """
    递归将numpy类型转换为Python原生类型，以便JSON序列化
    """
    if isinstance(obj, dict):
        return {k: convert_to_native_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_native_types(item) for item in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    else:
        return obj


def extract_voice_features(audio_path: str) -> Dict[str, Any]:
    """
    提取音频的声学特征

    Args:
        audio_path: 音频文件路径（支持wav, mp3, m4a等）

    Returns:
        包含各项声学特征的字典
    """
    # 加载音频，统一采样率为22050Hz
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)

    # ==================== 语音活动检测 VAD ====================
    # 过滤静音段，只分析有声段
    intervals = librosa.effects.split(y, top_db=25)
    if len(intervals) > 0:
        y_voiced = np.concatenate([y[start:end] for start, end in intervals])
        voiced_ratio = len(y_voiced) / len(y)
    else:
        y_voiced = y
        voiced_ratio = 1.0

    # ==================== 1. 基频 F0 ====================
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y_voiced,
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C6'),
        sr=sr
    )

    f0_valid = f0[~np.isnan(f0)]
    if len(f0_valid) > 0:
        f0_mean = float(np.mean(f0_valid))
        f0_std = float(np.std(f0_valid))
        f0_min = float(np.min(f0_valid))
        f0_max = float(np.max(f0_valid))
        f0_median = float(np.median(f0_valid))
        # 音高稳定性：变化系数越小越稳定
        pitch_stability = 1 - (f0_std / f0_mean) if f0_mean > 0 else 0
    else:
        f0_mean = f0_std = f0_min = f0_max = f0_median = 0
        pitch_stability = 0

    # ==================== 2. MFCC 梅尔频率倒谱系数 ====================
    mfcc = librosa.feature.mfcc(y=y_voiced, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1).tolist()
    mfcc_std = np.std(mfcc, axis=1).tolist()

    # MFCC第2维通常与声音明亮度相关
    mfcc2_mean = mfcc_mean[1] if len(mfcc_mean) > 1 else 0

    # ==================== 3. 频谱质心 Spectral Centroid ====================
    spectral_centroid = librosa.feature.spectral_centroid(y=y_voiced, sr=sr)[0]
    centroid_mean = float(np.mean(spectral_centroid))
    centroid_std = float(np.std(spectral_centroid))

    # ==================== 4. 频谱对比度 Spectral Contrast ====================
    spectral_contrast = librosa.feature.spectral_contrast(y=y_voiced, sr=sr)
    contrast_mean = np.mean(spectral_contrast, axis=1).tolist()

    # ==================== 5. 过零率 Zero Crossing Rate ====================
    zcr = librosa.feature.zero_crossing_rate(y_voiced)[0]
    zcr_mean = float(np.mean(zcr))
    zcr_std = float(np.std(zcr))

    # ==================== 6. RMS能量 ====================
    rms = librosa.feature.rms(y=y_voiced)[0]
    rms_mean = float(np.mean(rms))
    rms_std = float(np.std(rms))
    # 动态范围
    rms_dynamic_range = float(np.max(rms) - np.min(rms)) if len(rms) > 0 else 0

    # ==================== 7. 谐波比 Harmonic Ratio ====================
    harmonic, percussive = librosa.effects.hpss(y_voiced)
    harmonic_energy = np.sum(harmonic ** 2)
    total_energy = np.sum(y_voiced ** 2)
    harmonic_ratio = float(harmonic_energy / total_energy) if total_energy > 0 else 0

    # ==================== 8. 频谱滚降点 Spectral Rolloff ====================
    rolloff = librosa.feature.spectral_rolloff(y=y_voiced, sr=sr, roll_percent=0.85)[0]
    rolloff_mean = float(np.mean(rolloff))

    # ==================== 9. 频谱平坦度 Spectral Flatness ====================
    flatness = librosa.feature.spectral_flatness(y=y_voiced)[0]
    flatness_mean = float(np.mean(flatness))

    # ==================== 10. 频谱带宽 Spectral Bandwidth ====================
    bandwidth = librosa.feature.spectral_bandwidth(y=y_voiced, sr=sr)[0]
    bandwidth_mean = float(np.mean(bandwidth))

    # ==================== 11. 共振峰估计（简化版） ====================
    # 使用LPC进行共振峰估计
    try:
        # 取一段稳定的语音进行分析
        frame_length = min(2048, len(y_voiced))
        if frame_length > 512:
            mid_point = len(y_voiced) // 2
            frame = y_voiced[mid_point:mid_point + frame_length]

            # LPC分析
            lpc_order = 12
            a = librosa.lpc(frame, order=lpc_order)

            # 找到LPC多项式的根
            roots = np.roots(a)
            roots = roots[np.imag(roots) >= 0]  # 只取正频率

            # 转换为频率
            angles = np.arctan2(np.imag(roots), np.real(roots))
            formants = sorted(angles * (sr / (2 * np.pi)))
            formants = [f for f in formants if 200 < f < 5000]  # 过滤合理范围

            f1 = formants[0] if len(formants) > 0 else 0
            f2 = formants[1] if len(formants) > 1 else 0
            f3 = formants[2] if len(formants) > 2 else 0
        else:
            f1 = f2 = f3 = 0
    except Exception:
        f1 = f2 = f3 = 0

    # ==================== 12. 预判断逻辑（v4.0 基于音高稳定性优先） ====================
    # 性别预判
    if f0_mean > 200:
        gender_hint = "女声（高置信度）"
    elif f0_mean > 155:
        gender_hint = "女声（可能）"
    elif f0_mean > 140:
        gender_hint = "性别不确定，需结合音色判断"
    else:
        gender_hint = "男声（可能）"

    # ===== 核心改进：基于音高稳定性优先判断 =====
    # 音高稳定性是区分御姐音和少御音的关键！

    # 音高稳定性预判
    if pitch_stability > 0.85:
        stability_hint = "极高稳定性(>0.85)，控制力强，倾向播音腔/御姐音"
    elif pitch_stability > 0.70:
        stability_hint = "较高稳定性(0.70-0.85)，倾向温御音/知性音"
    elif pitch_stability > 0.50:
        stability_hint = "正常稳定性(0.50-0.70)，倾向少御音/少女音"
    else:
        stability_hint = "稳定性较低(<0.50)，情感丰富，倾向活泼少女/萝莉音"

    # 音色大类预判（综合音高稳定性和F0）
    if pitch_stability > 0.85 and 165 <= f0_mean <= 200:
        voice_type_hint = "【御姐音】音高稳定性极高+F0在御姐区间"
    elif pitch_stability > 0.85 and f0_mean > 200:
        voice_type_hint = "【沉稳少女音】音高稳定性极高但F0偏高"
    elif f0_mean > 260:
        voice_type_hint = "【萝莉音/少萝音】F0极高"
    elif f0_mean > 210:
        voice_type_hint = "【少女音】F0在少女区间"
    elif pitch_stability > 0.70 and f0_mean < 190:
        voice_type_hint = "【温御音】稳定性较高+F0偏低"
    elif 165 <= f0_mean <= 210:
        voice_type_hint = "【少御音】F0在少御区间，稳定性正常"
    elif f0_mean < 165:
        voice_type_hint = "【温御音/女王音】F0偏低"
    else:
        voice_type_hint = "【少御音】默认分类"

    # 清澈度预判
    if harmonic_ratio > 0.80:
        clarity_hint = "非常清澈(>0.80)，适合纯净/清甜修饰"
    elif harmonic_ratio > 0.65:
        clarity_hint = "较清晰(0.65-0.80)，中性质感"
    elif harmonic_ratio > 0.50:
        clarity_hint = "略带沙哑(0.50-0.65)，可考虑慵懒/磁性修饰"
    else:
        clarity_hint = "沙哑明显(<0.50)，可能是烟嗓或录音问题"

    # 亮度预判
    if centroid_mean > 3500:
        brightness_hint = "声音明亮(>3500Hz)，适合清亮/元气修饰"
    elif centroid_mean > 2000:
        brightness_hint = "亮度适中(2000-3500Hz)"
    else:
        brightness_hint = "声音偏暗沉温暖(<2000Hz)，适合温柔/朦胧修饰"

    # 气息感预判
    if zcr_mean > 0.15:
        breath_hint = "气息感明显(>0.15)，适合ASMR/轻柔修饰"
    elif zcr_mean > 0.08:
        breath_hint = "轻微气息感(0.08-0.15)"
    else:
        breath_hint = "发声扎实(<0.08)，气息感弱"

    # 能量预判
    if rms_mean > 0.08:
        energy_hint = "声音有力(>0.08)，适合高亢/霸气修饰"
    elif rms_mean > 0.03:
        energy_hint = "能量适中(0.03-0.08)"
    else:
        energy_hint = "声音轻柔(<0.03)，适合娇弱/安静修饰"

    # 修饰词建议（基于多特征组合）
    modifier_hints = []
    if pitch_stability > 0.90 and harmonic_ratio > 0.70:
        modifier_hints.append("字正腔圆")
    if pitch_stability > 0.85 and rms_mean > 0.05:
        modifier_hints.append("纯净高亢")
    if harmonic_ratio > 0.80 and centroid_mean < 2000:
        modifier_hints.append("酥酥麻麻")
    if centroid_mean < 2000 and rms_mean < 0.06:
        modifier_hints.append("小家碧玉")
    if harmonic_ratio < 0.55 and zcr_mean > 0.10:
        modifier_hints.append("平淡从容")
    if rms_mean > 0.08 and centroid_mean > 2200:
        modifier_hints.append("高亢")
    if centroid_mean > 3500 and zcr_mean > 0.15:
        modifier_hints.append("活泼可爱")
    if rms_mean < 0.04 and harmonic_ratio > 0.75:
        modifier_hints.append("安静舒心")

    modifier_hint = "、".join(modifier_hints) if modifier_hints else "需综合判断"

    # ==================== 汇总结果 ====================
    features = {
        "基本信息": {
            "音频时长_秒": round(duration, 2),
            "有效语音占比": round(voiced_ratio, 4),
            "采样率": sr
        },
        "基频F0_Hz": {
            "平均值": round(f0_mean, 2),
            "中位数": round(f0_median, 2),
            "标准差": round(f0_std, 2),
            "最小值": round(f0_min, 2),
            "最大值": round(f0_max, 2),
            "变化范围": round(f0_max - f0_min, 2),
            "变化系数": round(f0_std / f0_mean, 4) if f0_mean > 0 else 0,
            "音高稳定性": round(pitch_stability, 4)
        },
        "谐波比_清澈度": {
            "比值": round(harmonic_ratio, 4)
        },
        "频谱质心_声音亮度": {
            "平均值_Hz": round(centroid_mean, 2),
            "标准差": round(centroid_std, 2)
        },
        "过零率_气息感": {
            "平均值": round(zcr_mean, 6),
            "标准差": round(zcr_std, 6)
        },
        "RMS能量_音量强度": {
            "平均值": round(rms_mean, 6),
            "标准差": round(rms_std, 6),
            "动态范围": round(rms_dynamic_range, 6)
        },
        "频谱滚降点_高频成分": {
            "平均值_Hz": round(rolloff_mean, 2)
        },
        "频谱带宽": {
            "平均值_Hz": round(bandwidth_mean, 2)
        },
        "频谱平坦度_纯净度": {
            "平均值": round(flatness_mean, 6)
        },
        "共振峰估计_Hz": {
            "F1": round(f1, 2),
            "F2": round(f2, 2),
            "F3": round(f3, 2)
        },
        "MFCC_音色指纹": {
            "第2维均值_亮度相关": round(mfcc2_mean, 4),
            "13维均值": [round(x, 4) for x in mfcc_mean]
        },
        "频谱对比度_层次感": {
            "7频带均值": [round(x, 4) for x in contrast_mean]
        },
        "AI预判断": {
            "性别预判": gender_hint,
            "⭐音高稳定性预判": stability_hint,
            "⭐音色大类预判": voice_type_hint,
            "推荐修饰词": modifier_hint,
            "清澈度预判": clarity_hint,
            "亮度预判": brightness_hint,
            "气息感预判": breath_hint,
            "能量预判": energy_hint
        }
    }

    return convert_to_native_types(features)


class VoiceAnalysisService:
    """
    Voice Analysis Service Class
    """

    def analyze_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Analyze audio file and return features
        """
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        return extract_voice_features(audio_path)

    def get_voice_type_scores(self, features: Dict[str, Any], gender: str) -> Dict[str, float]:
        """
        Calculate voice type scores based on features

        This is a simplified scoring algorithm. In production,
        this should be replaced with FastGPT or a more sophisticated ML model.
        """
        f0_mean = features["基频F0_Hz"]["平均值"]
        pitch_stability = features["基频F0_Hz"]["音高稳定性"]
        harmonic_ratio = features["谐波比_清澈度"]["比值"]
        centroid_mean = features["频谱质心_声音亮度"]["平均值_Hz"]
        rms_mean = features["RMS能量_音量强度"]["平均值"]
        zcr_mean = features["过零率_气息感"]["平均值"]

        if gender == "female":
            # Female voice types
            scores = {
                "萝莉音": 0.0,
                "少女音": 0.0,
                "御姐音": 0.0,
                "女王音": 0.0,
                "软萌音": 0.0,
                "温柔音": 0.0,
                "中性音": 0.0,
                "甜美音": 0.0,
                "知性音": 0.0,
                "烟嗓音": 0.0
            }

            # Loli voice: high F0, low stability
            if f0_mean > 260:
                scores["萝莉音"] = min(40 + (f0_mean - 260) * 0.3, 60)
            if f0_mean > 230 and pitch_stability < 0.6:
                scores["萝莉音"] += 20

            # Young female: medium-high F0
            if 200 < f0_mean <= 260:
                scores["少女音"] = 30 + (260 - f0_mean) * 0.2

            # Mature female: high stability, medium F0
            if pitch_stability > 0.80 and 165 <= f0_mean <= 200:
                scores["御姐音"] = 40 + pitch_stability * 30

            # Queen: low F0, high energy
            if f0_mean < 170 and rms_mean > 0.05:
                scores["女王音"] = 30 + (170 - f0_mean) * 0.5

            # Soft cute: high harmonic, low energy
            if harmonic_ratio > 0.75 and rms_mean < 0.05:
                scores["软萌音"] = 35 + harmonic_ratio * 20

            # Gentle: low centroid, low energy
            if centroid_mean < 2500 and rms_mean < 0.05:
                scores["温柔音"] = 35 + (2500 - centroid_mean) * 0.01

            # Sweet: high harmonic, high centroid
            if harmonic_ratio > 0.70 and centroid_mean > 2500:
                scores["甜美音"] = 30 + harmonic_ratio * 25

            # Intellectual: high stability, medium-low F0
            if pitch_stability > 0.75 and f0_mean < 200:
                scores["知性音"] = 25 + pitch_stability * 20

            # Smoky: low harmonic
            if harmonic_ratio < 0.55:
                scores["烟嗓音"] = 30 + (0.55 - harmonic_ratio) * 100

            # Neutral
            scores["中性音"] = 15

        else:
            # Male voice types
            scores = {
                "正太音": 0.0,
                "少年音": 0.0,
                "青年音": 0.0,
                "大叔音": 0.0,
                "青攻音": 0.0,
                "青受音": 0.0,
                "奶狗音": 0.0,
                "狼狗音": 0.0,
                "播音音": 0.0,
                "烟嗓音": 0.0
            }

            if f0_mean > 180:
                scores["正太音"] = min(40 + (f0_mean - 180) * 0.5, 60)

            if 140 < f0_mean <= 180:
                scores["少年音"] = 35

            if 100 < f0_mean <= 140:
                scores["青年音"] = 35
                scores["青攻音"] = 30 if rms_mean > 0.05 else 0
                scores["青受音"] = 30 if rms_mean < 0.04 else 0

            if f0_mean <= 100:
                scores["大叔音"] = 40

            if pitch_stability > 0.85:
                scores["播音音"] = 35 + pitch_stability * 20

            if harmonic_ratio < 0.55:
                scores["烟嗓音"] = 30 + (0.55 - harmonic_ratio) * 100

            if harmonic_ratio > 0.75 and rms_mean < 0.04:
                scores["奶狗音"] = 35

            if harmonic_ratio < 0.65 and rms_mean > 0.06:
                scores["狼狗音"] = 35

        # Normalize scores to sum to 100
        total = sum(scores.values())
        if total > 0:
            scores = {k: round(v / total * 100, 1) for k, v in scores.items()}

        return scores


# Singleton instance
voice_analysis_service = VoiceAnalysisService()
