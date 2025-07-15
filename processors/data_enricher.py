        except Exception as e:
            self.logger.warning(f"Erreur inférence BPM pour '{track.title}': {e}")
        
        return None
    
    def _infer_track_album(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère l'album d'un track"""
        try:
            # Rechercher des tracks du même artiste avec des albums
            artist_tracks = self.database.get_tracks_by_artist_id(track.artist_id)
            
            # Grouper par album et compter
            album_counts = {}
            for t in artist_tracks:
                if t.album_title and t.id != track.id:
                    album_counts[t.album_title] = album_counts.get(t.album_title, 0) + 1
            
            if album_counts:
                # Prendre l'album le plus fréquent
                most_common_album = max(album_counts.items(), key=lambda x: x[1])
                album_title, count = most_common_album
                
                # Vérifier la cohérence temporelle si possible
                if track.release_year:
                    album_tracks = [t for t in artist_tracks if t.album_title == album_title]
                    album_years = [t.release_year for t in album_tracks if t.release_year]
                    
                    if album_years and abs(track.release_year - max(album_years)) <= 2:
                        track.album_title = album_title
                        
                        return EnrichmentResult(
                            entity_id=track.id,
                            entity_type="track",
                            enrichment_type=EnrichmentType.MISSING_DATA,
                            source=EnrichmentSource.INFERENCE,
                            field="album_title",
                            old_value=None,
                            new_value=album_title,
                            confidence=0.8,
                            success=True,
                            message=f"Album inféré à partir des tracks de l'artiste ({count} tracks)"
                        )
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence album pour '{track.title}': {e}")
        
        return None
    
    def _infer_release_year(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère l'année de sortie d'un track"""
        try:
            # Essayer d'extraire l'année de la date de sortie
            if track.release_date:
                year = extract_year_from_date(track.release_date)
                if year:
                    track.release_year = year
                    
                    return EnrichmentResult(
                        entity_id=track.id,
                        entity_type="track",
                        enrichment_type=EnrichmentType.MISSING_DATA,
                        source=EnrichmentSource.INFERENCE,
                        field="release_year",
                        old_value=None,
                        new_value=year,
                        confidence=0.9,
                        success=True,
                        message="Année extraite de la date de sortie"
                    )
            
            # Sinon, inférer à partir de l'album
            if track.album_title:
                album_tracks = self._get_tracks_from_album(track.album_title, track.artist_id)
                years = [t.release_year for t in album_tracks if t.release_year and t.id != track.id]
                
                if years:
                    # Prendre l'année la plus fréquente
                    from collections import Counter
                    year_counts = Counter(years)
                    most_common_year = year_counts.most_common(1)[0][0]
                    
                    track.release_year = most_common_year
                    
                    return EnrichmentResult(
                        entity_id=track.id,
                        entity_type="track",
                        enrichment_type=EnrichmentType.MISSING_DATA,
                        source=EnrichmentSource.INFERENCE,
                        field="release_year",
                        old_value=None,
                        new_value=most_common_year,
                        confidence=0.7,
                        success=True,
                        message=f"Année inférée à partir de l'album ({len(years)} tracks)"
                    )
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence année pour '{track.title}': {e}")
        
        return None
    
    def _infer_missing_credits(self, track: Track) -> List[EnrichmentResult]:
        """Infère les crédits manquants d'un track"""
        results = []
        
        try:
            # Rechercher des producteurs récurrents pour l'artiste
            if not any(c.credit_category == CreditCategory.PRODUCER for c in track.credits):
                producer_result = self._infer_producer_credit(track)
                if producer_result:
                    results.append(producer_result)
            
            # Inférer des crédits basés sur l'album
            if track.album_title:
                album_credit_results = self._infer_album_based_credits(track)
                results.extend(album_credit_results)
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence crédits pour '{track.title}': {e}")
        
        return results
    
    def _infer_producer_credit(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère le producteur principal d'un track"""
        try:
            # Analyser les producteurs récurrents de l'artiste
            artist_tracks = self.database.get_tracks_by_artist_id(track.artist_id)
            
            producer_counts = {}
            for t in artist_tracks:
                if t.id != track.id:
                    producers = [c.person_name for c in t.credits if c.credit_category == CreditCategory.PRODUCER]
                    for producer in producers:
                        producer_counts[producer] = producer_counts.get(producer, 0) + 1
            
            if producer_counts:
                # Prendre le producteur le plus fréquent
                most_common_producer = max(producer_counts.items(), key=lambda x: x[1])
                producer_name, count = most_common_producer
                
                # Seuil de confiance basé sur la fréquence
                confidence = min(0.9, count / len(artist_tracks))
                
                if confidence >= self.config['min_confidence_threshold']:
                    # Créer le crédit
                    new_credit = Credit(
                        track_id=track.id,
                        credit_category=CreditCategory.PRODUCER,
                        credit_type=CreditType.PRODUCER,
                        person_name=producer_name,
                        data_source=DataSource.WEB_SCRAPING,  # Utiliser une source existante
                        extraction_date=datetime.now()
                    )
                    
                    track.credits.append(new_credit)
                    
                    return EnrichmentResult(
                        entity_id=track.id,
                        entity_type="track",
                        enrichment_type=EnrichmentType.MISSING_DATA,
                        source=EnrichmentSource.INFERENCE,
                        field="credits",
                        old_value=len(track.credits) - 1,
                        new_value=len(track.credits),
                        confidence=confidence,
                        success=True,
                        message=f"Producteur inféré: {producer_name} ({count} collaborations)"
                    )
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence producteur pour '{track.title}': {e}")
        
        return None
    
    def _infer_album_based_credits(self, track: Track) -> List[EnrichmentResult]:
        """Infère des crédits basés sur l'album"""
        results = []
        
        try:
            album_tracks = self._get_tracks_from_album(track.album_title, track.artist_id)
            
            # Analyser les crédits récurrents dans l'album
            credit_frequency = {}
            
            for t in album_tracks:
                if t.id != track.id:
                    for credit in t.credits:
                        key = (credit.person_name, credit.credit_type)
                        credit_frequency[key] = credit_frequency.get(key, 0) + 1
            
            # Inférer les crédits très fréquents (ex: mixing/mastering)
            album_track_count = len(album_tracks)
            
            for (person_name, credit_type), count in credit_frequency.items():
                frequency = count / album_track_count
                
                # Si le crédit apparaît dans >70% des tracks de l'album
                if frequency > 0.7:
                    # Vérifier que ce crédit n'existe pas déjà
                    existing = any(
                        c.person_name == person_name and c.credit_type == credit_type 
                        for c in track.credits
                    )
                    
                    if not existing:
                        # Déterminer la catégorie
                        category = self._get_category_for_type(credit_type)
                        
                        new_credit = Credit(
                            track_id=track.id,
                            credit_category=category,
                            credit_type=credit_type,
                            person_name=person_name,
                            data_source=DataSource.WEB_SCRAPING,
                            extraction_date=datetime.now()
                        )
                        
                        track.credits.append(new_credit)
                        
                        results.append(EnrichmentResult(
                            entity_id=track.id,
                            entity_type="track",
                            enrichment_type=EnrichmentType.MISSING_DATA,
                            source=EnrichmentSource.CROSS_REFERENCE,
                            field="credits",
                            old_value=len(track.credits) - 1,
                            new_value=len(track.credits),
                            confidence=frequency,
                            success=True,
                            message=f"Crédit inféré de l'album: {person_name} ({credit_type.value})"
                        ))
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence crédits album pour '{track.title}': {e}")
        
        return results
    
    def _enrich_track_metadata(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit les métadonnées d'un track"""
        results = []
        
        # Enrichir le genre si manquant
        if not hasattr(track, 'genre') or not track.genre:
            genre_result = self._infer_track_genre(track)
            if genre_result:
                results.append(genre_result)
        
        # Enrichir la clé musicale si manquante
        if not track.key:
            key_result = self._infer_musical_key(track)
            if key_result:
                results.append(key_result)
        
        # Enrichir les featuring à partir du titre
        featuring_result = self._extract_featuring_from_title(track)
        if featuring_result:
            results.append(featuring_result)
        
        return results
    
    def _infer_track_genre(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère le genre d'un track"""
        try:
            # Analyser les crédits pour des indices de genre
            rap_indicators = 0
            
            for credit in track.credits:
                person_name = credit.person_name.lower()
                
                # Indices dans les noms de producteurs
                for genre, patterns in self.inference_rules['genre_inference']['producer_patterns'].items():
                    if any(pattern in person_name for pattern in patterns):
                        rap_indicators += 1
                        break
            
            # Analyser le titre pour des indices
            title_lower = track.title.lower()
            for keyword in self.inference_rules['genre_inference']['rap_keywords']:
                if keyword in title_lower:
                    rap_indicators += 1
            
            if rap_indicators > 0:
                confidence = min(0.8, rap_indicators * 0.3)
                
                # Pour l'instant, on infère seulement "rap" comme genre principal
                inferred_genre = "rap"
                
                return EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    enrichment_type=EnrichmentType.METADATA,
                    source=EnrichmentSource.INFERENCE,
                    field="genre",
                    old_value=None,
                    new_value=inferred_genre,
                    confidence=confidence,
                    success=True,
                    message=f"Genre inféré à partir de {rap_indicators} indices"
                )
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence genre pour '{track.title}': {e}")
        
        return None
    
    def _infer_musical_key(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère la clé musicale d'un track"""
        try:
            # Pour l'instant, inférence basique basée sur les tracks de l'album
            if track.album_title:
                album_tracks = self._get_tracks_from_album(track.album_title, track.artist_id)
                keys = [t.key for t in album_tracks if t.key and t.id != track.id]
                
                if keys:
                    # Prendre la clé la plus fréquente
                    from collections import Counter
                    key_counts = Counter(keys)
                    most_common_key = key_counts.most_common(1)[0][0]
                    
                    track.key = most_common_key
                    
                    return EnrichmentResult(
                        entity_id=track.id,
                        entity_type="track",
                        enrichment_type=EnrichmentType.METADATA,
                        source=EnrichmentSource.INFERENCE,
                        field="key",
                        old_value=None,
                        new_value=most_common_key,
                        confidence=0.5,
                        success=True,
                        message=f"Clé musicale inférée de l'album ({len(keys)} tracks)"
                    )
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence clé musicale pour '{track.title}': {e}")
        
        return None
    
    def _extract_featuring_from_title(self, track: Track) -> Optional[EnrichmentResult]:
        """Extrait les featuring du titre du track"""
        try:
            from ..utils.text_utils import extract_featured_artists_from_title
            
            clean_title, featuring_artists = extract_featured_artists_from_title(track.title)
            
            if featuring_artists and not track.featuring_artists:
                track.featuring_artists = featuring_artists
                
                return EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    enrichment_type=EnrichmentType.METADATA,
                    source=EnrichmentSource.INFERENCE,
                    field="featuring_artists",
                    old_value=[],
                    new_value=featuring_artists,
                    confidence=0.9,
                    success=True,
                    message=f"Featuring extraits du titre: {', '.join(featuring_artists)}"
                )
        
        except Exception as e:
            self.logger.warning(f"Erreur extraction featuring pour '{track.title}': {e}")
        
        return None
    
    def _enrich_track_relationships(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit les relations d'un track"""
        results = []
        
        # Lier à un album existant
        if not track.album_id and track.album_title:
            album_link_result = self._link_to_existing_album(track)
            if album_link_result:
                results.append(album_link_result)
        
        # Établir des relations avec d'autres tracks
        similarity_results = self._establish_track_similarities(track)
        results.extend(similarity_results)
        
        return results
    
    def _link_to_existing_album(self, track: Track) -> Optional[EnrichmentResult]:
        """Lie un track à un album existant"""
        try:
            # Rechercher un album avec le même titre et artiste
            with self.database.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id FROM albums 
                    WHERE title = ? AND artist_id = ?
                """, (track.album_title, track.artist_id))
                
                row = cursor.fetchone()
                if row:
                    track.album_id = row['id']
                    
                    return EnrichmentResult(
                        entity_id=track.id,
                        entity_type="track",
                        enrichment_type=EnrichmentType.RELATIONSHIPS,
                        source=EnrichmentSource.CROSS_REFERENCE,
                        field="album_id",
                        old_value=None,
                        new_value=row['id'],
                        confidence=1.0,
                        success=True,
                        message=f"Track lié à l'album existant (ID: {row['id']})"
                    )
        
        except Exception as e:
            self.logger.warning(f"Erreur liaison album pour '{track.title}': {e}")
        
        return None
    
    def _establish_track_similarities(self, track: Track) -> List[EnrichmentResult]:
        """Établit des similarités entre tracks"""
        results = []
        
        try:
            similar_tracks = self._find_similar_tracks(track, limit=3)
            
            if similar_tracks:
                similarity_data = []
                for similar_track in similar_tracks:
                    similarity_score = similarity_ratio(track.title, similar_track.title)
                    similarity_data.append({
                        'track_id': similar_track.id,
                        'title': similar_track.title,
                        'similarity': similarity_score
                    })
                
                # Stocker les similarités comme métadonnée (nécessiterait un champ dédié)
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    enrichment_type=EnrichmentType.RELATIONSHIPS,
                    source=EnrichmentSource.INFERENCE,
                    field="similar_tracks",
                    old_value=None,
                    new_value=similarity_data,
                    confidence=0.7,
                    success=True,
                    message=f"Établi {len(similar_tracks)} relations de similarité"
                ))
        
        except Exception as e:
            self.logger.warning(f"Erreur établissement similarités pour '{track.title}': {e}")
        
        return results
    
    def _validate_and_correct_track_data(self, track: Track) -> List[EnrichmentResult]:
        """Valide et corrige les données d'un track"""
        results = []
        
        # Validation et correction du BPM
        if track.bpm and track.bpm < 60:
            # Probable erreur de division par 2
            corrected_bpm = track.bpm * 2
            if corrected_bpm <= 200:
                track.bpm = corrected_bpm
                
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    enrichment_type=EnrichmentType.VALIDATION,
                    source=EnrichmentSource.INFERENCE,
                    field="bpm",
                    old_value=track.bpm // 2,
                    new_value=corrected_bpm,
                    confidence=0.8,
                    success=True,
                    message="BPM corrigé (doublé car trop bas)"
                ))
        
        # Validation des durées
        if track.duration_seconds and track.duration_seconds > 1800:  # >30min
            # Probable erreur d'unité (millisecondes au lieu de secondes)
            if track.duration_seconds > 10000:  # Très probablement en ms
                corrected_duration = track.duration_seconds // 1000
                track.duration_seconds = corrected_duration
                
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    enrichment_type=EnrichmentType.VALIDATION,
                    source=EnrichmentSource.INFERENCE,
                    field="duration_seconds",
                    old_value=corrected_duration * 1000,
                    new_value=corrected_duration,
                    confidence=0.9,
                    success=True,
                    message="Durée corrigée (conversion ms vers s)"
                ))
        
        return results
    
    def _enhance_track_data(self, track: Track) -> List[EnrichmentResult]:
        """Améliore la qualité des données d'un track"""
        results = []
        
        # Améliorer la qualité du titre
        if track.title:
            enhanced_title = self._enhance_title_quality(track.title)
            if enhanced_title != track.title:
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    enrichment_type=EnrichmentType.ENHANCEMENT,
                    source=EnrichmentSource.INFERENCE,
                    field="title",
                    old_value=track.title,
                    new_value=enhanced_title,
                    confidence=0.8,
                    success=True,
                    message="Titre amélioré (formatage et nettoyage)"
                ))
                track.title = enhanced_title
        
        return results
    
    def _enhance_title_quality(self, title: str) -> str:
        """Améliore la qualité d'un titre"""
        enhanced = title.strip()
        
        # Corriger la capitalisation
        words = enhanced.split()
        enhanced_words = []
        
        for i, word in enumerate(words):
            # Mots qui restent en minuscules (sauf en début de titre)
            if i > 0 and word.lower() in ['and', 'or', 'but', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with']:
                enhanced_words.append(word.lower())
            # Mots entre parenthèses
            elif word.startswith('(') and word.endswith(')'):
                enhanced_words.append(f"({word[1:-1].title()})")
            else:
                enhanced_words.append(word.title())
        
        return ' '.join(enhanced_words)
    
    def enrich_artist_data(self, artist_id: int) -> List[EnrichmentResult]:
        """
        Enrichit les données d'un artiste et de tous ses tracks.
        
        Args:
            artist_id: ID de l'artiste à enrichir
            
        Returns:
            Liste des résultats d'enrichissement
        """
        results = []
        
        try:
            self.logger.info(f"Enrichissement des données pour l'artiste {artist_id}")
            
            # Enrichir tous les tracks de l'artiste
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            
            for track in tracks:
                track_results = self.enrich_track(track)
                results.extend(track_results)
            
            # Enrichissement au niveau artiste
            artist_results = self._enrich_artist_metadata(artist_id, tracks)
            results.extend(artist_results)
            
            self.logger.info(f"Enrichissement artiste {artist_id} terminé: {len(results)} améliorations")
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur enrichissement artiste {artist_id}: {e}")
            return []
    
    def _enrich_artist_metadata(self, artist_id: int, tracks: List[Track]) -> List[EnrichmentResult]:
        """Enrichit les métadonnées d'un artiste"""
        results = []
        
        try:
            # Calculer des statistiques
            total_tracks = len(tracks)
            
            # Analyser les collaborations fréquentes
            collaborator_counts = {}
            for track in tracks:
                for credit in track.credits:
                    if credit.person_name != track.artist_name:
                        collaborator_counts[credit.person_name] = collaborator_counts.get(credit.person_name, 0) + 1
                
                for featuring in (track.featuring_artists or []):
                    if featuring != track.artist_name:
                        collaborator_counts[featuring] = collaborator_counts.get(featuring, 0) + 1
            
            # Identifier les collaborateurs récurrents
            frequent_collaborators = [
                name for name, count in collaborator_counts.items() 
                if count >= total_tracks * 0.3  # 30% des tracks
            ]
            
            if frequent_collaborators:
                results.append(EnrichmentResult(
                    entity_id=artist_id,
                    entity_type="artist",
                    enrichment_type=EnrichmentType.METADATA,
                    source=EnrichmentSource.INFERENCE,
                    field="frequent_collaborators",
                    old_value=None,
                    new_value=frequent_collaborators,
                    confidence=0.8,
                    success=True,
                    message=f"Identifié {len(frequent_collaborators)} collaborateurs fréquents"
                ))
            
            # Analyser la période d'activité
            years = [track.release_year for track in tracks if track.release_year]
            if years:
                min_year = min(years)
                max_year = max(years)
                activity_period = f"{min_year}-{max_year}" if min_year != max_year else str(min_year)
                
                results.append(EnrichmentResult(
                    entity_id=artist_id,
                    entity_type="artist",
                    enrichment_type=EnrichmentType.METADATA,
                    source=EnrichmentSource.INFERENCE,
                    field="active_years",
                    old_value=None,
                    new_value=activity_period,
                    confidence=0.9,
                    success=True,
                    message=f"Période d'activité calculée: {activity_period}"
                ))
        
        except Exception as e:
            self.logger.warning(f"Erreur enrichissement métadonnées artiste {artist_id}: {e}")
        
        return results
    
    def batch_enrich(self, entity_type: str, entity_ids: List[int], enrich_types: Optional[List[EnrichmentType]] = None) -> EnrichmentStats:
        """
        Enrichit plusieurs entités en lot.
        
        Args:
            entity_type: Type d'entité ('track', 'artist')
            entity_ids: Liste des IDs à enrichir
            enrich_types: Types d'enrichissement
            
        Returns:
            Statistiques d'enrichissement
        """
        stats = EnrichmentStats()
        stats.total_processed = len(entity_ids)
        
        try:
            self.logger.info(f"Enrichissement en lot: {len(entity_ids)} {entity_type}s")
            
            for entity_id in entity_ids:
                try:
                    if entity_type == 'track':
                        # Récupérer le track
                        with self.database.get_connection() as conn:
                            cursor = conn.execute("SELECT * FROM tracks WHERE id = ?", (entity_id,))
                            row = cursor.fetchone()
                            if row:
                                track = self.database._row_to_track(row)
                                track.credits = self.database.get_credits_by_track_id(track.id)
                                track.featuring_artists = self.database.get_features_by_track_id(track.id)
                                
                                results = self.enrich_track(track, enrich_types)
                                
                                # Compter les succès
                                successful = [r for r in results if r.success]
                                stats.successful_enrichments += len(successful)
                                stats.failed_enrichments += len(results) - len(successful)
                                
                                # Compter par champ
                                for result in successful:
                                    field = result.field
                                    stats.fields_enriched[field] = stats.fields_enriched.get(field, 0) + 1
                                    
                                    source = result.source.value
                                    stats.sources_used[source] = stats.sources_used.get(source, 0) + 1
                    
                    elif entity_type == 'artist':
                        results = self.enrich_artist_data(entity_id)
                        
                        successful = [r for r in results if r.success]
                        stats.successful_enrichments += len(successful)
                        stats.failed_enrichments += len(results) - len(successful)
                        
                        for result in successful:
                            field = result.field
                            stats.fields_enriched[field] = stats.fields_enriched.get(field, 0) + 1
                            
                            source = result.source.value
                            stats.sources_used[source] = stats.sources_used.get(source, 0) + 1
                
                except Exception as e:
                    self.logger.error(f"Erreur enrichissement {entity_type} {entity_id}: {e}")
                    stats.failed_enrichments += 1
            
            self.logger.info(f"Enrichissement en lot terminé: {stats.successful_enrichments} succès, {stats.failed_enrichments} échecs")
            return stats
            
        except Exception as e:
            self.logger.error(f"Erreur enrichissement en lot: {e}")
            return stats
    
    # Méthodes utilitaires
    
    def _find_similar_tracks(self, track: Track, limit: int = 5) -> List[Track]:
        """Trouve des tracks similaires"""
        try:
            artist_tracks = self.database.get_tracks_by_artist_id(track.artist_id)
            similar_tracks = []
            
            for other_track in artist_tracks:
                if other_track.id != track.id:
                    similarity = similarity_ratio(track.title, other_track.title)
                    if similarity > 0.3:  # Seuil de similarité
                        similar_tracks.append((other_track, similarity))
            
            # Trier par similarité décroissante
            similar_tracks.sort(key=lambda x: x[1], reverse=True)
            
            return [track for track, _ in similar_tracks[:limit]]
        
        except Exception as e:
            self.logger.warning(f"Erreur recherche tracks similaires: {e}")
            return []
    
    def _get_tracks_from_album(self, album_title: str, artist_id: int) -> List[Track]:
        """Récupère tous les tracks d'un album"""
        try:
            with self.database.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM tracks 
                    WHERE album_title = ? AND artist_id = ?
                """, (album_title, artist_id))
                
                tracks = []
                for row in cursor.fetchall():
                    track = self.database._row_to_track(row)
                    track.credits = self.database.get_credits_by_track_id(track.id)
                    track.featuring_artists = self.database.get_features_by_track_id(track.id)
                    tracks.append(track)
                
                return tracks
        
        except Exception as e:
            self.logger.warning(f"Erreur récupération tracks album '{album_title}': {e}")
            return []
    
    def _get_category_for_type(self, credit_type: CreditType) -> CreditCategory:
        """Détermine la catégorie pour un type de crédit"""
        type_to_category = {
            CreditType.PRODUCER: CreditCategory.PRODUCER,
            CreditType.EXECUTIVE_PRODUCER: CreditCategory.PRODUCER,
            CreditType.CO_PRODUCER: CreditCategory.PRODUCER,
            CreditType.MIXING: CreditCategory.TECHNICAL,
            CreditType.MASTERING: CreditCategory.TECHNICAL,
            CreditType.RECORDING: CreditCategory.TECHNICAL,
            CreditType.FEATURING: CreditCategory.FEATURING,
            CreditType.LEAD_VOCALS: CreditCategory.VOCAL,
            CreditType.BACKING_VOCALS: CreditCategory.VOCAL,
            CreditType.RAP: CreditCategory.VOCAL,
            CreditType.SONGWRITER: CreditCategory.COMPOSER,
            CreditType.COMPOSER: CreditCategory.COMPOSER,
            CreditType.GUITAR: CreditCategory.INSTRUMENT,
            CreditType.PIANO: CreditCategory.INSTRUMENT,
            CreditType.DRUMS: CreditCategory.INSTRUMENT,
            CreditType.BASS: CreditCategory.INSTRUMENT,
            CreditType.SAXOPHONE: CreditCategory.INSTRUMENT,
            CreditType.SAMPLE: CreditCategory.SAMPLE,
            CreditType.INTERPOLATION: CreditCategory.SAMPLE
        }
        return type_to_category.get(credit_type, CreditCategory.OTHER)
    
    def generate_enrichment_report(self, results: List[EnrichmentResult]) -> Dict[str, Any]:
        """
        Génère un rapport d'enrichissement.
        
        Args:
            results: Résultats d'enrichissement
            
        Returns:
            Rapport détaillé
        """
        try:
            # Statistiques globales
            total_results = len(results)
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            success_rate = (len(successful) / total_results * 100) if total_results > 0 else 0
            
            # Analyse par type d'enrichissement
            by_enrichment_type = {}
            for result in results:
                etype = result.enrichment_type.value
                if etype not in by_enrichment_type:
                    by_enrichment_type[etype] = {'total': 0, 'success': 0, 'failed': 0}
                
                by_enrichment_type[etype]['total'] += 1
                if result.success:
                    by_enrichment_type[etype]['success'] += 1
                else:
                    by_enrichment_type[etype]['failed'] += 1
            
            # Analyse par source
            by_source = {}
            for result in successful:
                source = result.source.value
                by_source[source] = by_source.get(source, 0) + 1
            
            # Analyse par champ
            by_field = {}
            for result in successful:
                field = result.field
                by_field[field] = by_field.get(field, 0) + 1
            
            # Top améliorations par confiance
            top_improvements = sorted(
                successful, 
                key=lambda x: x.confidence, 
                reverse=True
            )[:10]
            
            # Analyse des échecs
            failure_reasons = {}
            for result in failed:
                reason = result.message
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            
            # Calcul score de confiance moyen
            if successful:
                avg_confidence = sum(r.confidence for r in successful) / len(successful)
            else:
                avg_confidence = 0.0
            
            return {
                'summary': {
                    'total_enrichments': total_results,
                    'successful': len(successful),
                    'failed': len(failed),
                    'success_rate': round(success_rate, 1),
                    'average_confidence': round(avg_confidence, 2)
                },
                'by_enrichment_type': by_enrichment_type,
                'by_source': by_source,
                'by_field': by_field,
                'top_improvements': [
                    {
                        'entity_id': r.entity_id,
                        'entity_type': r.entity_type,
                        'field': r.field,
                        'enrichment_type': r.enrichment_type.value,
                        'source': r.source.value,
                        'confidence': r.confidence,
                        'message': r.message
                    }
                    for r in top_improvements
                ],
                'failure_analysis': failure_reasons,
                'recommendations': self._generate_enrichment_recommendations(results),
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur génération rapport enrichissement: {e}")
            return {'error': f'Erreur lors de la génération: {e}'}
    
    def _generate_enrichment_recommendations(self, results: List[EnrichmentResult]) -> List[str]:
        """Génère des recommandations d'enrichissement"""
        recommendations = []
        
        try:
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            # Recommandations basées sur les succès
            if successful:
                # Analyser les sources les plus efficaces
                source_success = {}
                for result in successful:
                    source = result.source.value
                    source_success[source] = source_success.get(source, 0) + 1
                
                if source_success:
                    best_source = max(source_success.items(), key=lambda x: x[1])
                    recommendations.append(f"Source la plus efficace: {best_source[0]} ({best_source[1]} succès)")
                
                # Analyser les champs les plus enrichis
                field_counts = {}
                for result in successful:
                    field = result.field
                    field_counts[field] = field_counts.get(field, 0) + 1
                
                top_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                recommendations.append(f"Champs le plus enrichis: {', '.join([f[0] for f in top_fields])}")
            
            # Recommandations basées sur les échecs
            if failed:
                failure_rate = len(failed) / len(results) * 100
                if failure_rate > 20:
                    recommendations.append(f"Taux d'échec élevé ({failure_rate:.1f}%) - Vérifier la configuration")
                
                # Analyser les types d'échecs
                failed_types = {}
                for result in failed:
                    etype = result.enrichment_type.value
                    failed_types[etype] = failed_types.get(etype, 0) + 1
                
                if failed_types:
                    worst_type = max(failed_types.items(), key=lambda x: x[1])
                    recommendations.append(f"Type d'enrichissement le plus problématique: {worst_type[0]}")
            
            # Recommandations générales
            if len(successful) > 0:
                avg_confidence = sum(r.confidence for r in successful) / len(successful)
                if avg_confidence < 0.7:
                    recommendations.append("Confiance moyenne faible - Améliorer les algorithmes d'inférence")
            
            inference_count = sum(1 for r in successful if r.source == EnrichmentSource.INFERENCE)
            if inference_count > len(successful) * 0.7:
                recommendations.append("Forte dépendance à l'inférence - Considérer plus de sources externes")
            
        except Exception as e:
            self.logger.warning(f"Erreur génération recommandations: {e}")
            recommendations.append("Erreur lors de la génération des recommandations")
        
        return recommendations
    
    def suggest_enrichment_priorities(self, artist_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Suggère des priorités d'enrichissement.
        
        Args:
            artist_id: ID de l'artiste (None pour analyse globale)
            
        Returns:
            Suggestions de priorités
        """
        try:
            # Récupérer les tracks à analyser
            if artist_id:
                tracks = self.database.get_tracks_by_artist_id(artist_id)
                scope = f"artiste {artist_id}"
            else:
                # Échantillon pour performance
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks LIMIT 100")
                    tracks = []
                    for row in cursor.fetchall():
                        track = self.database._row_to_track(row)
                        track.credits = self.database.get_credits_by_track_id(track.id)
                        tracks.append(track)
                scope = "global"
            
            if not tracks:
                return {'error': 'Aucun track trouvé'}
            
            # Analyser les données manquantes
            missing_data = {
                'duration': sum(1 for t in tracks if not t.duration_seconds),
                'bpm': sum(1 for t in tracks if not t.bpm),
                'album': sum(1 for t in tracks if not t.album_title),
                'producer': sum(1 for t in tracks if not any(c.credit_category == CreditCategory.PRODUCER for c in t.credits)),
                'release_year': sum(1 for t in tracks if not t.release_year),
                'key': sum(1 for t in tracks if not t.key),
                'lyrics': sum(1 for t in tracks if not t.has_lyrics)
            }
            
            total_tracks = len(tracks)
            
            # Calculer les pourcentages et priorités
            priorities = []
            for field, missing_count in missing_data.items():
                if missing_count > 0:
                    percentage = (missing_count / total_tracks) * 100
                    
                    # Déterminer la priorité
                    if field in ['duration', 'producer'] and percentage > 20:
                        priority = 'High'
                    elif field in ['bpm', 'album', 'release_year'] and percentage > 30:
                        priority = 'Medium'
                    elif percentage > 50:
                        priority = 'Low'
                    else:
                        priority = 'Optional'
                    
                    # Estimer l'effort d'enrichissement
                    if field in ['duration', 'bpm']:
                        effort = 'High'  # Nécessite sources externes
                    elif field in ['producer', 'release_year']:
                        effort = 'Medium'  # Inférence possible
                    else:
                        effort = 'Low'  # Inférence facile
                    
                    priorities.append({
                        'field': field,
                        'missing_count': missing_count,
                        'percentage': round(percentage, 1),
                        'priority': priority,
                        'effort': effort,
                        'potential_sources': self._suggest_sources_for_field(field)
                    })
            
            # Trier par priorité et pourcentage
            priority_order = {'High': 0, 'Medium': 1, 'Low': 2, 'Optional': 3}
            priorities.sort(key=lambda x: (priority_order.get(x['priority'], 4), -x['percentage']))
            
            # Suggestions d'actions
            action_plan = []
            high_priority = [p for p in priorities if p['priority'] == 'High']
            
            if high_priority:
                action_plan.append({
                    'phase': 'Phase 1 - Urgent',
                    'actions': [f"Enrichir {p['field']} ({p['missing_count']} tracks)" for p in high_priority],
                    'estimated_impact': 'High'
                })
            
            medium_priority = [p for p in priorities if p['priority'] == 'Medium']
            if medium_priority:
                action_plan.append({
                    'phase': 'Phase 2 - Important',
                    'actions': [f"Enrichir {p['field']} ({p['missing_count']} tracks)" for p in medium_priority],
                    'estimated_impact': 'Medium'
                })
            
            # Calcul du score de complétude global
            total_possible_fields = len(missing_data)
            fields_with_data = sum(1 for count in missing_data.values() if count < total_tracks * 0.5)
            completeness_score = (fields_with_data / total_possible_fields) * 100
            
            return {
                'scope': scope,
                'total_tracks_analyzed': total_tracks,
                'completeness_score': round(completeness_score, 1),
                'missing_data_analysis': missing_data,
                'enrichment_priorities': priorities,
                'action_plan': action_plan,
                'estimated_effort': {
                    'high_effort_fields': len([p for p in priorities if p['effort'] == 'High']),
                    'medium_effort_fields': len([p for p in priorities if p['effort'] == 'Medium']),
                    'low_effort_fields': len([p for p in priorities if p['effort'] == 'Low'])
                },
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur suggestion priorités enrichissement: {e}")
            return {'error': f'Erreur lors de l\'analyse: {e}'}
    
    def _suggest_sources_for_field(self, field: str) -> List[str]:
        """Suggère des sources d'enrichissement pour un champ"""
        source_mapping = {
            'duration': ['Spotify API', 'Last.fm API', 'Discogs API'],
            'bpm': ['Spotify API', 'External BPM databases', 'Audio analysis'],
            'album': ['Spotify API', 'Discogs API', 'Cross-reference'],
            'producer': ['Genius API', 'Discogs API', 'Cross-reference'],
            'release_year': ['Spotify API', 'Discogs API', 'Album inference'],
            'key': ['Spotify API', 'Audio analysis', 'Album inference'],
            'lyrics': ['Genius API', 'LyricFind API', 'Web scraping']
        }
        
        return source_mapping.get(field, ['Cross-reference', 'Manual input'])
    
    def create_enrichment_plan(self, artist_id: int, target_completeness: float = 80.0) -> Dict[str, Any]:
        """
        Crée un plan d'enrichissement pour atteindre un niveau de complétude cible.
        
        Args:
            artist_id: ID de l'artiste
            target_completeness: Niveau de complétude cible (0-100)
            
        Returns:
            Plan d'enrichissement détaillé
        """
        try:
            priorities = self.suggest_enrichment_priorities(artist_id)
            
            if 'error' in priorities:
                return priorities
            
            current_completeness = priorities['completeness_score']
            tracks_count = priorities['total_tracks_analyzed']
            
            if current_completeness >= target_completeness:
                return {
                    'message': f'Complétude actuelle ({current_completeness}%) déjà supérieure à la cible ({target_completeness}%)',
                    'current_completeness': current_completeness,
                    'target_completeness': target_completeness
                }
            
            # Calculer les enrichissements nécessaires
            enrichment_tasks = []
            estimated_improvements = 0
            
            for priority in priorities['enrichment_priorities']:
                if estimated_improvements + current_completeness >= target_completeness:
                    break
                
                field = priority['field']
                missing_count = priority['missing_count']
                
                # Estimer l'amélioration de complétude
                field_weight = self._get_field_weight(field)
                potential_improvement = (missing_count / tracks_count) * field_weight
                
                enrichment_tasks.append({
                    'field': field,
                    'tracks_to_enrich': missing_count,
                    'priority': priority['priority'],
                    'effort': priority['effort'],
                    'sources': priority['potential_sources'],
                    'estimated_improvement': round(potential_improvement, 1),
                    'estimated_time': self._estimate_enrichment_time(field, missing_count)
                })
                
                estimated_improvements += potential_improvement
            
            # Calcul des coûts et bénéfices
            total_estimated_time = sum(task['estimated_time'] for task in enrichment_tasks)
            expected_final_completeness = min(100.0, current_completeness + estimated_improvements)
            
            return {
                'artist_id': artist_id,
                'current_completeness': current_completeness,
                'target_completeness': target_completeness,
                'expected_final_completeness': round(expected_final_completeness, 1),
                'enrichment_tasks': enrichment_tasks,
                'execution_plan': {
                    'total_tasks': len(enrichment_tasks),
                    'estimated_total_time_hours': round(total_estimated_time, 1),
                    'high_priority_tasks': len([t for t in enrichment_tasks if t['priority'] == 'High']),
                    'external_api_calls_needed': self._estimate_api_calls(enrichment_tasks)
                },
                'recommendations': [
                    "Commencer par les tâches haute priorité",
                    "Utiliser l'inférence quand possible pour réduire les coûts",
                    "Valider les enrichissements avec des sources multiples"
                ],
                'created_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur création plan enrichissement: {e}")
            return {'error': f'Erreur lors de la création du plan: {e}'}
    
    def _get_field_weight(self, field: str) -> float:
        """Retourne le poids d'un champ dans le calcul de complétude"""
        weights = {
            'duration': 0.20,
            'producer': 0.20,
            'bpm': 0.15,
            'album': 0.15,
            'release_year': 0.10,
            'key': 0.10,
            'lyrics': 0.10
        }
        return weights.get(field, 0.05)
    
    def _estimate_enrichment_time(self, field: str, track_count: int) -> float:
        """Estime le temps nécessaire pour enrichir un champ (en heures)"""
        time_per_track = {
            'duration': 0.1,      # API rapide
            'bpm': 0.1,          # API rapide
            'album': 0.05,       # Inférence
            'producer': 0.2,     # Analyse complexe
            'release_year': 0.02, # Inférence simple
            'key': 0.1,          # API
            'lyrics': 0.15       # Scraping
        }
        
        return track_count * time_per_track.get(field, 0.1)
    
    def _estimate_api_calls(self, enrichment_tasks: List[Dict[str, Any]]) -> int:
        """Estime le nombre d'appels API nécessaires"""
        api_intensive_fields = ['duration', 'bpm', 'key', 'lyrics']
        
        total_calls = 0
        for task in enrichment_tasks:
            if task['field'] in api_intensive_fields:
                total_calls += task['tracks_to_enrich']
        
        return total_calls# processors/data_enricher.py
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ..models.entities import Track, Credit, Artist, Album
from ..models.enums import CreditType, CreditCategory, DataSource, AlbumType
from ..core.database import Database
from ..config.settings import settings
from ..utils.text_utils import similarity_ratio, extract_year_from_date

class EnrichmentSource(Enum):
    """Sources d'enrichissement"""
    GENIUS_API = "genius_api"
    SPOTIFY_API = "spotify_api"
    DISCOGS_API = "discogs_api"
    LASTFM_API = "lastfm_api"
    WEB_SCRAPING = "web_scraping"
    CROSS_REFERENCE = "cross_reference"  # Enrichissement croisé entre entités
    INFERENCE = "inference"              # Inférence basée sur les données existantes
    EXTERNAL_DB = "external_db"          # Bases de données externes

class EnrichmentType(Enum):
    """Types d'enrichissement"""
    MISSING_DATA = "missing_data"        # Compléter données manquantes
    METADATA = "metadata"                # Ajouter métadonnées
    RELATIONSHIPS = "relationships"      # Établir relations
    VALIDATION = "validation"           # Valider données existantes
    ENHANCEMENT = "enhancement"         # Améliorer qualité données
    CROSS_LINK = "cross_link"          # Lier données entre sources

@dataclass
class EnrichmentResult:
    """Résultat d'enrichissement"""
    entity_id: int
    entity_type: str
    enrichment_type: EnrichmentType
    source: EnrichmentSource
    field: str
    old_value: Optional[Any]
    new_value: Any
    confidence: float  # 0-1
    success: bool
    message: str

@dataclass
class EnrichmentStats:
    """Statistiques d'enrichissement"""
    total_processed: int = 0
    successful_enrichments: int = 0
    failed_enrichments: int = 0
    fields_enriched: Dict[str, int] = None
    sources_used: Dict[str, int] = None
    
    def __post_init__(self):
        if self.fields_enriched is None:
            self.fields_enriched = {}
        if self.sources_used is None:
            self.sources_used = {}

class DataEnricher:
    """
    Enrichisseur de données musicales.
    
    Responsabilités :
    - Compléter les données manquantes
    - Améliorer la qualité des métadonnées
    - Établir des relations entre entités
    - Valider et corriger les données existantes
    - Inférer des informations à partir du contexte
    """
    
    def __init__(self, database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        self.database = database or Database()
        
        # Configuration d'enrichissement
        self.config = {
            'auto_enrich_missing': settings.get('enrichment.auto_enrich_missing', True),
            'min_confidence_threshold': settings.get('enrichment.min_confidence', 0.7),
            'max_external_requests': settings.get('enrichment.max_requests_per_session', 100),
            'enable_inference': settings.get('enrichment.enable_inference', True),
            'prefer_official_sources': settings.get('enrichment.prefer_official_sources', True),
            'cross_reference_validation': settings.get('enrichment.cross_reference', True)
        }
        
        # Règles d'inférence
        self.inference_rules = self._load_inference_rules()
        
        # Cache pour éviter les requêtes répétées
        self._enrichment_cache = {}
        
        self.logger.info("DataEnricher initialisé")
    
    def _load_inference_rules(self) -> Dict[str, Any]:
        """Charge les règles d'inférence"""
        return {
            'album_type_rules': {
                'single': {'max_tracks': 3, 'keywords': ['single', 'feat']},
                'ep': {'max_tracks': 8, 'min_tracks': 4},
                'album': {'min_tracks': 8},
                'mixtape': {'keywords': ['mixtape', 'mix tape', 'street']},
                'live': {'keywords': ['live', 'concert', 'tour']}
            },
            'genre_inference': {
                'rap_keywords': ['rap', 'hip hop', 'hip-hop', 'trap', 'drill'],
                'producer_patterns': {
                    'trap': ['808', 'mafia', 'south', 'atlanta'],
                    'boom_bap': ['boom', 'bap', 'classic', 'east'],
                    'drill': ['drill', 'uk', 'chicago']
                }
            },
            'collaboration_rules': {
                'featuring_threshold': 0.3,  # Si >30% des tracks ont des featuring
                'crew_detection': 0.5       # Si >50% des collaborateurs récurrents
            },
            'temporal_rules': {
                'era_inference': {
                    '1980-1995': 'old_school',
                    '1995-2005': 'golden_age',
                    '2005-2015': 'modern',
                    '2015-': 'contemporary'
                }
            }
        }
    
    def enrich_track(self, track: Track, enrich_types: Optional[List[EnrichmentType]] = None) -> List[EnrichmentResult]:
        """
        Enrichit les données d'un track.
        
        Args:
            track: Track à enrichir
            enrich_types: Types d'enrichissement à effectuer
            
        Returns:
            Liste des résultats d'enrichissement
        """
        if enrich_types is None:
            enrich_types = [EnrichmentType.MISSING_DATA, EnrichmentType.METADATA, EnrichmentType.RELATIONSHIPS]
        
        results = []
        
        try:
            self.logger.info(f"Enrichissement du track '{track.title}'")
            
            for enrich_type in enrich_types:
                if enrich_type == EnrichmentType.MISSING_DATA:
                    results.extend(self._enrich_missing_track_data(track))
                elif enrich_type == EnrichmentType.METADATA:
                    results.extend(self._enrich_track_metadata(track))
                elif enrich_type == EnrichmentType.RELATIONSHIPS:
                    results.extend(self._enrich_track_relationships(track))
                elif enrich_type == EnrichmentType.VALIDATION:
                    results.extend(self._validate_and_correct_track_data(track))
                elif enrich_type == EnrichmentType.ENHANCEMENT:
                    results.extend(self._enhance_track_data(track))
            
            # Mettre à jour le track en base si des enrichissements ont réussi
            successful_enrichments = [r for r in results if r.success]
            if successful_enrichments:
                track.updated_at = datetime.now()
                self.database.update_track(track)
                self.logger.info(f"Track '{track.title}' enrichi avec {len(successful_enrichments)} améliorations")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur enrichissement track '{track.title}': {e}")
            return [EnrichmentResult(
                entity_id=track.id,
                entity_type="track",
                enrichment_type=EnrichmentType.MISSING_DATA,
                source=EnrichmentSource.INFERENCE,
                field="error",
                old_value=None,
                new_value=None,
                confidence=0.0,
                success=False,
                message=f"Erreur lors de l'enrichissement: {e}"
            )]
    
    def _enrich_missing_track_data(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit les données manquantes d'un track"""
        results = []
        
        # Enrichir la durée manquante
        if not track.duration_seconds:
            duration_result = self._infer_track_duration(track)
            if duration_result:
                results.append(duration_result)
        
        # Enrichir le BPM manquant
        if not track.bpm:
            bpm_result = self._infer_track_bpm(track)
            if bpm_result:
                results.append(bpm_result)
        
        # Enrichir l'album manquant
        if not track.album_title:
            album_result = self._infer_track_album(track)
            if album_result:
                results.append(album_result)
        
        # Enrichir l'année de sortie
        if not track.release_year:
            year_result = self._infer_release_year(track)
            if year_result:
                results.append(year_result)
        
        # Enrichir les crédits manquants
        if not track.credits or len(track.credits) < self.config.get('min_credits_expected', 1):
            credit_results = self._infer_missing_credits(track)
            results.extend(credit_results)
        
        return results
    
    def _infer_track_duration(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère la durée d'un track"""
        try:
            # Rechercher des tracks similaires du même artiste
            similar_tracks = self._find_similar_tracks(track)
            
            if similar_tracks:
                durations = [t.duration_seconds for t in similar_tracks if t.duration_seconds]
                if durations:
                    # Utiliser la médiane pour éviter les outliers
                    from statistics import median
                    inferred_duration = int(median(durations))
                    
                    # Validation de cohérence
                    if 30 <= inferred_duration <= 600:  # Entre 30s et 10min
                        track.duration_seconds = inferred_duration
                        
                        return EnrichmentResult(
                            entity_id=track.id,
                            entity_type="track",
                            enrichment_type=EnrichmentType.MISSING_DATA,
                            source=EnrichmentSource.INFERENCE,
                            field="duration_seconds",
                            old_value=None,
                            new_value=inferred_duration,
                            confidence=0.7,
                            success=True,
                            message=f"Durée inférée à partir de {len(durations)} tracks similaires"
                        )
        
        except Exception as e:
            self.logger.warning(f"Erreur inférence durée pour '{track.title}': {e}")
        
        return None
    
    def _infer_track_bpm(self, track: Track) -> Optional[EnrichmentResult]:
        """Infère le BPM d'un track"""
        try:
            # Rechercher des tracks du même album
            if track.album_title:
                album_tracks = self._get_tracks_from_album(track.album_title, track.artist_id)
                bpms = [t.bpm for t in album_tracks if t.bpm and t.id != track.id]
                
                if bpms:
                    # Utiliser la moyenne pour les BPM
                    from statistics import mean
                    inferred_bpm = int(mean(bpms))
                    
                    if 60 <= inferred_bpm <= 200:  # BPM raisonnable pour le rap
                        track.bpm = inferred_bpm
                        
                        return EnrichmentResult(
                            entity_id=track.id,
                            entity_type="track",
                            enrichment_type=EnrichmentType.MISSING_DATA,
                            source=EnrichmentSource.INFERENCE,
                            field="bpm",
                            old_value=None,
                            new_value=inferred_bpm,
                            confidence=0.6,
                            success=True,
                            message=f"BPM inféré à partir de l'album ({len(bpms)} tracks)"
                        )
        
        except Exception as e:
            