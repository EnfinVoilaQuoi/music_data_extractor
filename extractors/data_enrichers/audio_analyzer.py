# extractors/data_enrichers/audio_analyzer.py
"""
Analyseur audio optimisé pour l'analyse des caractéristiques musicales.
Version optimisée avec cache intelligent, analyse avancée et détection de patterns.
"""

import logging
import os
from functools import lru_cache
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime
import warnings

# Imports conditionnels pour l'analyse audio
try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    warnings.warn("Librosa non disponible - analyses audio limitées")

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False

try:
    from scipy import signal, stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Imports absolus
from core.cache import CacheManager
from config.settings import settings
from models.enums import DataSource, AudioFeature
from utils.text_utils import normalize_text


class AudioAnalyzer:
    """
    Analyseur spécialisé pour les caractéristiques audio des morceaux.
    
    Fonctionnalités optimisées :
    - Extraction des features audio (BPM, key, energy, etc.)
    - Analyse spectrale et harmonique avancée
    - Détection de patterns rythmiques
    - Classification de style musical
    - Analyse de la structure du morceau
    - Cache intelligent pour éviter les recalculs
    - Support de multiples formats audio
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        if not LIBROSA_AVAILABLE:
            self.logger.warning("⚠️ Librosa non disponible - fonctionnalités d'analyse audio limitées")
        
        # Configuration optimisée
        self.config = {
            'sample_rate': settings.get('audio.sample_rate', 22050),
            'hop_length': settings.get('audio.hop_length', 512),
            'frame_length': settings.get('audio.frame_length', 2048),
            'max_duration': settings.get('audio.max_duration', 300),  # 5 minutes max
            'enable_harmonic_analysis': settings.get('audio.harmonic_analysis', True),
            'enable_rhythm_analysis': settings.get('audio.rhythm_analysis', True),
            'enable_spectral_analysis': settings.get('audio.spectral_analysis', True),
            'cache_audio_features': settings.get('audio.cache_features', True),
            'supported_formats': settings.get('audio.supported_formats', ['.mp3', '.wav', '.flac', '.m4a', '.ogg'])
        }
        
        # Cache manager
        self.cache_manager = CacheManager(namespace='audio_analysis') if CacheManager else None
        
        # Configuration d'analyse spécialisée pour le rap/hip-hop
        self.rap_analysis_config = self._load_rap_analysis_config()
        
        # Statistiques d'analyse
        self.stats = {
            'files_analyzed': 0,
            'features_extracted': 0,
            'analysis_time_total': 0.0,
            'cache_hits': 0,
            'failed_analyses': 0,
            'average_analysis_time': 0.0
        }
        
        self.logger.info("✅ AudioAnalyzer optimisé initialisé")
    
    @lru_cache(maxsize=1)
    def _load_rap_analysis_config(self) -> Dict[str, Any]:
        """Charge la configuration d'analyse spécialisée pour le rap avec cache"""
        return {
            'bpm_range': {
                'min': 60,
                'max': 200,
                'typical_range': (70, 150),
                'common_bpms': [70, 80, 90, 100, 110, 120, 130, 140]
            },
            'key_detection': {
                'profile': 'rap',  # Profil spécialisé pour le rap
                'confidence_threshold': 0.6,
                'minor_preference': 1.1  # Léger biais vers les tonalités mineures
            },
            'rhythm_patterns': {
                'detect_swing': False,  # Rarement utilisé en rap
                'emphasize_downbeats': True,
                'detect_syncopation': True,
                'trap_hi_hat_detection': True
            },
            'energy_analysis': {
                'frequency_bands': {
                    'sub_bass': (20, 60),
                    'bass': (60, 250),
                    'low_mid': (250, 500),
                    'mid': (500, 2000),
                    'high_mid': (2000, 4000),
                    'presence': (4000, 8000),
                    'brilliance': (8000, 20000)
                },
                'rap_focus_frequencies': (80, 250, 2000, 8000),  # Kick, sub, vocal presence, brilliance
                'dynamic_range_analysis': True
            },
            'vocal_analysis': {
                'vocal_frequency_range': (80, 8000),
                'detect_vocal_segments': True,
                'analyze_vocal_energy': True,
                'formant_analysis': False  # Trop complexe pour ce contexte
            }
        }
    
    # ===== MÉTHODES PRINCIPALES =====
    
    def analyze_audio(self, audio_source: Union[str, Dict[str, Any]], 
                     analysis_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Analyse un fichier audio et extrait les caractéristiques musicales.
        
        Args:
            audio_source: Chemin vers le fichier ou dictionnaire avec metadata
            analysis_types: Types d'analyses à effectuer (None = toutes)
            
        Returns:
            Dictionnaire avec toutes les caractéristiques extraites
        """
        import time
        start_time = time.time()
        
        if not LIBROSA_AVAILABLE:
            return self._empty_result("Librosa non disponible pour l'analyse audio")
        
        # Préparation de la source audio
        audio_path = self._prepare_audio_source(audio_source)
        if not audio_path:
            return self._empty_result("Source audio invalide")
        
        # Génération de la clé de cache
        cache_key = self._generate_cache_key(audio_path, analysis_types)
        
        # Vérifier le cache
        if self.cache_manager and self.config['cache_audio_features']:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # Chargement du fichier audio
            audio_data, sr = self._load_audio_file(audio_path)
            if audio_data is None:
                return self._empty_result("Impossible de charger le fichier audio")
            
            # Types d'analyses à effectuer
            if analysis_types is None:
                analysis_types = ['basic', 'rhythm', 'harmonic', 'spectral', 'energy']
            
            analysis_results = {}
            
            # 1. Analyse de base (BPM, durée, etc.)
            if 'basic' in analysis_types:
                analysis_results['basic'] = self._analyze_basic_features(audio_data, sr)
            
            # 2. Analyse rythmique (BPM précis, patterns)
            if 'rhythm' in analysis_types and self.config['enable_rhythm_analysis']:
                analysis_results['rhythm'] = self._analyze_rhythm_features(audio_data, sr)
            
            # 3. Analyse harmonique (tonalité, accords)
            if 'harmonic' in analysis_types and self.config['enable_harmonic_analysis']:
                analysis_results['harmonic'] = self._analyze_harmonic_features(audio_data, sr)
            
            # 4. Analyse spectrale (timbres, textures)
            if 'spectral' in analysis_types and self.config['enable_spectral_analysis']:
                analysis_results['spectral'] = self._analyze_spectral_features(audio_data, sr)
            
            # 5. Analyse énergétique (dynamics, intensité)
            if 'energy' in analysis_types:
                analysis_results['energy'] = self._analyze_energy_features(audio_data, sr)
            
            # 6. Analyse spécialisée rap/hip-hop
            if 'rap_specific' in analysis_types:
                analysis_results['rap_specific'] = self._analyze_rap_features(audio_data, sr)
            
            # Compilation des résultats
            result = {
                'success': True,
                'audio_file': audio_path,
                'analysis_results': analysis_results,
                'summary_features': self._compile_summary_features(analysis_results),
                'quality_assessment': self._assess_analysis_quality(analysis_results),
                'processing_metadata': {
                    'analyzed_at': datetime.now().isoformat(),
                    'analyzer_version': '1.0.0',
                    'processing_time': time.time() - start_time,
                    'sample_rate': sr,
                    'duration_seconds': len(audio_data) / sr,
                    'analysis_types': analysis_types
                }
            }
            
            # Mise en cache
            if self.cache_manager and self.config['cache_audio_features']:
                self.cache_manager.set(cache_key, result, ttl=7200)  # Cache 2h
            
            self.stats['files_analyzed'] += 1
            self.stats['features_extracted'] += len(analysis_results)
            analysis_time = time.time() - start_time
            self.stats['analysis_time_total'] += analysis_time
            self.stats['average_analysis_time'] = self.stats['analysis_time_total'] / self.stats['files_analyzed']
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erreur analyse audio: {e}")
            self.stats['failed_analyses'] += 1
            return self._empty_result(f"Erreur d'analyse: {str(e)}")
    
    def _prepare_audio_source(self, audio_source: Union[str, Dict[str, Any]]) -> Optional[str]:
        """Prépare la source audio pour l'analyse"""
        try:
            if isinstance(audio_source, str):
                # Chemin direct vers le fichier
                if os.path.exists(audio_source):
                    return audio_source
            
            elif isinstance(audio_source, dict):
                # Dictionnaire avec métadonnées
                file_path = audio_source.get('file_path') or audio_source.get('audio_file')
                if file_path and os.path.exists(file_path):
                    return file_path
                
                # URL de preview (pour tests)
                preview_url = audio_source.get('preview_url')
                if preview_url:
                    self.logger.warning("URLs de preview non supportées actuellement")
            
        except Exception as e:
            self.logger.debug(f"Erreur préparation source audio: {e}")
        
        return None
    
    def _load_audio_file(self, file_path: str) -> Tuple[Optional[np.ndarray], Optional[int]]:
        """Charge un fichier audio avec librosa"""
        try:
            # Vérifier l'extension
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext not in self.config['supported_formats']:
                self.logger.warning(f"Format {file_ext} potentiellement non supporté")
            
            # Charger avec librosa
            audio_data, sample_rate = librosa.load(
                file_path,
                sr=self.config['sample_rate'],
                duration=self.config['max_duration']
            )
            
            if len(audio_data) == 0:
                return None, None
            
            return audio_data, sample_rate
            
        except Exception as e:
            self.logger.error(f"❌ Erreur chargement audio {file_path}: {e}")
            return None, None
    
    def _analyze_basic_features(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse les caractéristiques de base"""
        features = {}
        
        try:
            # Durée
            duration_seconds = len(audio_data) / sr
            features['duration_seconds'] = duration_seconds
            features['duration_ms'] = int(duration_seconds * 1000)
            
            # RMS Energy (volume moyen)
            rms = librosa.feature.rms(y=audio_data)[0]
            features['rms_energy'] = float(np.mean(rms))
            features['rms_std'] = float(np.std(rms))
            
            # Zero Crossing Rate (indicateur de percussions)
            zcr = librosa.feature.zero_crossing_rate(audio_data)[0]
            features['zero_crossing_rate'] = float(np.mean(zcr))
            
            # Centroide spectral (brillance)
            spectral_centroids = librosa.feature.spectral_centroid(y=audio_data, sr=sr)[0]
            features['spectral_centroid'] = float(np.mean(spectral_centroids))
            
            # Rolloff spectral
            spectral_rolloff = librosa.feature.spectral_rolloff(y=audio_data, sr=sr)[0]
            features['spectral_rolloff'] = float(np.mean(spectral_rolloff))
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse features de base: {e}")
        
        return features
    
    def _analyze_rhythm_features(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse les caractéristiques rythmiques"""
        features = {}
        
        try:
            # Détection du tempo (BPM)
            tempo, beats = librosa.beat.beat_track(
                y=audio_data, 
                sr=sr, 
                hop_length=self.config['hop_length']
            )
            
            features['bpm'] = float(tempo)
            features['beats_count'] = len(beats)
            features['beats_per_second'] = len(beats) / (len(audio_data) / sr)
            
            # Validation BPM pour le rap
            bpm_range = self.rap_analysis_config['bpm_range']
            if bpm_range['min'] <= tempo <= bpm_range['max']:
                features['bpm_valid_for_rap'] = True
                features['bpm_confidence'] = 'high'
            else:
                features['bpm_valid_for_rap'] = False
                features['bmp_confidence'] = 'low'
                
                # Tenter de corriger (double/moitié)
                if tempo < bpm_range['min']:
                    corrected_bmp = tempo * 2
                    if bpm_range['min'] <= corrected_bmp <= bpm_range['max']:
                        features['bmp_corrected'] = corrected_bmp
                elif tempo > bpm_range['max']:
                    corrected_bmp = tempo / 2
                    if bpm_range['min'] <= corrected_bmp <= bpm_range['max']:
                        features['bmp_corrected'] = corrected_bmp
            
            # Analyse de la régularité rythmique
            if len(beats) > 1:
                beat_intervals = np.diff(beats)
                features['rhythm_regularity'] = float(1.0 - np.std(beat_intervals) / np.mean(beat_intervals))
            
            # Détection de patterns trap (hi-hats rapides)
            if self.rap_analysis_config['rhythm_patterns']['trap_hi_hat_detection']:
                features['trap_pattern_detected'] = self._detect_trap_patterns(audio_data, sr, beats)
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse rythmique: {e}")
        
        return features
    
    def _analyze_harmonic_features(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse les caractéristiques harmoniques"""
        features = {}
        
        try:
            # Séparation harmonique/percussive
            y_harmonic, y_percussive = librosa.effects.hpss(audio_data)
            
            # Ratio harmonique/percussif
            harmonic_energy = np.sum(y_harmonic ** 2)
            percussive_energy = np.sum(y_percussive ** 2)
            
            if percussive_energy > 0:
                features['harmonic_percussive_ratio'] = float(harmonic_energy / percussive_energy)
            
            # Détection de tonalité avec chromagram
            chroma = librosa.feature.chroma_stft(y=y_harmonic, sr=sr)
            
            # Profil de tonalité moyen
            chroma_mean = np.mean(chroma, axis=1)
            
            # Détection de la tonalité principale
            key_profiles = self._get_key_profiles()
            key_correlations = {}
            
            for key_name, profile in key_profiles.items():
                correlation = np.corrcoef(chroma_mean, profile)[0, 1]
                if not np.isnan(correlation):
                    key_correlations[key_name] = correlation
            
            if key_correlations:
                detected_key = max(key_correlations.items(), key=lambda x: x[1])
                features['detected_key'] = detected_key[0]
                features['key_confidence'] = float(detected_key[1])
                
                # Validation pour le rap (préférence mineure)
                if 'minor' in detected_key[0].lower():
                    features['key_confidence'] *= self.rap_analysis_config['key_detection']['minor_preference']
            
            # Analyse de la complexité harmonique
            features['harmonic_complexity'] = float(np.std(chroma_mean))
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse harmonique: {e}")
        
        return features
    
    def _analyze_spectral_features(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse les caractéristiques spectrales"""
        features = {}
        
        try:
            # MFCC (Mel-frequency cepstral coefficients)
            mfccs = librosa.feature.mfcc(y=audio_data, sr=sr, n_mfcc=13)
            features['mfcc_mean'] = np.mean(mfccs, axis=1).tolist()
            features['mfcc_std'] = np.std(mfccs, axis=1).tolist()
            
            # Spectral features
            spectral_features = {
                'centroid': librosa.feature.spectral_centroid(y=audio_data, sr=sr)[0],
                'bandwidth': librosa.feature.spectral_bandwidth(y=audio_data, sr=sr)[0],
                'rolloff': librosa.feature.spectral_rolloff(y=audio_data, sr=sr)[0],
                'flatness': librosa.feature.spectral_flatness(y=audio_data)[0]
            }
            
            for feature_name, feature_values in spectral_features.items():
                features[f'spectral_{feature_name}_mean'] = float(np.mean(feature_values))
                features[f'spectral_{feature_name}_std'] = float(np.std(feature_values))
            
            # Contrast spectral (utile pour la musique avec voix)
            contrast = librosa.feature.spectral_contrast(y=audio_data, sr=sr)
            features['spectral_contrast_mean'] = np.mean(contrast, axis=1).tolist()
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse spectrale: {e}")
        
        return features
    
    def _analyze_energy_features(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse les caractéristiques énergétiques"""
        features = {}
        
        try:
            # Analyse par bandes de fréquences spécialisées rap
            frequency_bands = self.rap_analysis_config['energy_analysis']['frequency_bands']
            
            # Calcul du spectrogramme
            stft = librosa.stft(audio_data, hop_length=self.config['hop_length'])
            magnitude = np.abs(stft)
            
            # Fréquences correspondantes
            freqs = librosa.fft_frequencies(sr=sr, n_fft=self.config['frame_length'])
            
            band_energies = {}
            for band_name, (low_freq, high_freq) in frequency_bands.items():
                # Trouver les indices correspondants
                band_indices = np.where((freqs >= low_freq) & (freqs <= high_freq))[0]
                
                if len(band_indices) > 0:
                    band_energy = np.mean(magnitude[band_indices, :])
                    band_energies[f'{band_name}_energy'] = float(band_energy)
            
            features.update(band_energies)
            
            # Focus sur les fréquences importantes pour le rap
            rap_focus_freqs = self.rap_analysis_config['energy_analysis']['rap_focus_frequencies']
            
            total_rap_energy = 0
            for freq in rap_focus_freqs:
                freq_index = np.argmin(np.abs(freqs - freq))
                total_rap_energy += np.mean(magnitude[freq_index, :])
            
            features['rap_focus_energy'] = float(total_rap_energy / len(rap_focus_freqs))
            
            # Dynamic range
            if self.rap_analysis_config['energy_analysis']['dynamic_range_analysis']:
                rms = librosa.feature.rms(y=audio_data)[0]
                dynamic_range = float(np.max(rms) - np.min(rms))
                features['dynamic_range'] = dynamic_range
                
                # Compression ratio (approximation)
                if dynamic_range > 0:
                    features['compression_ratio'] = float(np.std(rms) / dynamic_range)
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse énergétique: {e}")
        
        return features
    
    def _analyze_rap_features(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse spécialisée pour les caractéristiques rap/hip-hop"""
        features = {}
        
        try:
            # Détection de la structure vocale
            if self.rap_analysis_config['vocal_analysis']['detect_vocal_segments']:
                vocal_segments = self._detect_vocal_segments(audio_data, sr)
                features['vocal_segments'] = vocal_segments
                
                if vocal_segments:
                    total_vocal_time = sum(seg['duration'] for seg in vocal_segments)
                    total_duration = len(audio_data) / sr
                    features['vocal_density'] = total_vocal_time / total_duration
            
            # Analyse du flow (variations rythmiques)
            features['flow_analysis'] = self._analyze_rap_flow(audio_data, sr)
            
            # Détection de samples (patterns répétitifs)
            features['sample_detection'] = self._detect_samples(audio_data, sr)
            
            # Classification de sous-genre rap
            features['rap_subgenre_hints'] = self._classify_rap_subgenre(audio_data, sr)
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse rap spécialisée: {e}")
        
        return features
    
    # ===== MÉTHODES UTILITAIRES SPÉCIALISÉES =====
    
    def _detect_trap_patterns(self, audio_data: np.ndarray, sr: int, beats: np.ndarray) -> bool:
        """Détecte les patterns caractéristiques de la trap"""
        try:
            # Analyser les hautes fréquences pour détecter les hi-hats rapides
            high_freq_cutoff = 8000
            high_freq_audio = librosa.effects.preemphasis(audio_data)
            
            # Onset detection sur les hautes fréquences
            onsets = librosa.onset.onset_detect(
                y=high_freq_audio, 
                sr=sr, 
                units='time',
                hop_length=self.config['hop_length'] // 2  # Plus de résolution
            )
            
            # Calculer la densité d'onsets
            if len(onsets) > 0 and len(audio_data) > 0:
                onset_density = len(onsets) / (len(audio_data) / sr)
                
                # Pattern trap typique: beaucoup d'onsets sur les hautes fréquences
                return onset_density > 8  # Plus de 8 onsets/seconde
            
        except Exception as e:
            self.logger.debug(f"Erreur détection trap: {e}")
        
        return False
    
    @lru_cache(maxsize=1)
    def _get_key_profiles(self) -> Dict[str, np.ndarray]:
        """Retourne les profils de tonalité avec cache"""
        # Profils simplifiés de Krumhansl-Schmuckler
        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        
        keys = {}
        key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        for i, key_name in enumerate(key_names):
            # Rotation du profil pour chaque tonalité
            keys[f'{key_name}_major'] = np.roll(major_profile, i)
            keys[f'{key_name}_minor'] = np.roll(minor_profile, i)
        
        return keys
    
    def _detect_vocal_segments(self, audio_data: np.ndarray, sr: int) -> List[Dict[str, Any]]:
        """Détecte les segments vocaux dans l'audio"""
        segments = []
        
        try:
            # Séparation harmonique/percussive pour isoler les voix
            y_harmonic, _ = librosa.effects.hpss(audio_data)
            
            # Centroide spectral pour détecter les caractéristiques vocales
            spectral_centroids = librosa.feature.spectral_centroid(y=y_harmonic, sr=sr)[0]
            
            # Seuillage adaptatif pour détecter les segments vocaux
            centroid_threshold = np.mean(spectral_centroids) + 0.5 * np.std(spectral_centroids)
            vocal_frames = spectral_centroids > centroid_threshold
            
            # Convertir en segments temporels
            frame_times = librosa.frames_to_time(
                np.arange(len(vocal_frames)), 
                sr=sr, 
                hop_length=self.config['hop_length']
            )
            
            # Grouper les frames consécutifs
            in_vocal_segment = False
            segment_start = 0
            
            for i, is_vocal in enumerate(vocal_frames):
                if is_vocal and not in_vocal_segment:
                    # Début de segment vocal
                    segment_start = frame_times[i]
                    in_vocal_segment = True
                elif not is_vocal and in_vocal_segment:
                    # Fin de segment vocal
                    segment_end = frame_times[i]
                    duration = segment_end - segment_start
                    
                    if duration > 0.5:  # Segments d'au moins 0.5 seconde
                        segments.append({
                            'start_time': segment_start,
                            'end_time': segment_end,
                            'duration': duration
                        })
                    
                    in_vocal_segment = False
            
        except Exception as e:
            self.logger.debug(f"Erreur détection segments vocaux: {e}")
        
        return segments
    
    def _analyze_rap_flow(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Analyse le flow du rap (variations rythmiques)"""
        flow_analysis = {}
        
        try:
            # Onset detection pour analyser les attaques
            onsets = librosa.onset.onset_detect(
                y=audio_data, 
                sr=sr, 
                units='time',
                hop_length=self.config['hop_length']
            )
            
            if len(onsets) > 1:
                # Analyse des intervalles entre onsets
                onset_intervals = np.diff(onsets)
                
                flow_analysis.update({
                    'onset_density': len(onsets) / (len(audio_data) / sr),
                    'flow_regularity': float(1.0 - np.std(onset_intervals) / np.mean(onset_intervals)),
                    'flow_complexity': float(np.std(onset_intervals)),
                    'average_onset_interval': float(np.mean(onset_intervals))
                })
                
                # Classification du style de flow
                if np.std(onset_intervals) < 0.1:
                    flow_analysis['flow_style'] = 'regular'
                elif np.std(onset_intervals) > 0.3:
                    flow_analysis['flow_style'] = 'complex'
                else:
                    flow_analysis['flow_style'] = 'moderate'
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse flow: {e}")
        
        return flow_analysis
    
    def _detect_samples(self, audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
        """Détecte la présence de samples (patterns répétitifs)"""
        sample_detection = {}
        
        try:
            # Analyse de la self-similarity matrix pour détecter les répétitions
            chroma = librosa.feature.chroma_stft(y=audio_data, sr=sr)
            
            # Matrice de similarité
            similarity_matrix = np.dot(chroma.T, chroma)
            
            # Normalisation
            similarity_matrix = similarity_matrix / np.max(similarity_matrix)
            
            # Détection de patterns répétitifs
            # Chercher des diagonales dans la matrice de similarité
            high_similarity_threshold = 0.8
            repetitive_segments = np.where(similarity_matrix > high_similarity_threshold)
            
            if len(repetitive_segments[0]) > 0:
                sample_detection['repetitive_patterns_detected'] = True
                sample_detection['repetition_density'] = len(repetitive_segments[0]) / similarity_matrix.size
            else:
                sample_detection['repetitive_patterns_detected'] = False
                sample_detection['repetition_density'] = 0.0
            
        except Exception as e:
            self.logger.debug(f"Erreur détection samples: {e}")
        
        return sample_detection
    
    def _classify_rap_subgenre(self, audio_data: np.ndarray, sr: int) -> Dict[str, float]:
        """Classifie le sous-genre de rap basé sur les caractéristiques audio"""
        subgenre_scores = {}
        
        try:
            # Caractéristiques pour différents sous-genres
            
            # 1. Trap - BPM modéré, beaucoup de hi-hats, sub-bass prononcé
            trap_score = 0.0
            
            # BPM dans la plage trap (130-150)
            tempo, _ = librosa.beat.beat_track(y=audio_data, sr=sr)
            if 130 <= tempo <= 150:
                trap_score += 0.3
            
            # Détection de patterns trap
            if self._detect_trap_patterns(audio_data, sr, np.array([])):
                trap_score += 0.4
            
            # Sub-bass fort
            stft = librosa.stft(audio_data)
            magnitude = np.abs(stft)
            freqs = librosa.fft_frequencies(sr=sr, n_fft=self.config['frame_length'])
            sub_bass_indices = np.where((freqs >= 20) & (freqs <= 60))[0]
            
            if len(sub_bass_indices) > 0:
                sub_bass_energy = np.mean(magnitude[sub_bass_indices, :])
                total_energy = np.mean(magnitude)
                if sub_bass_energy / total_energy > 0.15:
                    trap_score += 0.3
            
            subgenre_scores['trap'] = min(trap_score, 1.0)
            
            # 2. Boom Bap - BPM plus lent, kick et snare marqués
            boom_bap_score = 0.0
            
            if 85 <= tempo <= 105:
                boom_bap_score += 0.4
            
            # Analyse du ratio harmonique/percussif
            y_harmonic, y_percussive = librosa.effects.hpss(audio_data)
            perc_energy = np.sum(y_percussive ** 2)
            harm_energy = np.sum(y_harmonic ** 2)
            
            if perc_energy > harm_energy * 0.8:  # Beaucoup de percussions
                boom_bap_score += 0.3
            
            subgenre_scores['boom_bap'] = min(boom_bap_score, 1.0)
            
            # 3. Drill - Tempo rapide, patterns agressifs
            drill_score = 0.0
            
            if 140 <= tempo <= 180:
                drill_score += 0.4
            
            # Énergie élevée dans les mid-frequencies
            mid_freq_indices = np.where((freqs >= 500) & (freqs <= 2000))[0]
            if len(mid_freq_indices) > 0:
                mid_energy = np.mean(magnitude[mid_freq_indices, :])
                if mid_energy / total_energy > 0.25:
                    drill_score += 0.3
            
            subgenre_scores['drill'] = min(drill_score, 1.0)
            
        except Exception as e:
            self.logger.debug(f"Erreur classification sous-genre: {e}")
        
        return subgenre_scores
    
    def _compile_summary_features(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Compile les features principales en résumé"""
        summary = {}
        
        try:
            # Extraire les features clés de chaque analyse
            if 'basic' in analysis_results:
                basic = analysis_results['basic']
                summary.update({
                    'duration_seconds': basic.get('duration_seconds'),
                    'energy_level': basic.get('rms_energy'),
                    'brightness': basic.get('spectral_centroid')
                })
            
            if 'rhythm' in analysis_results:
                rhythm = analysis_results['rhythm']
                summary.update({
                    'bpm': rhythm.get('bpm'),
                    'rhythm_regularity': rhythm.get('rhythm_regularity'),
                    'trap_detected': rhythm.get('trap_pattern_detected')
                })
            
            if 'harmonic' in analysis_results:
                harmonic = analysis_results['harmonic']
                summary.update({
                    'detected_key': harmonic.get('detected_key'),
                    'key_confidence': harmonic.get('key_confidence'),
                    'harmonic_complexity': harmonic.get('harmonic_complexity')
                })
            
            if 'energy' in analysis_results:
                energy = analysis_results['energy']
                summary.update({
                    'bass_energy': energy.get('bass_energy'),
                    'vocal_energy': energy.get('mid_energy'),
                    'dynamic_range': energy.get('dynamic_range')
                })
            
            if 'rap_specific' in analysis_results:
                rap = analysis_results['rap_specific']
                summary.update({
                    'vocal_density': rap.get('vocal_density'),
                    'flow_style': rap.get('flow_analysis', {}).get('flow_style'),
                    'subgenre_hints': rap.get('rap_subgenre_hints')
                })
        
        except Exception as e:
            self.logger.debug(f"Erreur compilation résumé: {e}")
        
        return summary
    
    def _assess_analysis_quality(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Évalue la qualité de l'analyse effectuée"""
        quality_assessment = {
            'overall_quality': 0.0,
            'completeness': 0.0,
            'confidence': 0.0,
            'issues': []
        }
        
        try:
            total_analyses = len(analysis_results)
            successful_analyses = 0
            confidence_scores = []
            
            for analysis_type, results in analysis_results.items():
                if results and isinstance(results, dict):
                    successful_analyses += 1
                    
                    # Évaluer la confiance basée sur les résultats
                    if analysis_type == 'rhythm':
                        bpm_confidence = results.get('bpm_confidence', 'medium')
                        if bpm_confidence == 'high':
                            confidence_scores.append(0.9)
                        elif bpm_confidence == 'medium':
                            confidence_scores.append(0.7)
                        else:
                            confidence_scores.append(0.5)
                    
                    elif analysis_type == 'harmonic':
                        key_conf = results.get('key_confidence', 0.5)
                        confidence_scores.append(key_conf)
                    
                    else:
                        confidence_scores.append(0.8)  # Confiance par défaut
            
            # Calcul des métriques
            quality_assessment['completeness'] = successful_analyses / total_analyses if total_analyses > 0 else 0
            quality_assessment['confidence'] = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
            quality_assessment['overall_quality'] = (quality_assessment['completeness'] + quality_assessment['confidence']) / 2
            
            # Identification des problèmes
            if quality_assessment['completeness'] < 0.8:
                quality_assessment['issues'].append('Analyse incomplète - certains modules ont échoué')
            
            if quality_assessment['confidence'] < 0.6:
                quality_assessment['issues'].append('Confiance faible dans les résultats')
            
            # Vérifications spécifiques
            if 'rhythm' in analysis_results:
                bpm = analysis_results['rhythm'].get('bpm')
                if bpm and (bpm < 60 or bpm > 200):
                    quality_assessment['issues'].append(f'BPM détecté suspect: {bpm}')
        
        except Exception as e:
            self.logger.debug(f"Erreur évaluation qualité: {e}")
            quality_assessment['issues'].append(f'Erreur évaluation: {str(e)}')
        
        return quality_assessment
    
    # ===== MÉTHODES BATCH ET UTILITAIRES =====
    
    def batch_analyze_audio_files(self, file_paths: List[str], 
                                 analysis_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Analyse plusieurs fichiers audio en lot.
        
        Args:
            file_paths: Liste des chemins vers les fichiers
            analysis_types: Types d'analyses à effectuer
            
        Returns:
            Liste des résultats d'analyse
        """
        results = []
        
        self.logger.info(f"🎵 Analyse en lot de {len(file_paths)} fichiers audio")
        
        for i, file_path in enumerate(file_paths):
            try:
                self.logger.info(f"📁 Analyse {i+1}/{len(file_paths)}: {os.path.basename(file_path)}")
                
                result = self.analyze_audio(file_path, analysis_types)
                result['batch_info'] = {
                    'batch_index': i,
                    'batch_size': len(file_paths),
                    'file_name': os.path.basename(file_path)
                }
                
                results.append(result)
                
            except Exception as e:
                self.logger.error(f"❌ Erreur analyse {file_path}: {e}")
                results.append({
                    'success': False,
                    'error': str(e),
                    'audio_file': file_path,
                    'batch_info': {
                        'batch_index': i,
                        'batch_size': len(file_paths),
                        'file_name': os.path.basename(file_path)
                    }
                })
        
        # Statistiques du lot
        successful_analyses = [r for r in results if r.get('success', False)]
        
        self.logger.info(f"🏁 Analyse en lot terminée: {len(successful_analyses)}/{len(file_paths)} succès")
        
        return results
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def _generate_cache_key(self, audio_path: str, analysis_types: Optional[List[str]] = None) -> str:
        """Génère une clé de cache pour l'analyse audio"""
        import hashlib
        
        # Utiliser le chemin du fichier et sa taille/date de modification
        try:
            stat = os.stat(audio_path)
            file_signature = f"{audio_path}_{stat.st_size}_{stat.st_mtime}"
        except OSError:
            file_signature = audio_path
        
        if analysis_types:
            file_signature += "_" + "_".join(sorted(analysis_types))
        
        return hashlib.md5(file_signature.encode()).hexdigest()[:16]
    
    def _empty_result(self, error_message: str) -> Dict[str, Any]:
        """Retourne un résultat vide avec message d'erreur"""
        return {
            'success': False,
            'error': error_message,
            'audio_file': None,
            'analysis_results': {},
            'summary_features': {},
            'quality_assessment': {
                'overall_quality': 0.0,
                'completeness': 0.0,
                'confidence': 0.0,
                'issues': [error_message]
            },
            'processing_metadata': {
                'analyzed_at': datetime.now().isoformat(),
                'analyzer_version': '1.0.0'
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'analyse"""
        return self.stats.copy()
    
    def clear_cache(self) -> bool:
        """Vide le cache de l'analyseur"""
        if self.cache_manager:
            return self.cache_manager.clear()
        return True
    
    def get_supported_formats(self) -> List[str]:
        """Retourne la liste des formats audio supportés"""
        return self.config['supported_formats'].copy()
    
    def health_check(self) -> Dict[str, Any]:
        """Vérifie l'état de santé de l'analyseur"""
        health = {
            'status': 'healthy',
            'issues': [],
            'dependencies': {
                'librosa': LIBROSA_AVAILABLE,
                'soundfile': SOUNDFILE_AVAILABLE,
                'scipy': SCIPY_AVAILABLE
            },
            'capabilities': []
        }
        
        if not LIBROSA_AVAILABLE:
            health['status'] = 'degraded'
            health['issues'].append('Librosa manquant - analyses audio impossibles')
        else:
            health['capabilities'].extend(['basic_analysis', 'rhythm_analysis', 'spectral_analysis'])
        
        if not SOUNDFILE_AVAILABLE:
            health['issues'].append('SoundFile manquant - support de formats limité')
        
        if not SCIPY_AVAILABLE:
            health['issues'].append('SciPy manquant - analyses avancées limitées')
        else:
            health['capabilities'].append('advanced_signal_processing')
        
        # Test rapide si possible
        if LIBROSA_AVAILABLE:
            try:
                # Test de génération d'un signal simple
                test_signal = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 22050))
                tempo, _ = librosa.beat.beat_track(y=test_signal, sr=22050)
                if tempo > 0:
                    health['capabilities'].append('tempo_detection')
            except Exception as e:
                health['issues'].append(f'Test librosa échoué: {str(e)}')
        
        return health
    
    def get_analysis_capabilities(self) -> Dict[str, Any]:
        """Retourne les capacités d'analyse disponibles"""
        capabilities = {
            'available_analyses': [],
            'supported_features': [],
            'rap_specialized_features': [],
            'dependencies_status': {
                'librosa': LIBROSA_AVAILABLE,
                'soundfile': SOUNDFILE_AVAILABLE,
                'scipy': SCIPY_AVAILABLE
            }
        }
        
        if LIBROSA_AVAILABLE:
            capabilities['available_analyses'].extend([
                'basic_features', 'rhythm_analysis', 'harmonic_analysis',
                'spectral_analysis', 'energy_analysis', 'rap_specific_analysis'
            ])
            
            capabilities['supported_features'].extend([
                'bpm', 'key_detection', 'spectral_centroid', 'mfcc',
                'rms_energy', 'zero_crossing_rate', 'spectral_rolloff'
            ])
            
            capabilities['rap_specialized_features'].extend([
                'trap_pattern_detection', 'flow_analysis', 'vocal_segment_detection',
                'subgenre_classification', 'sample_detection'
            ])
        
        return capabilities