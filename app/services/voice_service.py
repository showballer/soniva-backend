"""
Voice Analysis Service
Based on voice_feature_extract.py
"""
import numpy as np
import librosa
from pathlib import Path
from typing import Dict, Any


def convert_to_native_types(obj):
    """
    Convert numpy types to Python native types for JSON serialization
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
    Extract voice features from audio file

    Args:
        audio_path: Audio file path (supports wav, mp3, m4a, etc.)

    Returns:
        Dictionary containing voice features
    """
    # Load audio, unified sample rate 22050Hz
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)

    # ==================== Voice Activity Detection VAD ====================
    intervals = librosa.effects.split(y, top_db=25)
    if len(intervals) > 0:
        y_voiced = np.concatenate([y[start:end] for start, end in intervals])
        voiced_ratio = len(y_voiced) / len(y)
    else:
        y_voiced = y
        voiced_ratio = 1.0

    # ==================== 1. Fundamental Frequency F0 ====================
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
        pitch_stability = 1 - (f0_std / f0_mean) if f0_mean > 0 else 0
    else:
        f0_mean = f0_std = f0_min = f0_max = f0_median = 0
        pitch_stability = 0

    # ==================== 2. MFCC ====================
    mfcc = librosa.feature.mfcc(y=y_voiced, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1).tolist()
    mfcc_std = np.std(mfcc, axis=1).tolist()
    mfcc2_mean = mfcc_mean[1] if len(mfcc_mean) > 1 else 0

    # ==================== 3. Spectral Centroid ====================
    spectral_centroid = librosa.feature.spectral_centroid(y=y_voiced, sr=sr)[0]
    centroid_mean = float(np.mean(spectral_centroid))
    centroid_std = float(np.std(spectral_centroid))

    # ==================== 4. Spectral Contrast ====================
    spectral_contrast = librosa.feature.spectral_contrast(y=y_voiced, sr=sr)
    contrast_mean = np.mean(spectral_contrast, axis=1).tolist()

    # ==================== 5. Zero Crossing Rate ====================
    zcr = librosa.feature.zero_crossing_rate(y_voiced)[0]
    zcr_mean = float(np.mean(zcr))
    zcr_std = float(np.std(zcr))

    # ==================== 6. RMS Energy ====================
    rms = librosa.feature.rms(y=y_voiced)[0]
    rms_mean = float(np.mean(rms))
    rms_std = float(np.std(rms))
    rms_dynamic_range = float(np.max(rms) - np.min(rms)) if len(rms) > 0 else 0

    # ==================== 7. Harmonic Ratio ====================
    harmonic, percussive = librosa.effects.hpss(y_voiced)
    harmonic_energy = np.sum(harmonic ** 2)
    total_energy = np.sum(y_voiced ** 2)
    harmonic_ratio = float(harmonic_energy / total_energy) if total_energy > 0 else 0

    # ==================== 8. Spectral Rolloff ====================
    rolloff = librosa.feature.spectral_rolloff(y=y_voiced, sr=sr, roll_percent=0.85)[0]
    rolloff_mean = float(np.mean(rolloff))

    # ==================== 9. Spectral Flatness ====================
    flatness = librosa.feature.spectral_flatness(y=y_voiced)[0]
    flatness_mean = float(np.mean(flatness))

    # ==================== 10. Spectral Bandwidth ====================
    bandwidth = librosa.feature.spectral_bandwidth(y=y_voiced, sr=sr)[0]
    bandwidth_mean = float(np.mean(bandwidth))

    # ==================== 11. Formant Estimation ====================
    try:
        frame_length = min(2048, len(y_voiced))
        if frame_length > 512:
            mid_point = len(y_voiced) // 2
            frame = y_voiced[mid_point:mid_point + frame_length]
            lpc_order = 12
            a = librosa.lpc(frame, order=lpc_order)
            roots = np.roots(a)
            roots = roots[np.imag(roots) >= 0]
            angles = np.arctan2(np.imag(roots), np.real(roots))
            formants = sorted(angles * (sr / (2 * np.pi)))
            formants = [f for f in formants if 200 < f < 5000]
            f1 = formants[0] if len(formants) > 0 else 0
            f2 = formants[1] if len(formants) > 1 else 0
            f3 = formants[2] if len(formants) > 2 else 0
        else:
            f1 = f2 = f3 = 0
    except Exception:
        f1 = f2 = f3 = 0

    # ==================== 12. Pre-judgment Logic ====================
    # Gender hint
    if f0_mean > 200:
        gender_hint = "female (high confidence)"
    elif f0_mean > 155:
        gender_hint = "female (likely)"
    elif f0_mean > 140:
        gender_hint = "uncertain, need timbre analysis"
    else:
        gender_hint = "male (likely)"

    # Pitch stability hint
    if pitch_stability > 0.85:
        stability_hint = "Very high stability (>0.85), strong control, tends to broadcast/mature female"
    elif pitch_stability > 0.70:
        stability_hint = "High stability (0.70-0.85), tends to warm mature/intellectual"
    elif pitch_stability > 0.50:
        stability_hint = "Normal stability (0.50-0.70), tends to young mature/young female"
    else:
        stability_hint = "Low stability (<0.50), emotional rich, tends to lively young/loli"

    # Voice type hint
    if pitch_stability > 0.85 and 165 <= f0_mean <= 200:
        voice_type_hint = "Mature female voice - high stability + F0 in mature range"
    elif pitch_stability > 0.85 and f0_mean > 200:
        voice_type_hint = "Stable young female voice - high stability but high F0"
    elif f0_mean > 260:
        voice_type_hint = "Loli/young loli voice - very high F0"
    elif f0_mean > 210:
        voice_type_hint = "Young female voice - F0 in young female range"
    elif pitch_stability > 0.70 and f0_mean < 190:
        voice_type_hint = "Warm mature voice - high stability + low F0"
    elif 165 <= f0_mean <= 210:
        voice_type_hint = "Young mature voice - F0 in young mature range, normal stability"
    elif f0_mean < 165:
        voice_type_hint = "Warm mature/queen voice - low F0"
    else:
        voice_type_hint = "Young mature voice - default"

    # Clarity hint
    if harmonic_ratio > 0.80:
        clarity_hint = "Very clear (>0.80), suitable for pure/sweet"
    elif harmonic_ratio > 0.65:
        clarity_hint = "Clear (0.65-0.80), neutral texture"
    elif harmonic_ratio > 0.50:
        clarity_hint = "Slightly husky (0.50-0.65), can consider lazy/magnetic"
    else:
        clarity_hint = "Obviously husky (<0.50), might be smoky or recording issue"

    # Brightness hint
    if centroid_mean > 3500:
        brightness_hint = "Bright voice (>3500Hz), suitable for clear/energetic"
    elif centroid_mean > 2000:
        brightness_hint = "Medium brightness (2000-3500Hz)"
    else:
        brightness_hint = "Dark warm voice (<2000Hz), suitable for gentle/hazy"

    # Breath hint
    if zcr_mean > 0.15:
        breath_hint = "Obvious breath (>0.15), suitable for ASMR/soft"
    elif zcr_mean > 0.08:
        breath_hint = "Light breath (0.08-0.15)"
    else:
        breath_hint = "Solid vocalization (<0.08), weak breath"

    # Energy hint
    if rms_mean > 0.08:
        energy_hint = "Powerful voice (>0.08), suitable for high/domineering"
    elif rms_mean > 0.03:
        energy_hint = "Medium energy (0.03-0.08)"
    else:
        energy_hint = "Soft voice (<0.03), suitable for delicate/quiet"

    # Modifier hints
    modifier_hints = []
    if pitch_stability > 0.90 and harmonic_ratio > 0.70:
        modifier_hints.append("Clear enunciation")
    if pitch_stability > 0.85 and rms_mean > 0.05:
        modifier_hints.append("Pure and high")
    if harmonic_ratio > 0.80 and centroid_mean < 2000:
        modifier_hints.append("Tingly")
    if centroid_mean < 2000 and rms_mean < 0.06:
        modifier_hints.append("Gentle and refined")
    if harmonic_ratio < 0.55 and zcr_mean > 0.10:
        modifier_hints.append("Calm and composed")
    if rms_mean > 0.08 and centroid_mean > 2200:
        modifier_hints.append("High-pitched")
    if centroid_mean > 3500 and zcr_mean > 0.15:
        modifier_hints.append("Lively and cute")
    if rms_mean < 0.04 and harmonic_ratio > 0.75:
        modifier_hints.append("Quiet and soothing")

    modifier_hint = ", ".join(modifier_hints) if modifier_hints else "Need comprehensive judgment"

    # ==================== Summary ====================
    features = {
        "basic_info": {
            "duration_seconds": round(duration, 2),
            "voiced_ratio": round(voiced_ratio, 4),
            "sample_rate": sr
        },
        "f0_hz": {
            "mean": round(f0_mean, 2),
            "median": round(f0_median, 2),
            "std": round(f0_std, 2),
            "min": round(f0_min, 2),
            "max": round(f0_max, 2),
            "range": round(f0_max - f0_min, 2),
            "variation_coefficient": round(f0_std / f0_mean, 4) if f0_mean > 0 else 0,
            "pitch_stability": round(pitch_stability, 4)
        },
        "harmonic_ratio": {
            "value": round(harmonic_ratio, 4)
        },
        "spectral_centroid": {
            "mean_hz": round(centroid_mean, 2),
            "std": round(centroid_std, 2)
        },
        "zero_crossing_rate": {
            "mean": round(zcr_mean, 6),
            "std": round(zcr_std, 6)
        },
        "rms_energy": {
            "mean": round(rms_mean, 6),
            "std": round(rms_std, 6),
            "dynamic_range": round(rms_dynamic_range, 6)
        },
        "spectral_rolloff": {
            "mean_hz": round(rolloff_mean, 2)
        },
        "spectral_bandwidth": {
            "mean_hz": round(bandwidth_mean, 2)
        },
        "spectral_flatness": {
            "mean": round(flatness_mean, 6)
        },
        "formants_hz": {
            "f1": round(f1, 2),
            "f2": round(f2, 2),
            "f3": round(f3, 2)
        },
        "mfcc": {
            "second_dim_mean": round(mfcc2_mean, 4),
            "all_dims_mean": [round(x, 4) for x in mfcc_mean]
        },
        "spectral_contrast": {
            "band_means": [round(x, 4) for x in contrast_mean]
        },
        "ai_hints": {
            "gender_hint": gender_hint,
            "stability_hint": stability_hint,
            "voice_type_hint": voice_type_hint,
            "modifier_hint": modifier_hint,
            "clarity_hint": clarity_hint,
            "brightness_hint": brightness_hint,
            "breath_hint": breath_hint,
            "energy_hint": energy_hint
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
        f0_mean = features["f0_hz"]["mean"]
        pitch_stability = features["f0_hz"]["pitch_stability"]
        harmonic_ratio = features["harmonic_ratio"]["value"]
        centroid_mean = features["spectral_centroid"]["mean_hz"]
        rms_mean = features["rms_energy"]["mean"]
        zcr_mean = features["zero_crossing_rate"]["mean"]

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
