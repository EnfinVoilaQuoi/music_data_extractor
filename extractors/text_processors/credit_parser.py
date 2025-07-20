# extractors/text_processors/credit_parser.py
"""
Parseur optimisé pour l'analyse et la normalisation des crédits musicaux.
Version optimisée avec patterns avancés, cache intelligent et détection de rôles.
"""

import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
from collections import defaultdict

# Imports absolus
from core.cache import CacheManager
from config.settings import settings
from utils.text_utils import normalize_text, clean_artist_name, calculate_similarity
from models.enums import DataSource, CreditType, CreditCategory

class CreditParser:
    """
    Parseur spécialisé pour l'analyse des crédits musicaux.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config = {
            'normalize_roles': settings.get('credits.normalize_roles', True),
            'detect_collaborations': settings.get('credits.detect_collaborations', True),
            'merge_similar_credits': settings.get('credits.merge_similar_credits', True),
            'extract_instruments': settings.get('credits.extract_instruments', True),
            'confidence_threshold': settings.get('credits.confidence_threshold', 0.7),
            'max_credits_per_role': settings.get('credits.max_credits_per_role', 50),
            'enable_fuzzy_matching': settings.get('credits.fuzzy_matching', True)
        }
        self.cache_manager = CacheManager(namespace='credits') if CacheManager else None
        self.patterns = self._compile_patterns()
        self.role_mappings = self._load_role_mappings()
        self.instrument_keywords = self._load_instrument_keywords()
        self.stats = {
            'credits_parsed': 0,
            'roles_normalized': 0,
            'collaborations_detected': 0,
            'duplicates_merged': 0,
            'cache_hits': 0,
            'total_processing_time': 0.0
        }
        self.logger.info("✅ CreditParser optimisé initialisé")

    @lru_cache(maxsize=1)
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile les patterns regex avec cache"""
        return {
            'credit_separators': re.compile(r'[,;|&\n]\s*', re.IGNORECASE),
            'role_separators': re.compile(r'[:]\s*', re.IGNORECASE),
            'name_separators': re.compile(r'\s*[,&]\s*|\s+and\s+|\s+et\s+', re.IGNORECASE),
            'producer_patterns': re.compile(r'\b(produc\w*|beat\w*|instrumental)\b', re.IGNORECASE),
            'writer_patterns': re.compile(r'\b(writ\w*|compos\w*|lyric\w*|author\w*)\b', re.IGNORECASE),
            'performer_patterns': re.compile(r'\b(vocal\w*|rap\w*|sing\w*|perform\w*)\b', re.IGNORECASE),
            'engineer_patterns': re.compile(r'\b(mix\w*|master\w*|engineer\w*|record\w*)\b', re.IGNORECASE),
            'instrument_patterns': re.compile(r'\b(guitar\w*|bass\w*|drum\w*|piano\w*|keyboard\w*|synth\w*)\b', re.IGNORECASE),
            'featuring_patterns': re.compile(r'\b(feat\w*|featuring)\b', re.IGNORECASE),
            'parentheses_content': re.compile(r'\([^)]*\)'),
            'bracket_content': re.compile(r'\[[^\]]*\]'),
            'extra_whitespace': re.compile(r'\s+'),
            'by_prefix': re.compile(r'^(by|par)\s+', re.IGNORECASE),
            'name_patterns': re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'),
            'stage_name_patterns': re.compile(r'\b[A-Z][a-z]*(?:[A-Z][a-z]*)*\b'),
            # Correction ici : il manquait un guillemet fermant à la regex ci-dessous
            'valid_name': re.compile(r'^[A-Za-z][A-Za-z\s\-\'\.]{1,50}$'),
            'valid_role': re.compile(r'^[A-Za-z][A-Za-z\s\-]{1,30}$'),
            'french_features': re.compile(r'\b(feat\.?\s*|avec\s+|ft\.?\s*)\s*([^,\n]+)', re.IGNORECASE),
            'french_roles': re.compile(r'\b(prod\.?\s*par|réalisé\s*par|mixé\s*par|écrit\s*par)\s+([^,\n]+)', re.IGNORECASE)
        }

    @lru_cache(maxsize=1)
    def _load_role_mappings(self) -> Dict[str, str]:
        """Charge les mappings de rôles avec cache"""
        return {
            # Production
            'producer': 'Producer',
            'produc': 'Producer',
            'beat maker': 'Producer',
            'beatmaker': 'Producer',
            'executive producer': 'Executive Producer',
            'co-producer': 'Co-Producer',
            'additional producer': 'Additional Producer',
            # Engineering
            'mixing engineer': 'Mixing Engineer',
            'mix engineer': 'Mixing Engineer',
            'mixed by': 'Mixing Engineer',
            'mixé par': 'Mixing Engineer',
            'mastering engineer': 'Mastering Engineer',
            'mastered by': 'Mastering Engineer',
            'masterisé par': 'Mastering Engineer',
            'recording engineer': 'Recording Engineer',
            'recorded by': 'Recording Engineer',
            'enregistré par': 'Recording Engineer',
            'sound engineer': 'Sound Engineer',
            # Writing
            'songwriter': 'Songwriter',
            'writer': 'Songwriter',
            'written by': 'Songwriter',
            'écrit par': 'Songwriter',
            'lyricist': 'Lyricist',
            'composer': 'Composer',
            'music by': 'Composer',
            'musique par': 'Composer',
            'arranger': 'Arranger',
            'arranged by': 'Arranger',
            'arrangé par': 'Arranger',
            # Performance
            'vocalist': 'Vocalist',
            'vocals': 'Vocalist',
            'lead vocals': 'Lead Vocalist',
            'backing vocals': 'Backing Vocalist',
            'rapper': 'Rapper',
            'rap': 'Rapper',
            'mc': 'Rapper',
            'featuring': 'Featured Artist',
            'feat': 'Featured Artist',
            'ft': 'Featured Artist',
            'avec': 'Featured Artist',
            # Instruments
            'guitarist': 'Guitarist',
            'guitar': 'Guitarist',
            'electric guitar': 'Electric Guitarist',
            'acoustic guitar': 'Acoustic Guitarist',
            'bassist': 'Bassist',
            'bass': 'Bassist',
            'bass guitar': 'Bassist',
            'drummer': 'Drummer',
            'drums': 'Drummer',
            'percussion': 'Percussionist',
            'pianist': 'Pianist',
            'piano': 'Pianist',
            'keyboardist': 'Keyboardist',
            'keyboards': 'Keyboardist',
            'synthesizer': 'Synthesizer Player',
            'synth': 'Synthesizer Player',
            # Autres
            'sampled': 'Sample Source',
            'sample': 'Sample Source',
            'interpolation': 'Interpolation Source',
            'director': 'Director',
            'réalisateur': 'Director',
            'photography': 'Photographer',
            'photo': 'Photographer'
        }

    @lru_cache(maxsize=1)
    def _load_instrument_keywords(self) -> Set[str]:
        """Charge les mots-clés d'instruments avec cache"""
        return {
            'guitar', 'guitare', 'bass', 'basse', 'drums', 'batterie', 'piano',
            'keyboard', 'clavier', 'synthesizer', 'synthé', 'synth', 'violin',
            'violon', 'saxophone', 'sax', 'trumpet', 'trompette', 'flute',
            'flûte', 'harmonica', 'accordion', 'accordéon', 'organ', 'orgue'
        }
    
    # ===== MÉTHODES PRINCIPALES =====
    
    def parse_credits(self, credit_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse un texte de crédits et extrait les informations structurées.
        
        Args:
            credit_text: Texte brut contenant les crédits
            context: Contexte additionnel (artiste, album, etc.)
            
        Returns:
            Dictionnaire avec les crédits parsés et normalisés
        """
        import time
        start_time = time.time()
        
        if not credit_text or len(credit_text.strip()) < 3:
            return self._empty_result("Texte de crédits vide ou trop court")
        
        # Génération de la clé de cache
        cache_key = self._generate_cache_key(credit_text, context)
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # 1. Nettoyage initial
            cleaned_text = self._clean_credit_text(credit_text)
            
            # 2. Extraction des crédits bruts
            raw_credits = self._extract_raw_credits(cleaned_text)
            
            # 3. Parsing et structuration
            parsed_credits = []
            for raw_credit in raw_credits:
                credit = self._parse_single_credit(raw_credit)
                if credit:
                    parsed_credits.append(credit)
            
            # 4. Normalisation des rôles
            if self.config['normalize_roles']:
                parsed_credits = self._normalize_credit_roles(parsed_credits)
                self.stats['roles_normalized'] += len(parsed_credits)
            
            # 5. Détection des collaborations
            collaboration_info = {}
            if self.config['detect_collaborations']:
                collaboration_info = self._detect_collaborations(parsed_credits)
                if collaboration_info.get('collaborations_found', 0) > 0:
                    self.stats['collaborations_detected'] += 1
            
            # 6. Fusion des crédits similaires
            if self.config['merge_similar_credits']:
                parsed_credits = self._merge_similar_credits(parsed_credits)
            
            # 7. Catégorisation
            categorized_credits = self._categorize_credits(parsed_credits)
            
            # 8. Validation et scoring
            validated_credits = self._validate_and_score_credits(parsed_credits)
            
            # Compilation du résultat
            result = {
                'success': True,
                'original_text': credit_text,
                'cleaned_text': cleaned_text,
                'total_credits_found': len(parsed_credits),
                'credits': validated_credits,
                'categorized_credits': categorized_credits,
                'collaboration_info': collaboration_info,
                'parsing_stats': {
                    'raw_extractions': len(raw_credits),
                    'valid_credits': len(validated_credits),
                    'success_rate': len(validated_credits) / len(raw_credits) if raw_credits else 0
                },
                'processing_metadata': {
                    'processed_at': datetime.now().isoformat(),
                    'parser_version': '1.0.0',
                    'processing_time': time.time() - start_time
                }
            }
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, result, ttl=3600)
            
            self.stats['credits_parsed'] += len(parsed_credits)
            self.stats['total_processing_time'] += time.time() - start_time
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erreur parsing crédits: {e}")
            return self._empty_result(f"Erreur de parsing: {str(e)}")
    
    def _clean_credit_text(self, text: str) -> str:
        """Nettoie le texte de crédits"""
        try:
            # Supprimer le contenu entre parenthèses et crochets
            text = self.patterns['parentheses_content'].sub('', text)
            text = self.patterns['bracket_content'].sub('', text)
            
            # Supprimer les préfixes "by/par"
            text = self.patterns['by_prefix'].sub('', text)
            
            # Normaliser les espaces
            text = self.patterns['extra_whitespace'].sub(' ', text)
            
            # Supprimer les caractères spéciaux en début/fin
            text = text.strip(' \t\n\r.,;:')
            
            return text
            
        except Exception as e:
            self.logger.debug(f"Erreur nettoyage crédits: {e}")
            return text.strip()
    
    def _extract_raw_credits(self, text: str) -> List[str]:
        """Extrait les crédits bruts du texte"""
        try:
            # Diviser par les séparateurs de crédits
            parts = self.patterns['credit_separators'].split(text)
            
            # Nettoyer et filtrer les parties
            raw_credits = []
            for part in parts:
                part = part.strip()
                if part and len(part) > 2:  # Ignorer les parties trop courtes
                    raw_credits.append(part)
            
            return raw_credits
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction crédits bruts: {e}")
            return [text]
    
    def _parse_single_credit(self, credit_text: str) -> Optional[Dict[str, Any]]:
        """Parse un crédit individuel"""
        try:
            # Chercher un pattern role: nom(s)
            role_match = self.patterns['role_separators'].split(credit_text, 1)
            
            if len(role_match) == 2:
                # Format "role: noms"
                role_part = role_match[0].strip()
                names_part = role_match[1].strip()
            else:
                # Pas de séparateur explicite, essayer de détecter automatiquement
                role_part, names_part = self._auto_detect_role_and_names(credit_text)
            
            if not names_part:
                return None
            
            # Extraire les noms multiples
            names = self._extract_names_from_text(names_part)
            
            if not names:
                return None
            
            # Créer le crédit structuré
            credit = {
                'original_text': credit_text,
                'role': role_part.strip() if role_part else 'Unknown',
                'names': names,
                'primary_name': names[0] if names else '',
                'is_collaboration': len(names) > 1,
                'extraction_method': 'pattern_parsing',
                'confidence': self._calculate_parsing_confidence(credit_text, role_part, names)
            }
            
            return credit
            
        except Exception as e:
            self.logger.debug(f"Erreur parsing crédit '{credit_text}': {e}")
            return None
    
    def _auto_detect_role_and_names(self, text: str) -> Tuple[str, str]:
        """Détecte automatiquement le rôle et les noms dans un texte"""
        text_lower = text.lower()
        
        # Rechercher des patterns de rôles connus
        for pattern_name, pattern in [
            ('producer', self.patterns['producer_patterns']),
            ('writer', self.patterns['writer_patterns']),
            ('performer', self.patterns['performer_patterns']),
            ('engineer', self.patterns['engineer_patterns']),
            ('instrument', self.patterns['instrument_patterns']),
            ('featuring', self.patterns['featuring_patterns'])
        ]:
            match = pattern.search(text_lower)
            if match:
                role_word = match.group()
                # Diviser le texte autour du mot de rôle
                parts = text.split(role_word, 1)
                if len(parts) == 2:
                    role_part = role_word
                    names_part = parts[1].strip()
                    return role_part, names_part
        
        # Patterns français spéciaux
        french_match = self.patterns['french_roles'].search(text)
        if french_match:
            role_part = french_match.group(1)
            names_part = french_match.group(2)
            return role_part, names_part
        
        # Aucun pattern détecté, considérer tout comme des noms
        return 'Unknown', text
    
    def _extract_names_from_text(self, names_text: str) -> List[str]:
        """Extrait les noms d'artistes d'un texte"""
        try:
            # Diviser par les séparateurs de noms
            parts = self.patterns['name_separators'].split(names_text)
            
            names = []
            for part in parts:
                name = clean_artist_name(part.strip())
                if name and self._is_valid_name(name):
                    names.append(name)
            
            return names
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction noms: {e}")
            return []
    
    def _is_valid_name(self, name: str) -> bool:
        """Valide qu'un nom est plausible"""
        if not name or len(name) < 2 or len(name) > 50:
            return False
        
        # Vérifier le pattern de nom valide
        if not self.patterns['valid_name'].match(name):
            return False
        
        # Filtrer les mots-clés non pertinents
        name_lower = name.lower()
        blacklist = {
            'unknown', 'various', 'multiple', 'others', 'etc', 'and', 'et',
            'credits', 'production', 'all', 'rights', 'reserved'
        }
        
        return name_lower not in blacklist
    
    def _normalize_credit_roles(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalise les rôles des crédits"""
        normalized_credits = []
        
        for credit in credits:
            role = credit.get('role', '').lower().strip()
            
            # Chercher une correspondance directe
            normalized_role = self.role_mappings.get(role)
            
            if not normalized_role:
                # Chercher une correspondance partielle
                for pattern, mapped_role in self.role_mappings.items():
                    if pattern in role or role in pattern:
                        normalized_role = mapped_role
                        break
            
            if not normalized_role:
                # Essayer de détecter par mots-clés
                normalized_role = self._detect_role_by_keywords(role)
            
            # Utiliser le rôle normalisé ou garder l'original titré
            credit['normalized_role'] = normalized_role or role.title()
            credit['role_category'] = self._categorize_role(normalized_role or role)
            
            normalized_credits.append(credit)
        
        return normalized_credits
    
    @lru_cache(maxsize=128)
    def _detect_role_by_keywords(self, role: str) -> Optional[str]:
        """Détecte un rôle par mots-clés avec cache"""
        role_lower = role.lower()
        
        # Production
        if any(word in role_lower for word in ['produc', 'beat', 'instrumental']):
            return 'Producer'
        
        # Engineering
        elif any(word in role_lower for word in ['mix', 'master', 'engineer', 'record']):
            if 'mix' in role_lower:
                return 'Mixing Engineer'
            elif 'master' in role_lower:
                return 'Mastering Engineer'
            elif 'record' in role_lower:
                return 'Recording Engineer'
            else:
                return 'Sound Engineer'
        
        # Writing
        elif any(word in role_lower for word in ['writ', 'compos', 'lyric', 'author']):
            if 'lyric' in role_lower:
                return 'Lyricist'
            elif 'compos' in role_lower:
                return 'Composer'
            else:
                return 'Songwriter'
        
        # Performance
        elif any(word in role_lower for word in ['vocal', 'rap', 'sing', 'feat']):
            if 'rap' in role_lower:
                return 'Rapper'
            elif 'feat' in role_lower:
                return 'Featured Artist'
            else:
                return 'Vocalist'
        
        # Instruments
        elif any(instrument in role_lower for instrument in self.instrument_keywords):
            return self._get_instrument_role(role_lower)
        
        return None
    
    def _get_instrument_role(self, role: str) -> str:
        """Détermine le rôle spécifique d'un instrument"""
        if 'guitar' in role or 'guitare' in role:
            return 'Guitarist'
        elif 'bass' in role or 'basse' in role:
            return 'Bassist'
        elif 'drum' in role or 'batterie' in role:
            return 'Drummer'
        elif 'piano' in role:
            return 'Pianist'
        elif 'keyboard' in role or 'clavier' in role:
            return 'Keyboardist'
        elif 'synth' in role:
            return 'Synthesizer Player'
        else:
            return 'Instrumentalist'
    
    @lru_cache(maxsize=64)
    def _categorize_role(self, role: str) -> str:
        """Catégorise un rôle de crédit"""
        role_lower = role.lower()
        
        if any(word in role_lower for word in ['produc', 'beat', 'instrumental']):
            return CreditCategory.PRODUCTION.value
        elif any(word in role_lower for word in ['mix', 'master', 'engineer', 'record']):
            return CreditCategory.ENGINEERING.value
        elif any(word in role_lower for word in ['writ', 'compos', 'lyric', 'author']):
            return CreditCategory.WRITING.value
        elif any(word in role_lower for word in ['vocal', 'rap', 'sing', 'feat']):
            return CreditCategory.PERFORMANCE.value
        elif any(instrument in role_lower for instrument in self.instrument_keywords):
            return CreditCategory.INSTRUMENTATION.value
        else:
            return CreditCategory.OTHER.value
    
    def _detect_collaborations(self, credits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Détecte les patterns de collaboration"""
        collaboration_info = {
            'collaborations_found': 0,
            'collaborative_roles': [],
            'featured_artists': [],
            'multiple_producers': False,
            'collaboration_score': 0.0
        }
        
        try:
            # Compter les collaborations par rôle
            role_counts = defaultdict(int)
            featured_artists = []
            
            for credit in credits:
                role = credit.get('normalized_role', '').lower()
                names = credit.get('names', [])
                
                if len(names) > 1:
                    collaboration_info['collaborations_found'] += 1
                    collaboration_info['collaborative_roles'].append({
                        'role': role,
                        'collaborators': names,
                        'count': len(names)
                    })
                
                if 'featured' in role or 'feat' in role:
                    featured_artists.extend(names)
                
                if 'producer' in role:
                    role_counts['producer'] += len(names)
            
            collaboration_info['featured_artists'] = list(set(featured_artists))
            collaboration_info['multiple_producers'] = role_counts['producer'] > 1
            
            # Calculer un score de collaboration
            total_collaborations = collaboration_info['collaborations_found']
            total_credits = len(credits)
            collaboration_info['collaboration_score'] = total_collaborations / total_credits if total_credits > 0 else 0
            
        except Exception as e:
            self.logger.debug(f"Erreur détection collaborations: {e}")
        
        return collaboration_info
    
    def _merge_similar_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fusionne les crédits similaires"""
        if not self.config['enable_fuzzy_matching']:
            return credits
        
        merged_credits = []
        processed_indices = set()
        
        for i, credit in enumerate(credits):
            if i in processed_indices:
                continue
            
            similar_credits = [credit]
            
            # Chercher des crédits similaires
            for j, other_credit in enumerate(credits[i+1:], i+1):
                if j in processed_indices:
                    continue
                
                if self._are_credits_similar(credit, other_credit):
                    similar_credits.append(other_credit)
                    processed_indices.add(j)
            
            # Fusionner si on a trouvé des similaires
            if len(similar_credits) > 1:
                merged_credit = self._merge_credit_group(similar_credits)
                merged_credits.append(merged_credit)
                self.stats['duplicates_merged'] += len(similar_credits) - 1
            else:
                merged_credits.append(credit)
            
            processed_indices.add(i)
        
        return merged_credits
    
    def _are_credits_similar(self, credit1: Dict[str, Any], credit2: Dict[str, Any]) -> bool:
        """Détermine si deux crédits sont similaires"""
        role1 = credit1.get('normalized_role', '').lower()
        role2 = credit2.get('normalized_role', '').lower()
        
        # Les rôles doivent être identiques ou très similaires
        if role1 != role2:
            role_similarity = calculate_similarity(role1, role2)
            if role_similarity < 0.8:
                return False
        
        # Vérifier la similarité des noms
        names1 = set(name.lower() for name in credit1.get('names', []))
        names2 = set(name.lower() for name in credit2.get('names', []))
        
        # Intersection des noms
        common_names = names1.intersection(names2)
        if common_names:
            return True
        
        # Similarité des noms individuels
        for name1 in names1:
            for name2 in names2:
                if calculate_similarity(name1, name2) > 0.85:
                    return True
        
        return False
    
    def _merge_credit_group(self, credits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fusionne un groupe de crédits similaires"""
        if not credits:
            return {}
        
        # Utiliser le premier crédit comme base
        merged = credits[0].copy()
        
        # Fusionner les noms
        all_names = set()
        for credit in credits:
            all_names.update(credit.get('names', []))
        
        merged['names'] = sorted(list(all_names))
        merged['primary_name'] = merged['names'][0] if merged['names'] else ''
        merged['is_collaboration'] = len(merged['names']) > 1
        merged['merged_from'] = len(credits)
        
        # Prendre la meilleure confiance
        merged['confidence'] = max(credit.get('confidence', 0) for credit in credits)
        
        return merged
    
    def _categorize_credits(self, credits: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Catégorise les crédits par type"""
        categorized = defaultdict(list)
        
        for credit in credits:
            category = credit.get('role_category', CreditCategory.OTHER.value)
            categorized[category].append(credit)
        
        return dict(categorized)
    
    def _validate_and_score_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Valide et score les crédits"""
        validated_credits = []
        
        for credit in credits:
            # Calculer le score de confiance si pas déjà fait
            if 'confidence' not in credit:
                credit['confidence'] = self._calculate_parsing_confidence(
                    credit.get('original_text', ''),
                    credit.get('role', ''),
                    credit.get('names', [])
                )
            
            # Valider selon le seuil de confiance
            if credit['confidence'] >= self.config['confidence_threshold']:
                validated_credits.append(credit)
        
        return validated_credits
    
    def _calculate_parsing_confidence(self, original_text: str, role: str, names: List[str]) -> float:
        """Calcule un score de confiance pour le parsing"""
        confidence = 0.5  # Base
        
        # Bonus pour un rôle reconnu
        if role and role.lower() in self.role_mappings:
            confidence += 0.2
        
        # Bonus pour des noms valides
        valid_names = [name for name in names if self._is_valid_name(name)]
        if valid_names:
            confidence += 0.2 * (len(valid_names) / len(names))
        
        # Bonus pour un texte structuré
        if ':' in original_text:
            confidence += 0.1
        
        # Pénalité pour un texte trop court ou trop long
        text_length = len(original_text)
        if text_length < 5:
            confidence -= 0.2
        elif text_length > 100:
            confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def _generate_cache_key(self, credit_text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Génère une clé de cache pour les crédits"""
        import hashlib
        
        content = credit_text
        if context:
            content += str(sorted(context.items()))
        
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _empty_result(self, error_message: str) -> Dict[str, Any]:
        """Retourne un résultat vide avec message d'erreur"""
        return {
            'success': False,
            'error': error_message,
            'original_text': '',
            'cleaned_text': '',
            'total_credits_found': 0,
            'credits': [],
            'categorized_credits': {},
            'collaboration_info': {},
            'parsing_stats': {
                'raw_extractions': 0,
                'valid_credits': 0,
                'success_rate': 0.0
            },
            'processing_metadata': {
                'processed_at': datetime.now().isoformat(),
                'parser_version': '1.0.0'
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de parsing"""
        return self.stats.copy()
    
    def clear_cache(self) -> bool:
        """Vide le cache du parser"""
        if self.cache_manager:
            return self.cache_manager.clear()
        return True